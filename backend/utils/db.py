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

_MONGO_URI = os.getenv("MONGODB_URI", "")

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


def _calorie_logs():
    return _get_db()["calorie_logs"]


def _conversation_turns():
    return _get_db()["conversation_turns"]


def _diet_plans():
    return _get_db()["diet_plans"]


def _fulfilled_requests():
    return _get_db()["fulfilled_requests"]


def _memory_summaries():
    return _get_db()["memory_summaries"]


def _workout_plans():
    return _get_db()["workout_plans"]


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

# Reverse map: muscle group → list of exercise keys (for replacement suggestions)
MUSCLE_EXERCISE_MAP: dict[str, list[str]] = {
    "Arms":      ["bicep_curl"],
    "Chest":     ["pushup"],
    "Back":      ["pullup"],
    "Legs":      ["squat", "knee_press", "knee_raise", "leg_raise"],
    "Shoulders": ["lateral_raise", "overhead_press"],
    "Core":      ["situp", "crunch", "leg_raise", "knee_raise"],
}

# Canonical display names for exercise keys
EXERCISE_DISPLAY_NAMES: dict[str, str] = {
    "squat":          "Squat",
    "pushup":         "Push-Up",
    "bicep_curl":     "Bicep Curl",
    "pullup":         "Pull-Up",
    "lateral_raise":  "Lateral Raise",
    "overhead_press": "Overhead Press",
    "situp":          "Sit-Up",
    "crunch":         "Crunch",
    "leg_raise":      "Leg Raise",
    "knee_raise":     "Knee Raise",
    "knee_press":     "Knee Press",
}


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
    """Overwrite the full onboarding profile dict."""
    result = _users().update_one(
        {"username": username},
        {"$set": {"profile": profile, "onboarding_complete": True}},
    )
    return result.matched_count > 0


def set_user_voice(username: str, voice_id: str) -> bool:
    """
    Persist the user's preferred Friday TTS voice WITHOUT touching the rest
    of the profile.  Uses a dot-path $set so existing onboarding data is safe.
    """
    result = _users().update_one(
        {"username": username},
        {"$set": {"friday_voice_id": voice_id}},   # top-level field, not inside profile
    )
    return result.matched_count > 0


def get_user_voice(username: str) -> Optional[str]:
    """Return the stored Friday voice ID for a user, or None."""
    doc = _users().find_one({"username": username}, {"_id": 0, "friday_voice_id": 1})
    return (doc or {}).get("friday_voice_id")


def get_user_profile(username: str) -> Optional[dict]:
    doc = _users().find_one({"username": username}, {"_id": 0, "profile": 1})
    if not doc:
        return None
    profile = doc.get("profile")
    if not profile or not isinstance(profile, dict):
        return None
    # A valid onboarding profile must have weight_kg.
    # Documents that only contain friday_voice_id (or other non-onboarding keys)
    # are NOT a complete profile — treat as not onboarded.
    if "weight_kg" not in profile:
        return None
    # Back-fill optional fields that may be missing from older stored documents
    # so the caller never sees KeyError / Pydantic validation failure.
    profile.setdefault("goals_extra", None)
    profile.setdefault("equipment_availability", [])
    profile.setdefault("dietary_restrictions", [])
    return profile


# ── Workout operations ────────────────────────────────────────────────────────

