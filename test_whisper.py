import whisper
import time

print("Loading Whisper model (this will download ~150MB on first run)...")
start = time.time()

# Use 'tiny' model for laptop - fastest and lightest
model = whisper.load_model("tiny")

print(f"✓ Model loaded in {time.time() - start:.2f} seconds")
print(f"✓ Model type: {model.__class__.__name__}")
print("\nWhisper is ready for speech recognition!")