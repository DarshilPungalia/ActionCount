import warnings
import os
import sys
import threading
import tempfile
from datetime import datetime, date

import av
import cv2
import streamlit as st
from streamlit_webrtc import VideoProcessorBase, WebRtcMode, webrtc_streamer, RTCConfiguration
import plotly.graph_objects as go

warnings.filterwarnings("ignore")

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from backend.counters.BicepCurlCounter import BicepCurlCounter
from backend.counters.PushupCounter import PushupCounter
from backend.counters.PullupCounter import PullupCounter
from backend.counters.SquatCounter import SquatCounter
from backend.counters.LateralRaiseCounter import LateralRaiseCounter
from backend.counters.OverheadPressCounter import OverheadPressCounter
from backend.counters.SitupCounter import SitupCounter
from backend.counters.CrunchCounter import CrunchCounter
from backend.counters.LegRaiseCounter import LegRaiseCounter
from backend.counters.KneeRaiseCounter import KneeRaiseCounter
from backend.counters.KneePressCounter import KneePressCounter
from backend.utils import db
from backend.utils.chatbot import _get_response
from dotenv import load_dotenv

load_dotenv()

# ── Auth helpers (Argon2 via passlib) ────────────────────────────────────────
from passlib.context import CryptContext
from jose import jwt, JWTError
from datetime import timedelta
from streamlit_cookies_controller import CookieController

SECRET_KEY = os.getenv("SECRET_KEY", "fallback-secret")
ALGORITHM  = os.getenv("ALGORITHM", "HS256")
_pwd_ctx   = CryptContext(schemes=["argon2"], deprecated="auto")

AUTH_COOKIE_NAME    = "ac_auth"
AUTH_COOKIE_EXPIRY  = 7   # days

def _hash_pw(p): return _pwd_ctx.hash(p)
def _verify_pw(p, h): return _pwd_ctx.verify(p, h)

def _create_auth_token(username: str) -> str:
    """Create a short-lived JWT for the auth cookie."""
    expire = datetime.utcnow() + timedelta(days=AUTH_COOKIE_EXPIRY)
    return jwt.encode({"sub": username, "exp": expire}, SECRET_KEY, algorithm=ALGORITHM)

def _decode_auth_token(token: str):
    """Decode the JWT; returns username string or None on failure."""
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        return payload.get("sub")
    except JWTError:
        return None


def _password_strength(p: str) -> tuple[str, str]:
    """Return (label, colour) for the password strength meter."""
    score = 0
    if len(p) >= 12: score += 1
    if len(p) >= 16: score += 1
    if any(c.isupper() for c in p): score += 1
    if any(c.islower() for c in p): score += 1
    if any(c.isdigit() for c in p): score += 1
    if any(c in '!@#$%^&*()-_=+[]{}|;:\'",./<>?' for c in p): score += 1
    if score <= 1:   return "Weak",        "#ef4444"
    if score <= 2:   return "Fair",        "#f59e0b"
    if score <= 3:   return "Good",        "#eab308"
    if score <= 4:   return "Strong",      "#10b981"
    return             "Very Strong",  "#6366f1"

# ── Exercise registry ──────────────────────────────────────────────────────────
EXERCISES = {
    "💪 Bicep Curl":     (BicepCurlCounter,     "Bicep Curl"),
    "🔼 Push-Up":        (PushupCounter,         "Push-Up"),
    "🏋️ Pull-Up":       (PullupCounter,          "Pull-Up"),
    "🦵 Squat":          (SquatCounter,           "Squat"),
    "🦾 Lateral Raise":  (LateralRaiseCounter,   "Lateral Raise"),
    "⬆️ Overhead Press": (OverheadPressCounter,  "Overhead Press"),
    "🧘 Sit-Up":         (SitupCounter,           "Sit-Up"),
    "🤸 Crunch":         (CrunchCounter,          "Crunch"),
    "🦿 Leg Raise":      (LegRaiseCounter,        "Leg Raise"),
    "🦵 Knee Raise":     (KneeRaiseCounter,       "Knee Raise"),
    "🦵 Knee Press":     (KneePressCounter,       "Knee Press"),
}

RTC_CONFIG = RTCConfiguration({"iceServers": [{"urls": ["stun:stun.l.google.com:19302"]}]})

FEEDBACK_EMOJI   = {"Up": "⬆️", "Down": "⬇️", "Fix Form": "⚠️", "Get in Position": "📍"}
FEEDBACK_COLOUR  = {"Up": "#10b981", "Down": "#3b82f6", "Fix Form": "#ef4444", "Get in Position": "#9ca3af"}
MUSCLE_COLOURS   = {"Arms": "#6366f1", "Chest": "#ef4444", "Back": "#f59e0b",
                    "Legs": "#10b981", "Shoulders": "#3b82f6", "Core": "#8b5cf6"}

BASE_MET = {
    "Bicep Curl":     3.0,
    "Push-Up":        8.0,
    "Pull-Up":        9.0,
    "Squat":          5.5,
    "Lateral Raise":  3.0,
    "Overhead Press": 4.5,
    "Sit-Up":         4.0,
    "Crunch":         3.8,
    "Leg Raise":      3.5,
    "Knee Raise":     3.5,
    "Knee Press":     4.0,
}

def _calc_calories(display_name: str, reps: int, set_time_s: float,
                   body_weight_kg: float, lifted_weight_kg: float) -> float:
    """Standard MET calorie formula with weight adjustment."""
    if body_weight_kg <= 0 or set_time_s <= 0:
        return 0.0
    base = BASE_MET.get(display_name, 4.0)
    ratio = (lifted_weight_kg / body_weight_kg) * 0.2 if body_weight_kg > 0 else 0.0
    adjusted_met = base * (1.0 + ratio)
    set_time_h = set_time_s / 3600.0
    return round(adjusted_met * body_weight_kg * set_time_h, 2)

st.set_page_config(page_title="ActionCount", page_icon="🏋️", layout="wide",
                   initial_sidebar_state="expanded")


# ── CSS ────────────────────────────────────────────────────────────────────────
def inject_css():
    st.markdown("""
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700;800&display=swap');
    html,body,[class*="css"]{font-family:'Inter',sans-serif;}
    [data-testid="stAppViewContainer"]{
        background:radial-gradient(ellipse at 20% 10%,#0f172a 0%,#0a0e1a 60%,#050810 100%);
        color:#f1f5f9;}
    [data-testid="stHeader"]{background:transparent;}
    [data-testid="stSidebar"]{
        background:linear-gradient(180deg,#111827 0%,#0f1623 100%);
        border-right:1px solid rgba(99,102,241,0.15);}
    [data-testid="stSidebarNav"]{display:none;}
    .stButton>button{
        background:linear-gradient(135deg,#6366f1,#8b5cf6)!important;
        color:#fff!important;border:none!important;border-radius:10px!important;
        font-weight:600!important;transition:all 0.2s ease!important;
        box-shadow:0 4px 18px rgba(99,102,241,0.28)!important;}
    .stButton>button:hover{transform:translateY(-1px)!important;
        box-shadow:0 6px 24px rgba(99,102,241,0.45)!important;}
    .stButton>button[kind="primary"]{
        background:linear-gradient(135deg,#10b981,#059669)!important;
        box-shadow:0 4px 18px rgba(16,185,129,0.28)!important;}
    [data-testid="stSelectbox"]>div>div{
        background:rgba(255,255,255,0.05)!important;
        border:1px solid rgba(99,102,241,0.25)!important;
        border-radius:10px!important;color:#f1f5f9!important;}
    [data-testid="stTextInput"]>div>div>input{
        background:rgba(255,255,255,0.05)!important;
        border:1px solid rgba(255,255,255,0.10)!important;
        border-radius:10px!important;color:#f1f5f9!important;}
    [data-testid="stNumberInput"]>div>div>input{
        background:rgba(255,255,255,0.05)!important;
        border:1px solid rgba(255,255,255,0.10)!important;
        border-radius:10px!important;color:#f1f5f9!important;}
    .stat-card{background:rgba(255,255,255,0.035);border:1px solid rgba(255,255,255,0.08);
        border-radius:16px;padding:22px 20px;backdrop-filter:blur(12px);margin-bottom:14px;}
    .stat-label{font-size:0.72rem;font-weight:600;letter-spacing:0.1em;
        text-transform:uppercase;color:#6b7280;margin-bottom:6px;}
    .stat-value{font-size:3.5rem;font-weight:800;line-height:1;color:#10b981;
        font-variant-numeric:tabular-nums;}
    .stat-value-sm{font-size:1.6rem;font-weight:700;line-height:1.2;}
    .stProgress>div>div>div>div{
        background:linear-gradient(90deg,#6366f1,#10b981)!important;border-radius:8px!important;}
    hr{border-color:rgba(255,255,255,0.07)!important;}
    ::-webkit-scrollbar{width:5px;}
    ::-webkit-scrollbar-thumb{background:#374151;border-radius:4px;}
    ::-webkit-scrollbar-thumb:hover{background:#6366f1;}
    </style>""", unsafe_allow_html=True)


