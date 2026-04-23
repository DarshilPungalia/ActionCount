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
        pages = {"🎯 Tracker": "tracker", "📊 Dashboard": "dashboard", "🤖 AI Coach": "chatbot"}
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

        # Save Set button at the TOP for quick access — no scrolling needed
        reps = int(st.session_state.counter_obj.counter) if st.session_state.counter_obj else 0
        _, display_name = EXERCISES[exercise_name]
        st.markdown(f"""
        <div class="stat-card" style="border-color:rgba(16,185,129,0.35);text-align:center;margin-bottom:8px;">
            <div class="stat-label">Reps This Session</div>
            <div class="stat-value">{reps}</div>
        </div>""", unsafe_allow_html=True)
        if st.button(f"✅ Save Set ({reps} reps)", use_container_width=True,
                     type="primary", disabled=(reps == 0), key="save_set_top"):
            db.save_workout(st.session_state.username, display_name, reps, 1)
            st.toast(f"Saved {reps} reps of {display_name}!", icon="💾")
            if st.session_state.counter_obj:
                st.session_state.counter_obj.reset()

        st.divider()

        # Form feedback and progress below the save button
        stats = {"counter": 0, "feedback": "Get in Position", "progress": 0.0, "correct_form": False}
        if ctx.state.playing and ctx.video_processor:
            stats = ctx.video_processor.get_stats()

        fb_colour = FEEDBACK_COLOUR.get(stats["feedback"], "#9ca3af")
        fb_emoji  = FEEDBACK_EMOJI.get(stats["feedback"], "")
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

        if st.button("🔄 Refresh Stats", use_container_width=True):
            st.rerun()



def _render_upload(exercise_name):
    import time as _time
    st.markdown(f"### {exercise_name} — Video Analysis")
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
        st.session_state["_upload_running"]      = True
        st.session_state["_upload_completed_at"] = 0.0

        with tempfile.NamedTemporaryFile(delete=False, suffix=".mp4") as tmp:
            tmp.write(uploaded.getvalue())
            tmp_path = tmp.name

        cap   = cv2.VideoCapture(tmp_path)
        total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT)) or 1
        idx   = 0
        try:
            while cap.isOpened():
                ret, frame = cap.read()
                if not ret:
                    break
                result = obj.process_frame(frame)
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

        prog_ph.empty()
        final_reps = int(obj.counter)
        st.session_state["_upload_final_reps"]   = final_reps
        st.session_state["_upload_running"]      = False
        st.session_state["_upload_completed_at"] = _time.time()
        form_ph.success(f"✅ Done — **{final_reps} reps** detected!")

    # ── Persistent Save button + countdown hint ────────────────────────────────
    stored_reps = st.session_state.get("_upload_final_reps", 0)
    stored_ex   = st.session_state.get("_upload_exercise", exercise_name)
    completed_at = st.session_state.get("_upload_completed_at", 0.0)
    if stored_reps > 0:
        _, display_name = EXERCISES.get(stored_ex, (None, stored_ex))
        elapsed = int(_time.time() - completed_at) if completed_at > 0 else 0
        remaining = max(0, 60 - elapsed)
        st.caption(f"⏱️ Auto-saves in {remaining}s if not saved manually.")
        if st.button(f"💾 Save {stored_reps} Reps to History",
                     type="primary", use_container_width=True, key="upload_save_btn"):
            db.save_workout(st.session_state.username, display_name, stored_reps, 1)
            st.toast("Workout saved!", icon="✅")
            st.session_state["_upload_final_reps"]   = 0
            st.session_state["_upload_completed_at"] = 0.0


# ═══════════════════════════════════════════════════════════════════════════════
# DASHBOARD PAGE
# ═══════════════════════════════════════════════════════════════════════════════

