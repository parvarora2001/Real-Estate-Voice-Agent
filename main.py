from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware
import ollama
from TTS.api import TTS
import whisper
import httpx
import os
from dotenv import load_dotenv

load_dotenv()

# Load Twilio credentials
TWILIO_ACCOUNT_SID = os.getenv("TWILIO_ACCOUNT_SID")
TWILIO_AUTH_TOKEN = os.getenv("TWILIO_AUTH_TOKEN")

# Verify credentials loaded
if not TWILIO_ACCOUNT_SID or not TWILIO_AUTH_TOKEN:
    print("⚠️  WARNING: Twilio credentials not loaded!")
    print("   Make sure .env file exists with TWILIO_ACCOUNT_SID and TWILIO_AUTH_TOKEN")
else:
    print(f"✅ Twilio SID: {TWILIO_ACCOUNT_SID[:10]}...")
    print(f"✅ Auth Token: {'*' * len(TWILIO_AUTH_TOKEN)}")

app = FastAPI()

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Global variables
whisper_model = None
tts = None
conversations = {}

@app.on_event("startup")
async def startup_event():
    """Load models on startup"""
    global whisper_model, tts
    try:
        print("\n🚀 Loading AI models...")
        whisper_model = whisper.load_model("tiny")
        print("   ✅ Whisper loaded")
        tts = TTS(model_name="tts_models/en/ljspeech/tacotron2-DDC", progress_bar=False)
        print("   ✅ TTS loaded")
        print("✅ All models ready!\n")
    except Exception as e:
        print(f"❌ Error loading models: {e}")

@app.middleware("http")
async def log_requests(request: Request, call_next):
    print(f"\n{'='*60}")
    print(f"📞 {request.method} {request.url.path}")
    print(f"{'='*60}")
    response = await call_next(request)
    return response

@app.get("/")
def home():
    return {
        "status": "AI Real Estate Assistant",
        "version": "2.0",
        "models_loaded": whisper_model is not None and tts is not None,
        "credentials_loaded": bool(TWILIO_ACCOUNT_SID and TWILIO_AUTH_TOKEN)
    }

@app.post("/voice/incoming")
async def handle_incoming_call(request: Request):
    """Handle incoming calls"""
    form_data = await request.form()
    call_sid = form_data.get("CallSid")
    
    print(f"📞 New call: {call_sid}")
    
    # Initialize conversation
    conversations[call_sid] = {"messages": [], "lead_info": {}}
    
    twiml = """<?xml version="1.0" encoding="UTF-8"?>
<Response>
    <Say voice="Polly.Joanna">
        Hello! Thank you for calling about our properties. 
        I'm your A I assistant. What type of property are you looking for?
    </Say>
    <Record maxLength="30" action="/voice/process" playBeep="true" transcribe="false"/>
</Response>"""
    
    return Response(content=twiml, media_type="application/xml")

@app.post("/voice/process")
async def process_recording(request: Request):
    """Process caller's response"""
    try:
        form_data = await request.form()
        
        # Get all form fields
        call_sid = form_data.get("CallSid")
        recording_url = form_data.get("RecordingUrl")
        recording_duration = form_data.get("RecordingDuration")
        
        print(f"\n🎤 Processing call: {call_sid}")
        print(f"   Duration: {recording_duration}s")
        print(f"   URL: {recording_url}")
        
        # Check if we got a recording
        if not recording_url:
            print("❌ No recording URL received")
            return create_error_response("I didn't catch that. Could you repeat?")
        
        # Check if recording is too short
        if recording_duration and int(recording_duration) < 1:
            print("⚠️  Recording too short")
            return create_error_response("That was too brief. Please tell me more.")
        
        # Download recording
        print("⬇️  Downloading...")
        audio_file = await download_recording(recording_url)
        
        if not audio_file:
            return create_error_response("I had trouble hearing that. Please try again.")
        
        # Transcribe
        print("🎯 Transcribing...")
        transcription = transcribe_audio(audio_file)
        print(f"👤 User: \"{transcription}\"")
        
        if not transcription or len(transcription) < 3:
            print("⚠️  Transcription too short")
            os.remove(audio_file)
            return create_error_response("I didn't quite catch that. Could you say that again?")
        
        # Generate AI response
        print("🧠 Thinking...")
        ai_response = generate_response(call_sid, transcription)
        print(f"🤖 AI: \"{ai_response}\"")
        
        # Clean up audio file
        if os.path.exists(audio_file):
            os.remove(audio_file)
        
        # Return response with next recording prompt
        twiml = f"""<?xml version="1.0" encoding="UTF-8"?>
<Response>
    <Say voice="Polly.Joanna">{escape_xml(ai_response)}</Say>
    <Record maxLength="30" action="/voice/process" playBeep="true" transcribe="false"/>
</Response>"""
        
        return Response(content=twiml, media_type="application/xml")
        
    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()
        return create_error_response("I'm having technical difficulties. Let me transfer you.")

