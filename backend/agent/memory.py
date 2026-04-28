"""
friday_memory.py
----------------
Shared system-prompt builder for the Friday AI agent.

Both the text chatbot and the voice pipeline call `build_system_prompt()`.
The `channel` parameter controls tone:
  - 'text'  → may use markdown, responses can be detailed
  - 'voice' → 1-2 sentences max, no markdown, speakable prose only

Context window strategy
-----------------------
1. Last 20 turns injected verbatim (configurable via RECENT_TURNS)
2. Older history summarised into a memory_summary (from DB)
3. Pinned memory: active diet plan + recent fulfilled requests — always injected
"""

from __future__ import annotations

import os
from datetime import datetime
from typing import Optional

from dotenv import load_dotenv

load_dotenv()

FRIDAY_NAME   = os.getenv("FRIDAY_NAME", "Friday")
RECENT_TURNS  = 20   # number of verbatim turns to inject


# ── Public API ────────────────────────────────────────────────────────────────

def build_system_prompt(username: str, channel: str = "text",
                         current_exercise: Optional[str] = None,
                         current_reps: Optional[int] = None) -> str:
    """
    Assemble the full system prompt for Friday.

    Imports db lazily to avoid circular imports at module load time.
    """
    # Lazy import to avoid circular dependencies
    from backend.utils import db  # noqa: PLC0415

    # ── 1. User profile ───────────────────────────────────────────────────────
    user_doc     = db.get_user(username) or {}
    profile      = db.get_user_profile(username) or {}
    display_name = user_doc.get("email", username).split("@")[0].capitalize()

    calorie_goal = profile.get("calorie_goal_daily", 2000)
    restrictions = ", ".join(profile.get("dietary_restrictions", [])) or "None"
    weight       = profile.get("weight_kg", "?")
    height       = profile.get("height_cm", "?")
    goal         = profile.get("target", "general_fitness").replace("_", " ").title()

    # ── 2. Pinned memory ──────────────────────────────────────────────────────
    diet_plan = db.get_active_diet_plan(username)
    diet_section = ""
    if diet_plan:
        diet_section = (
            f"\nActive diet plan ({diet_plan['title']}, created {diet_plan['created_at'][:10]}):\n"
            f"{diet_plan['content'][:400]}{'...' if len(diet_plan['content']) > 400 else ''}"
        )

    recent_requests = db.get_fulfilled_requests(username, limit=3)
    requests_section = ""
    if recent_requests:
        lines = [f"  - {r['summary']} ({r['timestamp'][:10]})" for r in recent_requests]
        requests_section = "\nRecent fulfilled requests:\n" + "\n".join(lines)

    # ── 3. Memory summary (older history) ────────────────────────────────────
    mem_summary = db.get_latest_memory_summary(username)
    mem_section = ""
    if mem_summary:
        mem_section = f"\nConversation summary (older history):\n{mem_summary['content']}"

    # ── 4. Recent turns (last N verbatim) ────────────────────────────────────
    turns = db.get_recent_turns(username, limit=RECENT_TURNS)
    turns_section = ""
    if turns:
        lines = []
        for t in turns:
            ch_tag = "[voice] " if t.get("channel") == "voice" else ""
            lines.append(f"{ch_tag}{t['role'].upper()}: {t['content']}")
        turns_section = "\nRecent conversation:\n" + "\n".join(lines)

    # ── 5. Current runtime context ────────────────────────────────────────────
    now          = datetime.now().strftime("%A %d %B %Y, %H:%M")
    exercise_ctx = f"Active exercise: {current_exercise}, reps so far: {current_reps}" \
                   if current_exercise else "No active exercise session"

    # ── 6. Channel-specific instruction ──────────────────────────────────────
    if channel == "voice":
        channel_instruction = (
            "You are responding via voice. Keep your reply to 1-2 sentences maximum. "
            "Use NO markdown, NO bullet points, NO lists. Speakable prose only. "
            "Be extremely concise — you are a co-pilot, not a lecturer."
        )
    else:
        channel_instruction = (
            "You are responding via text chat. You may use markdown. "
            "Responses can be detailed when the user asks for plans or explanations. "
            "Be helpful, thorough, but still avoid unnecessary filler."
        )

    # ── Assemble ──────────────────────────────────────────────────────────────
    prompt = f"""You are {FRIDAY_NAME}, an ambient AI assistant embedded in ActionCount — a real-time exercise tracking platform.
Tone: calm, minimal, precise. No filler phrases like "Great!", "Sure thing!", or "Of course!".
Speak like a calm co-pilot who gives exactly what is needed, nothing more.

Active user: {display_name}
Fitness goal: {goal}
Body weight: {weight} kg | Height: {height} cm
Dietary restrictions: {restrictions}
Time: {now}
{exercise_ctx}
{diet_section}{requests_section}{mem_section}{turns_section}

{channel_instruction}"""

    return prompt.strip()


def should_regenerate_summary(username: str) -> bool:
    """
    Returns True if the memory summary should be regenerated.
    Trigger: total turn count has grown by more than 40 turns since last summary.
    """
    from backend.utils import db  # noqa: PLC0415

    total = db.get_turn_count(username)
    summary = db.get_latest_memory_summary(username)
    if summary is None:
        return total >= 40
    covered_to = summary.get("turns_covered_to", 0)
    return (total - covered_to) >= 40