def render_dashboard_page():
    st.markdown("""
    <h1 style="font-size:2rem;font-weight:800;color:#f1f5f9;margin-bottom:4px;">📊 Dashboard</h1>
    <p style="color:#6b7280;font-size:0.9rem;margin-bottom:24px;">Your workout history & muscle breakdown</p>
    """, unsafe_allow_html=True)

    username = st.session_state.username

    # ── Calendar month navigation via arrow buttons ────────────────────────────
    year  = st.session_state["_dashboard_year"]
    month = st.session_state["_dashboard_month"]
    month_str = f"{year}-{month:02d}"

    nav_l, nav_c, nav_r = st.columns([1, 4, 1])
    with nav_l:
        if st.button("‹", use_container_width=True, key="cal_prev"):
            month -= 1
            if month < 1:
                month = 12; year -= 1
            st.session_state["_dashboard_year"]  = year
            st.session_state["_dashboard_month"] = month
            st.rerun()
    with nav_c:
        st.markdown(
            f"<p style='text-align:center;font-weight:700;font-size:1.05rem;margin:6px 0;'>"
            f"{datetime(year, month, 1).strftime('%B %Y')}</p>",
            unsafe_allow_html=True)
    with nav_r:
        if st.button("›", use_container_width=True, key="cal_next"):
            month += 1
            if month > 12:
                month = 1; year += 1
            st.session_state["_dashboard_year"]  = year
            st.session_state["_dashboard_month"] = month
            st.rerun()

    history      = db.get_workout_history(username)
    muscle_stats = db.get_monthly_stats(username, month_str)
    total_sets   = db.get_total_sets_month(username, month_str)

    # ── Summary cards ─────────────────────────────────────────────────────────
    days_trained = [d for d in history if d.startswith(month_str)]
    top_muscle   = max(muscle_stats, key=muscle_stats.get) if any(muscle_stats.values()) else "—"

    mc1, mc2, mc3 = st.columns(3)
    with mc1:
        st.markdown(f"""<div class="stat-card" style="border-color:rgba(16,185,129,0.25);text-align:center;">
            <div class="stat-label">Days Trained</div>
            <div class="stat-value">{len(days_trained)}</div></div>""", unsafe_allow_html=True)
    with mc2:
        st.markdown(f"""<div class="stat-card" style="border-color:rgba(99,102,241,0.25);text-align:center;">
            <div class="stat-label">Sets Performed</div>
            <div class="stat-value" style="color:#6366f1;">{total_sets:,}</div></div>""",
                    unsafe_allow_html=True)
    with mc3:
        st.markdown(f"""<div class="stat-card" style="border-color:rgba(245,158,11,0.25);text-align:center;">
            <div class="stat-label">Top Muscle</div>
            <div class="stat-value" style="color:#f59e0b;font-size:1.6rem;">{top_muscle}</div>
            </div>""", unsafe_allow_html=True)

    st.markdown("<br>", unsafe_allow_html=True)

    left_col, right_col = st.columns([3, 2], gap="large")

    # ── Calendar ──────────────────────────────────────────────────────────────
    with left_col:
        st.markdown("#### 📅 Workout Calendar")
        _render_calendar(history, month_str)

        workout_dates = sorted([d for d in history if d.startswith(month_str)], reverse=True)
        if workout_dates:
            st.markdown("<br>", unsafe_allow_html=True)
            chosen = st.selectbox("🔍 View workout for date", workout_dates,
                                  format_func=lambda d: datetime.strptime(d, "%Y-%m-%d")
                                  .strftime("%A, %b %d"))
            if chosen and chosen in history:
                _render_day_detail(chosen, history[chosen])

    # ── Muscle chart ──────────────────────────────────────────────────────────
    with right_col:
        st.markdown("#### 💪 Muscle Group Breakdown")
        if any(muscle_stats.values()):
            _render_muscle_chart(muscle_stats)
        else:
            st.info("No workout data for this month yet.")


