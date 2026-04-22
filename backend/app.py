import warnings
import os
import sys
import threading
import tempfile
import warnings

import av
import cv2
import streamlit as st
from streamlit_webrtc import (
    VideoProcessorBase,
    WebRtcMode,
    webrtc_streamer,
    RTCConfiguration,
)

warnings.filterwarnings("ignore")

# Ensure project root is on path for `backend.*`
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from backend.counters.BicepCurlCounter    import BicepCurlCounter
from backend.counters.PushupCounter       import PushupCounter
from backend.counters.PullupCounter       import PullupCounter
from backend.counters.SquatCounter        import SquatCounter
from backend.counters.LateralRaiseCounter import LateralRaiseCounter
from backend.counters.OverheadPressCounter import OverheadPressCounter
from backend.counters.SitupCounter        import SitupCounter
from backend.counters.CrunchCounter       import CrunchCounter
from backend.counters.LegRaiseCounter     import LegRaiseCounter
from backend.counters.KneeRaiseCounter    import KneeRaiseCounter
from backend.counters.KneePressCounter    import KneePressCounter


st.set_page_config(
    page_title="SmartSpotter",
    page_icon="🏋️",
    layout="wide",
    initial_sidebar_state="expanded",
)

EXERCISES: dict = {
    "💪  Bicep Curl":      BicepCurlCounter,
    "🔼  Push-Up":         PushupCounter,
    "🏋️  Pull-Up":        PullupCounter,
    "🦵  Squat":           SquatCounter,
    "🦾  Lateral Raise":   LateralRaiseCounter,
    "⬆️  Overhead Press": OverheadPressCounter,
    "🧘  Sit-Up":          SitupCounter,
    "🤸  Crunch":          CrunchCounter,
    "🦿  Leg Raise":       LegRaiseCounter,
    "🦵  Knee Raise":      KneeRaiseCounter,
    "🦵  Knee Press":      KneePressCounter,
}


RTC_CONFIG = RTCConfiguration(
    {"iceServers": [{"urls": ["stun:stun.l.google.com:19302"]}]}
)

FEEDBACK_EMOJI = {
    "Up":               "⬆️",
    "Down":             "⬇️",
    "Fix Form":         "⚠️",
    "Get in Position":  "📍",
}

FEEDBACK_COLOUR = {
    "Up":               "#10b981",
    "Down":             "#3b82f6",
    "Fix Form":         "#ef4444",
    "Get in Position":  "#9ca3af",
}


