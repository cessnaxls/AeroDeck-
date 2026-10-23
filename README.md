# AeroDeck Ops — iPad / phone flight operations workspace

A **new** standalone Flask application combining AeroSlate-style OpenSky aircraft discovery, a VATSIM live traffic viewer, SimBrief OFP import, a manual digital logbook, and optional OpenAI-generated *simulated* mission briefs. Responsive blue/gray UI, no maps, Zulu time throughout.

## Included features

- Aircraft generator: OpenSky `/states/all` live state vectors, randomized, filters for model/registration **only when aircraft metadata is uploaded**. The CSV is indexed by `icao24`, so no per-aircraft HexDB calls. Upload metadata in Settings (`icao24,registration,manufacturer,model,typecode`). Aircraft state data comes from OpenSky; metadata must be supplied separately. Without metadata, random aircraft still work but type and registration are generally unknown.
- VATSIM: public live V3 pilot feed, callsign/route search, prefill logbook or mission. **Not historical flight reconstruction, automatic OOOI tracking, or an authenticated VATSIM logbook sync.**
- SimBrief: fetch latest OFP from `https://www.simbrief.com/api/xml.fetcher.php?userid=...` using your numeric SimBrief user ID; prefill logbook/mission. SimBrief may change availability or field names.
- Logbook: manual entries with UTC dates/times, decimal hours, CSV export/import, delete, totals. **No FAA/EASA certification or automatic duty/legality calculations.**
- Mission ops: deterministic free scenario generator plus optional OpenAI API-backed simulated dispatch-style briefs; save/read/mark flown. **Not a real flight release, no verified weather, NOTAMs, fuel prices, or operational authorizations.**
- API health endpoint `/api/health`.

## Deploy on Render Free

1. Unzip, create a GitHub repo, and commit **all files**, including `render.yaml`.
2. In Render select **New → Blueprint**, connect the repo, and inspect the YAML. The service explicitly uses `plan: free`.
3. Set `OPENAI_API_KEY` as a **secret environment variable only if you want AI missions**. This is an OpenAI paid API and is **not included in Render Free**; leave unset for fully free Standard missions.
4. Open your `onrender.com` URL from Safari on iPad/iPhone.
5. Test `/api/health`, then Aircraft discovery. Render outbound networking might still be blocked or rate-limited by OpenSky; hosting does **not** guarantee OpenSky access.

**IMPORTANT DATA WARNING:** Render Free's filesystem is ephemeral; local SQLite flights, mission records and uploaded metadata can be erased on restart/redeploy. Export the logbook CSV often and keep your original aircraft CSV. **Do not treat Render Free as durable logbook storage.** For permanent storage, migrate to a free database with durable quotas or an Always Free VM with persistent boot storage. This package does not claim permanent cloud persistence.

## Run locally for development

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python app.py
```

Visit http://127.0.0.1:5000.

## Security and constraints

This starter has no login system; **do not enter sensitive personal data into a publicly accessible deployment**. Add authentication before using it as a personal production logbook. Do not expose OpenAI keys in client-side JavaScript. Requests to public APIs may fail or be rate-limited. Only use simulated mission briefs for training/planning; verify all operational data from official sources. API usage from OpenAI may incur charges.

## Status

This is a deployable **first-release foundation**, not a full port of every feature in the previous three desktop/web applications. In particular it does not yet include VATSIM historical tracks, SimBrief OFP PDF parsing, duty calculations, actual aircraft-specific performance, automated OOOI logging, or end-to-end authenticated flight logging. External service connectivity has not been tested from a live Render deployment.