def _render_calendar(history, month_str):
    """Render a compact HTML calendar grid."""
    try:
        year, month = map(int, month_str.split("-"))
    except ValueError:
        st.error("Invalid month format. Use YYYY-MM.")
        return

    import calendar
    cal = calendar.monthcalendar(year, month)
    month_name = datetime(year, month, 1).strftime("%B %Y")
    today_str  = date.today().isoformat()

    rows = ["<div style='font-size:0.85rem;'>"]
    rows.append(f"<p style='color:#6b7280;margin-bottom:8px;font-weight:600;'>{month_name}</p>")
    rows.append("<div style='display:grid;grid-template-columns:repeat(7,1fr);gap:4px;'>")

    for day_name in ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"]:
        rows.append(f"<div style='text-align:center;color:#4b5563;font-size:0.7rem;padding:4px;'>{day_name}</div>")

    for week in cal:
        for day in week:
            if day == 0:
                rows.append("<div></div>")
                continue
            date_str = f"{year}-{month:02d}-{day:02d}"
            has_data = date_str in history
            is_today = date_str == today_str
            bg  = "rgba(16,185,129,0.15)"  if has_data else "rgba(255,255,255,0.03)"
            bdr = "rgba(16,185,129,0.4)"   if has_data else "rgba(255,255,255,0.07)"
            col = "#10b981" if has_data else "#9ca3af"
            if is_today:
                bdr = "#6366f1"
                col = "#a5b4fc"
            dot = "<br><span style='display:block;width:5px;height:5px;border-radius:50%;background:#10b981;margin:0 auto;'></span>" if has_data else ""
            rows.append(f"""<div style='text-align:center;padding:6px 2px;border-radius:6px;
                background:{bg};border:1px solid {bdr};color:{col};font-weight:500;'>
                {day}{dot}</div>""")

    rows.append("</div></div>")
    st.markdown("".join(rows), unsafe_allow_html=True)


def _render_day_detail(date_str, exercises):
    """Scrollable detail card showing per-set breakdown for a workout day."""
    display = datetime.strptime(date_str, "%Y-%m-%d").strftime("%A, %B %d, %Y")
    st.markdown(f"""
    <div style="background:rgba(255,255,255,0.04);border:1px solid rgba(255,255,255,0.08);
        border-radius:14px;padding:16px;margin-top:8px;">
        <p style="color:#6b7280;font-size:0.75rem;margin:0 0 12px;">{display}</p>""",
        unsafe_allow_html=True)

    for ex, data in exercises.items():
        sets_list = db._entry_sets_list(data)
        total_reps = sum(sets_list)
        n_sets     = len(sets_list)
        st.markdown(f"""
        <div style="margin-bottom:10px;padding:10px 14px;border-radius:10px;
            background:rgba(255,255,255,0.03);border:1px solid rgba(255,255,255,0.08);">
            <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:8px;">
                <span style="color:#f1f5f9;font-weight:700;font-size:0.9rem;">{ex}</span>
                <span style="color:#10b981;font-weight:800;font-size:0.95rem;">{n_sets} set{'s' if n_sets!=1 else ''} &middot; {total_reps} total reps</span>
            </div>""", unsafe_allow_html=True)
        for i, rep_count in enumerate(sets_list, 1):
            st.markdown(f"""
            <div style="display:flex;justify-content:space-between;padding:4px 8px;
                border-radius:6px;background:rgba(255,255,255,0.02);margin-bottom:3px;">
                <span style="color:#9ca3af;font-size:0.8rem;">Set {i}</span>
                <span style="color:#d1d5db;font-weight:600;font-size:0.8rem;">{rep_count} reps</span>
            </div>""", unsafe_allow_html=True)
        st.markdown("</div>", unsafe_allow_html=True)

    st.markdown("</div>", unsafe_allow_html=True)


