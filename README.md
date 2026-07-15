# OpenClaw Discord Bot

OpenClaw Discord Bot is a local-first Discord assistant that sends inference requests to Google AI Studio.
It supports text and image workflows, channel-aware behavior, and persistent conversation memory. Later to be integrated with OpenClaw

Pipeline:
Discord -> Python Bot -> Google AI Studio -> PostgreSQL Database -> Discord response.

## Project Overview

- Designed for Discord communities that want a self-hosted AI assistant.
- Runs inference through Google AI Studio using a simple API key from the environment.
- Maintains short-term context and long-term memory per channel.
- Supports both conversational and image-based prompting.

## Core Capabilities

- Chat with Gemini models via Google AI Studio
- Image understanding for common image formats
-- Model selected via the configured Google model setting (no runtime switching from the bot)
- Channel-level AI enable/disable controls
- Channel-specific assistant behavior modes
- Persistent message history in PostgreSQL
- Long-term memory summaries generated in batches

## Architecture

```text
Discord Message
  |
  v
Bot Runtime
  |
  |-- Channel behavior routing
  |-- Load context and summaries from PostgreSQL
  |-- Optional image attachment processing
  v
Google AI Studio
  |
  v
Configured Model
  |
  v
Bot Runtime
  |
  |-- Save user/assistant messages to PostgreSQL
  |-- Periodically save long-term summaries
  v
PostgreSQL Database
  |
  v
Discord Response
```

## How It Behaves

When users send messages in AI-enabled channels:

1. Recent channel context is loaded.
2. Long-term summary memory is injected for text conversations.
3. The bot sends the request to Google AI Studio.
4. The response is cleaned and posted back to Discord.
5. Messages are persisted and periodically summarized.

For image requests, the bot prioritizes visual fidelity and avoids speculative answers when details are unclear.

## User Commands

- `!status`: Shows online state and AI channel state
- `!addchn <channel_name>`: Enables AI for a channel
- `!removechn <channel_name>`: Disables AI for a channel

**Model Setup**

- **Google AI Studio:** set `GOOGLE_API_KEY` (or `GOOGLE_AI_STUDIO_API_KEY`) and optionally `GOOGLE_MODEL` in your `.env` to use Gemini directly.
- The bot uses Google AI Studio only; no gateway or local proxy is required.

- `!addchn <channel_name>`: Enables AI for a channel
- `!removechn <channel_name>`: Disables AI for a channel

## Memory Model

- Short-term memory: recent message history per channel
- Long-term memory: compressed summaries of prior channel conversations
- Summaries are generated in fixed-size unsummarized batches