# ── Session state init ─────────────────────────────────────────────────────────
def _init_state():
    now = datetime.now()
    defaults = {
        "logged_in": False, "username": "", "onboarding_done": False,
        "page": "tracker",
        "last_exercise": list(EXERCISES.keys())[0],
        "counter_obj": None,
        "chat_history": [],
        # Dashboard calendar navigation
        "_dashboard_year":  now.year,
        "_dashboard_month": now.month,
        # Upload video UX
        "_upload_running":      False,
        "_upload_final_reps":   0,
        "_upload_exercise":     "",
        "_upload_completed_at": 0.0,
        # Weight inputs
        "_webcam_weight_kg":  0.0,
        "_upload_weight_kg":  0.0,
    }
    for k, v in defaults.items():
        if k not in st.session_state:
            st.session_state[k] = v


# ═══════════════════════════════════════════════════════════════════════════════
# AUTH PAGES
# ═══════════════════════════════════════════════════════════════════════════════

def render_login_page(cookie_manager=None):
    st.markdown("""
    <div style="text-align:center;padding:40px 0 20px;">
        <div style="font-size:3.5rem;margin-bottom:8px;">🏋️</div>
        <h1 style="font-size:2.2rem;font-weight:800;
            background:linear-gradient(135deg,#6366f1,#10b981);
            -webkit-background-clip:text;-webkit-text-fill-color:transparent;margin:0;">
            ActionCount</h1>
        <p style="color:#6b7280;margin-top:6px;">Your AI-powered fitness companion</p>
    </div>""", unsafe_allow_html=True)

    col = st.columns([1, 1.4, 1])[1]
    with col:
        tab_login, tab_signup = st.tabs(["Sign In", "Create Account"])

        # ── Sign In ────────────────────────────────────────────────────────────
        with tab_login:
            with st.form("login_form"):
                login_email = st.text_input("Email", placeholder="you@example.com", key="li_email")
                login_pwd   = st.text_input("Password", type="password",
                                            placeholder="Enter a Password", key="li_pwd")
                submitted = st.form_submit_button("Sign In", use_container_width=True)
                if submitted:
                    if not login_email or not login_pwd:
                        st.error("Please fill in all fields.")
                    else:
                        _do_login(login_email, login_pwd, cookie_manager)

        # ── Create Account ─────────────────────────────────────────────────────
        with tab_signup:
            # Password-rules hover tooltip (CSS-only, works in st.markdown)
            st.markdown("""<style>
._pwi{display:inline-block;position:relative;cursor:help;vertical-align:middle;}
._pwi ._pwt{display:none;position:absolute;left:20px;top:-6px;z-index:9999;
    background:#1e293b;border:1px solid rgba(255,255,255,.12);border-radius:8px;
    padding:10px 13px;width:215px;font-size:.7rem;line-height:1.65;
    color:#cbd5e1;white-space:normal;box-shadow:0 8px 32px rgba(0,0,0,.5);}
._pwi:hover ._pwt{display:block;}
._pwib{display:inline-flex;align-items:center;justify-content:center;
    width:14px;height:14px;border-radius:50%;border:1px solid #6b7280;
    color:#6b7280;font-size:9px;font-weight:700;line-height:1;user-select:none;}
</style>
<span class="_pwi">
  <span class="_pwib">i</span>
  <span class="_pwt">
    <strong style="color:#a5b4fc;display:block;margin-bottom:4px;">Password must include:</strong>
    &bull; At least 12 characters<br>
    &bull; One uppercase letter (A&ndash;Z)<br>
    &bull; One lowercase letter (a&ndash;z)<br>
    &bull; One digit (0&ndash;9)<br>
    &bull; One special character (!@#$&amp;&hellip;)
  </span>
</span>
<span style="font-size:0.73rem;color:#6b7280;margin-left:5px;">
  Hover <b>i</b> to see password rules
</span>""", unsafe_allow_html=True)

            with st.form("signup_form", clear_on_submit=False):
                new_user  = st.text_input("Username", placeholder="Enter a Username", key="su_user")
                new_email = st.text_input("Email *",   placeholder="you@example.com",  key="su_email")
                new_pwd   = st.text_input(
                    "Password *", type="password",
                    placeholder="Enter a Password",
                    key="su_pwd",
                    help="Min 12 chars · uppercase · digit · special character",
                )
                submitted2 = st.form_submit_button("Create Account", use_container_width=True)

            if submitted2:
                if not new_user or not new_email or not new_pwd:
                    st.error("Username, email and password are all required.")
                elif len(new_pwd) < 12:
                    st.error("Password must be at least 12 characters.")
                elif not any(c.isupper() for c in new_pwd):
                    st.error("Password must contain at least one uppercase letter.")
                elif not any(c.isdigit() for c in new_pwd):
                    st.error("Password must contain at least one digit.")
                elif not any(c in '!@#$%^&*()-_=+[]{}|;:\'",./\\<>?' for c in new_pwd):
                    st.error("Password must contain at least one special character.")
                elif db.get_user(new_user):
                    st.error("Username already taken. Please choose a different one.")
                elif db.get_user_by_email(new_email):
                    st.error("An account with this email already exists. Try signing in instead.")
                else:
                    db.create_user(new_user, _hash_pw(new_pwd), new_email)
                    st.session_state.username        = new_user
                    st.session_state.logged_in       = True
                    st.session_state.onboarding_done = False
                    # Write cookie so reload keeps the session
                    if cookie_manager is not None:
                        token = _create_auth_token(new_user)
                        cookie_manager.set(AUTH_COOKIE_NAME, token,
                                           max_age=AUTH_COOKIE_EXPIRY * 86400)
                    st.rerun()

def _do_login(email: str, password: str, cookie_manager=None):
    """Look up user by email, verify password, set session state and cookie."""
    username = db.get_username_by_email(email)
    if username is None:
        st.error("Incorrect email or password.")
        return
    user = db.get_user(username)
    if not user or not _verify_pw(password, user["hashed_password"]):
        st.error("Incorrect email or password.")
        return
    st.session_state.username        = username
    st.session_state.logged_in       = True
    st.session_state.onboarding_done = user.get("onboarding_complete", False)
    # Persist login in cookie so reload doesn't log the user out
    if cookie_manager is not None:
        token = _create_auth_token(username)
        cookie_manager.set(AUTH_COOKIE_NAME, token,
                           max_age=AUTH_COOKIE_EXPIRY * 86400)
    st.rerun()


# ═══════════════════════════════════════════════════════════════════════════════
# ONBOARDING PAGE
# ═══════════════════════════════════════════════════════════════════════════════

