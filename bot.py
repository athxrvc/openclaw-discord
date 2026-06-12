import os
import base64
import json
import requests
import discord

from dotenv import load_dotenv
from channel_modes import get_channel_mode
from db import save_message, load_recent_messages
from memory_manager import check_and_summarise, build_memory_context

load_dotenv()

TOKEN = os.getenv("DISCORD_TOKEN")
DEFAULT_MODEL = "maxwellb/gemma4-12b-it-oym"
MODEL = os.getenv("OLLAMA_MODEL", DEFAULT_MODEL)
OLLAMA_URL = os.getenv("OLLAMA_URL", "http://localhost:11434/api/generate")

current_model = MODEL

intents = discord.Intents.default()
intents.message_content = True

client = discord.Client(intents=intents)

ENABLED_CHANNELS_FILE = os.path.join("assets", "enabled_channels.json")


# =========================
# CHANNEL HELPERS
# =========================
def normalize_channel_name(channel_name: str) -> str:
    return channel_name.strip().lower().lstrip("#")


def load_disabled_channels() -> set[str]:
    if not os.path.exists(ENABLED_CHANNELS_FILE):
        return set()

    try:
        with open(ENABLED_CHANNELS_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)

        if isinstance(data, list):
            return {
                normalize_channel_name(name)
                for name in data
                if isinstance(name, str) and name.strip()
            }
    except Exception:
        pass

    return set()


def save_disabled_channels(channels: set[str]) -> None:
    os.makedirs(os.path.dirname(ENABLED_CHANNELS_FILE), exist_ok=True)
    with open(ENABLED_CHANNELS_FILE, "w", encoding="utf-8") as f:
        json.dump(sorted(channels), f, indent=2)


disabled_channels = load_disabled_channels()


# =========================
# IMAGE HELPER
# =========================
def download_image_as_base64(url):
    response = requests.get(url)
    response.raise_for_status()
    return base64.b64encode(response.content).decode("utf-8")


# =========================
# RESPONSE CLEANUP
# =========================
def clean_response(text):
    """Remove internal markers and debug tokens from model response."""
    import re
    
    if not text or not isinstance(text, str):
        return ""
    
    # Remove internal markers like <thought>, <channel|>, etc.
    text = re.sub(r'<[a-z_|\d]+>', '', text, flags=re.IGNORECASE)
    text = re.sub(r'</[a-z_|\d]+>', '', text, flags=re.IGNORECASE)
    
    # Remove bare URLs that look like model hallucinations
    text = re.sub(r'https?://\S+', '', text)
    
    # Clean up multiple spaces/newlines
    text = re.sub(r'\n{3,}', '\n\n', text)
    text = re.sub(r' {2,}', ' ', text)  # Remove multiple consecutive spaces
    
    text = text.strip()
    
    return text


def _normalize_chat_url(url: str) -> str:
    """Convert generate endpoint to chat endpoint for multimodal fidelity."""
    if url.endswith("/api/generate"):
        return url[:-len("/api/generate")] + "/api/chat"
    return url


def _base_inference_url(url: str) -> str:
    """Return base server URL without known endpoint suffixes."""
    for suffix in ("/api/generate", "/api/chat", "/v1/chat/completions", "/v1/completions"):
        if url.endswith(suffix):
            return url[:-len(suffix)]
    return url.rstrip("/")


def _extract_model_text(data: dict) -> str:
    """Extract text from Ollama, llama.cpp, or OpenAI-compatible responses."""
    if not isinstance(data, dict):
        return ""

    # Ollama generate
    if isinstance(data.get("response"), str):
        return data["response"]

    # Ollama chat
    message = data.get("message")
    if isinstance(message, dict) and isinstance(message.get("content"), str):
        return message["content"]

    # Some servers return top-level content
    if isinstance(data.get("content"), str):
        return data["content"]

    # OpenAI-compatible chat/completions
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


def _build_generate_prompt(prompt, system_prompt, history=None):
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


def _build_messages(system_prompt, prompt, history=None, images=None):
    """Build chat messages for Ollama chat-style APIs."""
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


def _to_openai_messages(ollama_messages):
    """Convert Ollama-style messages to OpenAI-compatible messages for v1 endpoints."""
    openai_messages = []
    for msg in ollama_messages:
        role = msg.get("role", "user")
        content = msg.get("content", "")
        images = msg.get("images") or []

        if images and role == "user":
            multi_content = [{"type": "text", "text": content or "Describe this image."}]
            for image_b64 in images:
                multi_content.append(
                    {
                        "type": "image_url",
                        "image_url": {
                            "url": f"data:image/jpeg;base64,{image_b64}"
                        }
                    }
                )
            openai_messages.append({"role": role, "content": multi_content})
        else:
            openai_messages.append({"role": role, "content": content})

    return openai_messages


