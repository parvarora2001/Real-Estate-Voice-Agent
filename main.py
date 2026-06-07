from fastapi import FastAPI, Request, Response
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from contextlib import asynccontextmanager
import os
import json
from typing import List, Dict, Optional

from pydantic import BaseModel
from dotenv import load_dotenv

import llm
from property_manager import PropertyManager
from lead_extractor import LeadExtractor
from models import LeadData

load_dotenv()

# Twilio credentials + public URL (the deployed app's https URL, used for call webhooks)
TWILIO_ACCOUNT_SID = os.getenv("TWILIO_ACCOUNT_SID")
TWILIO_AUTH_TOKEN = os.getenv("TWILIO_AUTH_TOKEN")
TWILIO_PHONE_NUMBER = os.getenv("TWILIO_PHONE_NUMBER")
PUBLIC_BASE_URL = (os.getenv("PUBLIC_BASE_URL") or "").strip().rstrip("/")

# Lazily-created Twilio REST client (only needed to place outbound calls)
twilio_client = None
if TWILIO_ACCOUNT_SID and TWILIO_AUTH_TOKEN:
    try:
        from twilio.rest import Client
        twilio_client = Client(TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN)
        print(f"✅ Twilio client ready (SID: {TWILIO_ACCOUNT_SID[:10]}...)")
    except Exception as e:
        print(f"⚠️  Could not init Twilio client: {e}")
else:
    print("⚠️  Twilio credentials not set — outbound calls disabled")

# Global state
property_manager: Optional[PropertyManager] = None
conversations: Dict[str, dict] = {}


@asynccontextmanager
async def lifespan(app: FastAPI):
    global property_manager
    print("\n🚀 Starting up...")
    if not llm.is_configured():
        print("⚠️  GEMINI_API_KEY not set — the agent's brain is offline")
    else:
        print(f"   ✅ Gemini ready ({llm.CHAT_MODEL})")
    property_manager = PropertyManager()
    print(f"   ✅ Property database ({property_manager.count_properties()} properties)")
    print("✅ Ready!\n")
    yield
    print("\n👋 Shutting down...")


app = FastAPI(lifespan=lifespan)

# Serve the recruiter-facing web form
if os.path.isdir("static"):
    app.mount("/static", StaticFiles(directory="static"), name="static")


@app.get("/")
def home():
    if os.path.exists("static/index.html"):
        return FileResponse("static/index.html")
    return JSONResponse({"status": "AI Real Estate Voice Agent", "form": "static/index.html missing"})


@app.get("/health")
def health():
    return {
        "status": "healthy",
        "gemini": llm.is_configured(),
        "twilio": twilio_client is not None,
        "public_url_set": bool(PUBLIC_BASE_URL),
        "properties": property_manager.count_properties() if property_manager else 0,
        "active_conversations": len(conversations),
    }


# ---------------------------------------------------------------------------
# Web form -> trigger an outbound call
# ---------------------------------------------------------------------------
class StartCallRequest(BaseModel):
    name: str
    phone: str            # E.164, e.g. +14155550123
    looking_for: str = ""  # what they want, used to seed the conversation