def save_workout(username: str, exercise: str, reps: int, sets: int,
                 workout_date: Optional[str] = None,
                 weight_kg: Optional[float] = None,
                 calories_burnt: Optional[float] = None) -> dict:
    """
    Append a completed set to the user's workout log.
    Each save call appends `reps` to the sets list, `weight_kg` to the weights list,
    and optionally `calories_burnt` to the calories list.
    `sets` param is kept for API compat but only `reps` is recorded per call.

    Returns the {exercise: {sets: [...], weights: [...], calories: [...]}} map for that day.
    """
    today = workout_date or date.today().isoformat()
    w = float(weight_kg) if weight_kg is not None else 0.0
    cal = float(calories_burnt) if calories_burnt is not None else 0.0

    _workouts().update_one(
        {"username": username, "date": today, "exercise": exercise},
        {
            "$push": {
                "sets":     reps,
                "weights":  w,
                "calories": cal,
            }
        },
        upsert=True,
    )

    # Return {exercise: {sets: [...], weights: [...], calories: [...]}} shape for that day
    day_docs = _workouts().find(
        {"username": username, "date": today},
        {"_id": 0, "exercise": 1, "sets": 1, "weights": 1, "calories": 1},
    )
    return {
        doc["exercise"]: {
            "sets":     doc.get("sets", []),
            "weights":  doc.get("weights", []),
            "calories": doc.get("calories", []),
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


def get_monthly_calories(username: str, year_month: Optional[str] = None) -> float:
    """
    Sum all calories burnt across every set for a given month (YYYY-MM).
    Returns total calories as a float.
    """
    target_month = year_month or datetime.now().strftime("%Y-%m")
    docs = _workouts().find(
        {"username": username, "date": {"$regex": f"^{target_month}"}},
        {"_id": 0, "calories": 1},
    )
    total = 0.0
    for doc in docs:
        cal_list = doc.get("calories", [])
        if isinstance(cal_list, list):
            total += sum(float(c) for c in cal_list)
    return round(total, 1)


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


# ── Calorie Log operations ────────────────────────────────────────────────────

def log_calorie_entry(username: str, entry: dict) -> dict:
    """
    Persist a single food-scan result.
    entry must contain: {timestamp, foods, total_calories, confidence, notes}
    foods is a list of {name, portion, calories}.
    Returns the stored document (with generated log_id).
    """
    import uuid
    log_id = str(uuid.uuid4())
    doc = {
        "log_id":        log_id,
        "username":      username,
        "timestamp":     entry.get("timestamp", datetime.utcnow().isoformat()),
        "foods":         entry.get("foods", []),
        "total_calories": float(entry.get("total_calories", 0)),
        "confidence":    entry.get("confidence", "low"),
        "notes":         entry.get("notes", ""),
    }
    _calorie_logs().insert_one(doc)
    return {k: v for k, v in doc.items() if k != "_id"}


def get_calorie_logs(username: str, limit: int = 20, offset: int = 0) -> list[dict]:
    """Return paginated calorie scan logs for a user, newest first."""
    docs = _calorie_logs().find(
        {"username": username},
        {"_id": 0, "username": 0},
        sort=[("timestamp", -1)],
    ).skip(offset).limit(limit)
    return list(docs)


def get_calories_today(username: str) -> float:
    """
    Sum total_calories from all food scans logged since midnight UTC today.
    Returns total as float.
    """
    today_start = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0).isoformat()
    docs = _calorie_logs().find(
        {"username": username, "timestamp": {"$gte": today_start}},
        {"_id": 0, "total_calories": 1},
    )
    return round(sum(float(d.get("total_calories", 0)) for d in docs), 1)


def delete_calorie_log(username: str, log_id: str) -> bool:
    """Delete a calorie log entry by log_id. Returns True if deleted."""
    result = _calorie_logs().delete_one({"username": username, "log_id": log_id})
    return result.deleted_count > 0


# ── Conversation Turns (unified text + voice memory) ──────────────────────────

def append_conversation_turn(username: str, role: str, content: str,
                              channel: str = "text", attachments: Optional[list] = None) -> dict:
    """
    Append a turn to the shared conversation history.
    channel: 'text' | 'voice'
    attachments: optional list of {type, ref_id} dicts
    """
    import uuid
    turn = {
        "turn_id":    str(uuid.uuid4()),
        "username":   username,
        "timestamp":  datetime.utcnow().isoformat(),
        "channel":    channel,
        "role":       role,
        "content":    content,
        "attachments": attachments or [],
    }
    _conversation_turns().insert_one(turn)
    return {k: v for k, v in turn.items() if k != "_id"}


def get_recent_turns(username: str, limit: int = 20) -> list[dict]:
    """Return the last N conversation turns across all channels, oldest first."""
    docs = _conversation_turns().find(
        {"username": username},
        {"_id": 0, "username": 0},
        sort=[("timestamp", -1)],
    ).limit(limit)
    return list(reversed(list(docs)))


def get_turn_count(username: str) -> int:
    """Return total number of conversation turns stored for a user."""
    return _conversation_turns().count_documents({"username": username})


# ── Diet Plans ────────────────────────────────────────────────────────────────

def save_diet_plan(username: str, title: str, content: str) -> dict:
    """Store a Friday-generated diet plan. Marks all previous plans as inactive."""
    import uuid
    plan_id = str(uuid.uuid4())
    # Deactivate previous plans
    _diet_plans().update_many(
        {"username": username}, {"$set": {"is_active": False}}
    )
    doc = {
        "plan_id":    plan_id,
        "username":   username,
        "created_at": datetime.utcnow().isoformat(),
        "title":      title,
        "content":    content,
        "is_active":  True,
    }
    _diet_plans().insert_one(doc)
    return {k: v for k, v in doc.items() if k != "_id"}


def get_active_diet_plan(username: str) -> Optional[dict]:
    """Return the current active diet plan for a user, or None."""
    doc = _diet_plans().find_one(
        {"username": username, "is_active": True},
        {"_id": 0, "username": 0},
        sort=[("created_at", -1)],
    )
    return doc


# ── Fulfilled Requests Log ────────────────────────────────────────────────────

def log_fulfilled_request(username: str, req_type: str,
                           summary: str, ref_id: Optional[str] = None) -> dict:
    """Log a significant action Friday has completed."""
    import uuid
    doc = {
        "request_id": str(uuid.uuid4()),
        "username":   username,
        "timestamp":  datetime.utcnow().isoformat(),
        "type":       req_type,   # 'diet_plan' | 'calorie_scan' | 'reminder' | 'custom'
        "summary":    summary,
        "ref_id":     ref_id,
    }
    _fulfilled_requests().insert_one(doc)
    return {k: v for k, v in doc.items() if k != "_id"}


def get_fulfilled_requests(username: str, limit: int = 5) -> list[dict]:
    """Return the N most recent fulfilled requests for context injection."""
    docs = _fulfilled_requests().find(
        {"username": username},
        {"_id": 0, "username": 0},
        sort=[("timestamp", -1)],
    ).limit(limit)
    return list(docs)


# ── Memory Summaries ──────────────────────────────────────────────────────────

def save_memory_summary(username: str, content: str,
                         turns_from: int, turns_to: int) -> dict:
    """Store a generated memory summary covering a range of turn indices."""
    import uuid
    doc = {
        "summary_id":         str(uuid.uuid4()),
        "username":           username,
        "generated_at":       datetime.utcnow().isoformat(),
        "content":            content,
        "turns_covered_from": turns_from,
        "turns_covered_to":   turns_to,
    }
    _memory_summaries().insert_one(doc)
    return {k: v for k, v in doc.items() if k != "_id"}


def get_latest_memory_summary(username: str) -> Optional[dict]:
    """Return the most recent memory summary for a user, or None."""
    doc = _memory_summaries().find_one(
        {"username": username},
        {"_id": 0, "username": 0},
        sort=[("generated_at", -1)],
    )
    return doc


# ── Workout Plans ─────────────────────────────────────────────────────────────
# Schema per document:
#   {
#     "username":  str,
#     "weekday":   str,          # "Mon" | "Tue" | "Wed" | "Thu" | "Fri" | "Sat" | "Sun"
#     "exercises": [             # ordered list; UI can reorder via drag-and-drop
#       {"exercise_key": str, "sets": int, "reps": int, "weight_kg": float}
#     ],
#     "created_at":  str,        # ISO datetime
#     "updated_at":  str,
#     "is_active":   bool,       # False when user explicitly deletes this day's plan
#   }

_WEEKDAYS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]


