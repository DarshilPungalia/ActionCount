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


def get_user_by_email(email: str) -> Optional[dict]:
    """Find a user record by email address (email is used as unique identifier)."""
    if not email:
        return None
    users = get_all_users()
    for username, record in users.items():
        if record.get("email", "").lower() == email.lower():
            return record
    return None


def get_username_by_email(email: str) -> Optional[str]:
    """Return the username (storage key) for a given email, or None if not found."""
    if not email:
        return None
    users = get_all_users()
    for username, record in users.items():
        if record.get("email", "").lower() == email.lower():
            return username
    return None


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


def _entry_sets_list(entry: dict) -> list[int]:
    """
    Normalise a workout entry to a list of per-set rep counts.
    Handles both the new list format  {"sets": [12, 10, 14]}
    and the old flat format           {"reps": 36, "sets": 3}.
    """
    s = entry.get("sets", [])
    if isinstance(s, list):
        return s
    # Legacy flat format — reconstruct as a single pseudo-set
    reps = entry.get("reps", 0)
    count = s if isinstance(s, int) and s > 0 else 1
    # Distribute reps evenly across old set count (best we can do)
    per_set, rem = divmod(reps, count)
    result = [per_set] * count
    result[-1] += rem
    return result


def save_workout(username: str, exercise: str, reps: int, sets: int,
                 workout_date: Optional[str] = None) -> dict:
    """
    Append a completed set to the user's workout log.
    Each save call appends `reps` once to the exercise's sets list.
    `sets` param is kept for API compat but only `reps` is recorded per call.
    """
    _ensure_dirs()
    today = workout_date or date.today().isoformat()
    path  = _workout_path(username)
    data  = _read_json(path, {})

    day = data.setdefault(today, {})
    if exercise in day:
        entry = day[exercise]
        # Migrate old flat format on-write
        if not isinstance(entry.get("sets"), list):
            entry["sets"] = _entry_sets_list(entry)
            entry.pop("reps", None)
        entry["sets"].append(reps)
    else:
        day[exercise] = {"sets": [reps]}

    _write_json(path, data)
    return data[today]


def get_workout_history(username: str) -> dict:
    """Return the full workout history dict {date: {exercise: {sets: [reps...]}}}."""
    _ensure_dirs()
    return _read_json(_workout_path(username), {})


def get_monthly_stats(username: str, year_month: Optional[str] = None) -> dict[str, int]:
    """
    Aggregate *sets* by muscle group for a given month (YYYY-MM).
    Returns {muscle_group: set_count}.
    """
    target_month = year_month or datetime.now().strftime("%Y-%m")
    history      = get_workout_history(username)
    muscle_sets: dict[str, int] = {g: 0 for g in MUSCLE_GROUPS}

    for day_key, exercises in history.items():
        if not day_key.startswith(target_month):
            continue
        for ex_name, entry in exercises.items():
            muscle = EXERCISE_MUSCLE_MAP.get(ex_name, "Other")
            if muscle in muscle_sets:
                sets_list = _entry_sets_list(entry)
                muscle_sets[muscle] += len(sets_list)

    return muscle_sets


def get_total_sets_month(username: str, year_month: Optional[str] = None) -> int:
    """Total number of sets performed in the given month."""
    return sum(get_monthly_stats(username, year_month).values())


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
