## Persistent Memory Setup

This project uses PostgreSQL + Prisma-backed tables to persist chat history and long-term summaries per Discord channel. Migrations/mirroring of the schema are managed via the local `prisma/` tooling, while runtime reads/writes go through `db.py` (psycopg2) so the bot does not depend on a generated Prisma client at runtime.

## What Is Included

- PostgreSQL connection support through `DATABASE_URL` or fallback `DB_*` environment variables
- Prisma schema for `Channel`, `Message`, and `Summary`
- Runtime schema bootstrap in `db.py` (idempotent CREATE/ALTER/INDEX statements)
- Legacy `channelName` → `channelCode` backfill for older deployments
- Centralized SQL access in `db.py`
- Summary pipeline orchestration in `memory_manager.py`
- LLM request/cleanup module in `llm.py` (multi-provider)
- Channel-aware recent-history loading before model calls
- Long-term summary generation in 100-message unsummarized batches

## Current File Responsibilities

- `bot.py` — Discord events/commands and runtime flow orchestration; loads/saves the disabled-channel set (`assets/enabled_channels.json`).
- `db.py` — all message + summary database reads/writes, schema bootstrap, `channelCode` resolution, and legacy column backfill.
- `memory_manager.py` — summary prompt building, summarization threshold check, and long-term + recent context assembly.
- `llm.py` — multi-provider `ask_model` (Google / OpenAI / Anthropic), response cleanup, and `summarise_with_model`.
- `channel_modes.py` — channel-name → system-prompt lookup (`general` is the default mode).
- `prisma/prisma/schema.prisma` — persistent model definitions.
- `prisma/prisma.config.ts` — Prisma config that reads the root `.env` and builds the datasource URL.
- `prisma/package.json` — Prisma scripts (`validate`, `generate`, `db:push`).
- `terraform/` — provisions the Cloud SQL Postgres 16 instance, database, and user.

## Data Model

### `Channel`

- `id`: auto-increment primary key
- `code`: short stable code (`chn_<10 hex chars>`) used by `Message` and `Summary` for lookups
- `name`: normalized Discord channel name (lowercased, leading `#` stripped)
- `createdAt`: insert timestamp

### `Message`

- `id`: auto-increment primary key
- `channelCode`: stable channel lookup code (FK-style reference to `Channel.code`)
- `role`: `user` or `assistant`
- `content`: message text
- `createdAt`: insert timestamp

### `Summary`

- `id`: auto-increment primary key
- `channelCode`: stable channel lookup code
- `summary`: compressed long-term memory text
- `startMessageId`: first message id included in this summary batch
- `endMessageId`: last message id included in this summary batch
- `createdAt`: insert timestamp

## Schema Bootstrap

`db.py` runs an idempotent schema bootstrap on its first connection per process:

1. Creates `Channel` if missing.
2. Adds `channelCode` columns on `Message` and `Summary` if missing.
3. Creates `idx_message_channel_code` and `idx_summary_channel_code`.
4. If a legacy `channelName` column exists on `Message` or `Summary`, it iterates the distinct names, ensures a `Channel` row, and backfills `channelCode`.

This allows newer deployments to drop `channelName` entirely while still being able to migrate older ones in place.

## `channelCode` Resolution

Every public read/write in `db.py` resolves a `channel_code` from the human-readable channel name through `_get_or_create_channel_code`:

1. Look up by `name` — return existing `code` if found.
2. Otherwise, generate a new `chn_<sha1[:10]>` `code`, retrying up to 100 times if the generated code collides with another channel.
3. Insert with `ON CONFLICT (name) DO UPDATE` and return the resulting `code`.

This avoids hot-path full-table reads and lets the bot upgrade legacy name-based rows transparently.

## Runtime Behavior

When a message is sent in an AI-enabled channel:

1. The bot normalizes the channel name and checks the disabled-channel set; disabled channels (and any message starting with `!`) are skipped.
2. The bot loads recent channel messages from `Message` (10 messages for text chats, 3 for image chats).
3. The channel-specific system prompt is loaded via `get_channel_mode(channel_name)`.
4. For text chats, `memory_manager.build_memory_context` assembles the long-term summaries (up to 10) and recent messages into a `LONG-TERM MEMORY (Summaries)` / `RECENT CONVERSATION` block.
5. The user message is stored in `Message` (`save_message`).
6. If image attachments are present, each one is downloaded and base64-encoded (Google provider only).
7. `llm.ask_model` is called via the resolved provider (Google / OpenAI / Anthropic) with the assembled system prompt, history, and images.
8. The response is cleaned (`clean_response` strips internal `<tag>` markers, URLs, and excess whitespace) and posted back to Discord (truncated at 1800 chars with `[truncated]`).
9. The assistant response is stored in `Message`.
10. `memory_manager.check_and_summarise` runs and, if at least 100 new unsummarized messages have accumulated, compresses them via `llm.summarise_with_model` and inserts a `Summary` row covering the batch.

## Summary Pipeline

- Threshold: `SUMMARY_THRESHOLD = 100` messages (`memory_manager.py`).
- Trigger: `check_and_summarise(channel_name, summarise_with_model)` once per assistant turn.
- Two-gate condition: the function first requires total message count for the channel `>= 100`, then fetches up to 100 unsummarized messages; a new summary is written only when at least 100 unsummarized messages are available in the window.
- Window selection: the next batch starts at `latest_summary.endMessageId + 1` (or from message id 1 if no prior summary exists).
- Output storage: `(channelCode, summary, startMessageId, endMessageId)` row in `Summary`.
- Errors: summary failures are logged (`[SUMMARY ERROR]`) and never crash the bot's response path.

## Provider Notes for Memory

- `summarise_with_model` calls the same `llm.ask_model` path as the chat flow, so it inherits whichever provider/configuration is active.
- For Google, image-related history, system instruction, and summarization calls all use the same model and key.
- OpenAI and Anthropic paths do not currently pass images through; memory and summary behavior are otherwise identical to the Google path.

## Required Environment Variables

At minimum, set:

- `DISCORD_TOKEN` — Discord bot token.
- A database connection: `DATABASE_URL` (preferred) **or** `DB_HOST` + `DB_NAME` + `DB_USER` + `DB_PASSWORD` (+ optional `DB_PORT`, `DB_SSLMODE`).
- At least one provider key, optionally overridden by `AI_PROVIDER`:
  - Google: `GOOGLE_API_KEY` (or `GOOGLE_AI_STUDIO_API_KEY`) and `GOOGLE_MODEL`.
  - OpenAI: `OPENAI_API_KEY` and `OPENAI_MODEL`.
  - Anthropic: `ANTHROPIC_API_KEY` and `ANTHROPIC_MODEL`.
  - Optional: `AI_PROVIDER` ∈ {`google`, `openai`, `anthropic`} to force a specific provider when multiple keys are present.

## Notes

- Model selection is controlled entirely through environment variables; there is no runtime model switching command.
- The bot does not depend on the Prisma generated client at runtime. `prisma/` exists for schema validation, generation, and `db push` workflows.
- Persistent memory is channel-scoped through `channelCode`, with names resolved through the `Channel` table.
- The disabled-channel set (`assets/enabled_channels.json`) lives outside the database by design, so AI can be toggled without touching Postgres.
