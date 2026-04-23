"""
db.py
-----
MongoDB-backed persistence layer for ActionCount.

Collections (inside the 'ActionCount' database)
------------------------------------------------
users    – {username, hashed_password, email, profile, onboarding_complete, created_at}
workouts – {username, date, exercise, sets}   (one doc per exercise-per-day)
chats    – {username, messages: [{role, content}]}
"""

from __future__ import annotations

import os
from datetime import date, datetime
from typing import Any, Optional

from dotenv import load_dotenv
from pymongo import MongoClient
from pymongo.server_api import ServerApi

# ── Load env & connect ────────────────────────────────────────────────────────
load_dotenv()

_MONGO_PASS = os.getenv("MONGODB_PASSWORD", "")
_MONGO_URI = (
    f"mongodb+srv://DarshilPungalia:{_MONGO_PASS}"
    "@cluster0.mbrvwfy.mongodb.net/?retryWrites=true&w=majority&appName=Cluster0"
)

_client: MongoClient | None = None


def _get_db():
    """Lazy singleton — creates the MongoClient on first call."""
    global _client
    if _client is None:
        _client = MongoClient(_MONGO_URI, server_api=ServerApi("1"))
    return _client["ActionCount"]


def _users():
    return _get_db()["users"]


def _workouts():
    return _get_db()["workouts"]


def _chats():
    return _get_db()["chats"]


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


# ── Helpers ───────────────────────────────────────────────────────────────────

def _entry_sets_list(entry: dict) -> list[int]:
    """
    Normalise a workout entry to a list of per-set rep counts.
    Handles both the new list format  {\"sets\": [12, 10, 14]}
    and the old flat format           {\"reps\": 36, \"sets\": 3}.
    """
    s = entry.get("sets", [])
    if isinstance(s, list):
        return s
    # Legacy flat format — reconstruct as a single pseudo-set
    reps = entry.get("reps", 0)
    count = s if isinstance(s, int) and s > 0 else 1
    per_set, rem = divmod(reps, count)
    result = [per_set] * count
    result[-1] += rem
    return result


def _strip_id(doc: dict | None) -> dict | None:
    """Remove MongoDB's internal _id field from a returned document."""
    if doc and "_id" in doc:
        doc.pop("_id")
    return doc


# ── User operations ───────────────────────────────────────────────────────────

def get_all_users() -> dict:
    """Return {username: user_record} for all users."""
    col = _users()
    return {doc["username"]: {k: v for k, v in doc.items() if k not in ("_id", "username")}
            for doc in col.find({})}


def get_user(username: str) -> Optional[dict]:
    doc = _users().find_one({"username": username}, {"_id": 0, "username": 0})
    return doc or None


def get_user_by_email(email: str) -> Optional[dict]:
    """Find a user record by email address (email is used as unique identifier)."""
    if not email:
        return None
    doc = _users().find_one(
        {"email": {"$regex": f"^{email}$", "$options": "i"}},
        {"_id": 0, "username": 0},
    )
    return doc or None


def get_username_by_email(email: str) -> Optional[str]:
    """Return the username (storage key) for a given email, or None if not found."""
    if not email:
        return None
    doc = _users().find_one(
        {"email": {"$regex": f"^{email}$", "$options": "i"}},
        {"_id": 0, "username": 1},
    )
    return doc["username"] if doc else None


def create_user(username: str, hashed_password: str, email: Optional[str] = None) -> dict:
    user_doc = {
        "username":            username,
        "hashed_password":     hashed_password,
        "email":               email,
        "profile":             None,
        "onboarding_complete": False,
        "created_at":          datetime.utcnow().isoformat(),
    }
    _users().update_one({"username": username}, {"$set": user_doc}, upsert=True)
    # Return without the internal fields
    return {k: v for k, v in user_doc.items() if k not in ("_id", "username")}


def update_user_profile(username: str, profile: dict) -> bool:
    result = _users().update_one(
        {"username": username},
        {"$set": {"profile": profile, "onboarding_complete": True}},
    )
    return result.matched_count > 0


def get_user_profile(username: str) -> Optional[dict]:
    doc = _users().find_one({"username": username}, {"_id": 0, "profile": 1})
    if not doc:
        return None
    return doc.get("profile")


# ── Workout operations ────────────────────────────────────────────────────────

def save_workout(username: str, exercise: str, reps: int, sets: int,
                 workout_date: Optional[str] = None) -> dict:
    """
    Append a completed set to the user's workout log.
    Each save call appends `reps` once to the exercise's sets list.
    `sets` param is kept for API compat but only `reps` is recorded per call.

    Returns the {exercise: {sets: [...]}} map for that day.
    """
    today = workout_date or date.today().isoformat()

    _workouts().update_one(
        {"username": username, "date": today, "exercise": exercise},
        {"$push": {"sets": reps}},
        upsert=True,
    )

    # Return {exercise: {sets: [reps...]}} shape (same as JSON layer)
    day_docs = _workouts().find(
        {"username": username, "date": today},
        {"_id": 0, "exercise": 1, "sets": 1},
    )
    return {doc["exercise"]: {"sets": doc.get("sets", [])} for doc in day_docs}


def get_workout_history(username: str) -> dict:
    """Return the full workout history dict {date: {exercise: {sets: [reps...]}}}."""
    docs = _workouts().find(
        {"username": username},
        {"_id": 0, "date": 1, "exercise": 1, "sets": 1},
    )
    history: dict[str, dict] = {}
    for doc in docs:
        day = doc["date"]
        ex  = doc["exercise"]
        history.setdefault(day, {})[ex] = {"sets": doc.get("sets", [])}
    return history


def get_monthly_stats(username: str, year_month: Optional[str] = None) -> dict[str, int]:
    """
    Aggregate *sets* by muscle group for a given month (YYYY-MM).
    Returns {muscle_group: set_count}.
    """
    target_month = year_month or datetime.now().strftime("%Y-%m")
    docs = _workouts().find(
        {"username": username, "date": {"$regex": f"^{target_month}"}},
        {"_id": 0, "exercise": 1, "sets": 1},
    )
    muscle_sets: dict[str, int] = {g: 0 for g in MUSCLE_GROUPS}
    for doc in docs:
        muscle = EXERCISE_MUSCLE_MAP.get(doc["exercise"], "Other")
        if muscle in muscle_sets:
            muscle_sets[muscle] += len(doc.get("sets", []))
    return muscle_sets


def get_total_sets_month(username: str, year_month: Optional[str] = None) -> int:
    """Total number of sets performed in the given month."""
    return sum(get_monthly_stats(username, year_month).values())


# ── Chat operations ───────────────────────────────────────────────────────────

def load_chat_history(username: str) -> list[dict]:
    """Return list of {role, content} dicts."""
    doc = _chats().find_one({"username": username}, {"_id": 0, "messages": 1})
    if not doc:
        return []
    return doc.get("messages", [])


def append_chat_message(username: str, role: str, content: str):
    _chats().update_one(
        {"username": username},
        {"$push": {"messages": {"$each": [{"role": role, "content": content}],
                                "$slice": -100}}},
        upsert=True,
    )


def clear_chat_history(username: str):
    _chats().update_one(
        {"username": username},
        {"$set": {"messages": []}},
        upsert=True,
    )
