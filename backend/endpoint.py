"""
endpoint.py
-----------
Single FastAPI entry point for the ActionCount backend.

Existing endpoints (preserved)
-------------------------------
GET  /                          → serve frontend/index.html (tracker)
GET  /exercises                 → list available exercise slugs
POST /session/start             → create a session, return session_id
GET  /session/{sid}/state       → poll current counter state
POST /session/{sid}/reset       → reset rep count
POST /upload/process            → upload video, returns MJPEG stream
WS   /ws/stream/{session_id}    → live camera WebSocket

Auth & Profile
--------------
POST /api/auth/signup           → create account
POST /api/auth/login            → get JWT token
GET  /api/user/profile          → get onboarding profile (auth required)
POST /api/user/profile          → save onboarding profile (auth required)

Workouts & Plans
----------------
POST /api/workout/save          → save a completed set
GET  /api/workout/history       → full workout history
GET  /api/workout/stats         → monthly muscle group aggregation
GET  /api/plans/today           → get today's weekday plan
GET  /api/plans/week            → full Mon-Sun schedule
POST /api/plans/save            → save/upsert a day's plan
DELETE /api/plans/{weekday}     → delete a day's plan
GET  /api/plans/suggest         → suggest replacement exercises (same muscle group)

Frontend pages served statically
---------------------------------
GET  /login                     → frontend/login.html
GET  /dashboard                 → frontend/dashboard.html
GET  /chatbot                   → frontend/chatbot.html
GET  /plans                     → frontend/plans.html
GET  /calorie                   → frontend/calorie.html

Calorie Scanner
---------------
POST /api/calorie/scan          → base64 JPEG → Gemini Vision → {foods, total_calories, …}
GET  /api/users/{u}/calories/today    → today's running total
GET  /api/users/{u}/calories/history  → paginated scan history
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
import tempfile
import time
from contextlib import asynccontextmanager
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

import cv2
import numpy as np
import uvicorn
from dotenv import load_dotenv
from fastapi import (
    Depends, FastAPI, File, Form, HTTPException,
    UploadFile, WebSocket, WebSocketDisconnect, status,
)
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse, StreamingResponse
from fastapi.security import OAuth2PasswordBearer
from fastapi.staticfiles import StaticFiles
from jose import JWTError, jwt
from passlib.context import CryptContext
from pydantic import BaseModel

# ── Force UTF-8 console output (Windows cp1252 can't print emoji) ─────────────
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")


# ── Environment ───────────────────────────────────────────────────────────────
load_dotenv()
SECRET_KEY                = os.getenv("SECRET_KEY", "fallback-secret-change-me")
ALGORITHM                 = os.getenv("ALGORITHM", "HS256")
ACCESS_TOKEN_EXPIRE_MINS  = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", "10080"))
GOOGLE_API_KEY            = os.getenv("GOOGLE_API_KEY", "")

# ── Path setup ────────────────────────────────────────────────────────────────
BACKEND_DIR  = Path(__file__).parent.resolve()
FRONTEND_DIR = BACKEND_DIR.parent / "frontend"
ROOT_DIR     = BACKEND_DIR.parent

for p in (str(BACKEND_DIR), str(ROOT_DIR)):
    if p not in sys.path:
        sys.path.insert(0, p)

from backend.utils.session_manager import SessionManager
from backend.utils import db
from backend.utils.validation import (
    SignupRequest, LoginRequest, TokenResponse,
    UserProfile, UserProfileResponse,
    SaveWorkoutRequest, WorkoutHistoryResponse, WorkoutStatsResponse,
    DayWorkout, WorkoutEntry, MuscleGroupStat,
    ExerciseVolume, VolumeResponse,
    MetricLogRequest, MetricPoint, MetricsResponse,
    ChatRequest, ChatResponse, ChatMessage,
    SaveWorkoutPlanRequest, WorkoutPlanResponse, WeeklyScheduleResponse,
    PlanExercise, ReplacementResponse, ReplacementSuggestion,
)
from backend.agent.chatbot import _get_response
from backend.agent.graph import invoke_friday
# TTS removed — see docs/tts_integration_reference.md to re-enable

from backend.agent.stt import FridaySTT

# ── Security helpers ──────────────────────────────────────────────────────────
pwd_context   = CryptContext(schemes=["argon2"], deprecated="auto")
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/auth/login")


def _hash_password(plain: str) -> str:
    return pwd_context.hash(plain)


def _verify_password(plain: str, hashed: str) -> bool:
    return pwd_context.verify(plain, hashed)


def _create_access_token(data: dict, expires_delta: Optional[timedelta] = None) -> str:
    to_encode = data.copy()
    expire = datetime.utcnow() + (expires_delta or timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINS))
    to_encode["exp"] = expire
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)


def _get_current_user(token: str = Depends(oauth2_scheme)) -> str:
    """Dependency — decode JWT and return username, or raise 401."""
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload  = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        username: str = payload.get("sub")
        if username is None:
            raise credentials_exception
    except JWTError:
        raise credentials_exception

    user = db.get_user(username)
    if user is None:
        raise credentials_exception
    return username

# ── Module-level Friday state ─────────────────────────────────────────────────
# Keyed by session_id — stores the latest raw JPEG bytes for calorie scanning
_active_frames: dict[str, bytes] = {}

# Keyed by username — active Friday WebSocket connections
_friday_ws_connections: dict[str, "WebSocket"] = {}

# Current channel per username: "text" | "voice"
_friday_channels: dict[str, str] = {}


def _get_user_channel(username: str) -> str:
    return _friday_channels.get(username, "text")


async def _broadcast_friday_async(msg: dict) -> None:
    """Async coroutine — send msg to all active Friday voice connections."""
    for username, ws in list(_friday_ws_connections.items()):
        if _get_user_channel(username) == "voice":
            try:
                await ws.send_json(msg)
            except Exception:
                pass


async def _broadcast_friday_all_async(msg: dict) -> None:
    """Async coroutine — send msg to ALL connected Friday users (any channel).
    Used for navigation frontend_commands so text-channel (chatbot) pages
    can still receive page-navigation directives.
    """
    for username, ws in list(_friday_ws_connections.items()):
        try:
            await ws.send_json(msg)
        except Exception:
            pass

# Keep the sync wrapper name for any legacy callers, now implemented safely
def _broadcast_friday(msg: dict) -> None:
    """
    Push a WebSocket message to ALL active Friday voice connections.
    NOTE: only safe when a loop is already running (from async context).
    For background-thread callers use run_coroutine_threadsafe directly.
    """
    try:
        loop = asyncio.get_running_loop()
        asyncio.ensure_future(_broadcast_friday_async(msg), loop=loop)
    except RuntimeError:
        pass   # no running loop — silently ignore (will be replaced by threadsafe path)


def _ensure_stt_running() -> None:
    """
    Lazily start the Whisper STT daemon the first time a user switches to voice
    channel. No-op if the daemon is already running.
    """
    stt = FridaySTT.instance()
    if stt._thread and stt._thread.is_alive():
        return  # already running

    # Capture the running event loop NOW (we're inside an async route handler).
    # The STT callbacks fire from a background thread that has NO event loop,
    # so we must close over this reference instead of calling get_event_loop() later.
    try:
        _loop = asyncio.get_running_loop()
    except RuntimeError:
        _loop = asyncio.get_event_loop()

    # ── Pre-compile fast-path regex patterns ────────────────────────────────
    import re as _re

    # Navigation commands are broadcast to ALL channels (voice + text) because
    # the chatbot page connects as text-channel and still needs nav commands.
    # They also skip LLM invocation — the page navigates instantly so a TTS
    # ack would be cut off anyway.
    _NAV_COMMANDS: frozenset = frozenset({
        "navigate_tracker", "navigate_dashboard", "navigate_chatbot",
        "navigate_plans",   "navigate_metrics",   "navigate_calorie",
        "navigate_back",
    })

    # Each entry: (compiled_pattern, frontend_command_key)
    # Patterns use word boundaries (\b) + multi-keyword anchoring so that
    # casual conversation containing individual words is NOT a false positive.
    _FAST_PATH_RULES: list[tuple[_re.Pattern, str]] = [

        # ── Calorie snapshot ─────────────────────────────────────────────────
        (_re.compile(
            r"\b(?:scan|take)\b.{0,15}\b(?:food|snapshot)\b"
            r"|\bcalorie\s+scan\b"
            r"|\b(?:what\s+are|tell\s+me).{0,20}\bcalories\b.{0,15}\b(?:this|it)\b"
            r"|\bhow\s+many\s+calories\b.{0,20}\b(?:this|it|have)\b"
            r"|\bcalories\b.{0,10}\bthis\b",
            _re.IGNORECASE,
        ), "calorie_snapshot"),

        # ── Save set ─────────────────────────────────────────────────────────
        (_re.compile(
            r"\b(?:save|log)\b.{0,20}\bset\b",
            _re.IGNORECASE,
        ), "save_set"),

        # ── Next set ─────────────────────────────────────────────────────────
        (_re.compile(
            r"\bnext\b.{0,15}\bset\b"
            r"|\bmove\b.{0,10}\bnext\b.{0,10}\bset\b",
            _re.IGNORECASE,
        ), "next_set"),

        # ── Stop set ─────────────────────────────────────────────────────────
        (_re.compile(
            r"\b(?:stop|end|finish)\b.{0,15}\bset\b",
            _re.IGNORECASE,
        ), "stop_set"),

        # ── Reset reps ───────────────────────────────────────────────────────
        (_re.compile(
            r"\breset\b.{0,15}\b(?:rep|reps|counter)\b"
            r"|\bclear\b.{0,10}\b(?:rep|reps)\b"
            r"|\bstart\s+over\b.{0,15}\b(?:rep|reps)\b",
            _re.IGNORECASE,
        ), "reset_reps"),

        # ── Start camera ─────────────────────────────────────────────────────
        (_re.compile(
            r"\bstart\b.{0,15}\b(?:camera|webcam|workout|session)\b"
            r"|\blet['\u2019]?s\s+(?:start|begin|go)\b"
            r"|\bbegin\b.{0,10}\b(?:workout|session)\b",
            _re.IGNORECASE,
        ), "start_camera"),

        # ── Stop camera ──────────────────────────────────────────────────────
        (_re.compile(
            r"\b(?:stop|end)\b.{0,15}\b(?:camera|webcam|workout|session)\b",
            _re.IGNORECASE,
        ), "stop_camera"),

        # ════════════════════════════════════════════════════════════════════
        # SITE NAVIGATION FAST-TRACKS
        # These bypass the LLM entirely and are broadcast to ALL channels so
        # chatbot (text-channel) and other pages can all navigate via voice.
        # ════════════════════════════════════════════════════════════════════

        # ── Navigate → Tracker ───────────────────────────────────────────────
        # "go to tracker", "back to workout", "start tracking", "go home"
        (_re.compile(
            r"\b(?:go\s+to|open|back\s+to|switch\s+to)\b.{0,15}\btracker\b"
            r"|\bgo\s+home\b"
            r"|\bback\s+to\s+(?:workout|exercise|training)\b"
            r"|\bstart\s+tracking\b",
            _re.IGNORECASE,
        ), "navigate_tracker"),

        # ── Navigate → Dashboard ─────────────────────────────────────────────
        # "go to dashboard", "show my stats", "show my progress"
        (_re.compile(
            r"\b(?:go\s+to|open|show|switch\s+to)\b.{0,15}\bdashboard\b"
            r"|\bshow\s+(?:my\s+)?(?:stats|progress|history)\b",
            _re.IGNORECASE,
        ), "navigate_dashboard"),

        # ── Navigate → Chatbot / AI Coach ────────────────────────────────────
        # "open chatbot", "chat with friday", "go to coach", "talk to AI"
        (_re.compile(
            r"\b(?:go\s+to|open|switch\s+to)\b.{0,15}\b(?:chatbot|chat|coach)\b"
            r"|\bchat\s+with\s+(?:friday|ai|coach)\b"
            r"|\btalk\s+to\s+(?:friday|ai)\b",
            _re.IGNORECASE,
        ), "navigate_chatbot"),

        # ── Navigate → Plans ─────────────────────────────────────────────────
        # "go to plans", "show my workout plan", "view my schedule"
        (_re.compile(
            r"\b(?:go\s+to|open|show|view|switch\s+to)\b.{0,15}\bplans?\b"
            r"|\bshow\s+(?:my\s+)?(?:workout\s+plan|schedule|weekly\s+plan)\b"
            r"|\bview\s+(?:my\s+)?(?:workout\s+plan|schedule)\b",
            _re.IGNORECASE,
        ), "navigate_plans"),

        # ── Navigate → Metrics ───────────────────────────────────────────────
        # "go to metrics", "track my weight", "log my weight"
        (_re.compile(
            r"\b(?:go\s+to|open|show|switch\s+to)\b.{0,15}\bmetrics\b"
            r"|\bshow\s+(?:my\s+)?(?:body\s+metrics|weight|measurements)\b"
            r"|\btrack\s+(?:my\s+)?(?:weight|body)\b"
            r"|\blog\s+(?:my\s+)?(?:weight|height|body)\b",
            _re.IGNORECASE,
        ), "navigate_metrics"),

        # ── Navigate → Calorie Scanner ───────────────────────────────────────
        # "open calorie scanner", "go to food tracking"
        # (distinct from calorie_snapshot which triggers a scan on current page)
        (_re.compile(
            r"\b(?:go\s+to|open|switch\s+to)\b.{0,20}\b(?:calorie\s+(?:scanner|page|tracker))\b"
            r"|\bopen\s+(?:food\s+scanner|food\s+tracking)\b"
            r"|\bgo\s+to\s+food\s+tracking\b",
            _re.IGNORECASE,
        ), "navigate_calorie"),

        # ── Navigate → Back ──────────────────────────────────────────────────
        # "go back", "take me back", "back to previous"
        (_re.compile(
            r"\bgo\s+back\b"
            r"|\btake\s+me\s+back\b"
            r"|\bback\s+to\s+previous\b",
            _re.IGNORECASE,
        ), "navigate_back"),
    ]

    def _on_transcript(transcript: str):
        print(f"[FridayWS] \U0001f4e8 Transcript received \u2192 checking fast-path rules …")

        # ── Regex fast-path: check all patterns before hitting the LLM ───────
        _fast_matched_nav = False
        for pattern, cmd in _FAST_PATH_RULES:
            if pattern.search(transcript):
                print(f"[FridayWS] ⚡ Fast-path match: {cmd!r} ← {transcript!r}")
                _is_nav = cmd in _NAV_COMMANDS
                # Navigation → broadcast to ALL channels (chatbot is text-channel)
                # Other commands → voice-channel only
                broadcast_fn = _broadcast_friday_all_async if _is_nav else _broadcast_friday_async
                asyncio.run_coroutine_threadsafe(
                    broadcast_fn({"type": "frontend_command",
                                  "data": {"command": cmd}}),
                    _loop,
                )
                if _is_nav:
                    _fast_matched_nav = True
                # Only first matching rule fires
                break

        # Navigation pages immediately — no LLM ack needed (would be cut off anyway)
        if _fast_matched_nav:
            return

        _voice_users = [
            (uname, ws)
            for uname, ws in list(_friday_ws_connections.items())
            if _get_user_channel(uname) == "voice"
        ]
        if not _voice_users:
            print(f"[FridayWS] ⚠  No voice-channel users connected — transcript dropped.")
            print(f"[FridayWS]    Connected users: {list(_friday_ws_connections.keys())}")
            print(f"[FridayWS]    Channels: {dict(_friday_channels)}")

        for uname, ws in _voice_users:
            frame = next(iter(_active_frames.values()), None) if _active_frames else None
            print(f"[FridayWS] Invoking agent for {uname!r} | frame={'yes' if frame else 'none'}")
            asyncio.run_coroutine_threadsafe(
                _handle_friday_message(ws, uname, transcript, "voice", frame),
                _loop,
            )

    def _on_speech_start():
        asyncio.run_coroutine_threadsafe(
            _broadcast_friday_async({"type": "friday_listening", "data": {"active": True}}),
            _loop,
        )

    def _on_speech_end():
        asyncio.run_coroutine_threadsafe(
            _broadcast_friday_async({"type": "friday_listening", "data": {"active": False}}),
            _loop,
        )

    print("[FridaySTT] First voice connection — starting STT daemon")
    stt.start(_on_transcript, on_speech_start=_on_speech_start, on_speech_end=_on_speech_end)


# ── App init ──────────────────────────────────────────────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI):
    SessionManager.instance()
    print("[ActionCount] Backend ready. STT will start on first voice connection.")
    yield
    FridaySTT.instance().stop()
    print("[ActionCount] Shutdown.")


app = FastAPI(title="ActionCount", version="3.0.0", lifespan=lifespan)

# CORS — allow the frontend to talk to the API
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Static files
if FRONTEND_DIR.exists():
    app.mount("/static", StaticFiles(directory=str(FRONTEND_DIR)), name="static")

# ── Constants ─────────────────────────────────────────────────────────────────
TARGET_FPS   = 30
MIN_FRAME_MS = 1000 / TARGET_FPS


# ═══════════════════════════════════════════════════════════════════════════════
# FRONTEND PAGE ROUTES
# ═══════════════════════════════════════════════════════════════════════════════

@app.get("/", response_class=HTMLResponse)
async def serve_tracker():
    """Serve the live tracker (index.html)."""
    p = FRONTEND_DIR / "index.html"
    return HTMLResponse(content=p.read_text(encoding="utf-8") if p.exists() else "<h1>Not found</h1>")


@app.get("/login", response_class=HTMLResponse)
async def serve_login():
    p = FRONTEND_DIR / "login.html"
    return HTMLResponse(content=p.read_text(encoding="utf-8") if p.exists() else "<h1>Not found</h1>")


@app.get("/dashboard", response_class=HTMLResponse)
async def serve_dashboard():
    p = FRONTEND_DIR / "dashboard.html"
    return HTMLResponse(content=p.read_text(encoding="utf-8") if p.exists() else "<h1>Not found</h1>")


@app.get("/chatbot", response_class=HTMLResponse)
async def serve_chatbot():
    p = FRONTEND_DIR / "chatbot.html"
    return HTMLResponse(content=p.read_text(encoding="utf-8") if p.exists() else "<h1>Not found</h1>")


@app.get("/metrics", response_class=HTMLResponse)
async def serve_metrics():
    p = FRONTEND_DIR / "metrics.html"
    return HTMLResponse(content=p.read_text(encoding="utf-8") if p.exists() else "<h1>Not found</h1>")


@app.get("/welcome", response_class=HTMLResponse)
async def serve_welcome():
    """Serve the post-login welcome landing page."""
    p = FRONTEND_DIR / "welcome.html"
    return HTMLResponse(content=p.read_text(encoding="utf-8") if p.exists() else "<h1>Not found</h1>")


@app.get("/plans", response_class=HTMLResponse)
async def serve_plans():
    """Serve the Workout Plans page."""
    p = FRONTEND_DIR / "plans.html"
    return HTMLResponse(content=p.read_text(encoding="utf-8") if p.exists() else "<h1>Not found</h1>")


@app.get("/calorie", response_class=HTMLResponse)
async def serve_calorie():
    """Serve the standalone Calorie Scanner page."""
    p = FRONTEND_DIR / "calorie.html"
    return HTMLResponse(content=p.read_text(encoding="utf-8") if p.exists() else "<h1>Not found</h1>")


# ══════════════════════════════════════════════════════════════════════════════
class MeResponse(BaseModel):
    username: str
    email: Optional[str] = None


@app.get("/api/me", response_model=MeResponse)
async def get_me(current_username: str = Depends(_get_current_user)):
    """Return the current user's display name and email from the JWT."""
    user = db.get_user(current_username)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    return MeResponse(
        username=current_username,
        email=user.get("email"),
    )


