"""
validation.py
-------------
Pydantic models for all ActionCount API request/response bodies.
"""

from __future__ import annotations
from typing import Optional
from pydantic import BaseModel, Field


# ── Auth ─────────────────────────────────────────────────────────────────────

class SignupRequest(BaseModel):
    username: str = Field(..., min_length=3, max_length=30)
    password: str = Field(..., min_length=12, description="Minimum 12 chars, must include upper, digit and symbol")
    email: Optional[str] = Field(default=None, description="Email address — used as unique identifier")
    # 'tracker' → indefinite JWT (10 yr); 'dashboard' → 7-day JWT
    app_type: Optional[str] = Field(default="tracker", description="Which sub-app is signing up")


class LoginRequest(BaseModel):
    email:    str
    password: str
    # 'tracker' → indefinite JWT (10 yr); 'dashboard' → 7-day JWT
    app_type: Optional[str] = Field(default="tracker", description="Which sub-app is logging in")


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    is_new_user: bool = False   # True if user hasn't completed onboarding


# ── User Profile / Onboarding ─────────────────────────────────────────────────

class UserProfile(BaseModel):
    weight_kg: float = Field(..., gt=0, lt=500, description="Body weight in kg")
    height_cm: float = Field(..., gt=0, lt=300, description="Height in cm")
    age: int = Field(..., gt=0, lt=150)
    gender: str = Field(..., pattern="^(male|female|other)$")
    target: str = Field(
        ...,
        description="Primary fitness goal",
        pattern="^(weight_loss|muscle_gain|endurance|general_fitness)$",
    )
    goals_extra: Optional[str] = Field(
        default=None,
        max_length=500,
        description="Free-text additional goal specifications from the user",
    )
    equipment_availability: list[str] = Field(
        default_factory=list,
        description="Available equipment, e.g. ['dumbbells', 'barbell', 'resistance_bands', 'pull_up_bar', 'none']",
    )
    dietary_restrictions: list[str] = Field(
        default_factory=list,
        description="e.g. ['vegan', 'gluten_free', 'nut_allergy']",
    )


class UserProfileResponse(UserProfile):
    username: str
    onboarding_complete: bool


# ── Workouts ──────────────────────────────────────────────────────────────────

class SaveWorkoutRequest(BaseModel):
    exercise: str               # e.g. "Bicep Curl"
    reps: int = Field(..., ge=1)
    sets: int = Field(default=1, ge=1)
    date: Optional[str] = None  # ISO date string YYYY-MM-DD; defaults to today
    weight_kg: Optional[float] = Field(default=None, ge=0, description="Weight used in kg (0 = bodyweight)")
    calories_burnt: Optional[float] = Field(default=None, ge=0, description="Estimated kcal burnt this set")


class WorkoutEntry(BaseModel):
    sets: list[int]       # per-set rep counts e.g. [12, 10, 14]
    weights: list[float] = Field(default_factory=list)  # per-set weights in kg

    @property
    def total_reps(self) -> int:
        return sum(self.sets)

    @property
    def total_sets(self) -> int:
        return len(self.sets)

    @property
    def total_volume(self) -> float:
        """Total volume = sum(reps_i × weight_i) for all sets."""
        w = list(self.weights) + [0.0] * max(0, len(self.sets) - len(self.weights))
        return round(sum(r * wt for r, wt in zip(self.sets, w)), 2)


class DayWorkout(BaseModel):
    """All exercises performed on a single day."""
    date: str                              # "YYYY-MM-DD"
    exercises: dict[str, WorkoutEntry]     # {"Bicep Curl": {sets:[12,10], weights:[20,20]}}


class WorkoutHistoryResponse(BaseModel):
    history: list[DayWorkout]


class MuscleGroupStat(BaseModel):
    muscle_group: str
    total_sets: int


class WorkoutStatsResponse(BaseModel):
    month: str   # "YYYY-MM"
    stats: list[MuscleGroupStat]


class ExerciseVolume(BaseModel):
    exercise: str
    total_volume_kg: float


class VolumeResponse(BaseModel):
    month: str
    volumes: list[ExerciseVolume]


# ── Body Metrics ──────────────────────────────────────────────────────────────

class MetricLogRequest(BaseModel):
    date: str = Field(..., description="ISO date YYYY-MM-DD, must not be in the future")
    weight_kg: Optional[float] = Field(default=None, gt=0, lt=500)
    height_cm: Optional[float] = Field(default=None, gt=0, lt=300)


