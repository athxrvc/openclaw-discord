import os
from db import get_connection

# =========================
# CONFIG
# =========================
SUMMARY_THRESHOLD = 100


# =========================
# MESSAGE FUNCTIONS
# =========================
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


# =========================
# SUMMARY FUNCTIONS
# =========================
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


# =========================
# SUMMARISATION BUILDER
# =========================
def build_summary_prompt(messages):
    text = "\n".join([f"{role}: {content}" for _, role, content in messages])

    return f"""
You are a memory compression system.

Summarise the conversation below into a compact memory.

Include:
- key decisions
- topics discussed
- tasks or plans
- important context

Conversation:
{text}
"""


# =========================
# MAIN CHECK FUNCTION
# =========================
def check_and_summarise(channel_name: str, ask_llm_func):
    """
    Call this after saving each message.
    ask_llm_func must be a function(prompt) -> response
    """

    count = count_messages(channel_name)

    if count < SUMMARY_THRESHOLD:
        return

    latest_summary = get_latest_summary(channel_name)

    start_id = latest_summary[1] + 1 if latest_summary else None

    messages = get_unsummarised_messages(
        channel_name,
        start_id=start_id,
        limit=SUMMARY_THRESHOLD,
    )

    if len(messages) < SUMMARY_THRESHOLD:
        return

    prompt = build_summary_prompt(messages)

    summary_text = ask_llm_func(prompt)

    first_id = messages[0][0]
    last_id = messages[-1][0]

    save_summary(channel_name, summary_text, first_id, last_id)

    print(f"[SUMMARY] {channel_name}: {first_id} → {last_id}")