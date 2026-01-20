import ollama

print("Testing Phi-3 LLM connection...\n")

# Simple test prompt
response = ollama.chat(
    model='phi3:mini',
    messages=[
        {
            'role': 'system',
            'content': 'You are a helpful real estate assistant. Keep responses concise and friendly.'
        },
        {
            'role': 'user',
            'content': 'Hi, I\'m interested in learning about available properties in downtown.'
        }
    ]
)

print("--- LLM Response ---")
print(response['message']['content'])
print("\n✓ LLM is working!")