# CLAUDE.md

Guidance for Claude Code when working in this repository.

## Project Overview

**Real Estate Voice Agent (v1, local-first)** — an inbound phone bot that qualifies
real-estate leads. The entire AI pipeline runs locally; the only cloud dependency is
Twilio's telephony layer.

A caller dials a Twilio number and speaks. The agent transcribes the audio, asks
qualifying questions, extracts a structured lead, scores it, matches properties, and
saves a report for a human agent to follow up.

## Pipeline / Architecture

```
Caller dials Twilio number
      ↓
POST /voice/incoming   → greets caller, opens a <Record> turn
      ↓
POST /voice/process    → per turn:
  ├── download_recording()   download MP3 from Twilio (httpx + basic auth)
  ├── transcribe_audio()     Whisper "tiny" (local)
  ├── generate_response()    Ollama phi3:mini (local) — asks ONE qualifying question
  └── returns TwiML          Twilio speaks reply via Polly.Joanna, records next turn
      ↓
Loop until should_end_call() → extract lead, score, match properties, write report
```

## Key Files

| File | Responsibility |
|---|---|
| `main.py` | FastAPI app; all call orchestration, conversation state, turn loop, lead report writing |
| `lead_extractor.py` | LLM-based structured lead extraction + rule-based scoring + next-steps |
| `models.py` | Pydantic `LeadData` and `LeadScore` / `FinancingStatus` / `PropertyType` enums |
| `property_manager.py` | ChromaDB + sentence-transformers (`all-MiniLM-L6-v2`) semantic property search |
| `load_sample_properties.py` | Seeds 5 sample listings into ChromaDB |
| `conversation_test.py` | Offline pipeline test (no Twilio) |

## Tech Stack

- **Web:** FastAPI + Uvicorn
- **Telephony:** Twilio Programmable Voice (TwiML)
- **LLM:** Ollama `phi3:mini` (local)
- **STT:** OpenAI Whisper `tiny` (local)
- **TTS:** Twilio Polly.Joanna (Coqui TTS is loaded but not wired into calls)
- **Vector DB:** ChromaDB + `sentence-transformers`
- **Package mgmt:** `uv` (see `pyproject.toml` / `uv.lock`)

## Common Commands

```bash
uv sync                       # install dependencies
ollama pull phi3:mini         # pull the LLM (required)
python load_sample_properties.py   # seed the property database
python main.py                # run server on http://localhost:8000
python conversation_test.py   # test pipeline without Twilio
ngrok http 8000               # expose locally for Twilio webhook
```

Env vars (`.env`): `TWILIO_ACCOUNT_SID`, `TWILIO_AUTH_TOKEN`, `TWILIO_PHONE_NUMBER`.

## API Endpoints

| Method | Path | Purpose |
|---|---|---|
| GET | `/` | Status + model health |
| GET | `/health` | Detailed health (models, auth, active conversations) |
| POST | `/voice/incoming` | Twilio inbound-call webhook |
| POST | `/voice/process` | Process a recorded caller turn |

## Conventions & Gotchas

- **Conversation state is in-memory** (`conversations` dict in `main.py`); lost on restart.
- **`should_end_call()`** ends after 5 user turns, or 3+ turns with budget + (timeline or
  financing), or on ending phrases ("thanks", "goodbye", etc.).
- **Lead reports** are written to `leads/` as both `.json` and human-readable `.txt`.
- **Temp recording files** use PID-based names (`recording_{pid}.mp3`) — not safe under
  concurrent calls; prefer `tempfile.NamedTemporaryFile` if touching that path.
- **Coqui TTS** is initialized at startup but unused in the call flow (Polly handles speech).
- ChromaDB metadata can't hold lists, so `features` is stored comma-joined and split back
  on read.

## Known Limitations

- Coqui TTS loaded but not wired into TwiML responses.
- No conversation persistence (in-memory only).
- PID-based temp filenames are not concurrency-safe.

---

## ⚠️ Exit Workflow — Session Update Protocol

**When the user's message is `exit` (or `/exit`, `quit`, `bye`, `goodbye`), you MUST do
the following BEFORE ending the session:**

1. Update the **Session Log** section at the bottom of this `CLAUDE.md`:
   - Add a new dated entry (use the real current date).
   - Summarize what changed this session: files added/modified/deleted, decisions made,
     and anything a future session should know.
   - If any of the project facts above (architecture, files, commands, conventions,
     limitations) became stale during the session, update them in place too.
2. Save the file.
3. Briefly confirm to the user what you logged, then end.

Keep entries concise (a few bullets). Do not duplicate git history — capture intent and
context, not a raw diff.

---

## Session Log

### 2026-06-06
- Created this `CLAUDE.md`: documented the project overview, pipeline, key files, tech
  stack, commands, conventions, and known limitations.
- Established the **Exit Workflow** above so this file is refreshed at the end of each
  session when the user types `exit`.
- Repo state at time of writing: working tree had uncommitted additions
  (`lead_extractor.py`, `models.py`, `property_manager.py`, `load_sample_properties.py`,
  `leads/`) and deletions of the old `test_*.py` / `*.wav` files; not yet committed.
