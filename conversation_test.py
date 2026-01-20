import whisper
import ollama
from TTS.api import TTS
import os

print("🤖 Initializing AI Real Estate Assistant...\n")

# Load all models
print("Loading Whisper (Speech-to-Text)...")
whisper_model = whisper.load_model("tiny")

print("Loading TTS (Text-to-Speech)...")
tts = TTS(model_name="tts_models/en/ljspeech/tacotron2-DDC", progress_bar=False)

print("\n✓ All models loaded!\n")

# Simulated conversation (we'll use real audio later)
def simulate_conversation():
    # Step 1: Simulate user speech input
    user_text = "Hi, I'm looking for a 3-bedroom apartment in downtown with a budget of $500,000"
    print(f"👤 User (simulated): {user_text}\n")
    
    # Step 2: LLM processes and responds
    print("🧠 AI is thinking...\n")
    response = ollama.chat(
        model='phi3:mini',
        messages=[
            {
                'role': 'system',
                'content': '''You are a helpful real estate assistant conducting a phone call. 
                Ask qualifying questions about: budget, location preferences, timeline, financing status.
                Keep responses short and conversational - you're on a phone call.'''
            },
            {
                'role': 'user',
                'content': user_text
            }
        ]
    )
    
    ai_response = response['message']['content']
    print(f"🤖 AI Assistant: {ai_response}\n")
    
    # Step 3: Convert AI response to speech
    print("🔊 Generating speech...\n")
    tts.tts_to_file(text=ai_response, file_path="ai_response.wav")
    
    print("✓ Response saved to ai_response.wav")
    print("\nPlay it with: afplay ai_response.wav\n")
    
    return ai_response

# Run the simulation
simulate_conversation()

print("=" * 60)
print("✅ Conversation loop working!")
print("=" * 60)