def render_onboarding_page():
    st.markdown("""
    <div style="text-align:center;padding:24px 0 8px;">
        <span style="font-size:2.5rem;">🎯</span>
        <h2 style="font-weight:800;color:#f1f5f9;margin:8px 0 4px;">Tell us about yourself</h2>
        <p style="color:#6b7280;font-size:0.9rem;">This personalizes your AI coach & recommendations</p>
    </div>""", unsafe_allow_html=True)

    col = st.columns([1, 2, 1])[1]
    with col:
        with st.form("onboarding_form"):
            c1, c2 = st.columns(2)
            with c1:
                weight = st.number_input("Weight (kg)", min_value=1.0, max_value=500.0,
                                         value=70.0, step=0.5)
                age    = st.number_input("Age", min_value=1, max_value=120, value=25)
            with c2:
                height = st.number_input("Height (cm)", min_value=1.0, max_value=300.0,
                                         value=175.0, step=0.5)
                gender = st.selectbox("Gender", ["male", "female", "other"])

            target = st.selectbox("Fitness Goal", {
                "weight_loss":     "🔥 Weight Loss",
                "muscle_gain":     "💪 Muscle Gain",
                "endurance":       "🏃 Endurance",
                "general_fitness": "⚡ General Fitness",
            }.keys(), format_func=lambda x: {
                "weight_loss": "🔥 Weight Loss", "muscle_gain": "💪 Muscle Gain",
                "endurance": "🏃 Endurance", "general_fitness": "⚡ General Fitness",
            }[x])

            restrictions = st.multiselect(
                "Dietary Restrictions",
                ["Vegetarian", "Vegan", "Gluten-Free", "Dairy-Free",
                 "Nut Allergy", "Halal", "Keto"],
                help="Select all that apply",
            )

            if st.form_submit_button("🚀 Get Started", use_container_width=True, type="primary"):
                profile = {
                    "weight_kg": weight, "height_cm": height,
                    "age": age, "gender": gender, "target": target,
                    "dietary_restrictions": [r.lower().replace("-", "_").replace(" ", "_")
                                             for r in restrictions],
                }
                db.update_user_profile(st.session_state.username, profile)
                st.session_state.onboarding_done = True
                st.success("Profile saved! Welcome 🎉")
                st.rerun()

# ═══════════════════════════════════════════════════════════════════════════════
# app.py  — PART 2 OF 3: Sidebar · VideoProcessor · Tracker Page
# Paste this AFTER Part 1 in the final app.py
# ═══════════════════════════════════════════════════════════════════════════════


# ── WebRTC Video Processor ────────────────────────────────────────────────────
class ExerciseVideoProcessor(VideoProcessorBase):
    def __init__(self):
        self.counter_obj = None
        self._lock = threading.Lock()
        self._last_stats = {"counter": 0, "feedback": "Get in Position",
                            "progress": 0.0, "correct_form": False}

    def recv(self, frame: av.VideoFrame) -> av.VideoFrame:
        img = frame.to_ndarray(format="bgr24")
        if self.counter_obj is not None:
            result = self.counter_obj.process_frame(img)
            with self._lock:
                self._last_stats = {k: v for k, v in result.items() if k != "frame"}
            return av.VideoFrame.from_ndarray(result["frame"], format="bgr24")
        return frame

    def get_stats(self):
        with self._lock:
            return dict(self._last_stats)


# ── Sidebar ───────────────────────────────────────────────────────────────────
def render_sidebar():
    with st.sidebar:
        st.markdown("""
        <div style="display:flex;align-items:center;gap:10px;padding:8px 0 20px;
            border-bottom:1px solid rgba(255,255,255,0.07);margin-bottom:16px;">
            <span style="font-size:1.6rem;">🏋️</span>
            <h1 style="font-size:1.15rem;font-weight:700;margin:0;
                background:linear-gradient(135deg,#6366f1,#10b981);
                -webkit-background-clip:text;-webkit-text-fill-color:transparent;">
                ActionCount</h1>
        </div>""", unsafe_allow_html=True)

        # Username display
        st.markdown(f"<p style='color:#6b7280;font-size:0.8rem;margin-bottom:12px;'>👤 {st.session_state.username}</p>",
                    unsafe_allow_html=True)

        # Page navigation
        st.markdown("**Navigation**")
        pages = {"🎯 Tracker": "tracker", "📊 Dashboard": "dashboard", "🤖 AI Coach": "chatbot", "📏 Metrics": "metrics"}
        for label, key in pages.items():
            active = st.session_state.page == key
            if st.button(label, use_container_width=True,
                         type="primary" if active else "secondary"):
                st.session_state.page = key
                st.rerun()

        st.divider()

        if st.session_state.page == "tracker":
            exercise_name = st.selectbox("**Exercise**", list(EXERCISES.keys()),
                                         key="exercise_select")
            mode = st.radio("**Input Mode**",
                            ["📸 Live Webcam", "📁 Upload Video"], key="mode_select")
            st.divider()

            c1, c2 = st.columns(2)
            with c1:
                if st.button("🔄 Reset", use_container_width=True):
                    if st.session_state.counter_obj:
                        st.session_state.counter_obj.reset()
                    st.toast("Counter reset!", icon="✅")
            with c2:
                if st.button("🆕 New", use_container_width=True):
                    cls, _ = EXERCISES[exercise_name]
                    st.session_state.counter_obj = cls()
                    st.session_state.last_exercise = exercise_name
                    st.toast(f"Started {exercise_name}!", icon="🏁")
        else:
            exercise_name, mode = None, None

        st.divider()
        if st.button("🚪 Logout", use_container_width=True):
            # Remove auth cookie so reload doesn't auto-login
            ctrl = st.session_state.get("_cookie_manager")
            if ctrl is not None:
                try:
                    ctrl.remove(AUTH_COOKIE_NAME)
                except Exception:
                    pass
            for k in list(st.session_state.keys()):
                del st.session_state[k]
            st.rerun()

    return exercise_name, mode


# ── Stats panel helper ────────────────────────────────────────────────────────
def render_stats_panel(counter, feedback, progress, correct_form):
    fb_colour = FEEDBACK_COLOUR.get(feedback, "#9ca3af")
    fb_emoji  = FEEDBACK_EMOJI.get(feedback, "")
    st.markdown(f"""
    <div class="stat-card" style="border-color:rgba(16,185,129,0.25);">
        <div class="stat-label">Reps This Session</div>
        <div class="stat-value">{counter}</div>
    </div>
    <div class="stat-card" style="border-color:{fb_colour}44;">
        <div class="stat-label">Form Feedback</div>
        <div class="stat-value-sm" style="color:{fb_colour};">{fb_emoji} {feedback}</div>
    </div>""", unsafe_allow_html=True)
    st.progress(int(progress) / 100)
    st.caption(f"{int(progress)}% complete")
    if correct_form:
        st.success("✅ Form Unlocked")
    else:
        st.info("📍 Get in Position")


# ═══════════════════════════════════════════════════════════════════════════════
# TRACKER PAGE
# ═══════════════════════════════════════════════════════════════════════════════

def render_tracker_page(exercise_name, mode):
    # Lazy init counter
    if ("counter_obj" not in st.session_state or st.session_state.counter_obj is None
            or st.session_state.get("last_exercise") != exercise_name):
        cls, _ = EXERCISES[exercise_name]
        st.session_state.counter_obj  = cls()
        st.session_state.last_exercise = exercise_name

    st.markdown("""
    <div style="text-align:center;padding:12px 0 4px;">
        <h1 style="font-size:2.2rem;font-weight:800;
            background:linear-gradient(135deg,#6366f1,#10b981);
            -webkit-background-clip:text;-webkit-text-fill-color:transparent;margin-bottom:4px;">
            SmartSpotter</h1>
        <p style="color:#6b7280;font-size:0.9rem;">Rep counting powered by MediaPipe Pose Estimation</p>
    </div>""", unsafe_allow_html=True)

    if "Webcam" in mode:
        _render_webcam(exercise_name)
    else:
        _render_upload(exercise_name)


