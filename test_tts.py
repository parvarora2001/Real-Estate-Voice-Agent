from TTS.api import TTS
import os

print("Loading TTS model (this may take a minute on first run)...\n")

# Use a lightweight, fast model perfect for laptops
tts = TTS(model_name="tts_models/en/ljspeech/tacotron2-DDC", progress_bar=True)

print("✓ TTS model loaded!\n")

# Generate speech
text = "Hello! I'm your AI real estate assistant. I'm here to help you find your perfect property."

output_file = "test_output.wav"

print(f"Generating speech: '{text}'\n")
tts.tts_to_file(text=text, file_path=output_file)

print(f"✓ Audio saved to: {output_file}")
print("\nYou can play it with: afplay test_output.wav")