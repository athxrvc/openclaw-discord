import os
import requests
import discord

from dotenv import load_dotenv

load_dotenv()

TOKEN = os.getenv("DISCORD_TOKEN")
MODEL = os.getenv("OLLAMA_MODEL")

intents = discord.Intents.default()
intents.message_content = True

client = discord.Client(intents=intents)

OLLAMA_URL = "http://localhost:11434/api/generate"


def ask_ollama(prompt):
    response = requests.post(
        OLLAMA_URL,
        json={
            "model": MODEL,
            "prompt": prompt,
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

    if not message.content.startswith("!ai"):
        return

    prompt = message.content[3:].strip()

    if not prompt:
        await message.channel.send(
            "Usage: !ai <question>"
        )
        return

    await message.channel.typing()

    try:
        answer = ask_ollama(prompt)

        if len(answer) > 1900:
            answer = answer[:1900] + "\n\n[truncated]"

        await message.channel.send(answer)

    except Exception as e:
        await message.channel.send(
            f"Error: {str(e)}"
        )


client.run(TOKEN)