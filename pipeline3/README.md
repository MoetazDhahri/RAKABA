# RAKABA - Pipeline 3 (Chatbot backend)

Flask backend for the RAKABA chatbot: one engine, two access-controlled
scopes (client / admin), a voice variant of each (ElevenLabs speech-to-text
+ text-to-speech), plus an autonomous investigation agent with explainable
tool-calling. No frontend here.

Two ways to run this: standalone (`app.py`, Flask, this directory) for
independent dev/testing, or mounted into the unified backend
(`pipeline3/router.py`, FastAPI, included from the repo-root `main.py`
alongside Pipeline 2) for the actual demo — both call the same logic in
`handlers.py`, so there's one source of truth either way. Running standalone
and the unified backend against the same `rakaba.duckdb` file at the same
time isn't supported (DuckDB allows one writer process per file); pick one.

## Setup

```bash
cd pipeline3
pip install -r requirements.txt
cp .env.example .env
# edit .env and set GROQ_API_KEY and ELEVENLABS_API_KEY
python app.py
```

Runs on `http://localhost:5000` by default (override with `FLASK_PORT`).

On first run, `db.py` opens `rakaba.duckdb` (path configurable via
`DUCKDB_PATH`) using the shared schema defined in `pipeline1/db.py` — the
same file Pipelines 1 and 2 write to. There's no separate `entities` table
anymore: entity data comes from Pipeline 1's `taxpayer_lifecycle` (joined
with `listings` for name/phone/address) and `entity_links`; document data
comes from Pipeline 2's `documents`. `db.py` only owns `declarations` and
`escalations`, which aren't produced by the other two pipelines.

### Running against real data

Since `declarations` is Pipeline 3's own table, it seeds a handful of rows
*only* against entity IDs that already exist in `taxpayer_lifecycle` — run
Pipeline 1 first (e.g. `python -m pipeline1.pipeline` from the repo root) so
there's something real to attach declarations to. If no entities exist yet,
`declarations` stays empty rather than inventing fake ones — nothing is
seeded for `entities`, `documents`, or `entity_links` here anymore, since
those belong to Pipelines 1 and 2 respectively and are seeded by them.

Columns actually queried (see `tools.py`/`app.py`):
- `taxpayer_lifecycle(entity_id, listing_id, status, match_score, notes)` + `listings(business_name, phone, location_text)` — Pipeline 1
- `entity_links(link_id, entity_id_a, entity_id_b, shared_attribute, link_score)` — Pipeline 1
- `documents(document_id, entity_id, file_metadata, integrity_score, integrity_flags, risk_flags, composite_score, submitted_date)` — Pipeline 2
- `declarations(declaration_id, entity_id, period, declaration_type, amount_declared, date_filed, status)` — Pipeline 3 (this module)

## Access control

