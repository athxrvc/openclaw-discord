from db import (
    count_messages,
    get_unsummarised_messages,
    get_latest_summary,
    save_summary,
    load_summaries,
)

# =========================
# CONFIG
# =========================
SUMMARY_THRESHOLD = 100


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


def build_memory_context(channel_name: str, recent_messages):
    try:
        summaries = load_summaries(channel_name, limit=10)
    except Exception as e:
        print(f"[MEMORY LOAD ERROR] {e}")
        summaries = []

    summary_text = "\n".join([f"- {s}" for s in summaries]) or "None"

    history_text = "\n".join([f"{r[0]}: {r[1]}" for r in recent_messages])

    return f"""
LONG-TERM MEMORY (Summaries):
{summary_text}

RECENT CONVERSATION:
{history_text}
"""