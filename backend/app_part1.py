# ═══════════════════════════════════════════════════════════════════════════════
# app.py  — PART 1 OF 3: Imports · Config · CSS · Auth · Onboarding
# Paste this at the TOP of the final app.py
# ═══════════════════════════════════════════════════════════════════════════════

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
from backend import db
from dotenv import load_dotenv

load_dotenv()

# ── Auth helpers (bcrypt via passlib) ─────────────────────────────────────────
from passlib.context import CryptContext
from jose import jwt, JWTError

SECRET_KEY = os.getenv("SECRET_KEY", "fallback-secret")
ALGORITHM  = os.getenv("ALGORITHM", "HS256")
_pwd_ctx   = CryptContext(schemes=["bcrypt"], deprecated="auto")

def _hash_pw(p): return _pwd_ctx.hash(p)
def _verify_pw(p, h): return _pwd_ctx.verify(p, h)

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
    defaults = {
        "logged_in": False, "username": "", "onboarding_done": False,
        "page": "tracker",
        "last_exercise": list(EXERCISES.keys())[0],
        "counter_obj": None,
        "chat_history": [],
    }
    for k, v in defaults.items():
        if k not in st.session_state:
            st.session_state[k] = v


# ═══════════════════════════════════════════════════════════════════════════════
# AUTH PAGES
# ═══════════════════════════════════════════════════════════════════════════════

def render_login_page():
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

        with tab_login:
            with st.form("login_form"):
                user = st.text_input("Username", placeholder="your_username")
                pwd  = st.text_input("Password", type="password", placeholder="••••••••")
                submitted = st.form_submit_button("Sign In", use_container_width=True)
                if submitted:
                    if not user or not pwd:
                        st.error("Please fill in all fields.")
                    else:
                        _do_login(user, pwd)

        with tab_signup:
            with st.form("signup_form"):
                new_user  = st.text_input("Username", placeholder="choose_a_username", key="su_user")
                new_email = st.text_input("Email (optional)", placeholder="you@example.com", key="su_email")
                new_pwd   = st.text_input("Password", type="password",
                                          placeholder="Min. 6 characters", key="su_pwd")
                submitted2 = st.form_submit_button("Create Account", use_container_width=True)
                if submitted2:
                    if not new_user or not new_pwd:
                        st.error("Username and password are required.")
                    elif len(new_pwd) < 6:
                        st.error("Password must be at least 6 characters.")
                    elif db.get_user(new_user):
                        st.error("Username already taken.")
                    else:
                        db.create_user(new_user, _hash_pw(new_pwd), new_email)
                        st.session_state.username   = new_user
                        st.session_state.logged_in  = True
                        st.session_state.onboarding_done = False
                        st.rerun()


def _do_login(username, password):
    user = db.get_user(username)
    if not user or not _verify_pw(password, user["hashed_password"]):
        st.error("Incorrect username or password.")
        return
    st.session_state.username        = username
    st.session_state.logged_in       = True
    st.session_state.onboarding_done = user.get("onboarding_complete", False)
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
        stats = {"counter": 0, "feedback": "Get in Position", "progress": 0.0, "correct_form": False}
        if ctx.state.playing and ctx.video_processor:
            stats = ctx.video_processor.get_stats()

        ph = st.empty()
        with ph.container():
            render_stats_panel(stats["counter"], stats["feedback"],
                               stats["progress"], stats["correct_form"])

        if st.button("🔄 Refresh Stats", use_container_width=True):
            if ctx.video_processor:
                stats = ctx.video_processor.get_stats()
            with ph.container():
                render_stats_panel(stats["counter"], stats["feedback"],
                                   stats["progress"], stats["correct_form"])

        st.divider()
        # Save Set button
        reps = stats.get("counter", 0)
        _, display_name = EXERCISES[exercise_name]
        if st.button(f"✅ Save Set ({reps} reps)", use_container_width=True,
                     type="primary", disabled=(reps == 0)):
            db.save_workout(st.session_state.username, display_name, reps, 1)
            st.toast(f"Saved {reps} reps of {display_name}!", icon="💾")
            if st.session_state.counter_obj:
                st.session_state.counter_obj.reset()


