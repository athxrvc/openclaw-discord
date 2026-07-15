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
GOOGLE_MODEL = os.getenv("GOOGLE_MODEL") or os.getenv("GOOGLE_AI_STUDIO_MODEL")
GOOGLE_API_BASE_URL = "https://generativelanguage.googleapis.com/v1beta/models"


AI_PROVIDER = os.getenv("AI_PROVIDER")

# OpenAI/Anthropic envs (optional)
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
OPENAI_MODEL = os.getenv("OPENAI_MODEL")
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY")
ANTHROPIC_MODEL = os.getenv("ANTHROPIC_MODEL")
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


def _ask_openai(prompt: str, system_prompt: str, history=None, images=None) -> str:
    model = OPENAI_MODEL or "gpt-3.5-turbo"
    url = "https://api.openai.com/v1/chat/completions"
    headers = {"Authorization": f"Bearer {OPENAI_API_KEY}", "Content-Type": "application/json"}

    messages = []
    if system_prompt:
        messages.append({"role": "system", "content": system_prompt})
    if history:
        for role, content in history:
            role_name = "assistant" if role == "assistant" else "user"
            messages.append({"role": role_name, "content": content})
    messages.append({"role": "user", "content": prompt})

    payload = {"model": model, "messages": messages, "temperature": 0.2}

    resp = requests.post(url, json=payload, headers=headers, timeout=120)
    try:
        resp.raise_for_status()
    except Exception as e:
        raise RuntimeError(f"OpenAI request failed: {resp.status_code} {resp.text}")

    data = resp.json()
    # Compatible with Chat Completions
    choice = (data.get("choices") or [None])[0]
    if choice and isinstance(choice.get("message"), dict):
        return choice["message"]["content"].strip()
    # Fallback
    return data.get("choices", [{}])[0].get("text", "").strip()


def _ask_anthropic(prompt: str, system_prompt: str, history=None, images=None) -> str:
    model = ANTHROPIC_MODEL or "claude-2"
    url = "https://api.anthropic.com/v1/complete"
    headers = {"x-api-key": ANTHROPIC_API_KEY, "Content-Type": "application/json"}

    # Build a simple Claude prompt
    human_prompt = prompt
    if system_prompt:
        human_prompt = system_prompt + "\n\n" + prompt

    payload = {
        "model": model,
        "prompt": f"\n\nHuman: {human_prompt}\n\nAssistant:",
        "max_tokens": 512,
        "temperature": 0.2,
    }

    resp = requests.post(url, json=payload, headers=headers, timeout=120)
    try:
        resp.raise_for_status()
    except Exception:
        raise RuntimeError(f"Anthropic request failed: {resp.status_code} {resp.text}")

    data = resp.json()
    return (data.get("completion") or "").strip()


def ask_model(prompt: str, system_prompt: str, history=None, images=None) -> str:

    # Provider selection: prefer explicit `AI_PROVIDER`, otherwise detect from available keys.
    provider = (AI_PROVIDER or "").strip().lower() or None
    if not provider:
        if OPENAI_API_KEY:
            provider = "openai"
        elif ANTHROPIC_API_KEY:
            provider = "anthropic"
        elif GOOGLE_API_KEY:
            provider = "google"

    if provider == "google":
        if not GOOGLE_API_KEY:
            raise RuntimeError("GOOGLE_API_KEY or GOOGLE_AI_STUDIO_API_KEY must be set for Google provider.")
        if not GOOGLE_MODEL:
            raise RuntimeError("GOOGLE_MODEL is not set. Set `GOOGLE_MODEL` to a model available for your project, or set `AI_PROVIDER` to another provider.")

    elif provider == "openai":
        if not OPENAI_API_KEY:
            raise RuntimeError("OPENAI_API_KEY must be set for OpenAI provider.")

    elif provider == "anthropic":
        if not ANTHROPIC_API_KEY:
            raise RuntimeError("ANTHROPIC_API_KEY must be set for Anthropic provider.")

    else:
        raise RuntimeError("No supported AI provider detected. Set AI_PROVIDER or provide OPENAI_API_KEY/ANTHROPIC_API_KEY/GOOGLE_API_KEY.")

    # Route to provider-specific implementation
    if provider == "openai":
        return _ask_openai(prompt, system_prompt, history, images)
    if provider == "anthropic":
        return _ask_anthropic(prompt, system_prompt, history, images)
    # default to google
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