def _render_webcam(exercise_name):
    vid_col, stats_col = st.columns([3, 1], gap="large")
    with vid_col:
        st.markdown(f"### {exercise_name}")
        ctx = webrtc_streamer(
            key=f"exercise-{exercise_name}",
            mode=WebRtcMode.SENDRECV,
            video_processor_factory=ExerciseVideoProcessor,
            rtc_configuration=RTC_CONFIG,
            media_stream_constraints={"video": True, "audio": False},
            async_processing=True,
        )
        if ctx.video_processor:
            ctx.video_processor.counter_obj = st.session_state.counter_obj

    with stats_col:
        st.markdown("### 📊 Stats")

        # Weight input for volume tracking
        weight_kg = st.number_input(
            "🏋️ Weight used (kg)", min_value=0.0, max_value=500.0,
            value=st.session_state.get("_webcam_weight_kg", 0.0),
            step=0.5, key="webcam_weight_input",
            help="Enter 0 for bodyweight exercises"
        )
        st.session_state["_webcam_weight_kg"] = weight_kg

        # Save Set button at the TOP for quick access — reads live stats
        _, display_name = EXERCISES[exercise_name]

        # Form feedback and progress below the save button
        stats = {"counter": 0, "feedback": "Get in Position", "progress": 0.0, "correct_form": False}
        if ctx.state.playing and ctx.video_processor:
            stats = ctx.video_processor.get_stats()
        reps = int(stats.get("counter", 0))

        fb_colour = FEEDBACK_COLOUR.get(stats["feedback"], "#9ca3af")
        fb_emoji  = FEEDBACK_EMOJI.get(stats["feedback"], "")
        st.markdown(f"""
        <div class="stat-card" style="border-color:rgba(16,185,129,0.35);text-align:center;margin-bottom:8px;">
            <div class="stat-label">Reps This Session</div>
            <div class="stat-value">{reps}</div>
        </div>""", unsafe_allow_html=True)
        if weight_kg > 0:
            volume_preview = reps * weight_kg
            st.caption(f"📦 Volume: {reps} × {weight_kg}kg = **{volume_preview:.1f} kg**")
        if st.button(f"✅ Save Set ({reps} reps)", use_container_width=True,
                     type="primary", disabled=(reps == 0), key="save_set_top"):
            # Estimate set time: ~3s per rep (reasonable default for Streamlit)
            est_set_time_s = reps * 3.0
            user_profile = db.get_user_profile(st.session_state.username) or {}
            body_weight  = float(user_profile.get("weight_kg", 70.0))
            cal = _calc_calories(display_name, reps, est_set_time_s, body_weight, weight_kg)
            db.save_workout(st.session_state.username, display_name, reps, 1,
                            weight_kg=weight_kg if weight_kg > 0 else None,
                            calories_burnt=cal if cal > 0 else None)
            cal_str = f" · ~{cal:.0f} kcal" if cal > 0 else ""
            st.toast(f"Saved {reps} reps of {display_name}{cal_str}!", icon="💾")
            if cal > 0:
                st.session_state["_last_set_calories"] = cal
            if st.session_state.counter_obj:
                st.session_state.counter_obj.reset()

        st.divider()
        st.markdown(f"""
        <div class="stat-card" style="border-color:{fb_colour}44;">
            <div class="stat-label">Form Feedback</div>
            <div class="stat-value-sm" style="color:{fb_colour};">{fb_emoji} {stats["feedback"]}</div>
        </div>""", unsafe_allow_html=True)
        st.progress(int(stats["progress"]) / 100)
        st.caption(f"{int(stats['progress'])}% complete")
        if stats["correct_form"]:
            st.success("✅ Form Unlocked")
        else:
            st.info("📍 Get in Position")

        # Auto-refresh every 1 second while camera is active
        import time as _t
        if ctx.state.playing:
            _t.sleep(1)
            st.rerun()



def _render_upload(exercise_name):
    import time as _time
    st.markdown(f"### {exercise_name} — Video Analysis")

    # Weight input for volume tracking
    weight_kg = st.number_input(
        "🏋️ Weight used (kg)", min_value=0.0, max_value=500.0,
        value=st.session_state.get("_upload_weight_kg", 0.0),
        step=0.5, key="upload_weight_input",
        help="Enter 0 for bodyweight exercises"
    )
    st.session_state["_upload_weight_kg"] = weight_kg

    uploaded = st.file_uploader("Drop a workout video here",
                                type=["mp4", "avi", "mov", "mkv"], key="video_upload")
    if not uploaded:
        st.info("📁 Upload a video to analyse your exercise form and count reps.")
        # Clear any stale state when a new file hasn't been dropped yet
        st.session_state["_upload_final_reps"]   = 0
        st.session_state["_upload_running"]      = False
        st.session_state["_upload_completed_at"] = 0.0
        return

    # ── Auto-commit check (60-second timer, fires on next Streamlit rerun) ────
    stored_reps = st.session_state.get("_upload_final_reps", 0)
    completed_at = st.session_state.get("_upload_completed_at", 0.0)
    if stored_reps > 0 and completed_at > 0 and (_time.time() - completed_at) >= 60:
        stored_ex = st.session_state.get("_upload_exercise", exercise_name)
        _, dn = EXERCISES.get(stored_ex, (None, stored_ex))
        db.save_workout(st.session_state.username, dn, stored_reps, 1)
        st.toast(f"⏱️ Auto-saved {stored_reps} reps of {dn}!", icon="💾")
        st.session_state["_upload_final_reps"]   = 0
        st.session_state["_upload_completed_at"] = 0.0
        stored_reps = 0

    vid_col, stats_col = st.columns([3, 1], gap="large")
    with vid_col:
        frame_ph = st.empty()
        prog_ph  = st.empty()
    with stats_col:
        st.markdown("### 📊 Analysis")
        counter_ph  = st.empty()
        feedback_ph = st.empty()
        form_ph     = st.empty()

    running = st.session_state.get("_upload_running", False)

    if st.button("▶ Start Analysis", type="primary", use_container_width=True,
                 disabled=running):
        # Auto-save any unsaved result from a previous analysis
        if stored_reps > 0:
            prev_ex = st.session_state.get("_upload_exercise", exercise_name)
            _, dn = EXERCISES.get(prev_ex, (None, prev_ex))
            db.save_workout(st.session_state.username, dn, stored_reps, 1)
            st.toast(f"Auto-saved previous {stored_reps} reps of {dn}!", icon="💾")

        obj = st.session_state.counter_obj
        obj.reset()
        st.session_state["_upload_final_reps"]   = 0
        st.session_state["_upload_exercise"]     = exercise_name
        st.session_state["_upload_weight_kg"]    = weight_kg
        st.session_state["_upload_running"]      = True
        st.session_state["_upload_completed_at"] = 0.0

        with tempfile.NamedTemporaryFile(delete=False, suffix=".mp4") as tmp:
            tmp.write(uploaded.getvalue())
            tmp_path = tmp.name

        cap   = cv2.VideoCapture(tmp_path)
        total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT)) or 1
        src_fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
        idx   = 0
        rep_timestamps = []   # track time when each rep is completed
        last_count = 0
        try:
            while cap.isOpened():
                ret, frame = cap.read()
                if not ret:
                    break
                result = obj.process_frame(frame)
                # Track rep timestamps
                cur_count = int(result.get("counter", 0))
                if cur_count > last_count:
                    rep_timestamps.append(idx / src_fps)
                    last_count = cur_count
                rgb    = cv2.cvtColor(result["frame"], cv2.COLOR_BGR2RGB)
                frame_ph.image(rgb, channels="RGB", use_container_width=True)
                prog_ph.progress(idx / total, text=f"Frame {idx}/{total}")
                fb_c = FEEDBACK_COLOUR.get(result["feedback"], "#9ca3af")
                fb_e = FEEDBACK_EMOJI.get(result["feedback"], "")
                with counter_ph.container():
                    st.markdown(f"""<div class="stat-card">
                        <div class="stat-label">Reps</div>
                        <div class="stat-value">{result['counter']}</div></div>""",
                                unsafe_allow_html=True)
                with feedback_ph.container():
                    st.markdown(f"""<div class="stat-card" style="border-color:{fb_c}44;">
                        <div class="stat-label">Feedback</div>
                        <div class="stat-value-sm" style="color:{fb_c};">{fb_e} {result['feedback']}</div>
                        </div>""", unsafe_allow_html=True)
                idx += 1
        finally:
            cap.release()
            os.unlink(tmp_path)

        # Compute set_time from rep timestamps
        if len(rep_timestamps) >= 2:
            set_time_s = rep_timestamps[-1] - rep_timestamps[0]
        elif rep_timestamps:
            set_time_s = rep_timestamps[0]
        else:
            set_time_s = idx / src_fps

        prog_ph.empty()
        final_reps = int(obj.counter)
        st.session_state["_upload_final_reps"]   = final_reps
        st.session_state["_upload_running"]      = False
        st.session_state["_upload_completed_at"] = _time.time()
        st.session_state["_upload_set_time_s"]   = set_time_s

        # Calculate and show calories
        _, _dn = EXERCISES.get(exercise_name, (None, exercise_name))
        _profile = db.get_user_profile(st.session_state.username) or {}
        _bw = float(_profile.get("weight_kg", 70.0))
        _cal = _calc_calories(_dn, final_reps, set_time_s, _bw, weight_kg)
        st.session_state["_upload_calories"] = _cal
        cal_str = f" · ~{_cal:.0f} kcal burnt" if _cal > 0 else ""
        form_ph.success(f"✅ Done — **{final_reps} reps** detected!{cal_str}")

    stored_reps  = st.session_state.get("_upload_final_reps", 0)
    stored_ex    = st.session_state.get("_upload_exercise", exercise_name)
    stored_w     = st.session_state.get("_upload_weight_kg", 0.0)
    stored_cal   = st.session_state.get("_upload_calories", 0.0)
    completed_at = st.session_state.get("_upload_completed_at", 0.0)
    if stored_reps > 0:
        _, display_name = EXERCISES.get(stored_ex, (None, stored_ex))
        elapsed = int(_time.time() - completed_at) if completed_at > 0 else 0
        remaining = max(0, 60 - elapsed)
        if stored_w > 0:
            st.caption(f"📦 Volume: {stored_reps} × {stored_w}kg = **{stored_reps * stored_w:.1f} kg**")
        if stored_cal > 0:
            st.markdown(f"""<div class="stat-card" style="border-color:rgba(239,68,68,0.25);text-align:center;">
                <div class="stat-label">🔥 Calories Burnt (Est.)</div>
                <div class="stat-value" style="color:#ef4444;">{stored_cal:.0f} <span style="font-size:1rem;color:#6b7280;">kcal</span></div>
            </div>""", unsafe_allow_html=True)
        st.caption(f"⏱️ Auto-saves in {remaining}s if not saved manually.")
        if st.button(f"💾 Save {stored_reps} Reps to History",
                     type="primary", use_container_width=True, key="upload_save_btn"):
            db.save_workout(st.session_state.username, display_name, stored_reps, 1,
                            weight_kg=stored_w if stored_w > 0 else None,
                            calories_burnt=stored_cal if stored_cal > 0 else None)
            st.toast("Workout saved!", icon="✅")
            st.session_state["_upload_final_reps"]   = 0
            st.session_state["_upload_completed_at"] = 0.0
            st.session_state["_upload_calories"]     = 0.0


