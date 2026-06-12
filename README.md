# OpenClaw Discord Bot

OpenClaw Discord Bot is a local-first Discord assistant powered by Ollama.
It supports both text and image workflows, channel-aware behavior, and runtime model switching.

Pipeline:
Discord -> Python Bot -> Ollama -> Local Model -> Discord response.

## What is new?

- Multimodal support for image attachments in `!ai` prompts
- Default single-model setup with `maxwellb/gemma4-12b-it-oym`
- Improved Ollama request flow for both text-only and image-enabled prompts
- Channel-based system prompting via `channel_modes.py`
- Better support for vision-capable workflows using a single model

## Features

- Chat with local Ollama models directly from Discord
- Send images with your prompt for vision-capable models
- Use one default model across channels to avoid frequent switching
- Channel-specific assistant behavior (`general`, `personal`, `code`, `bot-test`)
- Simple command interface: `!status`, `!switch`, `!addchn`, `!removechn`
- Lightweight Python implementation

## Architecture

```text
Discord Message
  |
  v
Python Discord Bot (discord.py)
  |
  |-- Channel enabled check (assets/enabled_channels.json)
  |-- Channel mode -> system prompt (channel_modes.py)
  |-- Save/load recent messages (Postgres via db.py)
  |-- Optional image attachment -> base64
  v
Ollama Generate API (http://localhost:11434/api/generate)
  |
  v
Configured Model (OLLAMA_MODEL / !switch)
  |
  v
Discord Response
```

## Requirements

- Python 3.10+
- Ollama installed and running locally
- Discord bot token
- The target model pulled in Ollama

Recommended model:

```bash
ollama pull maxwellb/gemma4-12b-it-oym
```

You can still use any compatible model name available in your local Ollama setup.

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
OLLAMA_MODEL=maxwellb/gemma4-12b-it-oym
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

Switches the active model at runtime.

Example:

```text
!switch maxwellb/gemma4-12b-it-oym
```

If needed, switch to another model later:

```text
!switch another-model-name
```

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

- Ollama endpoint is fixed to `http://localhost:11434/api/generate`
- Responses are non-streaming (`stream: false`)
- Large responses are truncated before Discord send
- Model choice is in-memory for the current bot process

## Current limitations

- No persistent conversation memory
- No slash commands yet
- No built-in model validation on `!switch` (errors come from Ollama response)
- Bot and Ollama are expected to run on the same machine

## Troubleshooting

If `!ai` fails:

- Confirm Ollama is running: `ollama list`
- Confirm selected model exists locally
- Check Discord bot token in `.env`
- Check terminal logs for request errors or timeout issues
