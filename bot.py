import os
import base64
import json
import requests
import discord

from dotenv import load_dotenv
from channel_modes import get_channel_mode
from db import save_message, load_recent_messages, ensure_channel
from memory_manager import check_and_summarise, build_memory_context
from llm import ask_model, clean_response, summarise_with_model

load_dotenv()

TOKEN = os.getenv("DISCORD_TOKEN")

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
# BOT EVENTS
# =========================
@client.event
async def on_ready():
    print(f"Logged in as {client.user}")


@client.event
async def on_message(message):
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
            f"Bot: Online\n"
            f"Current Channel: {channel_name}\n"
            f"AI Enabled: {ai_enabled}\n"
            f"Disabled Channels: {channel_list}"
        )
        return

    # model switching removed; gateway determines model

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

        try:
            ensure_channel(target_channel)
        except Exception as e:
            await message.channel.send(f"Channel enabled, but DB channel sync failed: {str(e)}")
            return

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
            answer = ask_model(
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