# ═══════════════════════════════════════════════════════════════════════════════
# API — AUTHENTICATION
# ═══════════════════════════════════════════════════════════════════════════════

@app.post("/api/auth/signup", response_model=TokenResponse)
async def signup(body: SignupRequest):
    """Create a new user account. Returns a JWT token immediately."""
    if db.get_user(body.username):
        raise HTTPException(status_code=409, detail="Username already exists.")
    if body.email and db.get_user_by_email(body.email):
        raise HTTPException(status_code=409, detail="An account with this email already exists.")

    hashed = _hash_password(body.password)
    db.create_user(body.username, hashed, body.email)

    token = _create_access_token({"sub": body.username})
    return TokenResponse(access_token=token, token_type="bearer", is_new_user=True)


@app.post("/api/auth/login", response_model=TokenResponse)
async def login(body: LoginRequest):
    """Authenticate via email + password and return a JWT token."""
    username = db.get_username_by_email(body.email)
    if username is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password.",
        )
    user = db.get_user(username)
    if not user or not _verify_password(body.password, user["hashed_password"]):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password.",
        )
    token = _create_access_token({"sub": username})
    is_new = not user.get("onboarding_complete", False)
    return TokenResponse(access_token=token, token_type="bearer", is_new_user=is_new)


# ═══════════════════════════════════════════════════════════════════════════════
# API — USER PROFILE (ONBOARDING)
# ═══════════════════════════════════════════════════════════════════════════════

