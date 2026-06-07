---
title: Real Estate Voice Agent
emoji: 🏠
colorFrom: blue
colorTo: green
sdk: docker
app_port: 7860
pinned: false
---

# 🏠 AI Real Estate Voice Agent

**🔗 Live demo: [parv28-real-estate.hf.space](https://parv28-real-estate.hf.space)**

> ⚠️ The demo runs on a Twilio **trial** account, which can only call **pre-verified**
> numbers. To get a live call, your number must be verified on the account first — reach
> out and I can verify it, or watch a recorded walkthrough.

A web-to-phone AI voice agent for real estate lead qualification. A visitor fills in a
short web form; the backend places a **real outbound phone call** and an AI agent talks
to them, qualifies the lead, matches properties, and saves a report for a human agent.

Built to be **deployable on a free tier** and shareable with a single link — point a
recruiter at the URL, they enter their number, and the AI calls them.

---

## How It Works

```
Visitor opens the web page  (Hugging Face Spaces)
        │  enters name + phone + what they want
        ▼
POST /api/start-call  ──▶  Twilio places an OUTBOUND call to the visitor
        ▼
Visitor's phone rings; they answer
        ▼
Twilio webhook /voice/outbound  →  AI greeting + question
        ▼
<Gather input="speech">  ── Twilio transcribes the caller's speech (built-in STT)
        ▼
POST /voice/process  →  Gemini generates the next question (Polly speaks it)
        ▼
Loop until qualified → Gemini extracts a structured lead
                     → properties matched via Gemini embeddings
                     → lead report written to leads/
```

There is **no local ML** — no Whisper, no Torch, no TTS models. Speech-to-text is
handled by Twilio's `<Gather>`, text-to-speech by Twilio Polly, and all intelligence by
Google Gemini. That keeps the container small enough for free hosting.

---

## Tech Stack

| Component | Technology |
|---|---|
| Web framework | FastAPI + Uvicorn |
| Frontend | Single static HTML page (`static/index.html`) |
| Telephony | Twilio Programmable Voice (outbound calls) |
| Speech-to-Text | Twilio `<Gather input="speech">` (built-in) |
| Text-to-Speech | Twilio Polly.Joanna |
| LLM | Google **Gemini** (`gemini-2.5-flash`) |
| Property search | Gemini embeddings + in-memory cosine similarity (NumPy) |
| Hosting | Hugging Face Spaces (Docker) |

---

## Project Structure

```
.
├── main.py             # FastAPI app: web form API + Twilio voice webhooks + brain
├── llm.py              # All Gemini calls (chat, JSON extraction, embeddings)
├── property_manager.py # In-memory semantic property search via Gemini embeddings
├── lead_extractor.py   # Gemini-based lead extraction + rule-based scoring
├── models.py           # Pydantic LeadData + enums
├── properties.json     # Demo property listings
├── static/index.html   # Recruiter-facing web form
├── Dockerfile          # For Hugging Face Spaces (port 7860)
├── requirements.txt    # Runtime dependencies
└── .env.example        # Required environment variables
```

---

## Environment Variables

See `.env.example`. Required:

| Variable | Purpose |
|---|---|
| `GEMINI_API_KEY` | Google Gemini key — free at [aistudio.google.com](https://aistudio.google.com/app/apikey) |
| `TWILIO_ACCOUNT_SID` / `TWILIO_AUTH_TOKEN` | Twilio credentials |
| `TWILIO_PHONE_NUMBER` | Your Twilio number, E.164 (`+1...`) |
| `PUBLIC_BASE_URL` | The deployed app's https URL (used as the Twilio webhook) |

> **Cost note:** Gemini has a free tier (with rate limits). Twilio is **not** free — a
> *trial* account can only call numbers you've **verified** in the console; to call any
> visitor you need a funded paid account and a purchased number.

---

## Run Locally

```bash
uv sync                       # or: pip install -r requirements.txt
cp .env.example .env          # then fill in your keys
python main.py                # serves on http://localhost:7860
```

To test outbound calls locally you must expose the server publicly and set
`PUBLIC_BASE_URL` to that URL:

```bash
ngrok http 7860               # set PUBLIC_BASE_URL to the https ngrok URL
```

---

## Deploy to Hugging Face Spaces

1. Create a new **Space** → SDK: **Docker**.
2. Push this repo to the Space (or connect the GitHub repo).
3. In **Settings → Variables and secrets**, add the env vars above as **Secrets**.
   Set `PUBLIC_BASE_URL` to your Space URL, e.g. `https://<user>-<space>.hf.space`.
4. The Space builds from the `Dockerfile` and serves on port 7860.
5. Open the Space URL, enter your details, and the agent calls you.

No separate Twilio webhook configuration is needed — outbound calls tell Twilio which URL
to hit (`PUBLIC_BASE_URL/voice/outbound`).

---

## API Endpoints

| Method | Path | Purpose |
|---|---|---|
| `GET` | `/` | Web form |
| `GET` | `/health` | Status (Gemini / Twilio / properties) |
| `POST` | `/api/start-call` | Trigger an outbound call (JSON: name, phone, looking_for) |
| `POST` | `/voice/outbound` | Twilio webhook — first turn of the call |
| `POST` | `/voice/process` | Twilio webhook — each subsequent turn |

---

## Notes & Limitations

- Conversation state is in-memory and cleared when a call ends; no database.
- Twilio webhooks are not signature-validated yet (see batch-two hardening).
- The demo catalog is 5 listings in `properties.json`.

## License

MIT
