import os, json, csv, io, random, sqlite3, datetime, re, xml.etree.ElementTree as ET
from pathlib import Path
import requests
from flask import Flask, jsonify, request, render_template, Response

app=Flask(__name__)
app.config['MAX_CONTENT_LENGTH']=8*1024*1024
DATA=Path(os.environ.get('DATA_DIR','data')); DATA.mkdir(parents=True,exist_ok=True)
DB=DATA/'ops.sqlite3'; META=DATA/'aircraft-metadata.csv'
HTTP=requests.Session(); HTTP.headers.update({'User-Agent':'AeroDeckOps/1.0 (personal aviation dashboard)'})

def db():
 c=sqlite3.connect(DB,timeout=15); c.row_factory=sqlite3.Row; return c

def init():
 with db() as c:
  c.execute('CREATE TABLE IF NOT EXISTS flights(id INTEGER PRIMARY KEY, date TEXT, tail TEXT, aircraft TEXT, dep TEXT, arr TEXT, out_z TEXT, off_z TEXT, on_z TEXT, in_z TEXT, block REAL DEFAULT 0, pic REAL DEFAULT 0, sic REAL DEFAULT 0, night REAL DEFAULT 0, imc REAL DEFAULT 0, approaches INTEGER DEFAULT 0, landings INTEGER DEFAULT 0, trip TEXT, source TEXT, notes TEXT, created TEXT)')
  c.execute('CREATE TABLE IF NOT EXISTS missions(id INTEGER PRIMARY KEY, created TEXT, title TEXT, origin TEXT, destination TEXT, aircraft TEXT, passengers INTEGER, cargo TEXT, difficulty TEXT, narrative TEXT, status TEXT DEFAULT "open")')
init()

def fail(message,status=400): return jsonify(error=str(message)),status

def fetch(url,params=None,timeout=18):
 r=HTTP.get(url,params=params,timeout=timeout); r.raise_for_status(); return r

def clean(s,n=80): return str(s or '').strip()[:n]

def metadata():
 if not META.exists(): return {}
 d={}
 with META.open(newline='',encoding='utf-8-sig') as f:
  for row in csv.DictReader(f):
   lower={k.strip().lower():v for k,v in row.items() if k}
   hx=clean(lower.get('icao24') or lower.get('hex') or lower.get('icao'),16).lower()
   if re.fullmatch(r'[0-9a-f]{6}',hx): d[hx]={'registration':clean(lower.get('registration') or lower.get('reg')),'manufacturer':clean(lower.get('manufacturername') or lower.get('manufacturer') or lower.get('make')),'model':clean(lower.get('model') or lower.get('typecode') or lower.get('type')),'typecode':clean(lower.get('typecode'))}
 return d

@app.get('/')
def home(): return render_template('index.html')

@app.get('/api/health')
def health(): return jsonify(ok=True,metadata_rows=len(metadata()),database=str(DB),persistence='ephemeral unless DATA_DIR points to persistent storage')

@app.post('/api/metadata')
def upload_metadata():
 f=request.files.get('file')
 if not f or not f.filename.lower().endswith('.csv'):return fail('Upload a .csv metadata file')
 content=f.read(); text=content.decode('utf-8-sig'); hdr=[h.lower().strip() for h in next(csv.reader(io.StringIO(text)))]
 if not any(h in hdr for h in ('icao24','hex','icao')):return fail('CSV must contain icao24 or hex column')
 META.write_bytes(content)
 return jsonify(ok=True,rows=len(metadata()))

@app.get('/api/aircraft')
def aircraft():
 try:
  states=fetch('https://opensky-network.org/api/states/all',timeout=25).json().get('states') or []
  if not states:return fail('OpenSky returned no aircraft. It may be rate-limited.',503)
  dbmeta=metadata(); airborne=request.args.get('airborne','true')=='true'
  if airborne:states=[s for s in states if len(s)>8 and s[8] is False]
  reg=clean(request.args.get('registration'),40).upper(); model=clean(request.args.get('model'),40).lower()
  candidates=[]
  for s in states:
   hx=str(s[0] or '').lower(); meta=dbmeta.get(hx,{})
   if reg and reg not in meta.get('registration','').upper():continue
   if model and model not in (meta.get('model','')+' '+meta.get('manufacturer','')+' '+meta.get('typecode','')).lower():continue
   candidates.append({'icao24':hx,'callsign':clean(s[1]),'country':clean(s[2]),'longitude':s[5],'latitude':s[6],'altitude_m':s[7],'on_ground':s[8],'speed_ms':s[9],'heading':s[10],**meta})
  random.shuffle(candidates)
  limit=min(max(int(request.args.get('limit',12)),1),40)
  return jsonify(total=len(candidates),states_received=len(states),metadata_rows=len(dbmeta),aircraft=candidates[:limit],source='OpenSky live state vectors + local metadata CSV; no HexDB calls')
 except requests.HTTPError as e:return fail(f'OpenSky HTTP {e.response.status_code}: {str(e)[:130]}',502)
 except Exception as e:return fail(f'OpenSky request failed: {str(e)[:200]}',502)

