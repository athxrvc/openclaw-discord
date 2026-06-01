import os
import requests
import discord

from dotenv import load_dotenv
from channel_modes import get_channel_mode

load_dotenv()

TOKEN = os.getenv("DISCORD_TOKEN")
MODEL = os.getenv("OLLAMA_MODEL")

intents = discord.Intents.default()
intents.message_content = True

client = discord.Client(intents=intents)

OLLAMA_URL = "http://localhost:11434/api/generate"


def ask_ollama(prompt, system_prompt):
    full_prompt = f"""System:
{system_prompt}

User:
{prompt}

Assistant:
"""

    response = requests.post(
        OLLAMA_URL,
        json={
            "model": MODEL,
            "prompt": full_prompt,
            "stream": False
        },
        timeout=300
    )

    response.raise_for_status()
    return response.json()["response"]


@client.event
async def on_ready():
    print(f"Logged in as {client.user}")


@client.event
async def on_message(message):
    if message.author == client.user:
        return

    content = message.content.strip()

    # STATUS COMMAND
    if content == "!status":
        await message.channel.send(
            f"Model: {MODEL}\nBot: Online"
        )
        return

    # AI COMMAND ONLY
    if not content.startswith("!ai"):
        return

    prompt = content[len("!ai"):].strip()

    if not prompt:
        await message.channel.send("Usage: !ai <question>")
        return

    channel_name = message.channel.name
    system_prompt = get_channel_mode(channel_name)

    try:
        async with message.channel.typing():
            answer = ask_ollama(prompt, system_prompt)

        if len(answer) > 1800:
            answer = answer[:1800] + "\n\n[truncated]"

        await message.channel.send(answer)

    except Exception as e:
        await message.channel.send(f"Error: {str(e)}")


client.run(TOKEN)