@app.get("/api/user/profile")
async def get_profile(username: str = Depends(_get_current_user)):
    """
    Return the user's onboarding profile.
    Always returns 200 so the auth guard can distinguish auth failure (401)
    from a genuine missing/incomplete profile (onboarding_complete=false).
    """
    profile = db.get_user_profile(username)
    if not profile:
        # User exists and token is valid, but onboarding not yet complete.
        return {"username": username, "onboarding_complete": False}
    try:
        return {"username": username, "onboarding_complete": True, **profile}
    except Exception:
        # Profile exists but is malformed (old schema) — treat as incomplete.
        return {"username": username, "onboarding_complete": False}


@app.post("/api/user/profile", response_model=UserProfileResponse)
async def save_profile(body: UserProfile, username: str = Depends(_get_current_user)):
    db.update_user_profile(username, body.model_dump())
    return UserProfileResponse(username=username, onboarding_complete=True, **body.model_dump())


# ═══════════════════════════════════════════════════════════════════════════════
# API — FRIDAY VOICE PREFERENCE
# ═══════════════════════════════════════════════════════════════════════════════

@app.get("/api/voices")
async def get_voices(_: str = Depends(_get_current_user)):
    """TTS removed. Returns empty list. See docs/tts_integration_reference.md."""
    return {"voices": [], "default": ""}