# ═══════════════════════════════════════════════════════════════════════════════
# DASHBOARD PAGE
# ═══════════════════════════════════════════════════════════════════════════════

def render_dashboard_page():
    st.markdown("""
    <h1 style="font-size:2rem;font-weight:800;color:#f1f5f9;margin-bottom:4px;">📊 Dashboard</h1>
    <p style="color:#6b7280;font-size:0.9rem;margin-bottom:24px;">Your workout history &amp; muscle breakdown</p>
    """, unsafe_allow_html=True)

    username  = st.session_state.username
    year      = st.session_state["_dashboard_year"]
    month     = st.session_state["_dashboard_month"]
    month_str = f"{year}-{month:02d}"

    nav_l, nav_c, nav_r = st.columns([1, 4, 1])
    with nav_l:
        if st.button("‹", use_container_width=True, key="cal_prev"):
            month -= 1
            if month < 1: month = 12; year -= 1
            st.session_state["_dashboard_year"]  = year
            st.session_state["_dashboard_month"] = month
            st.session_state["_selected_date"]   = None
            st.rerun()
    with nav_c:
        st.markdown(
            f"<p style='text-align:center;font-weight:700;font-size:1.05rem;margin:6px 0;'>"
            f"{datetime(year, month, 1).strftime('%B %Y')}</p>",
            unsafe_allow_html=True)
    with nav_r:
        if st.button("›", use_container_width=True, key="cal_next"):
            month += 1
            if month > 12: month = 1; year += 1
            st.session_state["_dashboard_year"]  = year
            st.session_state["_dashboard_month"] = month
            st.session_state["_selected_date"]   = None
            st.rerun()

    history      = db.get_workout_history(username)
    muscle_stats = db.get_monthly_stats(username, month_str)
    total_sets   = db.get_total_sets_month(username, month_str)
    volume_data  = db.get_monthly_volume_by_exercise(username, month_str)
    total_calories = db.get_monthly_calories(username, month_str)

    # Previous month for radar comparison
    prev_m_str = f"{year-1}-12" if month == 1 else f"{year}-{month-1:02d}"
    prev_muscle_stats = db.get_monthly_stats(username, prev_m_str)

    days_trained = [d for d in history if d.startswith(month_str)]
    top_muscle   = max(muscle_stats, key=muscle_stats.get) if any(muscle_stats.values()) else "—"
    total_volume = sum(volume_data.values())

    mc1, mc2, mc3, mc4, mc5 = st.columns(5)
    with mc1:
        st.markdown(f"""<div class="stat-card" style="border-color:rgba(16,185,129,0.25);text-align:center;">
            <div class="stat-label">Days Trained</div>
            <div class="stat-value">{len(days_trained)}</div></div>""", unsafe_allow_html=True)
    with mc2:
        st.markdown(f"""<div class="stat-card" style="border-color:rgba(99,102,241,0.25);text-align:center;">
            <div class="stat-label">Sets Performed</div>
            <div class="stat-value" style="color:#6366f1;">{total_sets:,}</div></div>""", unsafe_allow_html=True)
    with mc3:
        st.markdown(f"""<div class="stat-card" style="border-color:rgba(245,158,11,0.25);text-align:center;">
            <div class="stat-label">Top Muscle</div>
            <div class="stat-value" style="color:#f59e0b;font-size:1.6rem;">{top_muscle}</div></div>""", unsafe_allow_html=True)
    with mc4:
        st.markdown(f"""<div class="stat-card" style="border-color:rgba(139,92,246,0.25);text-align:center;">
            <div class="stat-label">Total Volume</div>
            <div class="stat-value" style="color:#8b5cf6;font-size:1.8rem;">{total_volume:,.0f}<span style="font-size:0.9rem;color:#6b7280;"> kg</span></div></div>""", unsafe_allow_html=True)
    with mc5:
        st.markdown(f"""<div class="stat-card" style="border-color:rgba(239,68,68,0.25);text-align:center;">
            <div class="stat-label">Calories Burnt</div>
            <div class="stat-value" style="color:#ef4444;font-size:1.8rem;">{total_calories:,.0f}<span style="font-size:0.9rem;color:#6b7280;"> kcal</span></div></div>""", unsafe_allow_html=True)

    st.markdown("<br>", unsafe_allow_html=True)
    left_col, right_col = st.columns([3, 2], gap="large")

    with left_col:
        st.markdown("#### 📅 Workout Calendar")
        _render_calendar(history, month_str)
        workout_dates = sorted([d for d in history if d.startswith(month_str)], reverse=True)
        if workout_dates:
            st.markdown("<br>", unsafe_allow_html=True)
            chosen = st.selectbox("🔍 View workout for date", workout_dates,
                                  format_func=lambda d: datetime.strptime(d, "%Y-%m-%d").strftime("%A, %b %d"))
            if chosen and chosen in history:
                _render_day_detail(chosen, history[chosen])

    with right_col:
        st.markdown("#### 🕸️ Muscle Distribution")
        _render_radar_chart(muscle_stats, prev_muscle_stats)
        st.markdown("#### 🫀 Muscle Heatmap")
        _render_svg_heatmap(muscle_stats)

    if volume_data:
        st.markdown("<br>", unsafe_allow_html=True)
        st.markdown("#### 📦 Volume Lifted This Month (kg)")
        _render_volume_chart(volume_data)


