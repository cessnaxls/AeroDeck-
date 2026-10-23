# AeroSlate FlightOps

New mobile/tablet-first Flask app combining FR24 paste-based flight discovery, mission operations, VATSIM live lookup, SimBrief website handoff, and a draft/final flight logbook. **Not for real-world dispatch or regulatory flight logging without independent verification.**

## Deploy to GitHub + Render Free
1. Create a new GitHub repository and upload **all project files**, preserving folders and `render.yaml`.
2. In Render, choose **New → Blueprint** and connect the repo. Confirm `plan: free` before deployment.
3. Open the Render URL on iPad or iPhone. Use the **Flight discovery** tab.
4. Optional AI: set `OPENAI_API_KEY` as a **secret environment variable** in Render. OpenAI API use is **not free**; don't set it if you need strictly zero cost.
5. To enable worldwide airport selection, download the actual OpenFlights `airports.dat` from https://github.com/jpatokal/openflights/blob/master/data/airports.dat and commit it to `data/airports.dat`. A small offline starter file is included. OpenFlights does not provide a large/medium/small classification; size uses an explicitly approximate curated list, with remaining airports considered small.

## How flight discovery works
Select or randomize an airport → open its FR24 airport page → select arrivals/departures on FR24 → copy flight table text → return and paste → parse → choose Mission or Logbook. Parser uses best-effort extraction of identifiers/registration/type and **never fabricates missing route information**. FR24 clipboard formats vary and may require refinement for a specific sample. The FR24 website may not allow copying tables easily on some devices.

## Integrations and limits
- **VATSIM**: live public `https://data.vatsim.net/v3/vatsim-data.json`, manual refresh, matching callsign or CID; no historical tracking or automatic OOOI.
- **SimBrief**: opens official SimBrief dispatch options with best-effort query parameters. Not authenticated API integration or OFP import.
- **OpenAI**: optional `POST /v1/responses` server-side. Paid usage, user-provided API key; generated brief is explicitly unverified.
- **FR24**: opens FR24 website; parsing of pasted text is local to your backend. No scraping or FR24 API credentials.
- **Database**: SQLite at `data/aeroslate.db`. Render Free filesystem is **ephemeral**, so records can disappear after restart/deploy. Export CSV and JSON backups frequently. **This build is not reliable permanent cloud logbook storage.** For durable zero-cost storage, add an external free-tier database with clear quotas or a client-side export/backup workflow. Do not use Render paid disks.
- **Airport size**: OpenFlights `airports.dat` lacks size metadata. Heuristic curated lists are used. Not an authoritative size/runway categorization.
- **No map**. Zulu-only time labels. Single Gunicorn worker avoids SQLite concurrency surprises.

## Local test
```
pip install -r requirements.txt
python app.py
```
Open http://localhost:5000

## What remains to build for full parity with earlier apps
This is a working foundation, **not a complete reconstruction** of all historic AeroSlate/VATSIM/Aero Mission Ops functionality. Missing: historical VATSIM track/OOOI, OFP PDF ingestion, verified dispatch performance and legality, automated job board, authenticated SimBrief retrieval, real flight data validation, complex international paperwork and reliable persistent hosted logbook. These should be implemented as explicit next phases rather than represented as working.