@app.post("/api/user/voice")
async def set_voice(body: dict, username: str = Depends(_get_current_user)):
    """TTS removed. Silently accepts so frontend voice picker doesn't crash."""
    return {"status": "noop", "voice_id": "", "voice_name": ""}


# ═══════════════════════════════════════════════════════════════════════════════
# API — WORKOUTS
# ═══════════════════════════════════════════════════════════════════════════════


@app.post("/api/workout/save")
async def save_workout(body: SaveWorkoutRequest, username: str = Depends(_get_current_user)):
    """Save a completed set for today (or the supplied date)."""
    day_data = db.save_workout(
        username, body.exercise, body.reps, body.sets, body.date, body.weight_kg,
        calories_burnt=getattr(body, "calories_burnt", None),
    )
    return {"status": "saved", "day": day_data}


@app.get("/api/workout/calories")
async def get_monthly_calories(
    month: Optional[str] = None,
    username: str = Depends(_get_current_user),
):
    """Return total calories burnt for the given YYYY-MM month."""
    year_month = month or datetime.now().strftime("%Y-%m")
    total = db.get_monthly_calories(username, year_month)
    return {"month": year_month, "total_calories": total}


@app.get("/session/{session_id}/summary")
async def get_session_summary(session_id: str):
    """Return final rep count and estimated calories for a completed upload session."""
    mgr = SessionManager.instance()
    try:
        session = mgr.get(session_id)
    except KeyError:
        raise HTTPException(status_code=404, detail=f"Session {session_id!r} not found")
    result = session.last_result or {}
    return {
        "reps": result.get("counter", 0),
        "calories_burnt": result.get("calories_burnt", 0.0),
    }