def _render_calendar(history, month_str):
    import calendar
    try:
        year, month = map(int, month_str.split("-"))
    except ValueError:
        return
    cal        = calendar.monthcalendar(year, month)
    month_name = datetime(year, month, 1).strftime("%B %Y")
    today_str  = date.today().isoformat()
    rows = [f"<div style='font-size:0.85rem;'><p style='color:#6b7280;margin-bottom:8px;font-weight:600;'>{month_name}</p>"]
    rows.append("<div style='display:grid;grid-template-columns:repeat(7,1fr);gap:4px;'>")
    for dn in ["Sun","Mon","Tue","Wed","Thu","Fri","Sat"]:
        rows.append(f"<div style='text-align:center;color:#4b5563;font-size:0.7rem;padding:4px;'>{dn}</div>")
    for week in cal:
        for day in week:
            if day == 0:
                rows.append("<div></div>"); continue
            date_str = f"{year}-{month:02d}-{day:02d}"
            has_data = date_str in history
            is_today = date_str == today_str
            bg  = "rgba(16,185,129,0.15)" if has_data else "rgba(255,255,255,0.03)"
            bdr = "rgba(16,185,129,0.4)"  if has_data else "rgba(255,255,255,0.07)"
            col = "#10b981" if has_data else "#9ca3af"
            if is_today: bdr = "#6366f1"; col = "#a5b4fc"
            dot = "<br><span style='display:block;width:5px;height:5px;border-radius:50%;background:#10b981;margin:0 auto;'></span>" if has_data else ""
            rows.append(f"<div style='text-align:center;padding:6px 2px;border-radius:6px;"
                        f"background:{bg};border:1px solid {bdr};color:{col};font-weight:500;'>{day}{dot}</div>")
    rows.append("</div></div>")
    st.markdown("".join(rows), unsafe_allow_html=True)


def _render_day_detail(date_str, exercises):
    display = datetime.strptime(date_str, "%Y-%m-%d").strftime("%A, %B %d, %Y")
    st.markdown(f"""<div style="background:rgba(255,255,255,0.04);border:1px solid rgba(255,255,255,0.08);
        border-radius:14px;padding:16px;margin-top:8px;">
        <p style="color:#6b7280;font-size:0.75rem;margin:0 0 12px;">{display}</p>""",
        unsafe_allow_html=True)
    for ex, data in exercises.items():
        sets_list    = db._entry_sets_list(data)
        weights_list = db._entry_weights_list(data)
        n_sets       = len(sets_list)
        total_reps   = sum(sets_list)
        w_list       = list(weights_list) + [0.0] * max(0, n_sets - len(weights_list))
        # Header: only show total reps
        st.markdown(f"""<div style="margin-bottom:10px;padding:10px 14px;border-radius:10px;
            background:rgba(255,255,255,0.03);border:1px solid rgba(255,255,255,0.08);">
            <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:8px;">
                <span style="color:#f1f5f9;font-weight:700;font-size:0.9rem;">{ex}</span>
                <span style="color:#10b981;font-weight:800;font-size:0.85rem;">{total_reps} reps</span>
            </div>""", unsafe_allow_html=True)
        for i, (rep_count, w) in enumerate(zip(sets_list, w_list), 1):
            # Per set: only reps + total set volume (no formula string)
            set_vol_str = f" &middot; {rep_count*w:.1f} kg vol" if w > 0 else ""
            st.markdown(f"""<div style="display:flex;justify-content:space-between;padding:4px 8px;
                border-radius:6px;background:rgba(255,255,255,0.02);margin-bottom:3px;">
                <span style="color:#9ca3af;font-size:0.8rem;">Set {i}</span>
                <span style="color:#d1d5db;font-weight:600;font-size:0.8rem;">{rep_count} reps{set_vol_str}</span>
            </div>""", unsafe_allow_html=True)
        st.markdown("</div>", unsafe_allow_html=True)
    st.markdown("</div>", unsafe_allow_html=True)


def _render_radar_chart(current_stats, prev_stats):
    groups    = ["Arms", "Chest", "Back", "Legs", "Shoulders", "Core"]
    cur_vals  = [current_stats.get(g, 0) for g in groups]
    prev_vals = [prev_stats.get(g, 0)    for g in groups]
    if not any(cur_vals) and not any(prev_vals):
        st.info("No workout data for this month yet."); return
    fig = go.Figure()
    fig.add_trace(go.Scatterpolar(
        r=prev_vals + [prev_vals[0]], theta=groups + [groups[0]],
        fill="toself", name="Previous",
        line=dict(color="#6b7280", width=1.5), fillcolor="rgba(107,114,128,0.12)"))
    fig.add_trace(go.Scatterpolar(
        r=cur_vals + [cur_vals[0]], theta=groups + [groups[0]],
        fill="toself", name="Current",
        line=dict(color="#6366f1", width=2.5), fillcolor="rgba(99,102,241,0.18)"))
    fig.update_layout(
        polar=dict(
            bgcolor="rgba(0,0,0,0)",
            radialaxis=dict(visible=True, showticklabels=False, gridcolor="rgba(255,255,255,0.08)"),
            angularaxis=dict(tickfont=dict(color="#9ca3af", size=11), gridcolor="rgba(255,255,255,0.08)"),
        ),
        paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
        legend=dict(font=dict(color="#9ca3af", size=11), bgcolor="rgba(0,0,0,0)", orientation="h", y=-0.15),
        margin=dict(t=20, b=30, l=20, r=20), height=260,
    )
    st.plotly_chart(fig, use_container_width=True)


