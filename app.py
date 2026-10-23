import csv, io, json, os, random, re, sqlite3, threading, urllib.parse
from datetime import datetime, timezone
from pathlib import Path
import requests
from flask import Flask, jsonify, render_template, request

ROOT=Path(__file__).resolve().parent
DB=Path(os.environ.get('DATABASE_PATH',str(ROOT/'data'/'aeroslate.db')))
DB.parent.mkdir(parents=True,exist_ok=True)
app=Flask(__name__)
app.config['MAX_CONTENT_LENGTH']=4*1024*1024
UA={'User-Agent':'AeroSlateFlightOps/1.0 (personal flight planning)'}

def utc(): return datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')
def conn():
 c=sqlite3.connect(DB,timeout=20);c.row_factory=sqlite3.Row;return c

def init():
 with conn() as c:
  c.execute('CREATE TABLE IF NOT EXISTS flights (id INTEGER PRIMARY KEY AUTOINCREMENT, created_z TEXT NOT NULL, flight_date TEXT, callsign TEXT, registration TEXT, aircraft TEXT, dep TEXT, arr TEXT, off_z TEXT, on_z TEXT, out_z TEXT, in_z TEXT, remarks TEXT, source TEXT, vatsim_cid TEXT, status TEXT DEFAULT "draft")')
  c.execute('CREATE TABLE IF NOT EXISTS missions (id INTEGER PRIMARY KEY AUTOINCREMENT, created_z TEXT NOT NULL, title TEXT, dep TEXT, arr TEXT, aircraft TEXT, registration TEXT, callsign TEXT, pax INTEGER, cargo_kg INTEGER, difficulty TEXT, notes TEXT, paperwork TEXT)')
  c.execute('CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT)')
init()

LARGE={'KATL','KDFW','KORD','KLAX','KJFK','KMIA','KSFO','KDEN','KSEA','KLAS','KPHX','KCLT','KIAH','KEWR','KBOS','KMSP','KDTW','KPHL','KIAD','KBWI','EGLL','EHAM','LFPG','EDDF','OMDB','WSSS','RJTT','YSSY','CYYZ','KIND'}
MEDIUM={'KSAV','KPBI','KCRW','KBHM','KCHS','KMGM','KMDW','KDAL','KTEB','KOPF','KFXE','KAPA','KSDL','KHPN','KSRQ','KORF','KRIC','KMYR','KJAX','KDAY','KCMH','KGRR','KLEX','KIND'}

def airport_size(icao,iata):
 if icao in LARGE:return 'large'
 if icao in MEDIUM:return 'medium'
 return 'small' # OpenFlights does not encode airport size; user may replace classifications.

def load_airports():
 path=ROOT/'data'/'airports.dat'; result=[]
 with path.open(encoding='utf-8',errors='replace',newline='') as f:
  for r in csv.reader(f):
   if len(r)<8:continue
   icao=r[5].strip().upper();iata=r[4].strip().upper()
   if not re.fullmatch('[A-Z0-9]{4}',icao):continue
   if r[4]=='\\N':iata=''
   result.append({'name':r[1],'city':r[2],'country':r[3],'iata':iata,'icao':icao,'size':airport_size(icao,iata)})
 return result
AIRPORTS=load_airports()
AIRPORT_INDEX={x['icao']:x for x in AIRPORTS}
IATA_INDEX={x['iata']:x for x in AIRPORTS if x['iata']}

def safe_airport(x):
 x=(x or '').upper().strip();a=AIRPORT_INDEX.get(x) or IATA_INDEX.get(x)
 return a['icao'] if a else (x if re.fullmatch('[A-Z0-9]{3,4}',x) else '')

