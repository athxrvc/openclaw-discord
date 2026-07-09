"""Model gateway integration helpers.

Provides `ask_model` and helpers to translate bot prompts into requests
to an inference gateway that exposes Ollama/OpenAI-compatible endpoints.
The gateway URL is read from `API_GATEWAY_URL`.
"""

import os
import re
import requests

API_GATEWAY_URL = os.getenv("API_GATEWAY_URL") or "http://localhost:11434/api/generate"
# Optional model name to request from the gateway. If present, include in payloads.
MODEL_NAME = os.getenv("API_MODEL")


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


def _normalize_chat_url(url: str) -> str:
    """Convert a '/api/generate' url to the corresponding '/api/chat' url.

    This allows using chat-style endpoints when available for better
    fidelity with message arrays and images.
    """
    if url.endswith("/api/generate"):
        return url[: -len("/api/generate")] + "/api/chat"
    return url


def _base_inference_url(url: str) -> str:
    """Return base server URL without known endpoint suffixes."""
    for suffix in ("/api/generate", "/api/chat", "/v1/chat/completions", "/v1/completions", "/v1"):
        if url.endswith(suffix):
            return url[: -len(suffix)]
    return url.rstrip("/")


def _extract_model_text(data: dict) -> str:
    """Extract textual content from varied gateway response shapes.

    Supports legacy Ollama-style responses, OpenAI v1 responses, and
    other simple responses containing `response` or `content` fields.
    """
    if not isinstance(data, dict):
        return ""

    if isinstance(data.get("response"), str):
        return data["response"]

    message = data.get("message")
    if isinstance(message, dict) and isinstance(message.get("content"), str):
        return message["content"]

    if isinstance(data.get("content"), str):
        return data["content"]

    choices = data.get("choices")
    if isinstance(choices, list) and choices:
        first = choices[0]
        if isinstance(first, dict):
            msg = first.get("message")
            if isinstance(msg, dict) and isinstance(msg.get("content"), str):
                return msg["content"]
            if isinstance(first.get("text"), str):
                return first["text"]

    return ""


def _build_generate_prompt(prompt: str, system_prompt: str, history=None) -> str:
    """Construct a plain-text prompt for non-chat generate endpoints.

    Includes a short history excerpt when available.
    """
    history_text = ""
    if history:
        history_lines = []
        for role, content in history:
            content_clean = content.strip()[:500] if content else ""
            if content_clean and role in ("user", "assistant"):
                history_lines.append(f"{role.capitalize()}: {content_clean}")
        history_text = "\n".join(history_lines)

    history_section = f"Conversation history:\n{history_text}\n" if history_text else ""
    return f"""You are a helpful Discord assistant.

{system_prompt}

{history_section}
Respond to the following user message:

{prompt or "Describe this image."}

If an image is provided, describe only what is visible and avoid guessing.
"""


def _build_messages(system_prompt: str, prompt: str, history=None, images=None):
    """Build OpenAI-compatible chat messages for the gateway.

    Returns a list of message dicts with `role` and `content` keys, and
    includes image data when present.
    """
    messages = []

    base_system = (
        "You are a helpful Discord assistant. "
        "Answer only what the user asked. "
        "If an image is provided, describe only what is visible in that image. "
        "If details are unclear, say so instead of guessing."
    )
    messages.append({"role": "system", "content": f"{base_system}\n\n{system_prompt}"})

    if history:
        for role, content in history:
            content_clean = content.strip()[:500] if content else ""
            if content_clean and role in ("user", "assistant"):
                messages.append({"role": role, "content": content_clean})

    user_message = {"role": "user", "content": prompt or "Describe this image."}
    if images:
        user_message["images"] = images
    messages.append(user_message)

    return messages


def _to_openai_messages(gateway_messages):
    """Convert gateway-style messages to OpenAI-compatible messages for v1 endpoints."""
    openai_messages = []
    for msg in gateway_messages:
        role = msg.get("role", "user")
        content = msg.get("content", "")
        images = msg.get("images") or []

        if images and role == "user":
            multi_content = [{"type": "text", "text": content or "Describe this image."}]
            for image_b64 in images:
                multi_content.append(
                    {
                        "type": "image_url",
                        "image_url": {"url": f"data:image/jpeg;base64,{image_b64}"},
                    }
                )
            openai_messages.append({"role": role, "content": multi_content})
        else:
            openai_messages.append({"role": role, "content": content})

    return openai_messages


def ask_model(prompt: str, system_prompt: str, history=None, images=None) -> str:
    effective_history = [] if images else (history or [])
    messages = _build_messages(system_prompt, prompt, history=effective_history, images=images)

    # Prefer OpenAI-compatible chat endpoint on the gateway for best support.
    base_url = _base_inference_url(API_GATEWAY_URL)
    v1_chat_url = f"{base_url}/v1/chat/completions"

    openai_chat_payload = {
        "messages": _to_openai_messages(messages),
        "temperature": 0.2,
        "stream": False,
    }
    if MODEL_NAME:
        openai_chat_payload["model"] = MODEL_NAME

    try:
        response = requests.post(v1_chat_url, json=openai_chat_payload, timeout=300)
        response.raise_for_status()
        text = _extract_model_text(response.json())
        if text.strip():
            return text
    except Exception:
        pass

    # Fallback to gateway's chat (Ollama-style) endpoint if available.
    chat_payload = {
        "model": MODEL_NAME,
        "messages": messages,
        "stream": False,
        "options": {"temperature": 0.2},
    }

    primary_chat_url = _normalize_chat_url(API_GATEWAY_URL)
    try:
        response = requests.post(primary_chat_url, json=chat_payload, timeout=300)
        response.raise_for_status()
        text = _extract_model_text(response.json())
        if text.strip():
            return text
    except Exception:
        pass

    generate_payload = {
        "model": MODEL_NAME,
        "prompt": _build_generate_prompt(prompt, system_prompt, history=effective_history),
        "stream": False,
        "options": {"temperature": 0.2},
    }
    if images:
        generate_payload["images"] = images

    generate_url = f"{base_url}/api/generate"

    response = requests.post(generate_url, json=generate_payload, timeout=300)
    response.raise_for_status()
    return _extract_model_text(response.json())


def summarise_with_model(summary_prompt: str) -> str:
    """Generate a compact summary using the configured inference gateway."""
    summary_system_prompt = (
        "You are a memory compression assistant. "
        "Return concise, factual summaries only."
    )
    text = ask_model(summary_prompt, summary_system_prompt, history=None, images=None)
    return clean_response(text) or "Summary unavailable."
