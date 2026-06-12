# OpenClaw Discord Bot

OpenClaw Discord Bot v2 is a local-first Discord assistant powered by llama.cpp.
It supports text workflows, channel-aware behavior, and runtime model switching.

Pipeline:
Discord -> Python Bot -> llama_server -> Local Model -> Discord response.

## What is new?

- Migrated from Ollama to llama.cpp for improved performance
- Uses OpenAI-compatible completions API (llama_server)
- Model downloaded and loaded directly with llama.cpp
- Channel-based system prompting via `channel_modes.py`
- Lightweight and resource-efficient local inference

## Features

- Chat with local llama.cpp models directly from Discord
- Use one default model across channels
- Channel-specific assistant behavior (`general`, `personal`, `code`, `bot-test`)
- Simple command interface: `!status`, `!switch`, `!addchn`, `!removechn`
- Lightweight Python implementation with fast local inference

## Architecture

```text
Discord Message
  |
  v
Python Discord Bot (discord.py)
  |
  |-- Channel mode -> system prompt
  v
llama_server OpenAI-compatible API (http://localhost:8080/v1/completions)
  |
  v
Active Model (local llama.cpp inference)
```

## Requirements

- Python 3.10+
- llama.cpp with llama_server running locally
- Discord bot token
- A model file (`.gguf`) downloaded and available to llama_server

Recommended setup:

Download a model and start llama_server:

```bash
lllama-cli -m path/to/model.gguf --server --port 8080
```

Or use llama_server directly:

```bash
llama-server -m path/to/model.gguf -c 2048
```

## Installation

1. Clone the repository:

```bash
git clone https://github.com/<your-username>/openclaw-discord.git
cd openclaw-discord
```

2. Install dependencies:

```bash
pip install -r requirements.txt
```

3. Create `.env` in the project root:

```env
DISCORD_TOKEN=your_discord_bot_token
LLAMA_MODEL=default
LLAMA_SERVER_URL=http://localhost:8080/v1/completions
```

## Run

```bash
python bot.py
```

## Commands

### AI messaging

In AI-enabled channels, normal messages are sent directly to the model.
You no longer need to prefix each message with `!ai`.

`!ai <prompt>` still works everywhere as an explicit one-off prompt.

If the message includes image attachments (`.png`, `.jpg`, `.jpeg`, `.webp`), the bot forwards them to Ollama for multimodal inference.

Example:

```text
!ai explain what is happening in this screenshot
```

### `!switch <model_name>`

Switches the active model identifier at runtime (requires llama_server restart with different model).

Example:

```text
!switch llama2
```

Note: Model switching only changes the identifier in the bot. The actual model loaded in llama_server must be restarted separately.

### `!addchn <channel_name>`

Enables auto-AI for the given channel name. After this, normal messages in that channel are treated as prompts.

Example:

```text
!addchn code
```

If no channel name is provided, the current channel is enabled.

### `!removechn <channel_name>`

Disables auto-AI for the given channel name. Messages in that channel will require `!ai` again.

Example:

```text
!removechn code
```

If no channel name is provided, the current channel is disabled.

### `!status`

Shows active model and bot online status.

## Channel Modes

System behavior is selected by Discord channel name using `channel_modes.py`.

Default modes in this repo:

- `general`: concise general assistant
- `personal`: productivity/planning tone
- `code`: senior engineering assistant tone
- `bot-test`: verbose testing/debug behavior

Unknown channel names fall back to `general`.

## Notes

- llama_server endpoint is `http://localhost:8080/v1/completions` (OpenAI-compatible)
- Responses are non-streaming (`stream: false`)
- Large responses are truncated before Discord send
- Model choice is in-memory for the current bot process
- llama_server model is loaded at startup and persists until server restart

## Current limitations

- No persistent conversation memory
- No slash commands yet
- No built-in model validation on `!switch` (errors come from Ollama response)
- Bot and Ollama are expected to run on the same machine

## Troubleshooting

If `!ai` fails:

- Confirm llama_server is running on port 8080: `curl http://localhost:8080/v1/models`
- Confirm the model is loaded in llama_server
- Check Discord bot token in `.env`
- Check terminal logs for request errors or timeout issues
- Ensure `LLAMA_SERVER_URL` matches your llama_server configuration