# =========================
# OLLAMA CALL
# =========================
def ask_ollama(prompt, system_prompt, history=None, images=None):
    effective_history = [] if images else (history or [])
    messages = _build_messages(system_prompt, prompt, history=effective_history, images=images)

    ollama_chat_payload = {
        "model": current_model,
        "messages": messages,
        "stream": False,
        "options": {
            "temperature": 0.2
        }
    }

    # 1) Try chat endpoint first.
    primary_chat_url = _normalize_chat_url(OLLAMA_URL)
    base_url = _base_inference_url(OLLAMA_URL)
    v1_chat_url = f"{base_url}/v1/chat/completions"

    # Try Ollama chat payload first.
    try:
        response = requests.post(primary_chat_url, json=ollama_chat_payload, timeout=300)
        response.raise_for_status()
        text = _extract_model_text(response.json())
        if text.strip():
            return text
    except Exception:
        pass

    # Then try OpenAI-compatible payload for llama.cpp-style v1 endpoints.
    openai_chat_payload = {
        "model": current_model,
        "messages": _to_openai_messages(messages),
        "temperature": 0.2,
        "stream": False
    }
    try:
        response = requests.post(v1_chat_url, json=openai_chat_payload, timeout=300)
        response.raise_for_status()
        text = _extract_model_text(response.json())
        if text.strip():
            return text
    except Exception:
        pass

    # 2) Fallback to generate endpoint style.
    generate_payload = {
        "model": current_model,
        "prompt": _build_generate_prompt(prompt, system_prompt, history=effective_history),
        "stream": False,
        "options": {
            "temperature": 0.2
        }
    }
    if images:
        generate_payload["images"] = images

    generate_url = f"{base_url}/api/generate"

    response = requests.post(generate_url, json=generate_payload, timeout=300)
    response.raise_for_status()
    text = _extract_model_text(response.json())
    return text


def summarise_with_model(summary_prompt: str) -> str:
    """Generate a compact summary using the active model."""
    summary_system_prompt = (
        "You are a memory compression assistant. "
        "Return concise, factual summaries only."
    )
    text = ask_ollama(summary_prompt, summary_system_prompt, history=None, images=None)
    return clean_response(text) or "Summary unavailable."


# =========================
# BOT EVENTS
# =========================
@client.event
async def on_ready():
    print(f"Logged in as {client.user}")


@client.event
async def on_message(message):
    global current_model
    global disabled_channels

    if message.author == client.user:
        return

    content = message.content.strip()
    channel_name = normalize_channel_name(getattr(message.channel, "name", ""))

    # =========================
    # STATUS
    # =========================
    if content == "!status":
        ai_enabled = "No" if channel_name in disabled_channels else "Yes"
        channel_list = ", ".join(sorted(disabled_channels)) or "None"

        await message.channel.send(
            f"Model: {current_model}\n"
            f"Bot: Online\n"
            f"Current Channel: {channel_name}\n"
            f"AI Enabled: {ai_enabled}\n"
            f"Disabled Channels: {channel_list}"
        )
        return

    # =========================
    # SWITCH MODEL
    # =========================
    if content.startswith("!switch"):
        new_model = content[len("!switch"):].strip()

        if not new_model:
            await message.channel.send("Usage: !switch <model_name>")
            return

        current_model = new_model
        await message.channel.send(f"Switched model to: `{current_model}`")
        return

    # =========================
    # DISABLE CHANNEL
    # =========================
    if content.startswith("!removechn"):
        channel_arg = content[len("!removechn"):].strip()
        target_channel = normalize_channel_name(channel_arg) if channel_arg else channel_name

        disabled_channels.add(target_channel)
        save_disabled_channels(disabled_channels)

        await message.channel.send(f"Channel `{target_channel}` disabled for AI.")
        return

    # =========================
    # ENABLE CHANNEL
    # =========================
    if content.startswith("!addchn"):
        channel_arg = content[len("!addchn"):].strip()
        target_channel = normalize_channel_name(channel_arg) if channel_arg else channel_name

        if target_channel in disabled_channels:
            disabled_channels.remove(target_channel)
            save_disabled_channels(disabled_channels)

        await message.channel.send(f"Channel `{target_channel}` enabled for AI.")
        return

    # =========================
    # AI TRIGGER
    # =========================
    if channel_name in disabled_channels:
        return

    if content.startswith("!"):
        return

    prompt = content
    if not prompt and not message.attachments:
        return

    # Load recent messages before saving current prompt to avoid duplicate context.
    history_limit = 3 if message.attachments else 10
    history = load_recent_messages(channel_name, limit=history_limit)

    base_system_prompt = get_channel_mode(channel_name)
    if message.attachments:
        # Keep image turns focused on the image request.
        system_prompt = base_system_prompt
    else:
        memory_context = build_memory_context(channel_name, history)
        system_prompt = (
            f"{base_system_prompt}\n\n"
            f"Use the memory context below as background:\n{memory_context}"
        )

    save_message(channel_name, "user", prompt)

    images = []

    if message.attachments:
        for file in message.attachments:
            if file.filename.lower().endswith((".png", ".jpg", ".jpeg", ".webp")):
                try:
                    img_b64 = download_image_as_base64(file.url)
                    images.append(img_b64)
                except Exception as e:
                    await message.channel.send(f"Failed to process image: {str(e)}")

    try:
        async with message.channel.typing():
            answer = ask_ollama(
                prompt,
                system_prompt,
                history=history,
                images=images
            )

        answer = clean_response(answer)
        
        if not answer:
            await message.channel.send("(No valid response generated)")
            return
        
        save_message(channel_name, "assistant", answer)

        # Summarize in 100-message batches for long-term memory.
        try:
            check_and_summarise(channel_name, summarise_with_model)
        except Exception as summary_error:
            print(f"[SUMMARY ERROR] {summary_error}")

        if len(answer) > 1800:
            answer = answer[:1800] + "\n\n[truncated]"

        await message.channel.send(answer)

    except Exception as e:
        await message.channel.send(f"Error: {str(e)}")


client.run(TOKEN)