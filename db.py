import os
import psycopg2


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


def save_message(channel: str, role: str, content: str) -> None:
    try:
        conn = get_connection()
        cur = conn.cursor()

        cur.execute(
            """
            INSERT INTO "Message" ("channelName", role, content)
            VALUES (%s, %s, %s)
            """,
            (channel, role, content),
        )

        conn.commit()
        conn.close()
    except Exception as e:
        print(f"[DB SAVE ERROR] {e}")


def load_recent_messages(channel: str, limit: int = 100):
    try:
        conn = get_connection()
        cur = conn.cursor()

        cur.execute(
            """
            SELECT role, content
            FROM "Message"
            WHERE "channelName" = %s
            ORDER BY id DESC
            LIMIT %s
            """,
            (channel, limit),
        )

        rows = cur.fetchall()
        conn.close()

        return list(reversed(rows))
    except Exception as e:
        print(f"[DB LOAD ERROR] {e}")
        return []


def count_messages(channel_name: str) -> int:
    conn = get_connection()
    cur = conn.cursor()

    cur.execute(
        """
        SELECT COUNT(*)
        FROM "Message"
        WHERE "channelName" = %s
        """,
        (channel_name,),
    )

    count = cur.fetchone()[0]
    conn.close()
    return count


def get_unsummarised_messages(channel_name: str, start_id: int | None = None, limit: int = 100):
    conn = get_connection()
    cur = conn.cursor()

    if start_id:
        cur.execute(
            """
            SELECT id, role, content
            FROM "Message"
            WHERE "channelName" = %s
            AND id > %s
            ORDER BY id ASC
            LIMIT %s
            """,
            (channel_name, start_id, limit),
        )
    else:
        cur.execute(
            """
            SELECT id, role, content
            FROM "Message"
            WHERE "channelName" = %s
            ORDER BY id ASC
            LIMIT %s
            """,
            (channel_name, limit),
        )

    rows = cur.fetchall()
    conn.close()
    return rows


def get_latest_summary(channel_name: str):
    conn = get_connection()
    cur = conn.cursor()

    cur.execute(
        """
        SELECT startMessageId, endMessageId
        FROM "Summary"
        WHERE "channelName" = %s
        ORDER BY "endMessageId" DESC
        LIMIT 1
        """,
        (channel_name,),
    )

    row = cur.fetchone()
    conn.close()

    return row if row else None


def save_summary(channel_name: str, summary: str, start_id: int, end_id: int):
    conn = get_connection()
    cur = conn.cursor()

    cur.execute(
        """
        INSERT INTO "Summary"
        ("channelName", summary, "startMessageId", "endMessageId")
        VALUES (%s, %s, %s, %s)
        """,
        (channel_name, summary, start_id, end_id),
    )

    conn.commit()
    conn.close()


def load_summaries(channel_name: str, limit: int = 10):
    conn = get_connection()
    cur = conn.cursor()

    cur.execute(
        """
        SELECT summary
        FROM "Summary"
        WHERE "channelName" = %s
        ORDER BY "endMessageId" DESC
        LIMIT %s
        """,
        (channel_name, limit),
    )

    rows = cur.fetchall()
    conn.close()

    return [r[0] for r in rows]