def inject_css():
    st.markdown("""
    <style>
    /* ── Global ────────────────────────────────────────────────────────────── */
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700;800&display=swap');

    html, body, [class*="css"] { font-family: 'Inter', sans-serif; }

    [data-testid="stAppViewContainer"] {
        background: radial-gradient(ellipse at 20% 10%, #0f172a 0%, #0a0e1a 60%, #050810 100%);
        color: #f1f5f9;
    }
    [data-testid="stHeader"] { background: transparent; }

    /* ── Sidebar ────────────────────────────────────────────────────────────── */
    [data-testid="stSidebar"] {
        background: linear-gradient(180deg, #111827 0%, #0f1623 100%);
        border-right: 1px solid rgba(99,102,241,0.15);
    }
    [data-testid="stSidebar"] .stMarkdown p,
    [data-testid="stSidebar"] label,
    [data-testid="stSidebar"] span {
        color: #d1d5db !important;
    }
    [data-testid="stSidebarNav"] { display: none; }

    /* ── Sidebar title ──────────────────────────────────────────────────────── */
    .sidebar-brand {
        display: flex; align-items: center; gap: 12px;
        padding: 8px 0 20px 0;
        border-bottom: 1px solid rgba(255,255,255,0.07);
        margin-bottom: 20px;
    }
    .sidebar-brand h1 {
        font-size: 1.25rem !important;
        font-weight: 700 !important;
        color: #f9fafb !important;
        margin: 0 !important;
        background: linear-gradient(135deg, #6366f1, #10b981);
        -webkit-background-clip: text;
        -webkit-text-fill-color: transparent;
    }

    /* ── Page heading ───────────────────────────────────────────────────────── */
    .page-header {
        text-align: center;
        padding: 16px 0 4px 0;
    }
    .page-header h1 {
        font-size: 2.4rem;
        font-weight: 800;
        background: linear-gradient(135deg, #6366f1 20%, #10b981 80%);
        -webkit-background-clip: text;
        -webkit-text-fill-color: transparent;
        margin-bottom: 4px;
    }
    .page-header p {
        color: #6b7280;
        font-size: 0.95rem;
        margin: 0;
    }

    /* ── Stat cards ─────────────────────────────────────────────────────────── */
    .stat-card {
        background: rgba(255,255,255,0.035);
        border: 1px solid rgba(255,255,255,0.08);
        border-radius: 16px;
        padding: 22px 20px;
        backdrop-filter: blur(12px);
        margin-bottom: 14px;
        transition: border-color 0.2s;
    }
    .stat-card:hover { border-color: rgba(99,102,241,0.35); }
    .stat-label {
        font-size: 0.72rem;
        font-weight: 600;
        letter-spacing: 0.1em;
        text-transform: uppercase;
        color: #6b7280;
        margin-bottom: 6px;
    }
    .stat-value {
        font-size: 3.5rem;
        font-weight: 800;
        line-height: 1;
        color: #10b981;
        font-variant-numeric: tabular-nums;
    }
    .stat-value-sm {
        font-size: 1.6rem;
        font-weight: 700;
        line-height: 1.2;
    }

    /* ── Feedback badge ─────────────────────────────────────────────────────── */
    .feedback-badge {
        display: inline-flex;
        align-items: center;
        gap: 8px;
        padding: 8px 18px;
        border-radius: 50px;
        font-size: 1rem;
        font-weight: 600;
        border: 1.5px solid;
    }

    /* ── Progress bar override ──────────────────────────────────────────────── */
    .stProgress > div > div > div > div {
        background: linear-gradient(90deg, #6366f1, #10b981) !important;
        border-radius: 8px !important;
    }
    .stProgress > div > div {
        background: rgba(255,255,255,0.06) !important;
        border-radius: 8px !important;
    }

    /* ── Buttons ────────────────────────────────────────────────────────────── */
    .stButton > button {
        background: linear-gradient(135deg, #6366f1, #8b5cf6) !important;
        color: #fff !important;
        border: none !important;
        border-radius: 10px !important;
        font-weight: 600 !important;
        font-size: 0.9rem !important;
        padding: 0.55em 1.4em !important;
        transition: all 0.2s ease !important;
        box-shadow: 0 4px 18px rgba(99,102,241,0.28) !important;
    }
    .stButton > button:hover {
        transform: translateY(-1px) !important;
        box-shadow: 0 6px 24px rgba(99,102,241,0.45) !important;
    }
    .stButton > button[kind="primary"] {
        background: linear-gradient(135deg, #10b981, #059669) !important;
        box-shadow: 0 4px 18px rgba(16,185,129,0.28) !important;
    }
    .stButton > button[kind="primary"]:hover {
        box-shadow: 0 6px 24px rgba(16,185,129,0.45) !important;
    }

    /* ── Select / radio ─────────────────────────────────────────────────────── */
    [data-testid="stSelectbox"] > div > div {
        background: rgba(255,255,255,0.05) !important;
        border: 1px solid rgba(99,102,241,0.25) !important;
        border-radius: 10px !important;
        color: #f1f5f9 !important;
    }
    [data-testid="stRadio"] > div {
        background: rgba(255,255,255,0.03) !important;
        border: 1px solid rgba(255,255,255,0.07) !important;
        border-radius: 10px !important;
        padding: 8px 12px !important;
    }

    /* ── File uploader ──────────────────────────────────────────────────────── */
    [data-testid="stFileUploader"] > div {
        background: rgba(255,255,255,0.03) !important;
        border: 2px dashed rgba(99,102,241,0.35) !important;
        border-radius: 14px !important;
    }
    [data-testid="stFileUploader"] label { color: #9ca3af !important; }

    /* ── Video / image frames ───────────────────────────────────────────────── */
    [data-testid="stImage"] img {
        border-radius: 14px;
        border: 1px solid rgba(99,102,241,0.2);
        box-shadow: 0 20px 60px rgba(0,0,0,0.5);
    }
    /* WebRTC video */
    video { border-radius: 14px !important; }

    /* ── Info / success / warning boxes ─────────────────────────────────────── */
    [data-testid="stInfo"] {
        background: rgba(99,102,241,0.08) !important;
        border: 1px solid rgba(99,102,241,0.25) !important;
        border-radius: 10px !important;
    }
    [data-testid="stSuccess"] {
        background: rgba(16,185,129,0.08) !important;
        border: 1px solid rgba(16,185,129,0.25) !important;
        border-radius: 10px !important;
    }

    /* ── Divider ────────────────────────────────────────────────────────────── */
    hr { border-color: rgba(255,255,255,0.07) !important; }

    /* ── Scrollbar ──────────────────────────────────────────────────────────── */
    ::-webkit-scrollbar { width: 5px; }
    ::-webkit-scrollbar-track { background: #0a0e1a; }
    ::-webkit-scrollbar-thumb { background: #374151; border-radius: 4px; }
    ::-webkit-scrollbar-thumb:hover { background: #6366f1; }
    </style>
    """, unsafe_allow_html=True)

