
## What was added

- PostgreSQL connection support through `DATABASE_URL` or fallback `DB_*` environment variables
- Prisma schema for `Message` and `Summary`
- Bot-side message persistence in `bot.py`
- Recent-message history loading before each Ollama request
- Local Prisma tooling in `prisma/` for schema validation and database sync

## Files Added Or Changed

- `db.py`: shared PostgreSQL connection helper
- `bot.py`: saves user and assistant messages, loads recent channel history
- `prisma/prisma/schema.prisma`: defines persistent models
- `prisma/prisma.config.ts`: Prisma config that reads the root `.env`
- `prisma/package.json`: Prisma scripts for validate, generate, and db push

## Data Model

### `Message`

- `id`: auto-increment primary key
- `channelName`: normalized Discord channel name
- `role`: `user` or `assistant`
- `content`: message text
- `createdAt`: insert timestamp

### `Summary`

- `id`: auto-increment primary key
- `channelName`: normalized Discord channel name
- `summary`: summary text
- `startTime`: summary window start
- `endTime`: summary window end
- `createdAt`: insert timestamp

`Summary` is defined in the schema for future memory compaction, but currently writes only `Message` rows.


## Runtime Behavior

When a message is sent in an AI-enabled channel:

1. The bot stores the incoming user message in `Message`
2. The bot loads the most recent 20 rows for that channel
3. The recent history is appended into the Ollama prompt
4. The assistant response is stored back into `Message`

This means memory is currently scoped by channel and limited to a recent-message window, not long-term summarization.

## Current Limitations

- The bot stores raw recent messages, not condensed summaries
- `Summary` exists in the schema but is not yet written by the bot
- Message history is capped in memory loading logic, currently `limit=20`