@app.get("/api/workout/volume", response_model=VolumeResponse)
async def get_volume(
    month: Optional[str] = None,
    username: str = Depends(_get_current_user),
):
    """Return total volume (reps × weight_kg) per exercise for the given YYYY-MM month."""
    year_month  = month or datetime.now().strftime("%Y-%m")
    vol_data    = db.get_monthly_volume_by_exercise(username, year_month)
    volumes = [
        ExerciseVolume(exercise=ex, total_volume_kg=vol)
        for ex, vol in sorted(vol_data.items(), key=lambda x: -x[1])
    ]
    return VolumeResponse(month=year_month, volumes=volumes)


@app.get("/api/workout/history", response_model=WorkoutHistoryResponse)
async def get_history(username: str = Depends(_get_current_user)):
    """Return the full workout history — used to populate the calendar."""
    raw = db.get_workout_history(username)
    history = [
        DayWorkout(
            date=day,
            exercises={
                ex: WorkoutEntry(
                    sets=db._entry_sets_list(data),
                    weights=db._entry_weights_list(data),
                )
                for ex, data in exercises.items()
            },
        )
        for day, exercises in sorted(raw.items())
    ]
    return WorkoutHistoryResponse(history=history)


# ═══════════════════════════════════════════════════════════════════════════════
# API — BODY METRICS
# ═══════════════════════════════════════════════════════════════════════════════

@app.post("/api/metrics/log", response_model=MetricPoint)
async def log_metric(body: MetricLogRequest, username: str = Depends(_get_current_user)):
    """Log body weight / height for a given date (must not be in the future)."""
    try:
        result = db.log_metric(username, body.date, body.weight_kg, body.height_cm)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return MetricPoint(**result)


@app.get("/api/metrics", response_model=MetricsResponse)
async def get_metrics(username: str = Depends(_get_current_user)):
    """Retrieve all body metric entries for the user, sorted by date."""
    data = db.get_metrics(username)
    return MetricsResponse(metrics=[MetricPoint(**d) for d in data])


@app.get("/api/workout/stats", response_model=WorkoutStatsResponse)
async def get_stats(
    month: Optional[str] = None,
    username: str = Depends(_get_current_user),
):
    """Return muscle-group set count aggregation for the given YYYY-MM month."""
    year_month  = month or datetime.now().strftime("%Y-%m")
    muscle_data = db.get_monthly_stats(username, year_month)
    stats = [
        MuscleGroupStat(muscle_group=g, total_sets=s)
        for g, s in muscle_data.items()
    ]
    return WorkoutStatsResponse(month=year_month, stats=stats)


# ═══════════════════════════════════════════════════════════════════════════════
# API — AI CHATBOT
# ═══════════════════════════════════════════════════════════════════════════════

@app.post("/api/chat", response_model=ChatResponse)
async def chat(body: ChatRequest, username: str = Depends(_get_current_user)):
    """Send a message to the Gemini-powered dietary chatbot."""
    # Save user message
    db.append_chat_message(username, "user", body.message)

    # Get AI response (runs in thread to avoid blocking the event loop)
    reply = await asyncio.to_thread(_get_response, username, body.message)

    # Save assistant reply
    db.append_chat_message(username, "assistant", reply)

    history = [ChatMessage(**m) for m in db.load_chat_history(username)]
    return ChatResponse(reply=reply, history=history)


@app.delete("/api/chat")
async def clear_chat(username: str = Depends(_get_current_user)):
    """Clear the user's chat history."""
    db.clear_chat_history(username)
    return {"status": "cleared"}


@app.get("/api/chat/history")
async def get_chat_history(username: str = Depends(_get_current_user)):
    """Load existing chat history on page load."""
    history = db.load_chat_history(username)
    return {"history": history}


# ═══════════════════════════════════════════════════════════════════════════════
# API — WORKOUT PLANS
# ═══════════════════════════════════════════════════════════════════════════════

_DAY_NAMES = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]


@app.get("/api/plans/today")
async def get_today_plan(
    day: Optional[str] = None,
    username: str = Depends(_get_current_user),
):
    """
    Return the recurring workout plan for today's weekday (or the supplied ?day= param).
    Returns null exercises list if no plan is set for that day.
    """
    weekday = day or _DAY_NAMES[datetime.now().weekday()]
    plan = db.get_workout_plan(username, weekday)
    if not plan:
        return {"weekday": weekday, "exercises": None, "has_plan": False}
    return {
        "weekday":   plan["weekday"],
        "exercises": plan.get("exercises", []),
        "has_plan":  True,
        "updated_at": plan.get("updated_at"),
    }


