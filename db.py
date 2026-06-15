import os
import hashlib
import psycopg2


_schema_ready = False


def _build_channel_code(channel_name: str, extra: str = "") -> str:
    digest = hashlib.sha1(f"{channel_name}{extra}".encode("utf-8")).hexdigest()[:10]
    return f"chn_{digest}"


def get_connection():
    database_url = os.getenv("DATABASE_URL")
    if database_url:
        return psycopg2.connect(database_url)

    connection_settings = {
        "host": os.getenv("DB_HOST"),
        "database": os.getenv("DB_NAME"),
        "user": os.getenv("DB_USER"),
        "password": os.getenv("DB_PASSWORD"),
        "port": os.getenv("DB_PORT", "5432"),
    }

    sslmode = os.getenv("DB_SSLMODE")
    if sslmode:
        connection_settings["sslmode"] = sslmode

    return psycopg2.connect(**connection_settings)


def _ensure_schema(conn) -> None:
    global _schema_ready

    if _schema_ready:
        return

    cur = conn.cursor()

    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS "Channel" (
            id SERIAL PRIMARY KEY,
            code TEXT UNIQUE NOT NULL,
            name TEXT UNIQUE NOT NULL,
            "createdAt" TIMESTAMP DEFAULT NOW()
        )
        """
    )

    cur.execute('ALTER TABLE "Message" ADD COLUMN IF NOT EXISTS "channelCode" TEXT')
    cur.execute('ALTER TABLE "Summary" ADD COLUMN IF NOT EXISTS "channelCode" TEXT')

    cur.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_message_channel_code
        ON "Message" ("channelCode")
        """
    )
    cur.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_summary_channel_code
        ON "Summary" ("channelCode")
        """
    )

    # Legacy backfill for deployments that still have channelName columns.
    # Newer schemas have dropped these columns, so skip safely when absent.
    cur.execute(
        """
        SELECT EXISTS (
            SELECT 1 FROM information_schema.columns
            WHERE table_schema = 'public' AND table_name = 'Message' AND column_name = 'channelName'
        )
        """
    )
    message_has_channel_name = cur.fetchone()[0]

    cur.execute(
        """
        SELECT EXISTS (
            SELECT 1 FROM information_schema.columns
            WHERE table_schema = 'public' AND table_name = 'Summary' AND column_name = 'channelName'
        )
        """
    )
    summary_has_channel_name = cur.fetchone()[0]

    if message_has_channel_name or summary_has_channel_name:
        channel_rows = []

        if message_has_channel_name:
            cur.execute(
                """
                SELECT DISTINCT "channelName"
                FROM "Message"
                WHERE "channelName" IS NOT NULL
                """
            )
            channel_rows.extend([row[0] for row in cur.fetchall() if row and row[0]])

        if summary_has_channel_name:
            cur.execute(
                """
                SELECT DISTINCT "channelName"
                FROM "Summary"
                WHERE "channelName" IS NOT NULL
                """
            )
            channel_rows.extend([row[0] for row in cur.fetchall() if row and row[0]])

        for channel_name in set(channel_rows):
            _get_or_create_channel_code(conn, channel_name)

        if message_has_channel_name:
            cur.execute(
                """
                UPDATE "Message" m
                SET "channelCode" = c.code
                FROM "Channel" c
                WHERE m."channelCode" IS NULL
                  AND m."channelName" = c.name
                """
            )

        if summary_has_channel_name:
            cur.execute(
                """
                UPDATE "Summary" s
                SET "channelCode" = c.code
                FROM "Channel" c
                WHERE s."channelCode" IS NULL
                  AND s."channelName" = c.name
                """
            )

    conn.commit()
    _schema_ready = True


def _get_or_create_channel_code(conn, channel_name: str) -> str:
    cur = conn.cursor()

    cur.execute(
        'SELECT code FROM "Channel" WHERE name = %s',
        (channel_name,),
    )
    row = cur.fetchone()
    if row:
        return row[0]

    for attempt in range(100):
        code = _build_channel_code(channel_name, extra=str(attempt) if attempt else "")

        cur.execute(
            'SELECT name FROM "Channel" WHERE code = %s',
            (code,),
        )
        code_row = cur.fetchone()
        if code_row and code_row[0] != channel_name:
            continue

        cur.execute(
            """
            INSERT INTO "Channel" (code, name)
            VALUES (%s, %s)
            ON CONFLICT (name) DO UPDATE SET name = EXCLUDED.name
            RETURNING code
            """,
            (code, channel_name),
        )
        inserted = cur.fetchone()
        conn.commit()
        return inserted[0]

    raise RuntimeError(f"Could not generate a unique channel code for '{channel_name}'")


def _resolve_channel_code(conn, channel_name: str) -> str:
    _ensure_schema(conn)
    return _get_or_create_channel_code(conn, channel_name)


def ensure_channel(channel_name: str) -> str:
    conn = get_connection()
    try:
        return _resolve_channel_code(conn, channel_name)
    finally:
        conn.close()


def save_message(channel: str, role: str, content: str) -> None:
    try:
        conn = get_connection()
        channel_code = _resolve_channel_code(conn, channel)
        cur = conn.cursor()

        cur.execute(
            """
            INSERT INTO "Message" ("channelCode", role, content)
            VALUES (%s, %s, %s)
            """,
            (channel_code, role, content),
        )

        conn.commit()
        conn.close()
    except Exception as e:
        print(f"[DB SAVE ERROR] {e}")


def load_recent_messages(channel: str, limit: int = 100):
    try:
        conn = get_connection()
        channel_code = _resolve_channel_code(conn, channel)
        cur = conn.cursor()

        cur.execute(
            """
            SELECT role, content
            FROM "Message"
            WHERE "channelCode" = %s
            ORDER BY id DESC
            LIMIT %s
            """,
            (channel_code, limit),
        )

        rows = cur.fetchall()
        conn.close()

        return list(reversed(rows))
    except Exception as e:
        print(f"[DB LOAD ERROR] {e}")
        return []


def count_messages(channel_name: str) -> int:
    conn = get_connection()
    channel_code = _resolve_channel_code(conn, channel_name)
    cur = conn.cursor()

    cur.execute(
        """
        SELECT COUNT(*)
        FROM "Message"
        WHERE "channelCode" = %s
        """,
        (channel_code,),
    )

    count = cur.fetchone()[0]
    conn.close()
    return count


def get_unsummarised_messages(channel_name: str, start_id: int | None = None, limit: int = 100):
    conn = get_connection()
    channel_code = _resolve_channel_code(conn, channel_name)
    cur = conn.cursor()

    if start_id:
        cur.execute(
            """
            SELECT id, role, content
            FROM "Message"
            WHERE "channelCode" = %s
            AND id > %s
            ORDER BY id ASC
            LIMIT %s
            """,
            (channel_code, start_id, limit),
        )
    else:
        cur.execute(
            """
            SELECT id, role, content
            FROM "Message"
            WHERE "channelCode" = %s
            ORDER BY id ASC
            LIMIT %s
            """,
            (channel_code, limit),
        )

    rows = cur.fetchall()
    conn.close()
    return rows


def get_latest_summary(channel_name: str):
    conn = get_connection()
    channel_code = _resolve_channel_code(conn, channel_name)
    cur = conn.cursor()

    cur.execute(
        """
        SELECT startMessageId, endMessageId
        FROM "Summary"
        WHERE "channelCode" = %s
        ORDER BY "endMessageId" DESC
        LIMIT 1
        """,
        (channel_code,),
    )

    row = cur.fetchone()
    conn.close()

    return row if row else None


def save_summary(channel_name: str, summary: str, start_id: int, end_id: int):
    conn = get_connection()
    channel_code = _resolve_channel_code(conn, channel_name)
    cur = conn.cursor()

    cur.execute(
        """
        INSERT INTO "Summary"
        ("channelCode", summary, "startMessageId", "endMessageId")
        VALUES (%s, %s, %s, %s)
        """,
        (channel_code, summary, start_id, end_id),
    )

    conn.commit()
    conn.close()


def load_summaries(channel_name: str, limit: int = 10):
    conn = get_connection()
    channel_code = _resolve_channel_code(conn, channel_name)
    cur = conn.cursor()

    cur.execute(
        """
        SELECT summary
        FROM "Summary"
        WHERE "channelCode" = %s
        ORDER BY "endMessageId" DESC
        LIMIT %s
        """,
        (channel_code, limit),
    )

    rows = cur.fetchall()
    conn.close()

    return [r[0] for r in rows]