def _render_upload(exercise_name):
    st.markdown(f"### {exercise_name} — Video Analysis")
    uploaded = st.file_uploader("Drop a workout video here",
                                type=["mp4", "avi", "mov", "mkv"], key="video_upload")
    if not uploaded:
        st.info("📁 Upload a video to analyse your exercise form and count reps.")
        return

    vid_col, stats_col = st.columns([3, 1], gap="large")
    with vid_col:
        frame_ph = st.empty()
        prog_ph  = st.empty()
    with stats_col:
        st.markdown("### 📊 Analysis")
        counter_ph  = st.empty()
        feedback_ph = st.empty()
        form_ph     = st.empty()

    if st.button("▶ Start Analysis", type="primary", use_container_width=True):
        obj = st.session_state.counter_obj
        obj.reset()
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
                frame_ph.image(rgb, channels="RGB", use_column_width=True)
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
        _, display_name = EXERCISES[exercise_name]
        form_ph.success(f"✅ Done — **{final_reps} reps** detected!")
        if final_reps > 0 and st.button("💾 Save to History", type="primary"):
            db.save_workout(st.session_state.username, display_name, final_reps, 1)
            st.toast("Workout saved!", icon="✅")


# ═══════════════════════════════════════════════════════════════════════════════
# DASHBOARD PAGE
# ═══════════════════════════════════════════════════════════════════════════════

