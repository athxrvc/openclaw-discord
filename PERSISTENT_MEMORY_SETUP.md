
## Persistent Memory Setup

This project uses PostgreSQL + Prisma-backed tables to persist chat history and long-term summaries per Discord channel.

## What Is Included

- PostgreSQL connection support through `DATABASE_URL` or fallback `DB_*` environment variables
- Prisma schema for `Channel`, `Message`, and `Summary`
- Centralized SQL access in `db.py`
- Summary pipeline orchestration in `memory_manager.py`
- LLM request/cleanup module in `llm.py`
- Channel-aware recent-history loading before model calls
- Long-term summary generation in 100-message unsummarized batches

## Current File Responsibilities

- `bot.py`: Discord events/commands and runtime flow orchestration
- `db.py`: all message + summary database reads/writes
- `memory_manager.py`: summary prompt building and summarization control flow
 - `llm.py`: model calls (`ask_model`) and response cleanup
- `prisma/prisma/schema.prisma`: persistent model definitions
- `prisma/prisma.config.ts`: Prisma config that reads the root `.env`
- `prisma/package.json`: Prisma scripts (`validate`, `generate`, `db:push`)

## Data Model

### `Message`

- `id`: auto-increment primary key
- `channelCode`: stable channel lookup code
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

### `Channel`

- `id`: auto-increment primary key
- `code`: generated unique code used by `Message` and `Summary`
- `name`: normalized Discord channel name
- `createdAt`: insert timestamp

## Runtime Behavior

When a message is sent in an AI-enabled channel:

1. The bot normalizes channel name and checks whether AI is enabled.
2. It loads recent channel messages from `Message` (text chats use larger history than image chats).
3. For text chats, `memory_manager.py` builds memory context using recent summaries + recent messages.
4. The user message is stored in `Message`.
5. The model is called through `llm.py` and the response is cleaned.
6. The assistant response is stored in `Message`.
7. Summarization check runs; each new 100-message unsummarized window is compressed into a `Summary` row.

## Notes

- Model selection is handled by the configured Google AI Studio model; the bot does not switch models at runtime.
- No gateway setup is required; configure `GOOGLE_API_KEY` (or `GOOGLE_AI_STUDIO_API_KEY`) in your `.env` instead.
- Persistent memory is channel-scoped through `channelCode`, with names resolved through the `Channel` table.
