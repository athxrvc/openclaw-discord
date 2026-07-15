# OpenClaw Discord Bot

OpenClaw Discord Bot is a local-first Discord assistant with **multi-provider LLM support** (Google AI Studio, OpenAI, and Anthropic), channel-aware behavior, and persistent conversation memory in PostgreSQL. It is being evolved into the messaging layer of the broader OpenClaw project.

Pipeline:

```
Discord → Python Bot → Configured LLM Provider → PostgreSQL Database → Discord response
```

## Project Overview

- Designed for Discord communities that want a self-hosted AI assistant.
- Runs inference through Google AI Studio, OpenAI, or Anthropic using simple API keys from the environment.
- Maintains short-term context (recent messages) and long-term memory (summaries) per channel.
- Supports both conversational and image-based prompting on the Google provider; OpenAI/Anthropic are text-only.
- Channel-level AI enable/disable controls with persistent on-disk state.
- Channel-specific assistant behavior modes (general, personal, code, bot-test).

## Core Capabilities

- Chat with Gemini (Google AI Studio), GPT-class (OpenAI), or Claude (Anthropic) models
- Automatic provider detection from available API keys, with explicit `AI_PROVIDER` override
- Image understanding for common formats (`.png`, `.jpg`, `.jpeg`, `.webp`) via the Google provider
- Channel-level AI enable/disable controls (`!addchn`, `!removechn`)
- Channel-specific assistant behavior modes via `channel_modes.py`
- Persistent message history in PostgreSQL (`Message` table)
- Long-term memory: 100-message unsummarized batch summaries (`Summary` table)

## Architecture

```
Discord Message
   |
   v
Bot Runtime (bot.py)
   |
   |-- normalize_channel_name + disabled_channels lookup
   |-- Channel behavior routing (channel_modes.py)
   |-- ensure_channel in DB (db.py)
   |-- Load recent context from PostgreSQL (db.py)
   |-- Optional image attachment processing (download_image_as_base64)
   v
llm.py  ──►  ask_model
   |
   |-- AI_PROVIDER explicit, else auto-detect (openai > anthropic > google)
   |-- Google AI Studio  (image-capable, multi-turn via systemInstruction + contents)
   |-- OpenAI Chat Completions  (text-only)
   |-- Anthropic completions  (text-only)
   v
Configured Model
   |
   v
Bot Runtime
   |
   |-- save_message (user + assistant) to PostgreSQL
   |-- check_and_summarise (memory_manager.py) — writes a new Summary when both gates pass (count >= 100 and next 100-message window is full)
   |-- clean_response (strip markers/URLs/whitespace) and Discord send
   v
PostgreSQL Database
   |
   v
Discord Response
```

## How It Behaves

When a user sends a message in an AI-enabled channel:

1. The channel name is normalized (lowercased, leading `#` stripped).
2. Recent channel messages are loaded from `Message` — 10 messages for text chats, 3 for image chats.
3. The channel-specific system prompt is loaded via `get_channel_mode(channel_name)`.
4. For text chats, `build_memory_context` injects the last 10 long-term summaries plus recent turns.
5. The user message is stored in `Message`.
6. If images are attached, each image is downloaded and base64-encoded for the Google provider.
7. `ask_model` calls the active provider and returns a response.
8. `clean_response` strips internal markers (`<tag>`), URLs, and excess whitespace.
9. The assistant response is stored in `Message`.
10. `check_and_summarise` runs each assistant turn and, via `summarise_with_model`, writes a new `Summary` row only when both gates pass: total channel message count ≥ 100 AND the next unsummarized window holds ≥ 100 messages.
11. The response is sent back to Discord (truncated at 1800 chars with `[truncated]` marker).

## User Commands

- `!status` — shows online state, current channel, AI-enabled state, and the list of disabled channels.
- `!addchn <channel_name>` — enables AI for a channel (also creates/ensures a `Channel` row in the DB). Defaults to the current channel if no name is given.
- `!removechn <channel_name>` — disables AI for a channel. Defaults to the current channel if no name is given.
- Any other `!`-prefixed message is silently ignored (the bot only responds to the commands listed above).

Disabled-channel state is persisted to `assets/enabled_channels.json` (sorted JSON list). The `assets/` directory is created on demand.

## LLM Providers & Configuration

The bot supports three providers. Detection precedence in `ask_model`:

1. If `AI_PROVIDER` is set (`google`, `openai`, or `anthropic`), it is honored.
2. Otherwise the first available key wins: `OPENAI_API_KEY` → `ANTHROPIC_API_KEY` → `GOOGLE_API_KEY` / `GOOGLE_AI_STUDIO_API_KEY`.
3. If no provider can be resolved, a clear `RuntimeError` is raised at startup.

### Google AI Studio (default, image-capable)

```
GOOGLE_API_KEY=...              # or GOOGLE_AI_STUDIO_API_KEY
GOOGLE_MODEL=gemini-2.5-flash   # any model that is enabled for your project
```

The Google provider uses `https://generativelanguage.googleapis.com/v1beta/models/{MODEL}:generateContent`,
supports `systemInstruction`, multi-turn `contents`, and multipart image payloads.

### OpenAI (text-only)

```
OPENAI_API_KEY=sk-...
OPENAI_MODEL=gpt-3.5-turbo      # any chat-completions model
AI_PROVIDER=openai              # optional, but recommended when multiple keys are present
```

The OpenAI provider uses Chat Completions at `https://api.openai.com/v1/chat/completions`.

### Anthropic (text-only)

```
ANTHROPIC_API_KEY=sk-ant-...
ANTHROPIC_MODEL=claude-2       # or another Claude model identifier
AI_PROVIDER=anthropic          # optional
```

The Anthropic provider uses the completions endpoint at `https://api.anthropic.com/v1/complete`.

> Note: image understanding is currently only implemented for the Google provider. Selecting `openai` or `anthropic` while attaching an image will produce a text-only response.

## Memory Model

- **Short-term memory:** the most recent messages per channel loaded from `Message` before each LLM call (10 for text chats, 3 for image chats).
- **Long-term memory:** compressed summaries in `Summary`, built by `memory_manager.py`.
- Summaries are generated in fixed-size unsummarized batches of **100 messages** (`SUMMARY_THRESHOLD = 100`).
- On each triggered summarization, the latest summary's `endMessageId + 1` is used as the new starting point, the next 100 messages are compressed, and a new `Summary` row is inserted.
- Up to 10 most recent summaries are injected into the text-chat system prompt per turn.

## File Responsibilities

- `bot.py` — Discord events/commands and runtime flow orchestration; loads disabled-channel state on startup.
- `llm.py` — multi-provider `ask_model`, image/history payload building, `clean_response`, and `summarise_with_model`.
- `db.py` — all message + summary database reads/writes; auto-creates schema; auto-resolves `channelCode` per channel.
- `memory_manager.py` — summary prompt building, threshold check, and context assembly.
- `channel_modes.py` — channel-name → system-prompt lookup with `general` as the default mode for any name not in the table.
- `prisma/prisma/schema.prisma` — persistent model definitions (`Channel`, `Message`, `Summary`).
- `prisma/prisma.config.ts` — Prisma config that reads the root `.env` and builds the datasource URL.
- `prisma/package.json` — Prisma scripts (`validate`, `generate`, `db:push`).
- `terraform/` — Cloud SQL (Postgres 16) provisioning for the database backend.