class ExerciseVideoProcessor(VideoProcessorBase):
    """
    Bridges streamlit-webrtc's WebRTC thread with the exercise counter.

    Why WebRTC over st.camera_input?
      • Frames are processed in a dedicated background thread → UI never blocks.
      • ~30 FPS throughput vs. single-snapshot per click with camera_input.
      • Direct browser ↔ Python peer connection over SRTP — lowest possible latency.
      • All stat overlays are rendered on the video itself, visible in real-time.
    """

    def __init__(self):
        self.counter_obj = None
        self._lock = threading.Lock()
        self._last_stats: dict = {
            "counter": 0,
            "feedback": "Get in Position",
            "progress": 0.0,
            "correct_form": False,
        }

    def recv(self, frame: av.VideoFrame) -> av.VideoFrame:
        img = frame.to_ndarray(format="bgr24")

        if self.counter_obj is not None:
            result = self.counter_obj.process_frame(img)
            with self._lock:
                self._last_stats = {k: v for k, v in result.items() if k != "frame"}
            return av.VideoFrame.from_ndarray(result["frame"], format="bgr24")

        return frame

    def get_stats(self) -> dict:
        with self._lock:
            return dict(self._last_stats)


def _init_session():
    if "last_exercise" not in st.session_state:
        st.session_state.last_exercise = list(EXERCISES.keys())[0]
    # Lazily initialise the counter only once (after Streamlit runtime is up)
    if "counter_obj" not in st.session_state or st.session_state.counter_obj is None:
        st.session_state.counter_obj = EXERCISES[st.session_state.last_exercise]()


