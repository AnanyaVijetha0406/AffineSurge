# CT-200 QA Traceability API (AffineSurge)

Backend for the Tri9T AI Engineering Internship assignment: parse the CardioTrack CT-200 manuals into a versioned hierarchical tree, select sections, generate QA test-case ideas with Gemini, and detect staleness when the document changes.

## Stack

- **FastAPI + Pydantic + SQLAlchemy + SQLite** — document tree, versions, selections
- **MongoDB Atlas** — LLM generation records
- **PyMuPDF** — PDF text extraction + hierarchy reconstruction
- **Google Gemini** — structured test-case generation with validation/retry

## Setup

```powershell
cd C:\AffineSurge
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

Ensure `.env` has:

```
GEMINI_API_KEY=...
MONGODB_URI=mongodb+srv://...
MONGODB_DB=ct200_qa
DATABASE_URL=sqlite:///./ct200.db
GEMINI_MODEL=gemini-2.0-flash
```

PDFs live in `data/ct200_manual.pdf` and `data/ct200_manual_v2.pdf`.

## Run API

```powershell
uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

Open docs: http://127.0.0.1:8000/docs

## v1 → v2 re-ingestion + staleness flow

```powershell
# Terminal 1: start server
uvicorn app.main:app --host 127.0.0.1 --port 8000

# Terminal 2: run demo
python scripts/demo_flow.py
```

Or manually:

```powershell
# 1) Ingest v1
curl -X POST http://127.0.0.1:8000/documents/ingest -H "Content-Type: application/json" -d "{\"pdf_path\":\"data/ct200_manual.pdf\",\"version_number\":1}"

# 2) List top sections
curl "http://127.0.0.1:8000/browse/sections?version=1"

# 3) Search a node, create selection, generate (see /docs for bodies)

# 4) Ingest v2 WITHOUT destroying v1
curl -X POST http://127.0.0.1:8000/documents/ingest -H "Content-Type: application/json" -d "{\"pdf_path\":\"data/ct200_manual_v2.pdf\",\"version_number\":2}"

# 5) Check generation staleness
curl http://127.0.0.1:8000/generations/{id}/staleness
```

## Tests

```powershell
pytest -q
```

Includes ≥3 unit tests for PDF irregularities (out-of-order `3.4`/`3.3`, deep `2.1.1.1`, duplicate Error Codes headings).

## Key API routes

| Method | Path | Purpose |
|--------|------|---------|
| POST | `/documents/ingest` | Parse PDF into a new version |
| GET | `/documents/versions` | List versions |
| GET | `/browse/sections?version=` | Top-level sections |
| GET | `/browse/nodes/{id}` | Node + children + hash |
| GET | `/browse/search?q=` | Search headings/body |
| GET | `/browse/nodes/{id}/changes` | Cross-version diff summary |
| POST | `/selections` | Version-pinned selection |
| POST | `/generate` | LLM test cases (`force` to regenerate) |
| GET | `/generations` | By selection_id or node_id |
| GET | `/generations/{id}/staleness` | Staleness report |

## Policies

- **Duplicate generate**: returns cached Mongo document for that selection unless `force=true`.
- **Malformed LLM output**: up to 3 retries with repair hint; then HTTP 502 — never invents fake cases.
- **Staleness**: hash compare of pinned selection snapshots vs latest version `node_key`s. Wording tweaks and clinical threshold changes are both flagged equally.

## Notes on Gemini + MongoDB

- **Gemini**: if the free-tier quota is exhausted (`429 RESOURCE_EXHAUSTED`), the API retries alternate Flash models, then uses a **rule-based fallback** (`llm_status=fallback_rule_based`) so versioning/staleness demos still work. Replace/fix your key in `.env` for real LLM output.
- **MongoDB Atlas**: Network Access must allow your IP (or `0.0.0.0/0` for demo). If Atlas SSL/IP checks fail, generations automatically persist to `data/generations.json` (justified JSON store fallback; see APPROACH.md).
