# OpenClaw Discord Bot (v1)

A simple Discord bot that connects to a local Ollama model (Qwen 2.5 Coder 14B) and allows you to chat with it using `!ai`.

This is **v1**, focused on getting a working end-to-end pipeline:
Discord -> Python Bot -> Ollama -> Local LLM -> Discord response.

---

## Features (v1)

- Chat with a local LLM from Discord
- Uses Ollama as the inference backend
- Lightweight Python bot (no heavy frameworks)
- Basic commands (`!ai`, `!status`)
- Runs locally on your machine

---

## Architecture

```text
Discord
	|
	v
Python Discord Bot
	|
	v
Ollama API (http://localhost:11434)
	|
	v
Qwen2.5-Coder:14B (local model)
```

---

## Requirements

- Python 3.10+
- Ollama installed
- Model downloaded:

	```bash
	ollama run qwen2.5-coder:14b
	```

- Discord bot token

---

## Installation

### 1. Clone repo

```bash
git clone https://github.com//openclaw-discord.git
cd openclaw-discord
```

### 2. Install dependencies

```bash
pip install -r requirements.txt
```

### 3. Create `.env`

```env
DISCORD_TOKEN=your_discord_bot_token
OLLAMA_MODEL=qwen2.5-coder:14b
```

## Run the bot

```bash
python bot.py
```

## Usage

### Ask the AI

```text
!ai explain recursion in simple terms
```

### Check bot status

```text
!status
```

## Notes

- Ollama must be running locally
- Bot must run on the same machine as Ollama (v1 setup)
- Responses are not streamed (single response only)
- No memory system yet (stateless)

## Limitations (v1)

- No conversation memory
- No OpenClaw tool execution yet
- No slash commands
- No remote access (PC must stay on)