@app.get("/api/plans/today/progress")
async def get_today_plan_progress(
    username: str = Depends(_get_current_user),
):
    """
    Return how many sets of each plan exercise have been logged today.

    Response: {
        "date": "YYYY-MM-DD",
        "progress": {"exercise_key": sets_done_int, ...},
        "plan_complete": bool   # true if all planned sets are done
    }

    Uses the DISPLAY_NAME → exercise_key mapping so it matches what
    tracker.js saves (display names) against what the plan stores (keys).
    """
    from datetime import date as _date  # noqa: PLC0415

    today     = _date.today().isoformat()
    weekday   = _DAY_NAMES[datetime.now().weekday()]
    plan      = db.get_workout_plan(username, weekday)

    if not plan or not plan.get("exercises"):
        return {"date": today, "progress": {}, "plan_complete": False}

    # Map display name → exercise_key (tracker.js saves display names)
    _KEY_TO_DISPLAY = {
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

    # Fetch today's workout log docs for this user
    from backend.utils.db import _workouts  # noqa: PLC0415
    today_docs = list(_workouts().find(
        {"username": username, "date": today},
        {"_id": 0, "exercise": 1, "sets": 1},
    ))

    # Build display_name → sets_done map
    logged: dict[str, int] = {}
    for doc in today_docs:
        name = doc.get("exercise", "")
        logged[name] = len(doc.get("sets", []))

    # Cross-reference plan exercises
    progress: dict[str, int] = {}
    plan_complete = True
    for ex in plan["exercises"]:
        key     = ex["exercise_key"]
        display = _KEY_TO_DISPLAY.get(key, key)
        done    = logged.get(display, 0)
        progress[key] = done
        if done < (ex.get("sets") or 1):
            plan_complete = False

    return {"date": today, "progress": progress, "plan_complete": plan_complete}



@app.get("/api/plans/week")
async def get_week_plan(username: str = Depends(_get_current_user)):
    """Return the full Mon–Sun workout schedule."""
    schedule = db.get_all_workout_plans(username)
    return {
        day: {
            "exercises": plan.get("exercises", []) if plan else None,
            "has_plan":  plan is not None,
        }
        for day, plan in schedule.items()
    }


@app.post("/api/plans/save")
async def save_plan(
    body: SaveWorkoutPlanRequest,
    username: str = Depends(_get_current_user),
):
    """Upsert a recurring workout plan for a given weekday."""
    exercises_raw = [ex.model_dump() for ex in body.exercises]
    try:
        saved = db.save_workout_plan(username, body.weekday, exercises_raw)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return {"status": "saved", "weekday": body.weekday, "plan": saved}


@app.delete("/api/plans/{weekday}")
async def delete_plan(weekday: str, username: str = Depends(_get_current_user)):
    """Soft-delete the recurring plan for the given weekday."""
    if weekday not in _DAY_NAMES:
        raise HTTPException(status_code=400, detail=f"Invalid weekday. Must be one of {_DAY_NAMES}.")
    deleted = db.delete_workout_plan(username, weekday)
    if not deleted:
        raise HTTPException(status_code=404, detail=f"No plan found for {weekday}.")
    return {"status": "deleted", "weekday": weekday}


@app.get("/api/plans/suggest", response_model=ReplacementResponse)
async def suggest_replacement(
    exercise: str,
    limit: int = 4,
    _: str = Depends(_get_current_user),
):
    """
    Return 3–4 alternative exercises from the same muscle group.
    Query param: exercise (exercise_key slug, e.g. 'bicep_curl')
    """
    suggestions_raw = db.suggest_replacement_exercises(exercise, limit=min(limit, 4))
    muscle = suggestions_raw[0]["muscle_group"] if suggestions_raw else None
    return ReplacementResponse(
        original_exercise=exercise,
        muscle_group=muscle,
        suggestions=[ReplacementSuggestion(**s) for s in suggestions_raw],
    )



# ═══════════════════════════════════════════════════════════════════════════════
# ORIGINAL ENDPOINTS (Preserved)
# ═══════════════════════════════════════════════════════════════════════════════

@app.get("/exercises")
async def list_exercises():
    mgr = SessionManager.instance()
    return {"exercises": mgr.list_exercises()}


class StartSessionRequest(BaseModel):
    exercise: str


class StartSessionResponse(BaseModel):
    session_id: str
    exercise:   str


@app.post("/session/start", response_model=StartSessionResponse)
async def start_session(body: StartSessionRequest):
    mgr = SessionManager.instance()
    try:
        sid = mgr.create(body.exercise)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return StartSessionResponse(session_id=sid, exercise=body.exercise)


@app.get("/session/{session_id}/state")
async def get_session_state(session_id: str):
    mgr = SessionManager.instance()
    try:
        session = mgr.get(session_id)
    except KeyError:
        raise HTTPException(status_code=404, detail=f"Session {session_id!r} not found")
    return session.last_result


@app.post("/session/{session_id}/reset")
async def reset_session(session_id: str):
    mgr = SessionManager.instance()
    try:
        mgr.reset(session_id)
    except KeyError:
        raise HTTPException(status_code=404, detail=f"Session {session_id!r} not found")
    return {"status": "reset", "session_id": session_id}


@app.post("/upload/process")
async def upload_process(
    file: UploadFile = File(...),
    exercise: str    = Form(...),
):
    mgr    = SessionManager.instance()
    suffix = Path(file.filename).suffix or ".mp4"
    with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
        tmp.write(await file.read())
        tmp_path = tmp.name

    try:
        sid = mgr.create(exercise)
    except ValueError as e:
        os.unlink(tmp_path)
        raise HTTPException(status_code=400, detail=str(e))

    async def _generate_mjpeg():
        session  = mgr.get(sid)
        cap      = cv2.VideoCapture(tmp_path)
        src_fps  = cap.get(cv2.CAP_PROP_FPS) or 30.0
        frame_sec = 1.0 / src_fps

        try:
            while cap.isOpened():
                t0 = asyncio.get_event_loop().time()
                ret, frame = await asyncio.to_thread(cap.read)
                if not ret:
                    break

                result   = session.counter.process_frame(frame)
                annotated = result["frame"]
                ok, buf  = await asyncio.to_thread(
                    cv2.imencode, ".jpg", annotated, [cv2.IMWRITE_JPEG_QUALITY, 85]
                )
                if not ok:
                    continue

                yield (
                    b"--frame\r\n"
                    b"Content-Type: image/jpeg\r\n\r\n"
                    + buf.tobytes()
                    + b"\r\n"
                )

                elapsed = asyncio.get_event_loop().time() - t0
                sleep_s = max(0.0, frame_sec - elapsed)
                if sleep_s > 0:
                    await asyncio.sleep(sleep_s)
        finally:
            cap.release()
            try:
                os.unlink(tmp_path)
            except OSError:
                pass
            mgr.destroy(sid)

    return StreamingResponse(
        _generate_mjpeg(),
        media_type="multipart/x-mixed-replace; boundary=frame",
    )


@app.websocket("/ws/stream/{session_id}")
async def ws_stream(websocket: WebSocket, session_id: str):
    """
    Refactored WebSocket handler (video_pipeline_implementation_plan.md §2b).

    Anti-pattern fixed
    ------------------
    Before: frame received → process_frame() blocked here → JSON sent
            (RTMPose inference, ~50–200ms, stalled the async loop)

    After : frame received → write to AtomicFrame (non-blocking overwrite)
                           → read latest result from AtomicResult
                           → JSON sent immediately
            InferenceWorker thread runs RTMPose at up to 15 fps independently.

    Latency impact
    --------------
    WebSocket receive/send loop is no longer gated by model inference time.
    The client receives a response for every frame it sends, using the most
    recent inference result available (renders last known result if inference
    is still in progress — satisfies plan render-thread requirement).
    """
    mgr = SessionManager.instance()
    try:
        session = mgr.get(session_id)
    except KeyError:
        await websocket.close(code=4004)
        return

    # Default payload returned before inference produces its first result
    _default_payload = {
        "counter": 0, "feedback": "Get in Position",
        "progress": 0.0, "correct_form": False,
        "keypoints": None, "skipped": False,
    }

    await websocket.accept()
    try:
        while True:
            data = await websocket.receive_bytes()

            # ── Decode JPEG ───────────────────────────────────────────────────
            cap_t0 = time.monotonic()
            frame  = _decode_jpeg(data)
            session.metrics.record_capture(time.monotonic() - cap_t0)

            if frame is None:
                await websocket.send_json({"error": "invalid frame"})
                continue

            # ── Store latest raw frame bytes for calorie scanner ──────────────
            _active_frames[session_id] = data

            # ── Hand frame to inference thread ────────────────────────────────
            session.atomic_frame.write(frame)

            # ── Return latest known result immediately (never blocks) ─────────
            result = session.atomic_result.read()
            payload = result if result is not None else _default_payload

            await websocket.send_json({**payload, "skipped": False})

            # TTS queue removed — posture corrections sent as friday_text
            # See docs/tts_integration_reference.md to restore audio push.

    except WebSocketDisconnect:
        pass
    finally:
        _active_frames.pop(session_id, None)
        mgr.destroy(session_id)


# ── Friday WebSocket helper ────────────────────────────────────────────────────

async def _handle_friday_message(
    ws: "WebSocket",
    username: str,
    message: str,
    channel: str,
    raw_frame: Optional[bytes],
) -> None:
    """Invoke Friday agent and push audio + data back over the Friday WebSocket."""
    print(f"[FridayWS] ▶ Handling message for {username!r} "
          f"| channel={channel!r} | text={message[:60]!r}")
    try:
        # Send command_ack immediately
        await ws.send_json({"type": "command_ack",
                            "data": {"command": message[:40], "status": "executing"}})

        # Invoke Friday graph in thread (LLM call is blocking)
        print(f"[FridayWS] 🤖 Invoking Friday LangGraph agent …")
        t0 = time.monotonic()
        result = await asyncio.to_thread(
            invoke_friday, username, message, channel, raw_frame
        )
        elapsed = time.monotonic() - t0
        print(f"[FridayWS] 🤖 Agent returned in {elapsed:.2f}s")

        response_text = result.get("response", "")
        intent        = result.get("intent", "chat")
        tool_result   = result.get("tool_result") or {}

        print(f"[FridayWS]    intent={intent!r} | response_len={len(response_text)} chars")
        if tool_result:
            print(f"[FridayWS]    tool_result keys: {list(tool_result.keys())}")

        # Push calorie_result for food scans
        if intent == "calorie_scan" and "foods" in tool_result:
            print(f"[FridayWS] 🍽  Sending calorie_result popup")
            await ws.send_json({"type": "calorie_result", "data": tool_result})

        # Push frontend commands
        if tool_result.get("frontend_command"):
            cmd = tool_result["frontend_command"]
            print(f"[FridayWS] 🎮 Sending frontend_command: {cmd!r}")
            await ws.send_json({"type": "frontend_command",
                                "data": {"command": cmd}})

        # Send response as text (TTS removed — see docs/tts_integration_reference.md)
        if response_text:
            await ws.send_json({"type": "friday_text", "data": {"text": response_text}})
            print(f"[FridayWS] Response cycle complete for {username!r}")

    except Exception as exc:
        print(f"[FridayWS] ❌ _handle_friday_message error for {username!r}: {exc}")


async def _push_friday_tts(ws: "WebSocket", username: str, text: str) -> None:
    """
    Push posture correction / motivation text to the Friday WebSocket.
    TTS removed — sends as friday_text. See docs/tts_integration_reference.md to restore audio.
    """
    try:
        await ws.send_json({"type": "friday_text", "data": {"text": text}})
    except Exception as exc:
        print(f"[FridayTTS] push error for {username!r}: {exc}")


# ── /ws/friday WebSocket ──────────────────────────────────────────────────────

@app.websocket("/ws/friday")
async def ws_friday(
    websocket: WebSocket,
    token: Optional[str] = None,
    channel: Optional[str] = None,
):
    """
    Friday push channel.
    Auth:    ?token=<jwt>   (query param, since WS headers are browser-limited)
    Channel: ?channel=voice (optional; defaults to 'voice' — tracker always uses voice)
    Channel can also be changed at runtime via {type: set_channel, data: {channel: voice|text}}.
    """
    # Authenticate
    if not token:
        await websocket.close(code=4001)
        return
    try:
        payload  = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        username = payload.get("sub")
        if not username or not db.get_user(username):
            raise ValueError("invalid user")
    except Exception:
        await websocket.close(code=4003)
        return

    await websocket.accept()
    _friday_ws_connections[username] = websocket
    # Pre-apply channel from query param — the tracker sends set_channel:voice on onopen,
    # but that message only arrives after receive_text() starts.  Setting it here avoids
    # the race where a transcript fires before the channel is switched.
    _initial_channel = channel if channel in ("text", "voice") else "voice"
    _friday_channels[username] = _initial_channel
    print(f"[FridayWS] {username!r} connected — initial channel={_initial_channel!r}")
    if _initial_channel == "voice":
        _ensure_stt_running()

    # Startup greeting
    try:
        profile   = db.get_user_profile(username) or {}
        user_doc  = db.get_user(username) or {}
        name      = user_doc.get("email", username).split("@")[0].capitalize()
        is_new    = not user_doc.get("onboarding_complete", False)

        if is_new:
            greeting = f"Hello {name}, I've created your profile. Let's get started."
        else:
            greeting = f"Hello {name}, welcome back. What are you up to?"

        # Send user_resolved event
        await websocket.send_json({
            "type": "user_resolved",
            "data": {"username": username, "name": name,
                     "calories_today": db.get_calories_today(username)},
        })

        # TTS greeting on voice channel only when user switches to voice
        await websocket.send_json({"type": "friday_text", "data": {"text": greeting}})

    except Exception as exc:
        print(f"[FridayWS] greeting error: {exc}")

    try:
        while True:
            raw = await websocket.receive_text()
            try:
                msg = json.loads(raw)
            except Exception:
                continue

            msg_type = msg.get("type", "message")

            # Channel switching
            if msg_type == "set_channel":
                new_channel = msg.get("data", {}).get("channel", "text")
                if new_channel in ("text", "voice"):
                    _friday_channels[username] = new_channel
                    print(f"[FridayWS] {username!r} switched to channel={new_channel!r}")
                    if new_channel == "voice":
                        # Start STT lazily — only when someone actually goes to voice mode
                        _ensure_stt_running()
                continue

            # Incoming message (text from chatbot UI or manual voice test)
            if msg_type == "message":
                text    = msg.get("data", {}).get("text", "").strip()
                channel = _get_user_channel(username)
                frame   = next(iter(_active_frames.values()), None) if _active_frames else None
                if text:
                    await _handle_friday_message(websocket, username, text, channel, frame)

    except WebSocketDisconnect:
        pass
    finally:
        _friday_ws_connections.pop(username, None)
        _friday_channels.pop(username, None)


# ═══════════════════════════════════════════════════════════════════════════════
# CALORIE SCANNER — REST endpoint (used by calorie.html)
# ═══════════════════════════════════════════════════════════════════════════════

class CalorieScanRequest(BaseModel):
    image_b64: str


@app.post("/api/calorie/scan")
async def calorie_scan(
    body: CalorieScanRequest,
    username: str = Depends(_get_current_user),
):
    """
    Accept a base64-encoded JPEG, run Gemini/Azure Vision, return
    {foods, total_calories, confidence, notes} and persist to DB.
    """
    import base64 as _b64
    import numpy as _np
    from backend.utils.calorie_tracker import scan_food_from_frame  # noqa: PLC0415

    try:
        raw = _b64.b64decode(body.image_b64)
        arr = _np.frombuffer(raw, dtype=_np.uint8)
        frame = cv2.imdecode(arr, cv2.IMREAD_COLOR)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Invalid image data: {exc}")

    if frame is None:
        raise HTTPException(status_code=400, detail="Could not decode image")

    result = await asyncio.to_thread(scan_food_from_frame, frame, username)

    if "error" in result:
        raise HTTPException(status_code=502, detail=result.get("message", "Scan failed"))

    return result


# ── Calorie History API ───────────────────────────────────────────────────────

@app.get("/api/users/{username}/calories/today", response_model=dict)
async def calories_today(username: str, current_user: str = Depends(_get_current_user)):
    """Return today's total food-scan calories for the user."""
    if current_user != username:
        raise HTTPException(status_code=403, detail="Access denied")
    total = db.get_calories_today(username)
    profile = db.get_user_profile(username) or {}
    return {"total_calories": total, "calorie_goal": profile.get("calorie_goal_daily", 2000)}


@app.get("/api/users/{username}/calories/history")
async def calories_history(
    username: str,
    limit: int = 20,
    offset: int = 0,
    current_user: str = Depends(_get_current_user),
):
    """Return paginated food-scan calorie logs."""
    if current_user != username:
        raise HTTPException(status_code=403, detail="Access denied")
    logs        = db.get_calorie_logs(username, limit=limit, offset=offset)
    total_today = db.get_calories_today(username)
    return {"logs": logs, "total_today": total_today}


@app.delete("/api/users/{username}/calories/{log_id}")
async def delete_calorie_log(
    username: str,
    log_id: str,
    current_user: str = Depends(_get_current_user),
):
    """Delete a specific calorie log entry."""
    if current_user != username:
        raise HTTPException(status_code=403, detail="Access denied")
    deleted = db.delete_calorie_log(username, log_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Log entry not found")
    return {"status": "deleted", "log_id": log_id}


# ── Helpers ───────────────────────────────────────────────────────────────────

def _decode_jpeg(data: bytes) -> Optional[np.ndarray]:
    arr = np.frombuffer(data, dtype=np.uint8)
    if arr.size == 0:
        return None
    return cv2.imdecode(arr, cv2.IMREAD_COLOR)


def _kps_to_list(kps: np.ndarray) -> list:
    return [[round(float(x), 2), round(float(y), 2)] for x, y in kps]


# ── Run ───────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    uvicorn.run("endpoint:app", host="127.0.0.1", port=8000, reload=True)