def extract_flights(text, airport='', direction='departures'):
 """Best-effort parser for user-pasted FR24 rows; preserves raw row, never invents data."""
 lines=[re.sub(r'\s+',' ',s).strip() for s in text.splitlines() if s.strip()]
 flights=[];seen=set();home=safe_airport(airport)
 ignore={'DEPARTURES','ARRIVALS','AIRPORT','FLIGHT','AIRLINE','AIRCRAFT','STATUS','TIME','SCHEDULED','ESTIMATED','ACTUAL','REGISTRATION','FROM','TO'}
 for i,line in enumerate(lines):
  upper=line.upper()
  if upper in ignore or len(line)<5:continue
  # Flight IDs, registration and equipment are independent, not fabricated.
  ids=re.findall(r'(?<![A-Z0-9])([A-Z]{1,3}\d{1,4}[A-Z]?)(?![A-Z0-9])',upper)
  ids=[x for x in ids if not re.fullmatch(r'[A-Z]\d{1,3}',x)]
  reg=re.search(r'\b(?:N\d{1,5}[A-Z]{0,2}|[A-Z]{1,2}-[A-Z0-9]{3,5}|C-[A-Z]{4}|G-[A-Z]{4})\b',upper)
  # Support common ICAO and IATA equipment codes, but only when marked by type context.
  typ=re.search(r'\b(?:A20N|A21N|A319|A320|A321|A333|A359|B738|B739|B38M|B39M|B772|B77W|B789|B788|E170|E175|E190|CRJ7|CRJ9|CL35|CL60|H25B|H25C|GLF4|GLF5|GLEX|C56X|C680|C750|PC12|BE40|BE58|C172|C208|DA40)\b',upper)
  # FR24 copied tables frequently include airport IATA in parentheses.
  codes=re.findall(r'\(([A-Z]{3})\)',upper)
  airports=[IATA_INDEX[x]['icao'] for x in codes if x in IATA_INDEX]
  if not ids and not reg and not (typ and airports):continue
  callsign=ids[0] if ids else ''
  if not callsign and not reg:continue
  key=(callsign,reg.group(0) if reg else '',line)
  if key in seen:continue
  seen.add(key)
  other=next((x for x in airports if x!=home),'')
  dep=home if direction=='departures' else other
  arr=other if direction=='departures' else home
  flights.append({'callsign':callsign,'registration':reg.group(0) if reg else '', 'aircraft':typ.group(0) if typ else '', 'dep':dep,'arr':arr,'raw':line,'confidence':'partial' if not other else 'route found'})
 return flights[:200]

@app.get('/')
def index():return render_template('index.html')
@app.get('/api/health')
def health():return jsonify(ok=True,utc=utc(),airports=len(AIRPORTS),database_persistent=bool(os.environ.get('PERSISTENT_STORAGE')))
@app.get('/api/airports')
def airports():
 q=request.args.get('q','').strip().lower();size=request.args.get('size','all')
 a=[x for x in AIRPORTS if (size=='all' or x['size']==size) and (not q or q in (' '.join([x['icao'],x['iata'],x['name'],x['city'],x['country']])).lower())]
 return jsonify(airports=a[:80],total=len(a))
@app.get('/api/airports/random')
def airport_random():
 size=request.args.get('size','all');a=[x for x in AIRPORTS if size=='all' or x['size']==size]
 return jsonify(airport=random.choice(a)) if a else (jsonify(error='No airports for this size'),404)
@app.post('/api/airports/upload')
def upload_airports():
 f=request.files.get('file')
 if not f or not f.filename.lower().endswith('.dat'):return jsonify(error='Select an airports.dat file'),400
 content=f.read();rows=list(csv.reader(io.StringIO(content.decode('utf-8-sig'))))
 valid=sum(1 for r in rows if len(r)>=8 and re.fullmatch('[A-Z0-9]{4}',r[5].strip().upper()))
 if valid<10:return jsonify(error='Not a valid OpenFlights airports.dat file'),400
 (ROOT/'data'/'airports.dat').write_bytes(content)
 global AIRPORTS,AIRPORT_INDEX,IATA_INDEX
 AIRPORTS=load_airports();AIRPORT_INDEX={x['icao']:x for x in AIRPORTS};IATA_INDEX={x['iata']:x for x in AIRPORTS if x['iata']}
 return jsonify(ok=True,count=len(AIRPORTS),warning='On Render Free, uploaded data may be lost after restart. Commit airports.dat to GitHub for durability.')
@app.post('/api/parse')
def parse():
 d=request.get_json(silent=True) or {};raw=str(d.get('text',''))[:200000]
 return jsonify(flights=extract_flights(raw,d.get('airport',''),d.get('direction','departures')),lines=len(raw.splitlines()))
@app.get('/api/fr24-link')
def fr24():
 icao=safe_airport(request.args.get('airport',''));a=AIRPORT_INDEX.get(icao)
 if not a:return jsonify(error='Choose a known airport'),400
 # FR24 airport page; user manually selects departures or arrivals on FR24.
 return jsonify(url='https://www.flightradar24.com/data/airports/'+(a['iata'] or a['icao']).lower(),iata=a['iata'],icao=icao)
@app.get('/api/vatsim')
def vatsim():
 callsign=re.sub('[^A-Z0-9]','',request.args.get('callsign','').upper())[:12]
 cid=re.sub('[^0-9]','',request.args.get('cid',''))[:12]
 if not callsign and not cid:return jsonify(error='Enter callsign or VATSIM CID'),400
 try:
  r=requests.get('https://data.vatsim.net/v3/vatsim-data.json',timeout=14,headers=UA);r.raise_for_status()
  pilots=[p for p in r.json().get('pilots',[]) if (callsign and p.get('callsign','').upper()==callsign) or (cid and str(p.get('cid'))==cid)]
  return jsonify(pilots=pilots[:20],online=bool(pilots),checked_z=utc())
 except requests.RequestException as e:return jsonify(error='VATSIM feed unavailable',detail=str(e)[:180]),502