@app.get('/api/vatsim')
def vatsim():
 try:
  data=fetch('https://data.vatsim.net/v3/vatsim-data.json',timeout=20).json(); pilots=data.get('pilots',[])
  term=clean(request.args.get('search'),50).upper(); matched=[p for p in pilots if not term or term in str(p.get('callsign','')).upper() or term in str(p.get('flight_plan',{})).upper()]
  return jsonify(total=len(pilots),pilots=[{'callsign':p.get('callsign'),'cid':p.get('cid'),'latitude':p.get('latitude'),'longitude':p.get('longitude'),'altitude':p.get('altitude'),'groundspeed':p.get('groundspeed'),'heading':p.get('heading'),'flight_plan':p.get('flight_plan')} for p in matched[:60]])
 except Exception as e:return fail('VATSIM request failed: '+str(e)[:180],502)

@app.get('/api/simbrief')
def simbrief():
 userid=clean(request.args.get('userid'),30)
 if not re.fullmatch(r'[0-9]{1,15}',userid):return fail('Enter your numeric SimBrief user ID')
 try:
  root=ET.fromstring(fetch('https://www.simbrief.com/api/xml.fetcher.php',{'userid':userid},timeout=30).content)
  if root.findtext('./fetch/status')=='Error':return fail(root.findtext('./fetch/message') or 'SimBrief returned an error',502)
  def val(path):return root.findtext(path) or ''
  return jsonify(origin=val('./origin/icao_code'),destination=val('./destination/icao_code'),alternate=val('./alternate/icao_code'),aircraft=val('./aircraft/icaocode'),callsign=val('./atc/callsign'),flight_number=val('./general/flight_number'),route=val('./general/route'),cruise_altitude=val('./general/initial_altitude'),scheduled_departure=val('./times/sched_out'),estimated_block=val('./times/est_block'),raw_source='SimBrief latest OFP XML')
 except Exception as e:return fail('SimBrief import failed: '+str(e)[:180],502)

FLIGHT_COLS=['date','tail','aircraft','dep','arr','out_z','off_z','on_z','in_z','block','pic','sic','night','imc','approaches','landings','trip','source','notes']
@app.route('/api/flights',methods=['GET','POST'])
def flights():
 if request.method=='GET':
  with db() as c:return jsonify(flights=[dict(x) for x in c.execute('SELECT * FROM flights ORDER BY date DESC,id DESC LIMIT 1500')])
 x=request.get_json(silent=True) or {}
 if not clean(x.get('date')) or not clean(x.get('dep')) or not clean(x.get('arr')):return fail('Date, departure, and arrival are required')
 vals=[]
 for k in FLIGHT_COLS:
  if k in ('block','pic','sic','night','imc'):
   try: v=max(0,float(x.get(k) or 0))
   except: return fail('Invalid decimal for '+k)
  elif k in ('approaches','landings'):
   try:v=max(0,int(x.get(k) or 0))
   except:return fail('Invalid integer for '+k)
  else:v=clean(x.get(k),1200 if k=='notes' else 100)
  vals.append(v)
 with db() as c:
  cur=c.execute('INSERT INTO flights ('+','.join(FLIGHT_COLS)+',created) VALUES ('+','.join(['?']*(len(FLIGHT_COLS)+1))+')',vals+[datetime.datetime.now(datetime.timezone.utc).isoformat()]); fid=cur.lastrowid
 return jsonify(ok=True,id=fid)

@app.delete('/api/flights/<int:fid>')
def delete_flight(fid):
 with db() as c:c.execute('DELETE FROM flights WHERE id=?',(fid,))
 return jsonify(ok=True)

@app.get('/api/flights/export')
def export_flights():
 with db() as c: rows=[dict(r) for r in c.execute('SELECT * FROM flights ORDER BY date,id')]
 out=io.StringIO(); w=csv.DictWriter(out,fieldnames=['id']+FLIGHT_COLS+['created']); w.writeheader();w.writerows(rows)
 return Response(out.getvalue(),mimetype='text/csv',headers={'Content-Disposition':'attachment; filename=aerodeck-logbook.csv'})