def _render_svg_heatmap(muscle_stats):
    groups   = ["Arms", "Chest", "Back", "Legs", "Shoulders", "Core"]
    max_sets = max((muscle_stats.get(g, 0) for g in groups), default=1) or 1

    def _col(muscle):
        v = muscle_stats.get(muscle, 0)
        if v == 0: return "rgba(255,255,255,0.06)"
        alpha = 0.25 + 0.65 * (v / max_sets)
        h = MUSCLE_COLOURS.get(muscle, "#6366f1").lstrip("#")
        r, g2, b = int(h[0:2],16), int(h[2:4],16), int(h[4:6],16)
        return f"rgba({r},{g2},{b},{alpha:.2f})"

    arms  = _col("Arms");  chest = _col("Chest"); back  = _col("Back")
    legs  = _col("Legs");  shold = _col("Shoulders"); core = _col("Core")

    svg = f"""<div style="display:flex;justify-content:center;gap:24px;padding:8px 0;">
<div style="text-align:center;">
  <div style="font-size:0.65rem;color:#4b5563;margin-bottom:4px;letter-spacing:.08em;">FRONT</div>
  <svg viewBox="0 0 120 260" width="100" height="220" xmlns="http://www.w3.org/2000/svg">
    <ellipse cx="60" cy="22" rx="16" ry="19" fill="rgba(255,255,255,0.08)" stroke="rgba(255,255,255,0.15)" stroke-width="1"/>
    <ellipse cx="30" cy="58" rx="16" ry="10" fill="{shold}" stroke="rgba(255,255,255,0.12)" stroke-width="1"/>
    <ellipse cx="90" cy="58" rx="16" ry="10" fill="{shold}" stroke="rgba(255,255,255,0.12)" stroke-width="1"/>
    <rect x="38" y="48" width="44" height="38" rx="6" fill="{chest}" stroke="rgba(255,255,255,0.12)" stroke-width="1"/>
    <rect x="40" y="88" width="40" height="44" rx="5" fill="{core}" stroke="rgba(255,255,255,0.12)" stroke-width="1"/>
    <rect x="13" y="55" width="15" height="42" rx="7" fill="{arms}" stroke="rgba(255,255,255,0.12)" stroke-width="1"/>
    <rect x="92" y="55" width="15" height="42" rx="7" fill="{arms}" stroke="rgba(255,255,255,0.12)" stroke-width="1"/>
    <rect x="10" y="99" width="13" height="36" rx="6" fill="{arms}" stroke="rgba(255,255,255,0.10)" stroke-width="1"/>
    <rect x="97" y="99" width="13" height="36" rx="6" fill="{arms}" stroke="rgba(255,255,255,0.10)" stroke-width="1"/>
    <rect x="40" y="134" width="17" height="58" rx="8" fill="{legs}" stroke="rgba(255,255,255,0.12)" stroke-width="1"/>
    <rect x="63" y="134" width="17" height="58" rx="8" fill="{legs}" stroke="rgba(255,255,255,0.12)" stroke-width="1"/>
    <rect x="41" y="194" width="14" height="46" rx="7" fill="rgba(255,255,255,0.05)" stroke="rgba(255,255,255,0.08)" stroke-width="1"/>
    <rect x="65" y="194" width="14" height="46" rx="7" fill="rgba(255,255,255,0.05)" stroke="rgba(255,255,255,0.08)" stroke-width="1"/>
  </svg>
</div>
<div style="text-align:center;">
  <div style="font-size:0.65rem;color:#4b5563;margin-bottom:4px;letter-spacing:.08em;">BACK</div>
  <svg viewBox="0 0 120 260" width="100" height="220" xmlns="http://www.w3.org/2000/svg">
    <ellipse cx="60" cy="22" rx="16" ry="19" fill="rgba(255,255,255,0.08)" stroke="rgba(255,255,255,0.15)" stroke-width="1"/>
    <ellipse cx="30" cy="58" rx="16" ry="10" fill="{shold}" stroke="rgba(255,255,255,0.12)" stroke-width="1"/>
    <ellipse cx="90" cy="58" rx="16" ry="10" fill="{shold}" stroke="rgba(255,255,255,0.12)" stroke-width="1"/>
    <rect x="34" y="48" width="52" height="50" rx="6" fill="{back}" stroke="rgba(255,255,255,0.12)" stroke-width="1"/>
    <rect x="40" y="98" width="40" height="34" rx="5" fill="{back}" stroke="rgba(255,255,255,0.12)" stroke-width="1"/>
    <rect x="13" y="55" width="15" height="42" rx="7" fill="{arms}" stroke="rgba(255,255,255,0.12)" stroke-width="1"/>
    <rect x="92" y="55" width="15" height="42" rx="7" fill="{arms}" stroke="rgba(255,255,255,0.12)" stroke-width="1"/>
    <rect x="10" y="99" width="13" height="36" rx="6" fill="{arms}" stroke="rgba(255,255,255,0.10)" stroke-width="1"/>
    <rect x="97" y="99" width="13" height="36" rx="6" fill="{arms}" stroke="rgba(255,255,255,0.10)" stroke-width="1"/>
    <rect x="40" y="134" width="17" height="58" rx="8" fill="{legs}" stroke="rgba(255,255,255,0.12)" stroke-width="1"/>
    <rect x="63" y="134" width="17" height="58" rx="8" fill="{legs}" stroke="rgba(255,255,255,0.12)" stroke-width="1"/>
    <rect x="41" y="194" width="14" height="46" rx="7" fill="rgba(255,255,255,0.05)" stroke="rgba(255,255,255,0.08)" stroke-width="1"/>
    <rect x="65" y="194" width="14" height="46" rx="7" fill="rgba(255,255,255,0.05)" stroke="rgba(255,255,255,0.08)" stroke-width="1"/>
  </svg>
</div></div>
<div style="display:flex;flex-wrap:wrap;gap:8px;justify-content:center;margin-top:6px;">"""
    for g in groups:
        c = MUSCLE_COLOURS.get(g, "#6366f1"); n = muscle_stats.get(g, 0)
        svg += f'<span style="font-size:0.7rem;color:#9ca3af;display:flex;align-items:center;gap:4px;"><span style="width:8px;height:8px;border-radius:50%;background:{c};display:inline-block;"></span>{g}: {n}</span>'
    svg += "</div>"
    st.markdown(svg, unsafe_allow_html=True)


def _render_volume_chart(volume_data):
    if not volume_data:
        st.info("No volume data yet — add weight when saving sets."); return
    exercises = list(volume_data.keys())
    volumes   = [volume_data[e] for e in exercises]
    colors    = [MUSCLE_COLOURS.get(db.EXERCISE_MUSCLE_MAP.get(e, ""), "#6366f1") for e in exercises]
    fig = go.Figure(go.Bar(
        x=exercises, y=volumes,
        marker=dict(color=colors, line=dict(color="rgba(0,0,0,0)")),
        text=[f"{v:,.1f} kg" for v in volumes], textposition="outside",
        textfont=dict(color="#9ca3af", size=11),
        hovertemplate="%{x}: %{y:,.1f} kg<extra></extra>",
    ))
    fig.update_layout(
        paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
        yaxis=dict(showgrid=True, gridcolor="rgba(255,255,255,0.06)", color="#6b7280", title="Volume (kg)"),
        xaxis=dict(color="#9ca3af", tickangle=-25),
        margin=dict(t=30, b=60, l=50, r=20), height=280, showlegend=False,
    )
    st.plotly_chart(fig, use_container_width=True)

# ═══════════════════════════════════════════════════════════════════════════════
# METRICS PAGE
# ═══════════════════════════════════════════════════════════════════════════════