def render_sidebar() -> tuple[str, str]:
    with st.sidebar:
        st.markdown("""
        <div class="sidebar-brand">
            <h1>🏋️ SmartSpotter</h1>
        </div>
        """, unsafe_allow_html=True)

        exercise_name = st.selectbox(
            "**Exercise**", list(EXERCISES.keys()), key="exercise_select",
            help="Select which exercise you want to track"
        )

        st.markdown("<br>", unsafe_allow_html=True)

        mode = st.radio(
            "**Input Mode**",
            ["📸  Live Webcam (WebRTC)", "📁  Upload Video"],
            key="mode_select",
        )

        st.divider()

        col_a, col_b = st.columns(2)
        with col_a:
            if st.button("🔄 Reset", use_container_width=True):
                st.session_state.counter_obj.reset()
                st.toast("Counter reset!", icon="✅")
        with col_b:
            if st.button("🆕 New", use_container_width=True,
                         help="Change exercise & start fresh"):
                st.session_state.counter_obj = EXERCISES[exercise_name]()
                st.session_state.last_exercise = exercise_name
                st.toast(f"Started {exercise_name}!", icon="🏁")

        # Auto-switch counter when exercise changes
        if exercise_name != st.session_state.last_exercise:
            st.session_state.counter_obj = EXERCISES[exercise_name]()
            st.session_state.last_exercise = exercise_name

        st.divider()
        st.markdown("""
        <div style="color:#4b5563;font-size:0.75rem;line-height:1.6;">
        <b style="color:#6b7280">How to use</b><br>
        1. Select your exercise above<br>
        2. Allow camera / upload a video<br>
        3. Get into position & start moving<br>
        4. Reps are counted automatically
        </div>
        """, unsafe_allow_html=True)

    return exercise_name, mode

def render_stats_panel(counter: int, feedback: str, progress: float, correct_form: bool):
    fb_colour = FEEDBACK_COLOUR.get(feedback, "#9ca3af")
    fb_emoji  = FEEDBACK_EMOJI.get(feedback, "")

    # Rep counter card
    st.markdown(f"""
    <div class="stat-card" style="border-color:rgba(16,185,129,0.25);">
        <div class="stat-label">Reps This Session</div>
        <div class="stat-value">{counter}</div>
    </div>
    """, unsafe_allow_html=True)

    # Feedback card
    st.markdown(f"""
    <div class="stat-card" style="border-color:{fb_colour}44;">
        <div class="stat-label">Form Feedback</div>
        <div class="stat-value-sm" style="color:{fb_colour};">
            {fb_emoji} {feedback}
        </div>
    </div>
    """, unsafe_allow_html=True)

    # Progress bar card
    st.markdown("""
    <div class="stat-card">
        <div class="stat-label">Exercise Progress</div>
    </div>
    """, unsafe_allow_html=True)
    st.progress(int(progress) / 100)
    st.caption(f"{int(progress)}% complete")

    # Form status indicator
    form_col, _ = st.columns([1, 1])
    with form_col:
        if correct_form:
            st.success("✅ Form Unlocked")
        else:
            st.info("📍 Get in Position")


def render_webcam_mode(exercise_name: str):
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

        st.caption(
            "📌 **Stats overlays are drawn live on the video feed.** "
            "Click **Refresh Stats** in the panel → to sync the sidebar numbers."
        )

    with stats_col:
        st.markdown("### 📊 Stats")

        # Poll latest stats from the background thread
        stats = {"counter": 0, "feedback": "Get in Position", "progress": 0.0, "correct_form": False}
        if ctx.state.playing and ctx.video_processor:
            stats = ctx.video_processor.get_stats()

        # Placeholder so we can refresh without full page reload
        stats_ph = st.empty()
        with stats_ph.container():
            render_stats_panel(
                stats["counter"],
                stats["feedback"],
                stats["progress"],
                stats["correct_form"],
            )

        if st.button("🔄 Refresh Stats", use_container_width=True):
            if ctx.video_processor:
                stats = ctx.video_processor.get_stats()
            with stats_ph.container():
                render_stats_panel(
                    stats["counter"],
                    stats["feedback"],
                    stats["progress"],
                    stats["correct_form"],
                )

        st.divider()
        st.markdown("""
        <div style="color:#4b5563;font-size:0.73rem;line-height:1.8;">
        <b style="color:#6b7280;">WebRTC Benefits</b><br>
        ⚡ ~30 FPS background thread<br>
        📡 Direct peer connection<br>
        🖥️ No UI blocking<br>
        🔒 Encrypted SRTP stream
        </div>
        """, unsafe_allow_html=True)