async def download_recording(recording_url: str) -> str:
    """Download recording from Twilio"""
    try:
        download_url = recording_url + ".mp3"
        
        print(f"   Auth: {TWILIO_ACCOUNT_SID[:10]}... / {'*' * 10}")
        
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.get(
                download_url,
                auth=(TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN)
            )
            
            if response.status_code == 401:
                print("❌ 401 Unauthorized - Check your Twilio credentials!")
                return None
            
            response.raise_for_status()
            
            temp_file = f"recording_{os.getpid()}.mp3"
            with open(temp_file, "wb") as f:
                f.write(response.content)
            
            print(f"   ✅ Saved: {temp_file} ({len(response.content)} bytes)")
            return temp_file
            
    except httpx.HTTPStatusError as e:
        print(f"❌ HTTP Error {e.response.status_code}: {e}")
        return None
    except Exception as e:
        print(f"❌ Download error: {e}")
        return None

def transcribe_audio(audio_file: str) -> str:
    """Transcribe with Whisper"""
    try:
        # Check file size
        file_size = os.path.getsize(audio_file)
        print(f"   📊 Audio file size: {file_size} bytes")
        
        if file_size < 1000:  # Less than 1KB is suspicious
            print("   ⚠️  File too small - might be empty")
            return ""
        
        # Transcribe
        result = whisper_model.transcribe(audio_file, fp16=False)
        transcription = result["text"].strip()
        
        print(f"   📝 Raw transcription: '{transcription}'")
        print(f"   📏 Length: {len(transcription)} chars")
        
        return transcription
        
    except Exception as e:
        print(f"❌ Transcription error: {e}")
        import traceback
        traceback.print_exc()
        return ""
    
def generate_response(call_sid: str, user_message: str) -> str:
    """Generate AI response"""
    try:
        conversation = conversations.get(call_sid, {"messages": []})
        
        # Add user message
        conversation["messages"].append({
            "role": "user",
            "content": user_message
        })
        
        # System prompt
        system_prompt = """You are a friendly real estate assistant on a phone call. 
Your goal: gather information about what the caller needs.
Ask about: property type, bedrooms, budget, location, timeline.
Rules:
- Keep responses SHORT (1-2 sentences max)
- Ask ONE question at a time
- Be conversational and natural
- Remember what they've told you"""
        
        messages = [{"role": "system", "content": system_prompt}] + conversation["messages"]
        
        # Get LLM response
        response = ollama.chat(model='phi3:mini', messages=messages)
        ai_message = response['message']['content']
        
        # Add to conversation
        conversation["messages"].append({
            "role": "assistant",
            "content": ai_message
        })
        
        conversations[call_sid] = conversation
        
        return ai_message
        
    except Exception as e:
        print(f"❌ LLM error: {e}")
        return "I understand. Can you tell me more about your budget and timeline?"

def escape_xml(text: str) -> str:
    """Escape XML special characters"""
    return (text
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
        .replace("'", "&apos;"))

def create_error_response(message: str) -> Response:
    """Create error TwiML response"""
    twiml = f"""<?xml version="1.0" encoding="UTF-8"?>
<Response>
    <Say voice="Polly.Joanna">{message}</Say>
    <Record maxLength="30" action="/voice/process" playBeep="true"/>
</Response>"""
    return Response(content=twiml, media_type="application/xml")

@app.get("/health")
def health():
    return {
        "status": "healthy",
        "models": {
            "whisper": whisper_model is not None,
            "tts": tts is not None,
            "llm": True
        },
        "auth": bool(TWILIO_ACCOUNT_SID and TWILIO_AUTH_TOKEN),
        "conversations": len(conversations)
    }

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000, log_level="info")