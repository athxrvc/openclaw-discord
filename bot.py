import os
import base64
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

    # add vision support
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

    if message.author == client.user:
        return

    content = message.content.strip()

    # =========================
    # STATUS
    # =========================
    if content == "!status":
        await message.channel.send(
            f"Model: {current_model}\nBot: Online"
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
    # AI COMMAND
    # =========================
    if not content.startswith("!ai"):
        return

    prompt = content[len("!ai"):].strip()

    if not prompt:
        await message.channel.send("Usage: !ai <question>")
        return

    # =========================
    # CHANNEL SYSTEM PROMPT
    # =========================
    channel_name = message.channel.name
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