@app.post("/api/start-call")
async def start_call(req: StartCallRequest):
    """Place an outbound call to the visitor and run the AI agent on it."""
    if twilio_client is None:
        return JSONResponse(
            {"ok": False, "error": "Calling is not configured on the server."},
            status_code=503,
        )
    if not PUBLIC_BASE_URL:
        return JSONResponse(
            {"ok": False, "error": "Server PUBLIC_BASE_URL is not set."},
            status_code=503,
        )

    phone = req.phone.strip()
    if not phone.startswith("+") or len(phone) < 8:
        return JSONResponse(
            {"ok": False, "error": "Please enter a phone number in international format, e.g. +14155550123."},
            status_code=400,
        )

    try:
        call = twilio_client.calls.create(
            to=phone,
            from_=TWILIO_PHONE_NUMBER,
            url=f"{PUBLIC_BASE_URL}/voice/outbound",
        )
    except Exception as e:
        print(f"❌ Failed to place call: {e}")
        return JSONResponse({"ok": False, "error": f"Could not place call: {e}"}, status_code=502)

    # Seed the conversation. If the visitor told us what they're looking for, treat it
    # as their opening turn so the agent can react to it.
    seed_messages = []
    if req.looking_for.strip():
        seed_messages.append({"role": "user", "content": req.looking_for.strip()})

    conversations[call.sid] = {
        "messages": seed_messages,
        "lead_data": None,
        "matching_properties": [],
        "context": {"name": req.name.strip(), "phone": phone, "looking_for": req.looking_for.strip()},
    }

    print(f"📞 Outbound call queued: {call.sid} -> {phone}")
    return {"ok": True, "call_sid": call.sid, "message": f"Calling {phone} now — please answer!"}


# ---------------------------------------------------------------------------
# Twilio voice webhooks
# ---------------------------------------------------------------------------
@app.post("/voice/outbound")
async def voice_outbound(request: Request):
    """First leg of the outbound call: greet and ask the opening question."""
    form = await request.form()
    call_sid = form.get("CallSid")
    convo = conversations.setdefault(
        call_sid, {"messages": [], "lead_data": None, "matching_properties": [], "context": {}}
    )
    name = convo.get("context", {}).get("name", "")
    looking_for = convo.get("context", {}).get("looking_for", "")

    greeting = f"Hello{' ' + name if name else ''}! Thanks for your interest in our properties. "
    if looking_for:
        greeting += f"I see you're interested in {looking_for}. Let me ask a few quick questions to find the best match. To start, what's your budget range?"
    else:
        greeting += "I'm your A I real estate assistant. What type of property are you looking for?"

    convo["messages"].append({"role": "assistant", "content": greeting})
    return _gather_twiml(greeting)


@app.post("/voice/process")
async def voice_process(request: Request):
    """Each subsequent turn: take the recognized speech and respond."""
    form = await request.form()
    call_sid = form.get("CallSid")
    speech = (form.get("SpeechResult") or "").strip()

    print(f"\n🎤 {call_sid} — caller said: \"{speech}\"")

    if not speech:
        return _gather_twiml("Sorry, I didn't catch that. Could you say it again?")

    ai_response, end_call = generate_response(call_sid, speech)
    print(f"🤖 AI: \"{ai_response}\"")

    if end_call:
        twiml = f"""<?xml version="1.0" encoding="UTF-8"?>
<Response>
    <Say voice="Polly.Joanna">{escape_xml(ai_response)}</Say>
    <Hangup/>
</Response>"""
        conversations.pop(call_sid, None)  # free state; report already saved
        return Response(content=twiml, media_type="application/xml")

    return _gather_twiml(ai_response)


def _gather_twiml(say_text: str) -> Response:
    """TwiML that speaks a prompt then listens for speech (Twilio does the STT)."""
    twiml = f"""<?xml version="1.0" encoding="UTF-8"?>
<Response>
    <Gather input="speech" action="/voice/process" method="POST" speechTimeout="auto" language="en-US">
        <Say voice="Polly.Joanna">{escape_xml(say_text)}</Say>
    </Gather>
    <Say voice="Polly.Joanna">I didn't hear anything. Goodbye for now!</Say>
    <Hangup/>
</Response>"""
    return Response(content=twiml, media_type="application/xml")