def _render_muscle_chart(muscle_stats):
    labels  = [k for k, v in muscle_stats.items() if v > 0]
    values  = [muscle_stats[k] for k in labels]
    colors  = [MUSCLE_COLOURS.get(k, "#6366f1") for k in labels]

    fig = go.Figure(go.Pie(
        labels=labels, values=values,
        marker=dict(colors=colors, line=dict(color="#111827", width=2)),
        hole=0.55, textinfo="label+percent",
        textfont=dict(color="#f1f5f9", size=12),
        hovertemplate="%{label}: %{value} sets<extra></extra>",
    ))
    fig.update_layout(
        paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
        margin=dict(t=10, b=10, l=10, r=10),
        legend=dict(font=dict(color="#9ca3af", size=11),
                    bgcolor="rgba(0,0,0,0)", orientation="h"),
        showlegend=True,
    )
    st.plotly_chart(fig, use_container_width=True)

    # Horizontal bars
    max_sets = max(values, default=1)
    for muscle, n_sets in muscle_stats.items():
        if n_sets == 0:
            continue
        pct   = n_sets / max_sets
        color = MUSCLE_COLOURS.get(muscle, "#6366f1")
        st.markdown(f"""
        <div style="margin-bottom:10px;">
            <div style="display:flex;justify-content:space-between;margin-bottom:4px;">
                <span style="font-size:0.78rem;color:#d1d5db;">{muscle}</span>
                <span style="font-size:0.78rem;color:#6b7280;">{n_sets} set{'s' if n_sets!=1 else ''}</span>
            </div>
            <div style="background:rgba(255,255,255,0.06);border-radius:999px;height:7px;overflow:hidden;">
                <div style="width:{pct*100:.0f}%;height:100%;background:{color};border-radius:999px;
                    transition:width 1s ease;"></div>
            </div>
        </div>""", unsafe_allow_html=True)



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

    # Load history once
    if not st.session_state.chat_history:
        st.session_state.chat_history = db.load_chat_history(username)

    # Clear button
    col1, col2 = st.columns([6, 1])
    with col2:
        if st.button("🗑 Clear", use_container_width=True):
            db.clear_chat_history(username)
            st.session_state.chat_history = []
            st.rerun()

    # Chat history display
    chat_container = st.container(height=450)
    with chat_container:
        if not st.session_state.chat_history:
            st.markdown("""
            <div style="text-align:center;padding:40px;color:#4b5563;">
                <div style="font-size:2.5rem;margin-bottom:12px;">🤖</div>
                <p style="margin:0;">Hi! I'm <strong style="color:#a5b4fc;">ActionBot</strong>.
                Ask me about meal plans, macros, supplements, or recovery!</p>
            </div>""", unsafe_allow_html=True)
        else:
            for msg in st.session_state.chat_history:
                with st.chat_message(msg["role"],
                                     avatar="🧑" if msg["role"]=="user" else "🤖"):
                    st.markdown(msg["content"])

    # Suggested prompts (shown when chat is empty)
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
                    _send_chat_message(username, prompt)
                    st.rerun()

    # Input
    user_input = st.chat_input("Ask about meal plans, nutrition, recovery…")
    if user_input:
        _send_chat_message(username, user_input)
        st.rerun()


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

    # ── Cookie Controller — synchronous, works on first render ────────────────
    ctrl = CookieController()
    st.session_state["_cookie_manager"] = ctrl

    # ── Restore session from cookie on page reload ─────────────────────────────
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

    # ── Auth gates ────────────────────────────────────────────────────────────
    if not st.session_state.logged_in:
        render_login_page(cookie_manager=ctrl)
        return

    if not st.session_state.onboarding_done:
        render_onboarding_page()
        return

    # Render sidebar and get active page controls
    exercise_name, mode = render_sidebar()

    page = st.session_state.page
    if page == "tracker":
        render_tracker_page(exercise_name, mode)
    elif page == "dashboard":
        render_dashboard_page()
    elif page == "chatbot":
        render_chatbot_page()


if __name__ == "__main__":
    main()
