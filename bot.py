import os
import base64
import json
import requests
import discord

from dotenv import load_dotenv
from channel_modes import get_channel_mode

load_dotenv()

TOKEN = os.getenv("DISCORD_TOKEN")
MODEL = os.getenv("OLLAMA_MODEL")

# default model
current_model = MODEL

intents = discord.Intents.default()
intents.message_content = True

client = discord.Client(intents=intents)

OLLAMA_URL = "http://localhost:11434/api/generate"
ENABLED_CHANNELS_FILE = os.path.join("assets", "enabled_channels.json")


def normalize_channel_name(channel_name: str) -> str:
    return channel_name.strip().lower().lstrip("#")


def load_enabled_channels() -> set[str]:
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


def save_enabled_channels(channels: set[str]) -> None:
    os.makedirs(os.path.dirname(ENABLED_CHANNELS_FILE), exist_ok=True)
    with open(ENABLED_CHANNELS_FILE, "w", encoding="utf-8") as f:
        json.dump(sorted(channels), f, indent=2)


enabled_channels = load_enabled_channels()


# =========================
# IMAGE HELPER
# =========================
def download_image_as_base64(url):
    response = requests.get(url)
    response.raise_for_status()
    return base64.b64encode(response.content).decode("utf-8")


# =========================
# OLLAMA CALL
# =========================
def ask_ollama(prompt, system_prompt, images=None):

    full_prompt = f"""System:
{system_prompt}

User:
{prompt}

Assistant:
"""

    payload = {
        "model": current_model,
        "prompt": full_prompt,
        "stream": False
    }

    if images:
        payload["images"] = images

    response = requests.post(
        OLLAMA_URL,
        json=payload,
        timeout=300
    )

    response.raise_for_status()
    return response.json()["response"]


@client.event
async def on_ready():
    print(f"Logged in as {client.user}")


@client.event
async def on_message(message):
    global current_model
    global enabled_channels

    if message.author == client.user:
        return

    content = message.content.strip()
    channel_name = normalize_channel_name(getattr(message.channel, "name", ""))

    # =========================
    # STATUS
    # =========================
    if content == "!status":
        ai_enabled = "Yes" if channel_name in enabled_channels else "No"

        channel_list = ", ".join(sorted(enabled_channels))
        if not channel_list:
            channel_list = "None"

        await message.channel.send(
            f"Model: {current_model}\n"
            f"Bot: Online\n"
            f"Current Channel: {channel_name}\n"
            f"AI Enabled: {ai_enabled}\n"
            f"AI Channels: {channel_list}"
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
    # ENABLE CHANNEL
    # =========================
    if content.startswith("!addchn"):
        channel_arg = content[len("!addchn"):].strip()
        target_channel = normalize_channel_name(channel_arg) if channel_arg else channel_name

        if target_channel in enabled_channels:
            await message.channel.send(f"Channel `{target_channel}` is already AI-enabled.")
            return

        enabled_channels.add(target_channel)
        save_enabled_channels(enabled_channels)

        await message.channel.send(f"Channel `{target_channel}` is now AI-enabled.")
        return

    # =========================
    # DISABLE CHANNEL
    # =========================
    if content.startswith("!removechn"):
        channel_arg = content[len("!removechn"):].strip()
        target_channel = normalize_channel_name(channel_arg) if channel_arg else channel_name

        if target_channel not in enabled_channels:
            await message.channel.send(f"Channel `{target_channel}` is not AI-enabled.")
            return

        enabled_channels.remove(target_channel)
        save_enabled_channels(enabled_channels)

        await message.channel.send(f"Channel `{target_channel}` is no longer AI-enabled.")
        return

    # =========================
    # AI MESSAGE (NO !ai ANYMORE)
    # =========================

    if channel_name not in enabled_channels:
        return

    # ignore bot commands
    if content.startswith("!"):
        return

    prompt = content

    if not prompt and not message.attachments:
        return

    # =========================
    # SYSTEM PROMPT
    # =========================
    system_prompt = get_channel_mode(channel_name)

    # =========================
    # IMAGE HANDLING
    # =========================
    images = []

    if message.attachments:
        for file in message.attachments:
            if file.filename.lower().endswith((".png", ".jpg", ".jpeg", ".webp")):
                try:
                    img_b64 = download_image_as_base64(file.url)
                    images.append(img_b64)
                except Exception as e:
                    await message.channel.send(f"Failed to process image: {str(e)}")

    # =========================
    # CALL MODEL
    # =========================
    try:
        async with message.channel.typing():
            answer = ask_ollama(prompt, system_prompt, images=images)

        if len(answer) > 1800:
            answer = answer[:1800] + "\n\n[truncated]"

        await message.channel.send(answer)

    except Exception as e:
        await message.channel.send(f"Error: {str(e)}")


client.run(TOKEN)