def render_upload_mode(exercise_name: str):
    st.markdown(f"### {exercise_name} — Video Analysis")

    uploaded = st.file_uploader(
        "Drop a workout video here",
        type=["mp4", "avi", "mov", "mkv"],
        key="video_upload",
        help="Supports MP4, AVI, MOV, MKV",
    )

    if not uploaded:
        st.markdown("""
        <div style="text-align:center;padding:40px;color:#4b5563;">
            <div style="font-size:3rem;">📁</div>
            <p>Upload a video to analyse your exercise form and count reps.</p>
        </div>
        """, unsafe_allow_html=True)
        return

    vid_col, stats_col = st.columns([3, 1], gap="large")

    with vid_col:
        frame_ph  = st.empty()
        prog_ph   = st.empty()

    with stats_col:
        st.markdown("### 📊 Analysis")
        counter_ph  = st.empty()
        feedback_ph = st.empty()
        progress_ph = st.empty()
        status_ph   = st.empty()
        form_ph     = st.empty()

    if st.button("▶  Start Analysis", type="primary", use_container_width=True):
        counter_obj = st.session_state.counter_obj
        counter_obj.reset()

        # Save to a temp file so OpenCV can open it
        with tempfile.NamedTemporaryFile(delete=False, suffix=".mp4") as tmp:
            tmp.write(uploaded.getvalue())
            tmp_path = tmp.name

        cap = cv2.VideoCapture(tmp_path)
        total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT)) or 1
        frame_idx = 0

        try:
            while cap.isOpened():
                ret, frame = cap.read()
                if not ret:
                    break

                result = counter_obj.process_frame(frame)
                rgb    = cv2.cvtColor(result["frame"], cv2.COLOR_BGR2RGB)

                frame_ph.image(rgb, channels="RGB", use_column_width=True)
                prog_ph.progress(frame_idx / total, text=f"Processing frame {frame_idx}/{total}")

                fb_colour = FEEDBACK_COLOUR.get(result["feedback"], "#9ca3af")
                fb_emoji  = FEEDBACK_EMOJI.get(result["feedback"], "")

                with counter_ph.container():
                    st.markdown(f"""
                    <div class="stat-card" style="border-color:rgba(16,185,129,0.25);">
                        <div class="stat-label">Reps</div>
                        <div class="stat-value">{result['counter']}</div>
                    </div>
                    """, unsafe_allow_html=True)

                with feedback_ph.container():
                    st.markdown(f"""
                    <div class="stat-card" style="border-color:{fb_colour}44;">
                        <div class="stat-label">Feedback</div>
                        <div class="stat-value-sm" style="color:{fb_colour};">
                            {fb_emoji} {result['feedback']}
                        </div>
                    </div>
                    """, unsafe_allow_html=True)

                with progress_ph.container():
                    st.progress(int(result["progress"]) / 100)

                frame_idx += 1

        finally:
            cap.release()
            try:
                os.unlink(tmp_path)
            except OSError:
                pass

        prog_ph.empty()
        status_ph.success(
            f"✅ Analysis complete — **{int(counter_obj.counter)} reps** detected!"
        )

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



def main():
    inject_css()
    _init_session()

    exercise_name, mode = render_sidebar()

    # Page header
    st.markdown("""
    <div class="page-header">
        <h1>SmartSpotter</h1>
        <p>Rep counting powered by MediaPipe Pose Estimation & WebRTC</p>
    </div>
    """, unsafe_allow_html=True)

    st.markdown("<br>", unsafe_allow_html=True)

    if "Webcam" in mode:
        render_webcam_mode(exercise_name)
    else:
        render_upload_mode(exercise_name)


if __name__ == "__main__":
    main()