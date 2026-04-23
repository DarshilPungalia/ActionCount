"""
models.py
---------
Pydantic models for all ActionCount API request/response bodies.
"""

from __future__ import annotations
from typing import Optional
from pydantic import BaseModel, Field


# ── Auth ─────────────────────────────────────────────────────────────────────

class SignupRequest(BaseModel):
    username: str = Field(..., min_length=3, max_length=30)
    password: str = Field(..., min_length=12, description="Minimum 12 chars, must include upper, digit and symbol")
    email: str = Field(..., description="Required — used as the unique account identifier")


class LoginRequest(BaseModel):
    email:    str
    password: str


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
        description="fitness goal",
        pattern="^(weight_loss|muscle_gain|endurance|general_fitness)$",
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


class WorkoutEntry(BaseModel):
    sets: list[int]   # per-set rep counts e.g. [12, 10, 14]

    @property
    def total_reps(self) -> int:
        return sum(self.sets)

    @property
    def total_sets(self) -> int:
        return len(self.sets)


class DayWorkout(BaseModel):
    """All exercises performed on a single day."""
    date: str                              # "YYYY-MM-DD"
    exercises: dict[str, WorkoutEntry]     # {"Bicep Curl": {sets:[12,10]}}


class WorkoutHistoryResponse(BaseModel):
    history: list[DayWorkout]


class MuscleGroupStat(BaseModel):
    muscle_group: str
    total_sets: int


class WorkoutStatsResponse(BaseModel):
    month: str   # "YYYY-MM"
    stats: list[MuscleGroupStat]


# ── Chat ──────────────────────────────────────────────────────────────────────

class ChatRequest(BaseModel):
    message: str = Field(..., min_length=1, max_length=2000)


class ChatMessage(BaseModel):
    role: str    # "user" | "assistant"
    content: str


class ChatResponse(BaseModel):
    reply: str
    history: list[ChatMessage]