# ---------------------------------------------------------------------------
# Conversation brain (Gemini)
# ---------------------------------------------------------------------------
def generate_response(call_sid: str, user_message: str):
    """Returns (reply_text, should_end). Mirrors the original qualification logic."""
    convo = conversations.setdefault(
        call_sid, {"messages": [], "lead_data": None, "matching_properties": [], "context": {}}
    )
    convo["messages"].append({"role": "user", "content": user_message})

    # Time to wrap up? Extract the lead, match properties, save a report.
    if should_end_call(convo["messages"]):
        try:
            print("✅ Extracting lead information...")
            lead_data = LeadExtractor.extract_lead_info(convo["messages"], call_sid)
            print("🔍 Finding matching properties...")
            matching = find_matching_properties(lead_data)
            convo["lead_data"] = lead_data
            convo["matching_properties"] = matching

            print("\n" + "=" * 60)
            print("📊 LEAD SUMMARY")
            print("=" * 60)
            print(lead_data.ai_summary)
            print(f"\n🎯 Lead Score: {lead_data.lead_score.value.upper()}")
            if matching:
                print(f"\n🏠 {len(matching)} matching properties:")
                for i, p in enumerate(matching, 1):
                    print(f"   {i}. {p.get('address')} - ${p.get('price'):,}")
            print("=" * 60 + "\n")

            save_lead_report(lead_data, matching)

            if matching:
                return (
                    f"Great news! I found {len(matching)} properties that match what you're "
                    "looking for. An agent will call you within 24 hours with the details. Thank you!",
                    True,
                )
            return (
                "Thank you for all that information! An agent will review your requirements and "
                "reach out within 24 hours. Have a great day!",
                True,
            )
        except Exception as e:
            print(f"❌ Wrap-up error: {e}")
            return ("Thank you! An agent will follow up with you shortly. Goodbye!", True)

    # Otherwise, ask the next qualifying question.
    conv_text = " ".join(m["content"] for m in convo["messages"] if m["role"] == "user").lower()
    needs = []
    if not any(w in conv_text for w in ["bathroom", "bath"]):
        needs.append("number of bathrooms")
    if not any(w in conv_text for w in ["$", "dollar", "thousand", "k", "budget"]):
        needs.append("budget range")
    if not any(w in conv_text for w in ["month", "week", "year", "asap", "immediately", "soon"]):
        needs.append("move-in timeline")
    if not any(w in conv_text for w in ["approved", "pre-approved", "cash", "financing", "mortgage"]):
        needs.append("financing status")

    system_prompt = f"""You are a friendly real estate assistant on a phone call. Ask ONE short
question to gather information.

Still need to know: {needs[0] if needs else 'nothing more'}

Rules:
1. Ask ONLY ONE question.
2. Keep it under 15 words.
3. Be warm and conversational.
4. Don't repeat information already provided.

Respond with ONLY your question."""

    try:
        reply = llm.generate_reply(system_prompt, convo["messages"], max_tokens=60)
        reply = reply.split("\n")[0].strip().strip('"')
        if not reply or len(reply) > 200:
            reply = f"Got it! What's your {needs[0]}?" if needs else "Perfect! Let me get you to an agent."
    except Exception as e:
        print(f"❌ Gemini error: {e}")
        reply = f"Got it! What's your {needs[0]}?" if needs else "Thanks! An agent will follow up."

    convo["messages"].append({"role": "assistant", "content": reply})
    return (reply, False)


def should_end_call(messages: list) -> bool:
    num_user = len([m for m in messages if m["role"] == "user"])
    if num_user >= 5:
        return True

    conv_text = " ".join(m["content"] for m in messages if m["role"] == "user").lower()
    has_budget = any(c.isdigit() for c in conv_text) and (
        "$" in conv_text or "dollar" in conv_text or "thousand" in conv_text or "k" in conv_text
    )
    has_timeline = any(w in conv_text for w in ["month", "week", "year", "asap", "soon", "immediately"])
    has_financing = any(w in conv_text for w in ["approved", "pre-approved", "cash", "financing"])
    if num_user >= 3 and has_budget and (has_timeline or has_financing):
        return True

    for msg in reversed(messages):
        if msg["role"] == "user":
            last = msg["content"].lower()
            ending = ["that's all", "thank you", "thanks", "goodbye", "that's it",
                      "no more questions", "i'm good", "nothing else", "that's everything"]
            return any(p in last for p in ending)
    return False