class MetricPoint(BaseModel):
    date: str
    weight_kg: Optional[float] = None
    height_cm: Optional[float] = None


class MetricsResponse(BaseModel):
    metrics: list[MetricPoint]


# ── Chat ──────────────────────────────────────────────────────────────────────

class ChatRequest(BaseModel):
    message: str = Field(..., min_length=1, max_length=2000)


class ChatMessage(BaseModel):
    role: str    # "user" | "assistant"
    content: str


class ChatResponse(BaseModel):
    reply: str
    history: list[ChatMessage]


# ── Calorie Tracker ───────────────────────────────────────────────────────────

class FoodItem(BaseModel):
    name: str
    portion: str
    calories: float


class CalorieLogEntry(BaseModel):
    log_id: str
    timestamp: str
    foods: list[FoodItem]
    total_calories: float
    confidence: str   # "low" | "medium" | "high"
    notes: str = ""


class CalorieLogResponse(BaseModel):
    logs: list[CalorieLogEntry]
    total_today: float


class CaloriesTodayResponse(BaseModel):
    total_calories: float
    calorie_goal: Optional[int] = None


# ── Friday Memory & Unified Agent ─────────────────────────────────────────────

class ConversationTurn(BaseModel):
    turn_id: str
    timestamp: str
    channel: str       # "text" | "voice"
    role: str          # "user" | "assistant"
    content: str
    attachments: list[dict] = []


class DietPlan(BaseModel):
    plan_id: str
    created_at: str
    title: str
    content: str
    is_active: bool


class FulfilledRequest(BaseModel):
    request_id: str
    timestamp: str
    type: str          # "diet_plan" | "calorie_scan" | "reminder" | "custom"
    summary: str
    ref_id: Optional[str] = None


# ── Workout Plans ─────────────────────────────────────────────────────────────

class PlanExercise(BaseModel):
    """A single exercise entry within a workout plan."""
    exercise_key: str = Field(..., description="Slug key e.g. 'bicep_curl'")
    sets: int         = Field(..., ge=1, le=20)
    reps: int         = Field(..., ge=1, le=200)
    weight_kg: float  = Field(default=0.0, ge=0, description="0 = bodyweight")


class SaveWorkoutPlanRequest(BaseModel):
    weekday: str     = Field(..., pattern="^(Mon|Tue|Wed|Thu|Fri|Sat|Sun)$")
    exercises: list[PlanExercise] = Field(..., min_length=1)
    workout_time: Optional[str] = Field(
        default=None,
        description="Optional HH:MM time to auto-start the workout (e.g. '18:30')",
    )


class WorkoutPlanResponse(BaseModel):
    weekday: str
    exercises: list[PlanExercise]
    workout_time: Optional[str] = None   # HH:MM or None
    updated_at: str
    is_active: bool


class WeeklyScheduleResponse(BaseModel):
    schedule: dict[str, Optional[list[PlanExercise]]]
    # Keys: Mon–Sun; value is None when no plan set for that day


class ReplacementSuggestion(BaseModel):
    exercise_key: str
    display_name: str
    muscle_group: str


class ReplacementResponse(BaseModel):
    original_exercise: str
    muscle_group: Optional[str]
    suggestions: list[ReplacementSuggestion]


# ── To-Do List ────────────────────────────────────────────────────────────────

class SaveToDoRequest(BaseModel):
    date: str = Field(..., description="ISO date YYYY-MM-DD")
    task: str = Field(..., min_length=1, max_length=500)
    time: Optional[str] = Field(
        default=None,
        description="HH:MM for hour-specific tasks, null/omit for all-day tasks",
    )

    @classmethod
    def _validate_time(cls, v):
        """Accept HH:MM or None."""
        if v is None or v == "":
            return None
        import re
        if not re.match(r'^([01]\d|2[0-3]):[0-5]\d$', v):
            raise ValueError('time must be HH:MM (00:00–23:59) or omitted')
        return v

    def model_post_init(self, __context):
        self.time = self._validate_time(self.time)


class ToDoItem(BaseModel):
    todo_id: str
    date:    str
    time:    Optional[str] = None
    task:    str
    completed: bool
    created_at: str


class ToDoListResponse(BaseModel):
    date:  str
    todos: list[ToDoItem]