def save_workout_plan(username: str, weekday: str, exercises: list[dict]) -> dict:
    """
    Upsert the recurring workout plan for a given weekday.
    `exercises` is an ordered list of {exercise_key, sets, reps, weight_kg}.
    The plan repeats every week on this weekday until explicitly deleted.
    """
    if weekday not in _WEEKDAYS:
        raise ValueError(f"Invalid weekday '{weekday}'. Must be one of {_WEEKDAYS}.")
    now = datetime.utcnow().isoformat()
    doc = {
        "username":   username,
        "weekday":    weekday,
        "exercises":  exercises,
        "updated_at": now,
        "is_active":  True,
    }
    existing = _workout_plans().find_one({"username": username, "weekday": weekday})
    if existing:
        _workout_plans().update_one(
            {"username": username, "weekday": weekday},
            {"$set": {k: v for k, v in doc.items() if k != "username"}},
        )
    else:
        doc["created_at"] = now
        _workout_plans().insert_one(doc)
    result = _workout_plans().find_one(
        {"username": username, "weekday": weekday}, {"_id": 0, "username": 0}
    )
    return result or {}


def get_workout_plan(username: str, weekday: str) -> Optional[dict]:
    """Return the active recurring plan for `weekday`, or None if not set."""
    if weekday not in _WEEKDAYS:
        return None
    doc = _workout_plans().find_one(
        {"username": username, "weekday": weekday, "is_active": True},
        {"_id": 0, "username": 0},
    )
    return doc


def get_all_workout_plans(username: str) -> dict[str, Optional[dict]]:
    """Return the full weekly schedule as {weekday: plan_or_None}."""
    docs = _workout_plans().find(
        {"username": username, "is_active": True},
        {"_id": 0, "username": 0},
    )
    schedule: dict[str, Optional[dict]] = {day: None for day in _WEEKDAYS}
    for doc in docs:
        schedule[doc["weekday"]] = doc
    return schedule


def delete_workout_plan(username: str, weekday: str) -> bool:
    """Soft-delete a day's plan (marks is_active=False). Returns True if found."""
    result = _workout_plans().update_one(
        {"username": username, "weekday": weekday},
        {"$set": {"is_active": False, "updated_at": datetime.utcnow().isoformat()}},
    )
    return result.matched_count > 0


def suggest_replacement_exercises(exercise_key: str, limit: int = 4) -> list[dict]:
    """
    Return up to `limit` alternative exercises from the same muscle group.
    Each result: {exercise_key, display_name, muscle_group}
    """
    # Normalise key
    key = exercise_key.lower().replace("-", "_").replace(" ", "_")
    # Find the muscle group for the given exercise
    display_name = EXERCISE_DISPLAY_NAMES.get(key, "")
    muscle = EXERCISE_MUSCLE_MAP.get(display_name) or next(
        (m for m, keys in MUSCLE_EXERCISE_MAP.items() if key in keys), None
    )
    if not muscle:
        return []
    # Return all same-group exercises except the current one
    candidates = [
        {
            "exercise_key":  k,
            "display_name":  EXERCISE_DISPLAY_NAMES.get(k, k),
            "muscle_group":  muscle,
        }
        for k in MUSCLE_EXERCISE_MAP.get(muscle, [])
        if k != key
    ]
    return candidates[:limit]