def find_matching_properties(lead_data: LeadData) -> List[Dict]:
    if not property_manager:
        return []

    # Build search query from lead requirements (.value so the enum serializes to
    # "house", not "PropertyType.HOUSE")
    query_parts = []
    if lead_data.property_type:
        query_parts.append(lead_data.property_type.value)
    if lead_data.bedrooms:
        query_parts.append(f"{lead_data.bedrooms} bedroom")
    if lead_data.preferred_locations:
        query_parts.append(" ".join(lead_data.preferred_locations))
    query = " ".join(query_parts) if query_parts else "property"
    print(f"   🔍 Search query: '{query}'")

    semantic_matches = property_manager.search_properties(query, n_results=5)
    matches = list(semantic_matches)

    if lead_data.max_budget and matches:
        matches = [p for p in matches if p.get("price", 0) <= lead_data.max_budget]
    if lead_data.min_budget and matches:
        matches = [p for p in matches if p.get("price", float("inf")) >= lead_data.min_budget]
    if lead_data.bedrooms and matches:
        matches = [p for p in matches if p.get("bedrooms") == lead_data.bedrooms]

    # If filtering eliminated everything, fall back to the closest semantic matches
    # rather than handing the agent an empty list.
    if not matches:
        print("   ℹ️  No properties passed all filters — falling back to closest matches")
        matches = semantic_matches

    return matches[:3]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def escape_xml(text: str) -> str:
    return (text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
            .replace('"', "&quot;").replace("'", "&apos;"))


def save_lead_report(lead_data: LeadData, matching_properties: List[Dict] = None):
    try:
        os.makedirs("leads", exist_ok=True)
        timestamp = lead_data.extracted_at.strftime("%Y%m%d_%H%M%S")
        filename = f"leads/lead_{lead_data.call_sid}_{timestamp}.json"

        report_data = lead_data.model_dump()
        if matching_properties:
            report_data["matching_properties"] = matching_properties
        with open(filename, "w") as f:
            json.dump(report_data, f, indent=2, default=str)
        print(f"💾 Lead report saved: {filename}")

        txt_filename = filename.replace(".json", ".txt")
        with open(txt_filename, "w") as f:
            f.write("=" * 60 + "\nREAL ESTATE LEAD REPORT\n" + "=" * 60 + "\n\n")
            f.write(f"Call ID: {lead_data.call_sid}\nDate: {lead_data.extracted_at}\n\n")
            f.write((lead_data.ai_summary or "") + "\n\n")
            f.write(f"Next Steps:\n{lead_data.next_steps}\n\n")
            if matching_properties:
                f.write("=" * 60 + f"\nMATCHING PROPERTIES ({len(matching_properties)} found)\n" + "=" * 60 + "\n\n")
                for i, prop in enumerate(matching_properties, 1):
                    f.write(f"{i}. {prop.get('address', 'Unknown')}\n")
                    f.write(f"   Type: {prop.get('property_type', 'N/A')}\n")
                    f.write(f"   Price: ${prop.get('price', 0):,}\n")
                    f.write(f"   Beds/Baths: {prop.get('bedrooms', 'N/A')}/{prop.get('bathrooms', 'N/A')}\n\n")
            f.write("=" * 60 + "\nFULL CONVERSATION\n" + "=" * 60 + "\n\n")
            for msg in lead_data.conversation_transcript:
                role = "Agent" if msg["role"] == "assistant" else "Caller"
                f.write(f"{role}: {msg['content']}\n\n")
        print(f"📄 Human-readable report: {txt_filename}")
    except Exception as e:
        print(f"❌ Error saving lead report: {e}")


if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", "7860"))
    uvicorn.run(app, host="0.0.0.0", port=port, log_level="info")
