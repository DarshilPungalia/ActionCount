"""
db.py
-----
MongoDB-backed persistence layer for ActionCount.

Collections (inside the 'ActionCount' database)
------------------------------------------------
users    – {username, hashed_password, email, profile, onboarding_complete, created_at}
workouts – {username, date, exercise, sets: [int], weights: [float]}
           one doc per exercise-per-day; sets[i] pairs with weights[i]
chats    – {username, messages: [{role, content}]}
metrics  – {username, date, weight_kg, height_cm}
           one doc per user per day (upsert)
"""

from __future__ import annotations

import os
from datetime import date, datetime
from typing import Any, Optional

from dotenv import load_dotenv
from pymongo import MongoClient, ASCENDING
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


def _metrics():
    return _get_db()["metrics"]


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
    Handles both the new list format  {"sets": [12, 10, 14]}
    and the old flat format           {"reps": 36, "sets": 3}.
    """
    s = entry.get("sets", [])
    if isinstance(s, list):
        return [int(x) for x in s]
    # Legacy flat format — reconstruct as a single pseudo-set
    reps = entry.get("reps", 0)
    count = s if isinstance(s, int) and s > 0 else 1
    per_set, rem = divmod(reps, count)
    result = [per_set] * count
    result[-1] += rem
    return result


def _entry_weights_list(entry: dict) -> list[float]:
    """Return the per-set weights list, defaulting to 0.0 if not present."""
    w = entry.get("weights", [])
    if isinstance(w, list):
        return [float(x) for x in w]
    return []


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
                 workout_date: Optional[str] = None,
                 weight_kg: Optional[float] = None) -> dict:
    """
    Append a completed set to the user's workout log.
    Each save call appends `reps` to the sets list and `weight_kg` to the weights list.
    `sets` param is kept for API compat but only `reps` is recorded per call.

    Returns the {exercise: {sets: [...], weights: [...]}} map for that day.
    """
    today = workout_date or date.today().isoformat()
    w = float(weight_kg) if weight_kg is not None else 0.0

    _workouts().update_one(
        {"username": username, "date": today, "exercise": exercise},
        {
            "$push": {
                "sets":    reps,
                "weights": w,
            }
        },
        upsert=True,
    )

    # Return {exercise: {sets: [...], weights: [...]}} shape for that day
    day_docs = _workouts().find(
        {"username": username, "date": today},
        {"_id": 0, "exercise": 1, "sets": 1, "weights": 1},
    )
    return {
        doc["exercise"]: {
            "sets":    doc.get("sets", []),
            "weights": doc.get("weights", []),
        }
        for doc in day_docs
    }


def get_workout_history(username: str) -> dict:
    """Return the full workout history dict {date: {exercise: {sets, weights}}}."""
    docs = _workouts().find(
        {"username": username},
        {"_id": 0, "date": 1, "exercise": 1, "sets": 1, "weights": 1},
    )
    history: dict[str, dict] = {}
    for doc in docs:
        day = doc["date"]
        ex  = doc["exercise"]
        history.setdefault(day, {})[ex] = {
            "sets":    doc.get("sets", []),
            "weights": doc.get("weights", []),
        }
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


def get_volume_history(username: str, year_month: Optional[str] = None) -> dict:
    """
    Return total volume (reps × weight_kg) per exercise per day.
    If year_month given (YYYY-MM), only that month.
    Returns {date: {exercise: total_volume_kg}}.
    """
    query: dict = {"username": username}
    if year_month:
        query["date"] = {"$regex": f"^{year_month}"}

    docs = _workouts().find(query, {"_id": 0, "date": 1, "exercise": 1, "sets": 1, "weights": 1})
    volume: dict[str, dict[str, float]] = {}
    for doc in docs:
        day = doc["date"]
        ex  = doc["exercise"]
        sets_list    = doc.get("sets", [])
        weights_list = doc.get("weights", [])
        # Pad weights to same length as sets (default 0.0 for old records)
        w_list = list(weights_list) + [0.0] * max(0, len(sets_list) - len(weights_list))
        total_vol = sum(r * w for r, w in zip(sets_list, w_list))
        volume.setdefault(day, {})[ex] = round(total_vol, 2)
    return volume


def get_monthly_volume_by_exercise(username: str, year_month: Optional[str] = None) -> dict[str, float]:
    """
    Aggregate total volume (reps × weight_kg) per exercise for a given month.
    Returns {exercise_name: total_kg_volume}.
    """
    target_month = year_month or datetime.now().strftime("%Y-%m")
    vol_history  = get_volume_history(username, target_month)
    totals: dict[str, float] = {}
    for day_data in vol_history.values():
        for ex, vol in day_data.items():
            totals[ex] = round(totals.get(ex, 0.0) + vol, 2)
    return totals


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


# ── Body Metrics operations ───────────────────────────────────────────────────

def log_metric(username: str, metric_date: str, weight_kg: Optional[float],
               height_cm: Optional[float]) -> dict:
    """
    Upsert a body metric entry for a given date.
    Only fields explicitly provided (not None) are updated.
    metric_date must be YYYY-MM-DD and must not be in the future.
    """
    today = date.today().isoformat()
    if metric_date > today:
        raise ValueError("Cannot log metrics for a future date.")

    update_fields: dict = {}
    if weight_kg is not None:
        update_fields["weight_kg"] = float(weight_kg)
    if height_cm is not None:
        update_fields["height_cm"] = float(height_cm)

    if not update_fields:
        return {}

    _metrics().update_one(
        {"username": username, "date": metric_date},
        {"$set": update_fields},
        upsert=True,
    )

    doc = _metrics().find_one({"username": username, "date": metric_date},
                               {"_id": 0, "username": 0})
    return doc or {}


def get_metrics(username: str) -> list[dict]:
    """
    Return all body metric entries for a user, sorted by date ascending.
    Each entry: {date, weight_kg?, height_cm?}
    """
    docs = _metrics().find(
        {"username": username},
        {"_id": 0, "username": 0},
        sort=[("date", ASCENDING)],
    )
    return list(docs)
