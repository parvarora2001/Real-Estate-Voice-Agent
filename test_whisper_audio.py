import whisper

print("Loading Whisper model...")
model = whisper.load_model("tiny")

# We'll transcribe a sample audio file
# First, let's test with a URL (Whisper can handle this)
print("\nTranscribing sample audio...")

# Test with a short audio sample
audio_path = "https://github.com/openai/whisper/raw/main/tests/jfk.flac"

result = model.transcribe(audio_path)

print("\n--- Transcription Result ---")
print(result["text"])
print("\n--- Full Details ---")
print(f"Language detected: {result['language']}")
print(f"Segments: {len(result['segments'])}")