Enforced in code, not just prompting:
- `/api/chat/client` only ever queries client-safe columns (no `risk_score`,
  raw `lifecycle_state`, or other entities' data) and translates the
  lifecycle state through a fixed mapping before it ever reaches the prompt.
- A keyword/intent classifier (`escalation.py`) runs before any Groq call and
  short-circuits sensitive questions (shared accounts/family, linked entities,
  legal-risk "what if I don't declare", investigation/suspicion) straight to
  a fixed escalation reply + a logged row in `escalations`.
- `/api/chat/admin` and `/api/investigate` are unrestricted and assume the
  caller has already been authenticated/authorized as an inspector upstream
  (this backend takes `inspector_id` as a simple role flag, per the hackathon
  scope - wire in real auth later).

## Voice (`/api/voice/chat/client`, `/api/voice/chat/admin`)

Speaks and listens via ElevenLabs (Scribe for speech-to-text, the
multilingual model for text-to-speech) as a thin layer in front of
`chat_client`/`chat_admin` in `handlers.py` - **not** a separate path: every
access-control and escalation rule above still applies to a voice turn
exactly as it does to a typed one, since the transcribed text is handed to
the exact same function.

Request: `multipart/form-data` with `entity_id` (or `inspector_id`),
optionally `conversation_history` (a JSON-encoded string, since form data has
no native array type), and `audio` (the recorded clip - wav/mp3/webm/anything
ElevenLabs' STT accepts). Response: the same JSON shape as the text endpoint,
plus `transcript` (what was heard) and `audio_base64` + `audio_format` (the
spoken reply, `mp3`). If synthesis fails, the response still carries the text
`reply` with an `audio_error` field instead of losing the answer entirely.

```bash
curl -X POST http://localhost:5000/api/voice/chat/client \
  -F "entity_id=<entity_id from Pipeline 1>" \
  -F "audio=@question.mp3"
```

**Language**: both directions auto-detect from content - no language
parameter to set, no dropdown to build. Verified directly against this
project's own ElevenLabs account (not assumed from documentation):

| Input | Detected as | Round-trip quality |
|---|---|---|
| French | `fra` | Exact |
| English | `eng` | Exact |
| Modern Standard Arabic (Arabic script) | `ara` | Exact |
| Tunisian Derja, **Arabic script** (e.g. `أهلا، الملف متاعك تحت المراجعة توا`) | `ara` | Close - occasional dialectal-word substitution with a similar-sounding word from another Arabic dialect (`متاعك`→`بتاعك`, `توا`→`توّا`); meaning intact |
| Tunisian Derja, **Latin transliteration / "Arabizi"** (e.g. `Ahla, el malaf mte3ek...`) | misdetected as `epo` (Esperanto) | Unusable - garbled |

Practical takeaway: **the client must speak/write Derja in Arabic script**,
not Arabizi, for this to work. There's no dedicated Tunisian dialect code in
ElevenLabs' API - "Tunisian support" here means "Arabic support, which
tolerates Tunisian vocabulary reasonably well when it's in Arabic script."
This is worth knowing before promising judges perfect Tunisian voice
support; it's good, not flawless.

All voices on this account are tagged `language: en` (labels reflect the
voice's original accent, not a hard restriction) - the default,
`EXAVITQu4vr4xnSDxMaL` ("Sarah", reassuring/confident, fits the client
persona's non-accusatory tone), speaks all three languages via the
multilingual model but with a non-native accent in French/Arabic. Swap it
via `ELEVENLABS_VOICE_ID` if your account has language-native voices you'd
rather use.

## Getting an entity_id to test with

Entity IDs are generated by Pipeline 1 (`ENT-xxxxxxxx`), not fixed demo IDs.
After running Pipeline 1 once, grab one from the shared DB:

```bash
python -c "
from pipeline1 import db
conn = db.get_connection()
print(conn.execute('SELECT entity_id FROM taxpayer_lifecycle LIMIT 5').fetchall())
"
```

## Example requests

### Client chat (normal question)
```bash
curl -X POST http://localhost:5000/api/chat/client \
  -H "Content-Type: application/json" \
  -d '{
    "entity_id": "<entity_id from Pipeline 1>",
    "message": "Quel est mon statut actuellement ?",
    "conversation_history": []
  }'
```

### Client chat (escalation trigger)
```bash
curl -X POST http://localhost:5000/api/chat/client \
  -H "Content-Type: application/json" \
  -d '{
    "entity_id": "<entity_id from Pipeline 1>",
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
    "entity_id": "<entity_id from Pipeline 1, ideally one that appears in entity_links>"
  }'
```

### List escalations (admin dashboard)
```bash
curl http://localhost:5000/api/escalations
```

## Files

- `handlers.py` - framework-agnostic route logic (single source of truth); both adapters below call this
- `app.py` - standalone Flask adapter (dev/testing)
- `router.py` - FastAPI adapter, mounted into the repo-root `main.py` for the unified backend
- `__init__.py` - sys.path bootstrap so this package's flat sibling-imports resolve when mounted from outside
- `db.py` - DuckDB connection (shared file, shared schema from `pipeline1/db.py`) + declarations seeding
- `groq_client.py` - Groq API wrapper (chat + tool-calling loop)
- `voice.py` - ElevenLabs wrapper (speech-to-text via Scribe, text-to-speech via the multilingual model)
- `tools.py` - the 4 investigation tools + JSON schemas
- `escalation.py` - client-side keyword/intent classifier
- `prompts.py` - system prompts for all three chatbot surfaces
