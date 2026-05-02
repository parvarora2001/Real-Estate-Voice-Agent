# 🏠 Real Estate Voice Agent — Local (v1)

A fully local AI voice agent for real estate lead qualification — no cloud services, no API costs. Runs entirely on your machine using Ollama, Whisper, and Coqui TTS.

> **This is v1** — a local-first proof of concept. For the production-grade Azure deployment with outbound calling, lead scoring, Redis property matching, and retry scheduling, see [Real-Estate-Voice-Agent-Azure](https://github.com/parvarora2001/Real-Estate-Voice-Agent-Azure).

---

## What It Does

Handles inbound calls via Twilio. When someone calls the number:

1. Twilio routes the call to this FastAPI server
2. The caller speaks — Twilio records the audio
3. **Whisper** (running locally) transcribes the recording
4. **Ollama (phi3:mini)** generates a qualifying response — no OpenAI API needed
5. **Polly.Joanna** (Twilio TTS) speaks the response back
6. The loop repeats until the conversation ends

Everything except Twilio's telephony layer runs on your machine.

---

## Architecture

```
Caller dials Twilio number
        ↓
POST /voice/incoming  →  FastAPI server (local)
        ↓
Twilio records caller response (30s max)
        ↓
POST /voice/process
  ├── Download recording (MP3) from Twilio
  ├── Transcribe with Whisper (local, no cloud)
  ├── Generate response with Ollama phi3:mini (local, no cloud)
  └── Return TwiML → Twilio speaks response via Polly
        ↓
Loop until conversation ends
```

---

## Why Local?

| Concern | This Repo | Azure Version |
|---|---|---|
| LLM cost | $0 — Ollama runs locally | Azure OpenAI (GPT-4) |
| Transcription cost | $0 — Whisper runs locally | Azure Speech + Whisper fallback |
| TTS | Twilio Polly (billed per char) | Twilio Polly |
| Telephony | Twilio (billed per min) | Twilio (billed per min) |
| Setup complexity | Low | High |
| Scalability | Single machine | Azure App Service |

This version is ideal for development, demos, and understanding the core pipeline before committing to cloud infrastructure.

---

## Tech Stack

| Component | Technology |
|---|---|
| Web Framework | FastAPI + Uvicorn |
| Telephony | Twilio Programmable Voice |
| LLM | Ollama — `phi3:mini` (runs locally) |
| Speech-to-Text | OpenAI Whisper `tiny` (runs locally) |
| Text-to-Speech | Coqui TTS — `tacotron2-DDC` (loaded, not yet wired to calls) |
| Voice Synthesis | Twilio Polly.Joanna (used in TwiML responses) |

---

## Project Structure

```
.
├── main.py                  # FastAPI app — all voice logic
├── conversation_test.py     # Test multi-turn conversation flow
├── test_llm.py              # Test Ollama LLM responses in isolation
├── test_tts.py              # Test Coqui TTS audio generation
├── test_whisper.py          # Test Whisper transcription
├── test_whisper_audio.py    # Test Whisper on a specific audio file
├── ai_response.wav          # Sample generated TTS audio
├── test_output.wav          # Sample Whisper test output
└── pyproject.toml           # Dependencies
```

The test files aren't throwaway scripts — they show the component-by-component development process: LLM → TTS → Whisper → integration.

---

## Prerequisites

- Python 3.11+
- [Ollama](https://ollama.ai) installed and running
- `phi3:mini` model pulled: `ollama pull phi3:mini`
- Twilio account with a phone number
- ngrok (or similar) to expose local server to Twilio

---

## Setup

### 1. Install dependencies

```bash
git clone https://github.com/parvarora2001/Real-Estate-Voice-Agent.git
cd Real-Estate-Voice-Agent

pip install uv
uv sync

# Or pip
pip install -r requirements.txt
```

### 2. Configure environment

Create a `.env` file:

```env
TWILIO_ACCOUNT_SID=ACxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
TWILIO_AUTH_TOKEN=your_auth_token
TWILIO_PHONE_NUMBER=+1xxxxxxxxxx
```

### 3. Pull the LLM

```bash
ollama pull phi3:mini
```

### 4. Run

```bash
python main.py
# Server starts at http://localhost:8000
```

### 5. Expose to Twilio

```bash
ngrok http 8000
```

Copy the `https://` URL into your Twilio phone number's Voice webhook:
`https://your-ngrok-url.ngrok.io/voice/incoming`

---

## API Endpoints

| Method | Endpoint | Description |
|---|---|---|
| `GET` | `/` | Status + model health check |
| `GET` | `/health` | Detailed health (models, auth, active conversations) |
| `POST` | `/voice/incoming` | Twilio inbound call webhook |
| `POST` | `/voice/process` | Process recorded caller response |

---

## Testing Components Independently

Each part of the pipeline can be tested in isolation before wiring calls through it:

```bash
# Test LLM responses
python test_llm.py

# Test TTS audio generation
python test_tts.py

# Test Whisper transcription
python test_whisper.py

# Test full conversation flow (no Twilio needed)
python conversation_test.py
```

---

## How It Evolved → Azure Version

After validating the core pipeline locally, the architecture was extended into a production deployment:

| Feature | v1 (This Repo) | v2 (Azure) |
|---|---|---|
| Call direction | Inbound only | Inbound + outbound |
| LLM | Ollama phi3:mini (local) | Azure OpenAI GPT-4 |
| Transcription | Whisper only | Azure Speech + Whisper fallback |
| Lead storage | In-memory only | SQLite + SQLAlchemy |
| Property matching | None | Redis-indexed listings |
| Retry logic | None | 4-attempt scheduler with quiet hours |
| Lead scoring | None | Hot / Warm / Cold |
| Deployment | Local + ngrok | Docker + Azure App Service |

---

## Known Limitations

- Coqui TTS is loaded on startup but not yet wired into TwiML responses — Polly is used instead. Connecting it would eliminate the last Twilio-billed component from the AI pipeline.
- PID-based temp filenames (`recording_{pid}.mp3`) are not safe under concurrent calls — use `tempfile.NamedTemporaryFile` for multi-caller scenarios.
- No conversation persistence — all state is in-memory and lost on restart.

---

## License

MIT