"""Gemini-backed LLM helpers.

Centralizes all Google Gemini calls so the rest of the app never imports the SDK
directly. Reads the API key from GEMINI_API_KEY (or GOOGLE_API_KEY).
"""
import os
import json
from typing import List, Dict, Optional

from google import genai
from google.genai import types

CHAT_MODEL = os.getenv("GEMINI_CHAT_MODEL", "gemini-2.5-flash")
EMBED_MODEL = os.getenv("GEMINI_EMBED_MODEL", "text-embedding-004")

_API_KEY = os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")

# A single shared client. If the key is missing we keep the module importable so the
# app can still boot and report the misconfiguration via /health.
client: Optional[genai.Client] = genai.Client(api_key=_API_KEY) if _API_KEY else None


def is_configured() -> bool:
    return client is not None


def _to_contents(messages: List[Dict]) -> list:
    """Map our internal {role: user|assistant, content} messages to Gemini turns.

    Gemini uses the role 'model' (not 'assistant') and has no 'system' message role
    (system text is passed separately via system_instruction), so system messages
    are dropped here.
    """
    contents = []
    for m in messages:
        role = m.get("role")
        if role == "system":
            continue
        contents.append({
            "role": "model" if role == "assistant" else "user",
            "parts": [{"text": m["content"]}],
        })
    return contents


def generate_reply(system_prompt: str, messages: List[Dict],
                   max_tokens: int = 60, temperature: float = 0.7) -> str:
    """Generate a short conversational reply."""
    if client is None:
        raise RuntimeError("Gemini client not configured (missing GEMINI_API_KEY).")

    response = client.models.generate_content(
        model=CHAT_MODEL,
        contents=_to_contents(messages),
        config=types.GenerateContentConfig(
            system_instruction=system_prompt,
            temperature=temperature,
            max_output_tokens=max_tokens,
        ),
    )
    return (response.text or "").strip()


def extract_json(prompt: str) -> dict:
    """Run a one-shot prompt and parse the JSON response.

    Uses Gemini's JSON mode so the output is guaranteed to be valid JSON.
    """
    if client is None:
        raise RuntimeError("Gemini client not configured (missing GEMINI_API_KEY).")

    response = client.models.generate_content(
        model=CHAT_MODEL,
        contents=[{"role": "user", "parts": [{"text": prompt}]}],
        config=types.GenerateContentConfig(
            response_mime_type="application/json",
            temperature=0.1,
        ),
    )
    text = (response.text or "").strip()
    return json.loads(text)


def embed(texts: List[str]) -> List[List[float]]:
    """Return embedding vectors for a list of texts."""
    if client is None:
        raise RuntimeError("Gemini client not configured (missing GEMINI_API_KEY).")

    response = client.models.embed_content(model=EMBED_MODEL, contents=texts)
    return [e.values for e in response.embeddings]
