"""Google AI Studio integration helpers.

Provides `ask_model` and helpers to translate bot prompts into requests
for Google AI Studio using a simple API key from the environment.
"""

import os
import re
import requests
from dotenv import load_dotenv

load_dotenv()

GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY") or os.getenv("GOOGLE_AI_STUDIO_API_KEY")
GOOGLE_MODEL = os.getenv("GOOGLE_MODEL") or "gemini-2.0-flash"
GOOGLE_API_BASE_URL = "https://generativelanguage.googleapis.com/v1beta/models"


def clean_response(text: str) -> str:
    """Remove internal markers and debug tokens from model response."""
    if not text or not isinstance(text, str):
        return ""

    text = re.sub(r"<[a-z_|\d]+>", "", text, flags=re.IGNORECASE)
    text = re.sub(r"</[a-z_|\d]+>", "", text, flags=re.IGNORECASE)

    text = re.sub(r"https?://\S+", "", text)

    text = re.sub(r"\n{3,}", "\n\n", text)
    text = re.sub(r" {2,}", " ", text)

    return text.strip()


def _build_google_payload(system_prompt: str, prompt: str, history=None, images=None):
    """Build a Google AI Studio generateContent payload."""
    contents = []

    if history:
        for role, content in history:
            content_clean = content.strip()[:500] if content else ""
            if not content_clean:
                continue
            google_role = "model" if role == "assistant" else "user"
            contents.append({"role": google_role, "parts": [{"text": content_clean}]})

    user_parts = [{"text": prompt or "Describe this image."}]
    if images:
        for image_b64 in images:
            user_parts.append(
                {
                    "inlineData": {
                        "mimeType": "image/jpeg",
                        "data": image_b64,
                    }
                }
            )

    contents.append({"role": "user", "parts": user_parts})

    payload = {
        "contents": contents,
        "generationConfig": {"temperature": 0.2},
    }
    if system_prompt:
        payload["systemInstruction"] = {"parts": [{"text": system_prompt}]}
    return payload


def _extract_google_text(data: dict) -> str:
    """Extract text from Google AI Studio generateContent responses."""
    if not isinstance(data, dict):
        return ""

    for candidate in data.get("candidates") or []:
        if not isinstance(candidate, dict):
            continue
        content = candidate.get("content")
        if not isinstance(content, dict):
            continue
        parts = content.get("parts") or []
        if not isinstance(parts, list):
            continue
        texts = []
        for part in parts:
            if isinstance(part, dict) and isinstance(part.get("text"), str):
                texts.append(part["text"])
        if texts:
            return "".join(texts)

    return ""


def ask_model(prompt: str, system_prompt: str, history=None, images=None) -> str:
    if not GOOGLE_API_KEY:
        raise RuntimeError("GOOGLE_API_KEY or GOOGLE_AI_STUDIO_API_KEY must be set in the environment.")

    effective_history = [] if images else (history or [])
    google_url = f"{GOOGLE_API_BASE_URL}/{GOOGLE_MODEL}:generateContent?key={GOOGLE_API_KEY}"
    google_payload = _build_google_payload(
        system_prompt=system_prompt,
        prompt=prompt,
        history=effective_history,
        images=images,
    )

    response = requests.post(google_url, json=google_payload, timeout=300)
    response.raise_for_status()
    text = _extract_google_text(response.json())
    if text.strip():
        return text

    raise RuntimeError("Google AI Studio returned an empty response.")


def summarise_with_model(summary_prompt: str) -> str:
    """Generate a compact summary using Google AI Studio."""
    summary_system_prompt = (
        "You are a memory compression assistant. "
        "Return concise, factual summaries only."
    )
    text = ask_model(summary_prompt, summary_system_prompt, history=None, images=None)
    return clean_response(text) or "Summary unavailable."
