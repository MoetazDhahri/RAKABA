# RAKABA - Pipeline 3 (Chatbot backend)

Flask backend for the RAKABA chatbot: one engine, two access-controlled
scopes (client / admin), plus an autonomous investigation agent with
explainable tool-calling. No frontend here.

This is a standalone Flask app, separate from the FastAPI app in `main.py` /
`pipeline2/` at the repo root. It runs and is tested independently; wiring it
into the shared `main.py` (per the pattern noted there for Pipelines 1 and 3)
is a follow-up integration step, not done here.

## Setup

```bash
cd pipeline3
pip install -r requirements.txt
cp .env.example .env
# edit .env and set GROK_API_KEY
python app.py
```

Runs on `http://localhost:5000` by default (override with `FLASK_PORT`).

On first run, `db.py` opens `rakaba.duckdb` (path configurable via
`DUCKDB_PATH`). If it doesn't exist yet, or is missing the expected tables,
it creates the schema and seeds realistic fake Tunisian data automatically -
nothing else to run.

### Plugging in the real database

Once your teammate's real `rakaba.duckdb` exists with the `entities`,
`declarations`, `documents`, and `entity_links` tables populated, just point
`DUCKDB_PATH` at that file (in `.env` or the environment) instead of the
default. As long as those four tables exist, `db.py` will use them as-is and
skip mock seeding; it will still add the `escalations` table if missing.

Expected columns (see `db.py` for full DDL):
- `entities(entity_id, name, entity_type, phone, address, lifecycle_state, risk_score, created_at)`
- `declarations(declaration_id, entity_id, period, declaration_type, amount_declared, date_filed, status)`
- `documents(document_id, entity_id, doc_type, integrity_flag, flag_reason, submitted_at)`
- `entity_links(link_id, entity_id_a, entity_id_b, link_type, shared_value)`

## Access control

Enforced in code, not just prompting:
- `/api/chat/client` only ever queries client-safe columns (no `risk_score`,
  raw `lifecycle_state`, or other entities' data) and translates the
  lifecycle state through a fixed mapping before it ever reaches the prompt.
- A keyword/intent classifier (`escalation.py`) runs before any Grok call and
  short-circuits sensitive questions (shared accounts/family, linked entities,
  legal-risk "what if I don't declare", investigation/suspicion) straight to
  a fixed escalation reply + a logged row in `escalations`.
- `/api/chat/admin` and `/api/investigate` are unrestricted and assume the
  caller has already been authenticated/authorized as an inspector upstream
  (this backend takes `inspector_id` as a simple role flag, per the hackathon
  scope - wire in real auth later).

## Mock demo data

Seeded entities include:
- `E-1001` Sfax Textiles SARL - trusted taxpayer
- `E-1002` Youssef Ben Ali - individual, in regularisation, one missing declaration
- `E-1003` Manel Trading Co - detected, two missing declarations, a flagged document
- `E-1004` / `E-1005` - share the same phone number (`entites_liees` demo)
- `E-1006` Tunis Auto Pieces - compliant

## Example requests

### Client chat (normal question)
```bash
curl -X POST http://localhost:5000/api/chat/client \
  -H "Content-Type: application/json" \
  -d '{
    "entity_id": "E-1002",
    "message": "Quel est mon statut actuellement ?",
    "conversation_history": []
  }'
```

### Client chat (escalation trigger)
```bash
curl -X POST http://localhost:5000/api/chat/client \
  -H "Content-Type: application/json" \
  -d '{
    "entity_id": "E-1002",
    "message": "Que se passe-t-il si je ne declare pas ce trimestre ?",
    "conversation_history": []
  }'
```

### Admin chat
```bash
curl -X POST http://localhost:5000/api/chat/admin \
  -H "Content-Type: application/json" \
  -d '{
    "inspector_id": "amira",
    "message": "Explique-moi la difference entre les etats Detecte et Contacte.",
    "conversation_history": []
  }'
```

### Investigation agent
```bash
curl -X POST http://localhost:5000/api/investigate \
  -H "Content-Type: application/json" \
  -d '{
    "inspector_id": "amira",
    "entity_id": "E-1005"
  }'
```

### List escalations (admin dashboard)
```bash
curl http://localhost:5000/api/escalations
```

## Files

- `app.py` - Flask app + routes
- `db.py` - DuckDB connection + mock data seeding
- `grok_client.py` - Grok API wrapper (chat + tool-calling loop)
- `tools.py` - the 4 investigation tools + JSON schemas
- `escalation.py` - client-side keyword/intent classifier
- `prompts.py` - system prompts for all three chatbot surfaces