@app.post('/api/flights/import')
def import_flights():
 f=request.files.get('file')
 if not f:return fail('Choose a CSV file')
 try:
  reader=csv.DictReader(io.StringIO(f.read().decode('utf-8-sig')))
  if not {'date','dep','arr'}.issubset(reader.fieldnames or []):return fail('CSV needs date, dep, arr columns')
  count=0
  with db() as c:
   for x in reader:
    if not x.get('date') or not x.get('dep') or not x.get('arr'):continue
    vals=[]
    for k in FLIGHT_COLS:
     v=x.get(k) or ''
     if k in ('block','pic','sic','night','imc'):v=float(v or 0)
     elif k in ('approaches','landings'):v=int(v or 0)
     else:v=clean(v,1200 if k=='notes' else 100)
     vals.append(v)
    c.execute('INSERT INTO flights ('+','.join(FLIGHT_COLS)+',created) VALUES ('+','.join(['?']*(len(FLIGHT_COLS)+1))+')',vals+[datetime.datetime.now(datetime.timezone.utc).isoformat()]);count+=1
  return jsonify(ok=True,imported=count)
 except Exception as e:return fail('Import failed: '+str(e)[:200])

@app.route('/api/missions',methods=['GET','POST'])
def missions():
 if request.method=='GET':
  with db() as c:return jsonify(missions=[dict(r) for r in c.execute('SELECT * FROM missions ORDER BY id DESC LIMIT 100')])
 x=request.get_json(silent=True) or {}; origin=clean(x.get('origin'),4).upper(); dest=clean(x.get('destination'),4).upper()
 if not re.fullmatch('[A-Z0-9]{3,4}',origin) or not re.fullmatch('[A-Z0-9]{3,4}',dest):return fail('Enter origin and destination airport codes')
 aircraft=clean(x.get('aircraft'),80) or 'Business jet';difficulty=clean(x.get('difficulty'),30) or 'Normal';pax=max(0,min(int(x.get('passengers') or 0),300)); cargo=clean(x.get('cargo'),150)
 title=f'{origin} → {dest} · {aircraft}';narrative=''
 if x.get('ai'):
  key=os.environ.get('OPENAI_API_KEY','')
  if not key:return fail('OPENAI_API_KEY is not configured. Choose Standard mission or configure a key.')
  try:
   payload={'model':os.environ.get('OPENAI_MODEL','gpt-4.1-mini'),'messages':[{'role':'system','content':'You create fictional flight simulation missions. No invented real-time facts, fuel prices, permits, or regulatory approvals. Clearly distinguish simulated operational assumptions from verified information. Format concise sections: Mission, Crew Brief, Passenger/Cargo, Operational Considerations, Paperwork Checklist.'},{'role':'user','content':f'Create a realistic simulated Part 91/135-style mission from {origin} to {dest}, aircraft {aircraft}, {pax} passengers, cargo {cargo}, difficulty {difficulty}. Avoid asserting flight legality or current airport conditions.'}],'temperature':0.7,'max_tokens':850}
   r=requests.post('https://api.openai.com/v1/chat/completions',json=payload,headers={'Authorization':'Bearer '+key},timeout=45);r.raise_for_status();narrative=r.json()['choices'][0]['message']['content']
  except Exception as e:return fail('OpenAI generation failed: '+str(e)[:180],502)
 else:
  narrative=f'SIMULATED MISSION\nRoute: {origin} → {dest}\nAircraft: {aircraft}\nPassengers: {pax}; cargo: {cargo or "None specified"}\nDifficulty: {difficulty}\n\nCREW BRIEF\nReview aircraft performance, weather, NOTAMs, fuel reserves, alternates, and landing suitability using current official sources.\n\nPAPERWORK CHECKLIST\nFlight release / flight plan; passenger manifest; weight and balance; airport suitability; international documents if applicable.\n\nTraining scenario only. No real-time operational clearance or verified fuel quotes.'
 with db() as c:
  cur=c.execute('INSERT INTO missions(created,title,origin,destination,aircraft,passengers,cargo,difficulty,narrative) VALUES (?,?,?,?,?,?,?,?,?)',(datetime.datetime.now(datetime.timezone.utc).isoformat(),title,origin,dest,aircraft,pax,cargo,difficulty,narrative));mid=cur.lastrowid
 return jsonify(ok=True,id=mid,title=title,narrative=narrative)

@app.post('/api/missions/<int:mid>/status')
def mission_status(mid):
 status=(request.get_json(silent=True) or {}).get('status','open')
 if status not in ('open','planned','flown','archived'):return fail('Invalid status')
 with db() as c:c.execute('UPDATE missions SET status=? WHERE id=?',(status,mid))
 return jsonify(ok=True)

if __name__=='__main__':app.run(host='0.0.0.0',port=int(os.environ.get('PORT',5000)))