def render_metrics_page():
    st.markdown("""
    <h1 style="font-size:2rem;font-weight:800;color:#f1f5f9;margin-bottom:4px;">📏 Body Metrics</h1>
    <p style="color:#6b7280;font-size:0.9rem;margin-bottom:24px;">Track your weight &amp; height over time</p>
    """, unsafe_allow_html=True)

    username = st.session_state.username
    today    = date.today()

    # ── Log new metric ────────────────────────────────────────────────────────
    with st.expander("➕ Log Today's Metrics", expanded=True):
        with st.form("metrics_form"):
            c1, c2, c3 = st.columns(3)
            with c1:
                log_date = st.date_input("Date", value=today, max_value=today, key="metric_date")
            with c2:
                log_weight = st.number_input("Body Weight (kg)", min_value=0.0,
                                             max_value=500.0, value=0.0, step=0.1, key="metric_weight")
            with c3:
                log_height = st.number_input("Height (cm)", min_value=0.0,
                                             max_value=300.0, value=0.0, step=0.1, key="metric_height")
            if st.form_submit_button("💾 Save Metrics", use_container_width=True, type="primary"):
                w = log_weight if log_weight > 0 else None
                h = log_height if log_height > 0 else None
                if w is None and h is None:
                    st.error("Enter at least one value (weight or height).")
                else:
                    try:
                        db.log_metric(username, log_date.isoformat(), w, h)
                        st.success(f"✅ Metrics saved for {log_date.strftime('%B %d, %Y')}!")
                        st.rerun()
                    except ValueError as e:
                        st.error(str(e))

    # ── Load history ──────────────────────────────────────────────────────────
    metrics = db.get_metrics(username)
    if not metrics:
        st.info("No metrics logged yet. Start tracking above! 📈")
        return

    dates   = [m["date"] for m in metrics]
    weights = [m.get("weight_kg") for m in metrics]
    heights = [m.get("height_cm") for m in metrics]

    # ── Weight chart ──────────────────────────────────────────────────────────
    w_pairs = [(d, w) for d, w in zip(dates, weights) if w is not None]
    h_pairs = [(d, h) for d, h in zip(dates, heights) if h is not None]

    chart_col1, chart_col2 = st.columns(2)

    with chart_col1:
        st.markdown("#### ⚖️ Weight Over Time")
        if w_pairs:
            _render_metric_chart(w_pairs, "Weight (kg)", "#10b981")
        else:
            st.info("No weight data logged yet.")

    with chart_col2:
        st.markdown("#### 📐 Height Over Time")
        if h_pairs:
            _render_metric_chart(h_pairs, "Height (cm)", "#6366f1")
        else:
            st.info("No height data logged yet.")

    # ── History table ─────────────────────────────────────────────────────────
    st.markdown("<br>", unsafe_allow_html=True)
    st.markdown("#### 📋 Full History")
    rows_html = ""
    for m in reversed(metrics):
        d  = datetime.strptime(m["date"], "%Y-%m-%d").strftime("%b %d, %Y")
        wt = f"{m['weight_kg']:.1f} kg" if m.get("weight_kg") else "—"
        ht = f"{m['height_cm']:.1f} cm" if m.get("height_cm") else "—"
        rows_html += f"""<div style="display:flex;justify-content:space-between;padding:8px 14px;
            border-radius:8px;background:rgba(255,255,255,0.03);border:1px solid rgba(255,255,255,0.06);margin-bottom:4px;">
            <span style="color:#9ca3af;font-size:0.82rem;">{d}</span>
            <span style="color:#10b981;font-weight:600;font-size:0.82rem;">⚖️ {wt}</span>
            <span style="color:#6366f1;font-weight:600;font-size:0.82rem;">📐 {ht}</span>
        </div>"""
    st.markdown(rows_html, unsafe_allow_html=True)


def _render_metric_chart(pairs, ylabel, color):
    """
    Plot a metric over time.
    Connect points with a line only if consecutive dates differ by ≤ 7 days,
    otherwise show isolated markers.
    """
    if not pairs:
        return
    x_vals = [p[0] for p in pairs]
    y_vals = [p[1] for p in pairs]

    # Build segments: connected where gap ≤ 7 days, gap otherwise
    from datetime import datetime as dt2
    fig = go.Figure()

    seg_x, seg_y = [x_vals[0]], [y_vals[0]]
    for i in range(1, len(x_vals)):
        gap = (dt2.strptime(x_vals[i], "%Y-%m-%d") - dt2.strptime(x_vals[i-1], "%Y-%m-%d")).days
        if gap <= 7:
            seg_x.append(x_vals[i]); seg_y.append(y_vals[i])
        else:
            # Flush current segment
            if len(seg_x) > 1:
                fig.add_trace(go.Scatter(x=seg_x, y=seg_y, mode="lines+markers",
                    line=dict(color=color, width=2.5),
                    marker=dict(color=color, size=7),
                    showlegend=False, hovertemplate="%{x}: %{y}<extra></extra>"))
            else:
                fig.add_trace(go.Scatter(x=seg_x, y=seg_y, mode="markers",
                    marker=dict(color=color, size=9),
                    showlegend=False, hovertemplate="%{x}: %{y}<extra></extra>"))
            seg_x, seg_y = [x_vals[i]], [y_vals[i]]

    # Final segment
    mode = "lines+markers" if len(seg_x) > 1 else "markers"
    fig.add_trace(go.Scatter(x=seg_x, y=seg_y, mode=mode,
        line=dict(color=color, width=2.5),
        marker=dict(color=color, size=7 if len(seg_x) > 1 else 10),
        showlegend=False, hovertemplate="%{x}: %{y}<extra></extra>"))

    fig.update_layout(
        paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
        yaxis=dict(showgrid=True, gridcolor="rgba(255,255,255,0.06)", color="#6b7280", title=ylabel),
        xaxis=dict(type="category", color="#9ca3af", tickangle=-25, showgrid=False),
        margin=dict(t=20, b=50, l=50, r=20), height=260,
    )
    st.plotly_chart(fig, use_container_width=True)


# ═══════════════════════════════════════════════════════════════════════════════
# AI CHATBOT PAGE
# ═══════════════════════════════════════════════════════════════════════════════

def render_chatbot_page():
    st.markdown("""
    <h1 style="font-size:2rem;font-weight:800;color:#f1f5f9;margin-bottom:4px;">🤖 AI Diet Coach</h1>
    <p style="color:#6b7280;font-size:0.9rem;margin-bottom:20px;">
        Personalized nutrition advice powered by Gemini</p>
    """, unsafe_allow_html=True)

    username = st.session_state.username

    if not st.session_state.chat_history:
        st.session_state.chat_history = db.load_chat_history(username)

    col1, col2 = st.columns([6, 1])
    with col2:
        if st.button("🗑 Clear", use_container_width=True):
            db.clear_chat_history(username)
            st.session_state.chat_history = []
            st.rerun()

    chat_container = st.container(height=450)
    with chat_container:
        if not st.session_state.chat_history:
            st.markdown("""<div style="text-align:center;padding:40px;color:#4b5563;">
                <div style="font-size:2.5rem;margin-bottom:12px;">🤖</div>
                <p style="margin:0;">Hi! I'm <strong style="color:#a5b4fc;">ActionBot</strong>.
                Ask me about meal plans, macros, supplements, or recovery!</p>
            </div>""", unsafe_allow_html=True)
        else:
            for msg in st.session_state.chat_history:
                with st.chat_message(msg["role"], avatar="🧑" if msg["role"]=="user" else "🤖"):
                    st.markdown(msg["content"])

    if not st.session_state.chat_history:
        st.markdown("**Try asking:**")
        c1, c2 = st.columns(2)
        prompts = [
            "Give me a high-protein meal plan",
            "What to eat before a workout?",
            "How many calories should I eat daily?",
            "Suggest a post leg-day meal",
        ]
        for i, prompt in enumerate(prompts):
            with (c1 if i % 2 == 0 else c2):
                if st.button(f"💬 {prompt}", use_container_width=True, key=f"prompt_{i}"):
                    _send_chat_message(username, prompt); st.rerun()

    user_input = st.chat_input("Ask about meal plans, nutrition, recovery…")
    if user_input:
        _send_chat_message(username, user_input); st.rerun()


def _send_chat_message(username, message):
    db.append_chat_message(username, "user", message)
    st.session_state.chat_history.append({"role": "user", "content": message})
    with st.spinner("ActionBot is thinking…"):
        reply = _get_response(username, message)
    db.append_chat_message(username, "assistant", reply)
    st.session_state.chat_history.append({"role": "assistant", "content": reply})


# ═══════════════════════════════════════════════════════════════════════════════
# MAIN ENTRY POINT
# ═══════════════════════════════════════════════════════════════════════════════

def main():
    inject_css()
    _init_state()

    ctrl = CookieController()
    st.session_state["_cookie_manager"] = ctrl

    if not st.session_state.logged_in:
        token = ctrl.get(AUTH_COOKIE_NAME)
        if token:
            username = _decode_auth_token(token)
            if username:
                user = db.get_user(username)
                if user:
                    st.session_state.username        = username
                    st.session_state.logged_in       = True
                    st.session_state.onboarding_done = user.get("onboarding_complete", False)

    if not st.session_state.logged_in:
        render_login_page(cookie_manager=ctrl); return

    if not st.session_state.onboarding_done:
        render_onboarding_page(); return

    exercise_name, mode = render_sidebar()

    page = st.session_state.page
    if page == "tracker":
        render_tracker_page(exercise_name, mode)
    elif page == "dashboard":
        render_dashboard_page()
    elif page == "chatbot":
        render_chatbot_page()
    elif page == "metrics":
        render_metrics_page()


if __name__ == "__main__":
    main()