@app.route('/api/flights',methods=['GET','POST'])
def flights():
 if request.method=='GET':
  with conn() as c:return jsonify(flights=[dict(r) for r in c.execute('SELECT * FROM flights ORDER BY id DESC LIMIT 500')])
 d=request.get_json(silent=True) or {};fields=['flight_date','callsign','registration','aircraft','dep','arr','off_z','on_z','out_z','in_z','remarks','source','vatsim_cid','status']
 vals=[str(d.get(x,'')).strip()[:2000] for x in fields]
 if not (d.get('dep') or d.get('callsign')):return jsonify(error='Enter a departure or callsign'),400
 if vals[-1] not in ('draft','final'):vals[-1]='draft'
 with conn() as c:
  cur=c.execute('INSERT INTO flights (created_z,'+','.join(fields)+') VALUES ('+','.join(['?']*(len(fields)+1))+')',[utc()]+vals)
  return jsonify(ok=True,id=cur.lastrowid)
@app.post('/api/flights/<int:fid>/finalize')
def finalize(fid):
 with conn() as c:
  r=c.execute('UPDATE flights SET status="final" WHERE id=? AND status="draft"',(fid,))
  return jsonify(ok=bool(r.rowcount)),(200 if r.rowcount else 409)
@app.delete('/api/flights/<int:fid>')
def delete_flight(fid):
 with conn() as c:
  r=c.execute('DELETE FROM flights WHERE id=?',(fid,));return jsonify(ok=bool(r.rowcount))
@app.route('/api/missions',methods=['GET','POST'])
def missions():
 if request.method=='GET':
  with conn() as c:return jsonify(missions=[dict(r) for r in c.execute('SELECT * FROM missions ORDER BY id DESC LIMIT 150')])
 d=request.get_json(silent=True) or {};fields=['title','dep','arr','aircraft','registration','callsign','pax','cargo_kg','difficulty','notes','paperwork']
 vals=[str(d.get(k,''))[:6000] for k in fields]
 for i in [6,7]:
  try:vals[i]=max(0,int(vals[i] or 0))
  except ValueError:vals[i]=0
 if not vals[1]:return jsonify(error='Departure airport required'),400
 with conn() as c:
  cur=c.execute('INSERT INTO missions (created_z,'+','.join(fields)+') VALUES ('+','.join(['?']*12)+')',[utc()]+vals)
  return jsonify(ok=True,id=cur.lastrowid)
@app.post('/api/ai/dispatch')
def ai_dispatch():
 d=request.get_json(silent=True) or {};key=os.environ.get('OPENAI_API_KEY','').strip()
 if not key:return jsonify(error='OPENAI_API_KEY is not configured. Manual missions remain available.'),400
 details=json.dumps(d.get('mission',{}),ensure_ascii=False)[:10000]
 prompt=('Prepare a concise fictional flight-operations mission brief from this mission JSON. Clearly label every unverified item as UNVERIFIED. Never invent actual weather, NOTAMs, fuel price, performance, permits, crew duty legality, FBO availability, or dispatch authorization. Include mission summary, routing, passenger/cargo manifest placeholders, required verification checklist, international/customs considerations if relevant, and crew notes. Use Zulu time only. JSON: '+details)
 try:
  r=requests.post('https://api.openai.com/v1/responses',headers={'Authorization':'Bearer '+key,'Content-Type':'application/json'},json={'model':os.environ.get('OPENAI_MODEL','gpt-4.1-mini'),'input':prompt,'max_output_tokens':1300},timeout=55)
  if not r.ok:return jsonify(error='OpenAI API request failed',detail=r.text[:400]),502
  data=r.json();content='\n'.join(p.get('text','') for item in data.get('output',[]) for p in item.get('content',[]) if p.get('type')=='output_text')
  return jsonify(text=content or 'No text returned')
 except requests.RequestException as e:return jsonify(error='OpenAI connection failed',detail=str(e)[:200]),502
@app.get('/api/settings')
def settings():return jsonify(ai_configured=bool(os.environ.get('OPENAI_API_KEY')),simbrief_user_configured=bool(os.environ.get('SIMBRIEF_USERNAME')),airports=len(AIRPORTS),storage_warning=not bool(os.environ.get('PERSISTENT_STORAGE')))

if __name__=='__main__':app.run(host='0.0.0.0',port=int(os.environ.get('PORT',5000)))
