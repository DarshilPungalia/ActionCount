"""
db.py
-----
JSON-backed persistence layer for ActionCount.

Directory layout
----------------
data/
  users.json              – {username: {hashed_password, email, profile, onboarding_complete}}
  workouts/
    <username>.json       – {"2026-04-23": {"Bicep Curl": {reps, sets}, ...}}
  chats/
    <username>.json       – [{"role": "user|assistant", "content": "..."}]
"""

from __future__ import annotations

import json
import os
from datetime import date, datetime
from pathlib import Path
from typing import Any, Optional

# ── Root data directory ───────────────────────────────────────────────────────
DATA_DIR      = Path(__file__).parent.parent / "data"
USERS_FILE    = DATA_DIR / "users.json"
WORKOUTS_DIR  = DATA_DIR / "workouts"
CHATS_DIR     = DATA_DIR / "chats"

# ── Muscle group mapping ──────────────────────────────────────────────────────
EXERCISE_MUSCLE_MAP: dict[str, str] = {
    # Arms
    "Bicep Curl":      "Arms",
    # Chest
    "Push-Up":         "Chest",
    "Push Up":         "Chest",
    # Back
    "Pull-Up":         "Back",
    "Pull Up":         "Back",
    # Legs
    "Squat":           "Legs",
    "Knee Press":      "Legs",
    # Shoulders
    "Lateral Raise":   "Shoulders",
    "Overhead Press":  "Shoulders",
    # Core
    "Sit-Up":          "Core",
    "Sit Up":          "Core",
    "Crunch":          "Core",
    "Leg Raise":       "Core",
    "Knee Raise":      "Core",
}

MUSCLE_GROUPS = ["Arms", "Chest", "Back", "Legs", "Shoulders", "Core"]


def _ensure_dirs():
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    WORKOUTS_DIR.mkdir(parents=True, exist_ok=True)
    CHATS_DIR.mkdir(parents=True, exist_ok=True)


def _read_json(path: Path, default: Any = None) -> Any:
    """Read a JSON file, returning `default` if it doesn't exist."""
    if not path.exists():
        return default if default is not None else {}
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return default if default is not None else {}


def _write_json(path: Path, data: Any):
    """Write data to a JSON file atomically-ish."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


# ── User operations ───────────────────────────────────────────────────────────

def get_all_users() -> dict:
    _ensure_dirs()
    return _read_json(USERS_FILE, {})


def get_user(username: str) -> Optional[dict]:
    users = get_all_users()
    return users.get(username)


def create_user(username: str, hashed_password: str, email: Optional[str] = None) -> dict:
    _ensure_dirs()
    users = get_all_users()
    user = {
        "hashed_password":    hashed_password,
        "email":              email,
        "profile":            None,
        "onboarding_complete": False,
        "created_at":         datetime.utcnow().isoformat(),
    }
    users[username] = user
    _write_json(USERS_FILE, users)
    return user


def update_user_profile(username: str, profile: dict) -> bool:
    users = get_all_users()
    if username not in users:
        return False
    users[username]["profile"]             = profile
    users[username]["onboarding_complete"] = True
    _write_json(USERS_FILE, users)
    return True


def get_user_profile(username: str) -> Optional[dict]:
    user = get_user(username)
    if not user:
        return None
    return user.get("profile")


# ── Workout operations ────────────────────────────────────────────────────────

def _workout_path(username: str) -> Path:
    return WORKOUTS_DIR / f"{username}.json"


def save_workout(username: str, exercise: str, reps: int, sets: int,
                 workout_date: Optional[str] = None) -> dict:
    """
    Append a completed set to the user's workout log.
    If the same exercise already has an entry for that date, reps and sets
    are accumulated (e.g. doing two "Save Set" presses in one session).
    """
    _ensure_dirs()
    today = workout_date or date.today().isoformat()
    path  = _workout_path(username)
    data  = _read_json(path, {})

    day = data.setdefault(today, {})
    if exercise in day:
        day[exercise]["reps"] += reps
        day[exercise]["sets"] += sets
    else:
        day[exercise] = {"reps": reps, "sets": sets}

    _write_json(path, data)
    return data[today]


def get_workout_history(username: str) -> dict:
    """Return the full workout history dict {date: {exercise: {reps, sets}}}."""
    _ensure_dirs()
    return _read_json(_workout_path(username), {})


def get_monthly_stats(username: str, year_month: Optional[str] = None) -> dict[str, int]:
    """
    Aggregate reps by muscle group for a given month (YYYY-MM).
    Defaults to the current month.
    """
    target_month = year_month or datetime.now().strftime("%Y-%m")
    history      = get_workout_history(username)
    muscle_reps: dict[str, int] = {g: 0 for g in MUSCLE_GROUPS}

    for day_key, exercises in history.items():
        if not day_key.startswith(target_month):
            continue
        for ex_name, entry in exercises.items():
            muscle = EXERCISE_MUSCLE_MAP.get(ex_name, "Other")
            if muscle in muscle_reps:
                muscle_reps[muscle] += entry.get("reps", 0)

    return muscle_reps


# ── Chat operations ───────────────────────────────────────────────────────────

def _chat_path(username: str) -> Path:
    return CHATS_DIR / f"{username}.json"


def load_chat_history(username: str) -> list[dict]:
    """Return list of {role, content} dicts."""
    _ensure_dirs()
    return _read_json(_chat_path(username), [])


def append_chat_message(username: str, role: str, content: str):
    history = load_chat_history(username)
    history.append({"role": role, "content": content})
    # Keep last 100 messages to prevent unbounded growth
    if len(history) > 100:
        history = history[-100:]
    _write_json(_chat_path(username), history)


def clear_chat_history(username: str):
    _write_json(_chat_path(username), [])
