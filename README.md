# OpenClaw Discord Bot

OpenClaw Discord Bot is a local-first Discord assistant that sends inference requests to a configured model gateway.
It supports text and image workflows, channel-aware behavior, and persistent conversation memory. Later to be integrated with OpenClaw

Pipeline:
Discord -> Python Bot -> Model Gateway -> Model -> PostgreSQL Database -> Discord response.

## Project Overview

- Designed for Discord communities that want a self-hosted AI assistant.
- Runs inference through a local or remote model gateway configured via environment variables.
- Maintains short-term context and long-term memory per channel.
- Supports both conversational and image-based prompting.

## Core Capabilities

- Chat with local or remote models via the configured gateway
- Image understanding for common image formats
-- Gateway-selected model (no runtime switching from the bot)
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
Model Gateway
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
3. The bot sends the request to the configured model gateway.
4. The response is cleaned and posted back to Discord.
5. Messages are persisted and periodically summarized.

For image requests, the bot prioritizes visual fidelity and avoids speculative answers when details are unclear.

## User Commands

- `!status`: Shows online state and AI channel state
- `!addchn <channel_name>`: Enables AI for a channel
- `!removechn <channel_name>`: Disables AI for a channel

**Gateway Setup**

- **Env var:** set `API_GATEWAY_URL` to your gateway endpoint (e.g. `https://your-gateway.example/v1`). The bot reads this at runtime.
- **Local gateway:** if you want a local inference gateway (LiteLLM) and an externally reachable URL, follow the LiteLLM + Cloudflare Tunnel guide in this repo: https://github.com/athxrvc/LiteLLM-setup

- `!addchn <channel_name>`: Enables AI for a channel
- `!removechn <channel_name>`: Disables AI for a channel

## Memory Model

- Short-term memory: recent message history per channel
- Long-term memory: compressed summaries of prior channel conversations
- Summaries are generated in fixed-size unsummarized batches