def render_dashboard_page():
    st.markdown("""
    <h1 style="font-size:2rem;font-weight:800;color:#f1f5f9;margin-bottom:4px;">📊 Dashboard</h1>
    <p style="color:#6b7280;font-size:0.9rem;margin-bottom:24px;">Your workout history & muscle breakdown</p>
    """, unsafe_allow_html=True)

    username = st.session_state.username

    # Month selector
    col1, col2 = st.columns([2, 1])
    with col2:
        now = datetime.now()
        month_str = st.text_input("Month (YYYY-MM)", value=now.strftime("%Y-%m"),
                                   label_visibility="collapsed")

    history      = db.get_workout_history(username)
    muscle_stats = db.get_monthly_stats(username, month_str)

    # ── Summary cards ─────────────────────────────────────────────────────────
    days_trained = [d for d in history if d.startswith(month_str)]
    total_reps   = sum(muscle_stats.values())
    top_muscle   = max(muscle_stats, key=muscle_stats.get) if any(muscle_stats.values()) else "—"

    mc1, mc2, mc3 = st.columns(3)
    with mc1:
        st.markdown(f"""<div class="stat-card" style="border-color:rgba(16,185,129,0.25);text-align:center;">
            <div class="stat-label">Days Trained</div>
            <div class="stat-value">{len(days_trained)}</div></div>""", unsafe_allow_html=True)
    with mc2:
        st.markdown(f"""<div class="stat-card" style="border-color:rgba(99,102,241,0.25);text-align:center;">
            <div class="stat-label">Total Reps</div>
            <div class="stat-value" style="color:#6366f1;">{total_reps:,}</div></div>""",
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

        # Date detail popup via selectbox
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
    """Scrollable detail card for a workout day."""
    display = datetime.strptime(date_str, "%Y-%m-%d").strftime("%A, %B %d, %Y")
    st.markdown(f"""
    <div style="background:rgba(255,255,255,0.04);border:1px solid rgba(255,255,255,0.08);
        border-radius:14px;padding:16px;margin-top:8px;">
        <p style="color:#6b7280;font-size:0.75rem;margin:0 0 12px;">{display}</p>""",
        unsafe_allow_html=True)

    for ex, data in exercises.items():
        reps, sets = data.get("reps", 0), data.get("sets", 1)
        st.markdown(f"""
        <div style="display:flex;justify-content:space-between;align-items:center;
            padding:10px 14px;margin-bottom:6px;border-radius:10px;
            background:rgba(255,255,255,0.03);border:1px solid rgba(255,255,255,0.06);">
            <div>
                <span style="color:#f1f5f9;font-weight:600;font-size:0.88rem;">{ex}</span>
                <span style="color:#6b7280;font-size:0.75rem;margin-left:8px;">{sets} set{'s' if sets!=1 else ''}</span>
            </div>
            <span style="color:#10b981;font-weight:800;font-size:1.1rem;">{reps} reps</span>
        </div>""", unsafe_allow_html=True)

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
        hovertemplate="%{label}: %{value} reps<extra></extra>",
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
    max_reps = max(values, default=1)
    for muscle, reps in muscle_stats.items():
        if reps == 0:
            continue
        pct   = reps / max_reps
        color = MUSCLE_COLOURS.get(muscle, "#6366f1")
        st.markdown(f"""
        <div style="margin-bottom:10px;">
            <div style="display:flex;justify-content:space-between;margin-bottom:4px;">
                <span style="font-size:0.78rem;color:#d1d5db;">{muscle}</span>
                <span style="font-size:0.78rem;color:#6b7280;">{reps} reps</span>
            </div>
            <div style="background:rgba(255,255,255,0.06);border-radius:999px;height:7px;overflow:hidden;">
                <div style="width:{pct*100:.0f}%;height:100%;background:{color};border-radius:999px;
                    transition:width 1s ease;"></div>
            </div>
        </div>""", unsafe_allow_html=True)


# ═══════════════════════════════════════════════════════════════════════════════
# AI CHATBOT PAGE
# ═══════════════════════════════════════════════════════════════════════════════

def _get_ai_response(username: str, message: str) -> str:
    api_key = os.getenv("GOOGLE_API_KEY", "")
    if not api_key:
        return "⚠️ GOOGLE_API_KEY not set in .env file."
    try:
        from langchain_google_genai import ChatGoogleGenerativeAI
        from langchain_core.messages import HumanMessage, SystemMessage, AIMessage

        profile = db.get_user_profile(username) or {}
        history = db.load_chat_history(username)

        target_map = {"weight_loss": "Weight Loss", "muscle_gain": "Muscle Gain",
                      "endurance": "Building Endurance", "general_fitness": "General Fitness"}
        restrictions = ", ".join(profile.get("dietary_restrictions", [])) or "None"

        system = (
            "You are ActionBot, a personalized fitness and nutrition AI. "
            "Provide evidence-based dietary and fitness advice tailored to the user's profile.\n\n"
            f"User Profile:\n"
            f"  Age: {profile.get('age','?')}, Gender: {profile.get('gender','?')}, "
            f"  Weight: {profile.get('weight_kg','?')}kg, Height: {profile.get('height_cm','?')}cm\n"
            f"  Goal: {target_map.get(profile.get('target',''),'General Fitness')}\n"
            f"  Dietary Restrictions: {restrictions}\n\n"
            "Always respect dietary restrictions. Be concise, friendly, and practical. "
            "Include specific quantities and macros in meal plans."
        )

        llm = ChatGoogleGenerativeAI(model="gemini-2.0-flash", google_api_key=api_key,
                                     temperature=0.7)
        msgs = [SystemMessage(content=system)]
        for m in history[-20:]:
            msgs.append(HumanMessage(content=m["content"]) if m["role"] == "user"
                        else AIMessage(content=m["content"]))
        msgs.append(HumanMessage(content=message))
        return llm.invoke(msgs).content
    except Exception as e:
        return f"⚠️ AI error: {e}"


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
        reply = _get_ai_response(username, message)
    db.append_chat_message(username, "assistant", reply)
    st.session_state.chat_history.append({"role": "assistant", "content": reply})


# ═══════════════════════════════════════════════════════════════════════════════
# MAIN ENTRY POINT
# ═══════════════════════════════════════════════════════════════════════════════

def main():
    inject_css()
    _init_state()

    # Auth gates
    if not st.session_state.logged_in:
        render_login_page()
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
