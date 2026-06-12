import os
import base64
import json
import requests
import discord

from dotenv import load_dotenv
from channel_modes import get_channel_mode
from db import get_connection

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
# DATABASE
# =========================
def save_message(channel, role, content):
    try:
        conn = get_connection()
        cur = conn.cursor()

        cur.execute(
            """
            INSERT INTO "Message" ("channelName", role, content)
            VALUES (%s, %s, %s)
            """,
            (channel, role, content),
        )

        conn.commit()
        conn.close()
    except Exception as e:
        print(f"[DB SAVE ERROR] {e}")


def load_recent_messages(channel, limit=100):
    try:
        conn = get_connection()
        cur = conn.cursor()

        cur.execute(
            """
            SELECT role, content
            FROM "Message"
            WHERE "channelName" = %s
            ORDER BY id DESC
            LIMIT %s
            """,
            (channel, limit),
        )

        rows = cur.fetchall()
        conn.close()

        return list(reversed(rows))
    except Exception as e:
        print(f"[DB LOAD ERROR] {e}")
        return []


# =========================
# OLLAMA CALL
# =========================
def ask_ollama(prompt, system_prompt, history=None, images=None):

    history_text = ""

    if history:
        history_text = "\n".join([f"{r[0]}: {r[1]}" for r in history])

    full_prompt = f"""System:
{system_prompt}

Conversation history:
{history_text}

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

    system_prompt = get_channel_mode(channel_name)

    save_message(channel_name, "user", prompt)

    history = load_recent_messages(channel_name, limit=100)

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

        save_message(channel_name, "assistant", answer)

        if len(answer) > 1800:
            answer = answer[:1800] + "\n\n[truncated]"

        await message.channel.send(answer)

    except Exception as e:
        await message.channel.send(f"Error: {str(e)}")


client.run(TOKEN)