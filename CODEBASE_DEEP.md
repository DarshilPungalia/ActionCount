━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
SECTION 1 — PROJECT IDENTITY
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

- **Project name:** ActionCount
- **Version:** 1.0.0
- **License:** Proprietary/Internal

**Elevator Pitch:**
ActionCount is a local-first, AI-powered fitness tracking platform that leverages real-time computer vision to count repetitions and analyze exercise form directly in the browser. It features a multi-modal LangGraph-driven voice assistant (Friday) that acts as an intelligent personal trainer, capable of generating diet plans, providing vocal motivation, and navigating the application via speech. The system combines ultra-low latency WebRTC streaming with on-device AI inference to ensure complete privacy and performance without relying on cloud processing for its core mechanics.

**Core Technical Problem & Approach:**
The core technical problem was tracking high-speed human motion in real-time with precise angle calculation while maintaining a responsive 30 FPS UI, all without cooking the user's GPU or racking up massive cloud bills. The chosen approach was to push the heavy CV workload (RTMPose) into a dedicated C++ ONNX Runtime backend thread, decoupling it from the FastAPI asyncio loop and Streamlit/Vanilla JS rendering loops. The AI assistant (Friday) was similarly localized using Silero VAD and CrispASR to avoid the latency and cost of cloud STT, providing instant "barge-in" capable voice interactions.

**Non-Trivial Architecture Factors:**

1. **Concurrency Challenges:** Handling WebRTC frame ingress, atomic frame buffering, and pose inference on different threads without locking the Global Interpreter Lock (GIL) or causing frame backpressure.
2. **Multi-Modal AI Pipeline:** Coordinating LangGraph state machines with local STT models, routing intents via fast LLMs, and executing backend tools (database queries, calorie vision APIs) seamlessly.
3. **Latency Requirements:** Voice commands like "save set" must bypass standard LLM latency to feel instant, necessitating a regex hot-path interceptor in the WebSocket layer.

**System Modules:**

1. **Inference Engine:** RTMPose wrapper running via ONNX Runtime for skeletal extraction.
2. **Exercise State Machines (Counters):** Math-heavy classes computing 2D dot-product angles for rep debouncing.
3. **Voice Agent (Friday):** LangGraph orchestrator + Silero VAD + CrispASR local STT.
4. **WebSocket Signaling & WebRTC:** Real-time data bus for video streaming and agent audio.
5. **Calorie Scanner:** Gemini Vision integration for nutritional parsing from images.
6. **Auth System:** JWT + Argon2 secured API layer.
7. **Frontend HUD / State Machine:** Vanilla JS canvas renderers, interactive standby/workout toggles, and to-do lists.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
SECTION 2 — FULL TECH STACK WITH JUSTIFICATION
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

**FastAPI (Latest)**

- **Category:** Web Backend
- **Usage:** Core asynchronous API server serving REST endpoints (`endpoint.py`) and WebSockets (`/ws/stream/{sid}`, `/ws/friday`).
- **Why:** High-performance ASGI support makes it perfect for handling concurrent WebRTC signaling and AI stream parsing simultaneously, significantly outperforming Flask.

**Uvicorn[standard]**

- **Category:** Web Server
- **Usage:** ASGI server to run FastAPI.
- **Why:** Industry standard for FastAPI; provides uvloop for maximum async performance on Windows/Linux.

**Streamlit**

- **Category:** Legacy Frontend
- **Usage:** Used in `app.py` for legacy dashboard elements.
- **Why:** Extremely fast prototyping, though the project is migrating heavily to Vanilla JS for precise canvas control.

**PyMongo[srv]**

- **Category:** Database Driver
- **Usage:** Connects to MongoDB Atlas for persistence (`db.py`).
- **Why:** Flexible schema allows for dynamic workout plans, chat history structures, and varying exercise metric shapes without rigid migrations.

**Passlib / Argon2**

- **Category:** Auth
- **Usage:** Hashing user passwords securely.
- **Why:** Argon2 is the current OWASP recommended standard over bcrypt due to memory-hardness against GPU cracking.

**Jose (python-jose)**

- **Category:** Auth
- **Usage:** Creating and verifying JWT tokens for API access.
- **Why:** Lightweight and supports standard HS256 signatures required for stateless frontend auth.

**rtmlib (RTMPose)**

- **Category:** Machine Learning (Computer Vision)
- **Usage:** Extracts 17 COCO keypoints from live webcam frames (`PoseDetector.py`).
- **Why:** Significantly lighter and faster than MediaPipe for full-body tracking, and highly portable via ONNX.

**ONNX Runtime (onnxruntime-gpu)**

- **Category:** ML Engine
- **Usage:** Hardware acceleration backend for rtmlib.
- **Why:** Bypasses PyTorch overhead, allowing RTMPose to run efficiently on consumer GPUs (like RTX 4050).

**OpenCV (opencv-python)**

- **Category:** Video Processing
- **Usage:** Frame scaling, BGR/RGB conversion, and debug rendering.
- **Why:** De-facto standard for matrix-based image manipulation.

**LangGraph & Langchain**

- **Category:** AI Orchestration
- **Usage:** Manages the Friday AI's memory, state transitions, and tool-calling loop (`graph.py`).
- **Why:** Provides deterministic state-machine control over LLMs, preventing hallucinations and allowing strict integration with local tools (saving sets, fetching calories).

**Silero VAD**

- **Category:** Audio Processing
- **Usage:** Voice Activity Detection to segment user speech (`stt.py`).
- **Why:** Runs locally in milliseconds, preventing the STT engine from burning CPU cycles on background noise.

**CrispASR (Qwen3)**

- **Category:** Local STT
- **Usage:** Transcribes spoken audio into text (`stt.py`).
- **Why:** Standalone compiled executable (Rust/C++) that bypasses Python GIL, offering near-instant transcription locally without cloud API costs.

**Google Generative AI (Gemini)**

- **Category:** Cloud AI
- **Usage:** Vision analysis for food scanning (`calorie_tracker.py`) and fast intent routing.
- **Why:** Gemini 1.5 Flash provides ultra-cheap, highly capable multi-modal analysis where local models struggle (food identification).

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
SECTION 3 — ARCHITECTURE (MULTIPLE VIEWS)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

### 3A. SYSTEM CONTEXT

The ActionCount platform sits between the **User** (providing webcam video, microphone audio, and UI clicks) and **External APIs** (MongoDB Atlas for data persistence, Anthropic/Gemini APIs for LLM reasoning). The system boundary encloses the Python Backend (FastAPI, ONNX, LangGraph) and the local executables (CrispASR for STT). Voice output TTS (Voxtral) was recently deprecated, meaning the system boundary now strictly outputs text to the frontend client, which handles rendering and navigation.

### 3B. CONTAINER VIEW

1. **FastAPI Uvicorn Process (Main):** Hosts the REST API, serves static files, and manages the async event loop for WebSockets.
2. **InferenceWorker Threads (Daemon):** One spawned per active webcam session. Reads from `AtomicFrame`, runs RTMPose on ONNX, and writes to `AtomicResult`.
3. **Friday STT Thread/Subprocess:** Silero VAD runs in a background thread, piping active audio chunks to the `crispasr.exe` subprocess.
4. **Browser Client (Vanilla JS):** Holds the DOM state, Canvas rendering loop (`requestAnimationFrame`), and WebSocket connections.

### 3C. COMPONENT VIEW — BACKEND

- **`endpoint.py`**: API Router. Collaborates with `session_manager` and `db.py`. Owns WebSocket lifecycle. Runs in async context.
- **`app.py`**: Legacy Streamlit server. Owns Streamlit state. Runs synchronous blocking context.
- **`utils/session_manager.py`**: Thread Coordinator. Collaborates with `InferenceWorker`. Owns `AtomicFrame`/`AtomicResult` singletons.
- **`detector/PoseDetector.py`**: Vision Engine. Collaborates with `rtmlib`. Owns the ONNX runtime session state.
- **`counters/*.py`**: Math Logic. Collaborates with `PoseDetector`. Owns the state machine (up/down, velocity deque, reps).
- **`agent/graph.py`**: AI State Machine. Collaborates with Langchain LLMs and `db.py`. Owns `AgentState`.
- **`agent/stt.py`**: Audio Pipeline. Collaborates with `sounddevice` and `crispasr`. Owns audio buffers and VAD state.
- **`utils/db.py`**: Persistence. Collaborates with PyMongo. Owns no state (stateless utility).

### 3D. COMPONENT VIEW — FRONTEND

- **`app.js`**: Core orchestrator. Collaborates with all other JS files. Owns high-level tab state and initialization.
- **`session.js`**: UI State sync. Collaborates with `api.js` and Canvas API. Owns the lerp animation loop and `SkeletonDrawer`.
- **`live.js`**: WebRTC Manager. Collaborates with `navigator.mediaDevices`. Owns the local video stream and MJPEG outbound loop.
- **`dashboard.js`**: Analytics rendering. Collaborates with Chart.js and SVG DOM. Owns muscle map heatmap opacity logic.
- **`friday_client.js`**: Global Voice Nav. Collaborates with `/ws/friday`. Owns global text-based assistant overlays and voice fast-tracking.
- **`standby.js`**: Task Manager. Collaborates with Tracker UI. Owns To-Do list state and the toggle between Standby and Workout modes.

### 3E. DEPLOYMENT VIEW

**Production / Local Run:**

- Requires Windows 11 / Linux with NVIDIA GPU (CUDA toolkit installed).
- **Simultaneous Processes:** `python -m uvicorn backend.endpoint:app --host 0.0.0.0 --port 8000`, plus the `crispasr` binary running via subprocess.
- **Static Files:** Served directly by FastAPI via `StaticFiles(directory="frontend")` mapped to `/`.
- **Environment Variables:** `MONGO_URI`, `JWT_SECRET`, `GEMINI_API_KEY`, `ANTHROPIC_API_KEY` must be present in `.env`.
- **Port:** 8000 (FastAPI), 8501 (Streamlit legacy).

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
SECTION 4 — EXHAUSTIVE FILE-BY-FILE BREAKDOWN
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

#### FILE: `generate_report.py`

**Role:** Component
**Line count:** 715
**Imports:** re, ast, os
**Exports / Public API:**

- `def write_report()`: No docstring provided. Participates in module logic.
- `def get_section_1()`: No docstring provided. Participates in module logic.
- `def get_section_2()`: No docstring provided. Participates in module logic.
- `def get_section_3()`: No docstring provided. Participates in module logic.
- `def get_section_5()`: No docstring provided. Participates in module logic.
- `def get_section_6()`: No docstring provided. Participates in module logic.
- `def get_section_7()`: No docstring provided. Participates in module logic.
- `def get_section_8()`: No docstring provided. Participates in module logic.
- `def get_section_9()`: No docstring provided. Participates in module logic.
- `def get_section_10()`: No docstring provided. Participates in module logic.
- `def get_section_11()`: No docstring provided. Participates in module logic.
- `def get_section_12()`: No docstring provided. Participates in module logic.
- `def get_section_13()`: No docstring provided. Participates in module logic.
- `def get_section_14()`: No docstring provided. Participates in module logic.
- `def get_section_15()`: No docstring provided. Participates in module logic.
- `def get_section_16()`: No docstring provided. Participates in module logic.
- `def get_section_17()`: No docstring provided. Participates in module logic.
- `def extract_python_info()`: No docstring provided. Participates in module logic.
- `def extract_js_info()`: No docstring provided. Participates in module logic.
- `def get_section_4()`: No docstring provided. Participates in module logic.
  **Class definitions:**

**Interaction narrative:** Automatically analyzed component. Participates in backend routing and ML execution.

#### FILE: `backend/app.py`

**Role:** Component
**Line count:** 1278
**Imports:** backend.counters.PullupCounter, backend.counters.BicepCurlCounter, streamlit_webrtc, os, backend.counters.KneePressCounter, backend.counters.KneeRaiseCounter, backend.agent.chatbot, backend.counters.SitupCounter, backend.utils, av, backend.counters.LateralRaiseCounter, backend.counters.OverheadPressCounter, jose, streamlit_cookies_controller, tempfile, backend.counters.CrunchCounter, sys, backend.counters.LegRaiseCounter, backend.counters.SquatCounter, time, dotenv, warnings, backend.counters.PushupCounter, streamlit, passlib.context, plotly.graph_objects, threading, cv2, datetime, calendar
**Exports / Public API:**

- `def _hash_pw()`: No docstring provided. Participates in module logic.
- `def _verify_pw()`: No docstring provided. Participates in module logic.
- `def _create_auth_token()`: Create a short-lived JWT for the auth cookie.
- `def _decode_auth_token()`: Decode the JWT; returns username string or None on failure.
- `def _password_strength()`: Return (label, colour) for the password strength meter.
- `def _calc_calories()`: Standard MET calorie formula with weight adjustment.
- `def inject_css()`: No docstring provided. Participates in module logic.
- `def _init_state()`: No docstring provided. Participates in module logic.
- `def render_login_page()`: No docstring provided. Participates in module logic.
- `def _do_login()`: Look up user by email, verify password, set session state and cookie.
- `def render_onboarding_page()`: No docstring provided. Participates in module logic.
- `def render_sidebar()`: No docstring provided. Participates in module logic.
- `def render_stats_panel()`: No docstring provided. Participates in module logic.
- `def render_tracker_page()`: No docstring provided. Participates in module logic.
- `def _render_webcam()`: No docstring provided. Participates in module logic.
- `def _render_upload()`: No docstring provided. Participates in module logic.
- `def render_dashboard_page()`: No docstring provided. Participates in module logic.
- `def _render_calendar()`: No docstring provided. Participates in module logic.
- `def _render_day_detail()`: No docstring provided. Participates in module logic.
- `def _render_radar_chart()`: No docstring provided. Participates in module logic.
- `def _render_svg_heatmap()`: No docstring provided. Participates in module logic.
- `def _render_volume_chart()`: No docstring provided. Participates in module logic.
- `def render_metrics_page()`: No docstring provided. Participates in module logic.
- `def _render_metric_chart()`: Plot a metric over time. Connect points with a line only if consecutive dates differ by ≤ 7 days, otherwise show isolated markers.
- `def render_chatbot_page()`: No docstring provided. Participates in module logic.
- `def _send_chat_message()`: No docstring provided. Participates in module logic.
- `def main()`: No docstring provided. Participates in module logic.
  **Class definitions:**
- **Class `ExerciseVideoProcessor`**:
  - `__init__()`: Method execution
  - `recv()`: Method execution
  - `get_stats()`: Method execution
    **Interaction narrative:** Automatically analyzed component. Participates in backend routing and ML execution.

#### FILE: `backend/endpoint.py`

**Role:** Component
**Line count:** 1439
**Imports:** fastapi.staticfiles, **future**, backend.agent.graph, os, json, pydantic, backend.agent.chatbot, numpy, fastapi, backend.utils, base64, fastapi.responses, jose, backend.utils.db, backend.utils.session_manager, fastapi.middleware.cors, asyncio, tempfile, pathlib, fastapi.security, re, contextlib, sys, time, uvicorn, dotenv, backend.utils.validation, backend.agent.stt, passlib.context, backend.utils.calorie_tracker, cv2, datetime, typing
**Exports / Public API:**

- `def _hash_password()`: No docstring provided. Participates in module logic.
- `def _verify_password()`: No docstring provided. Participates in module logic.
- `def _create_access_token()`: No docstring provided. Participates in module logic.
- `def _get_current_user()`: Dependency — decode JWT and return username, or raise 401.
- `def _get_user_channel()`: No docstring provided. Participates in module logic.
- `def _broadcast_friday()`: Push a WebSocket message to ALL active Friday voice connections. NOTE: only safe when a loop is already running (from async context). For background-thread callers use run_coroutine_threadsafe directly.
- `def _ensure_stt_running()`: Lazily start the Whisper STT daemon the first time a user switches to voice channel. No-op if the daemon is already running.
- `def _decode_jpeg()`: No docstring provided. Participates in module logic.
- `def _kps_to_list()`: No docstring provided. Participates in module logic.
  **Class definitions:**
- **Class `MeResponse`**:

- **Class `StartSessionRequest`**:

- **Class `StartSessionResponse`**:

- **Class `CalorieScanRequest`**:

**Interaction narrative:** Automatically analyzed component. Participates in backend routing and ML execution.

#### FILE: `backend/__init__.py`

**Role:** Component
**Line count:** 1
**Imports:**
**Exports / Public API:**

**Class definitions:**

**Interaction narrative:** Automatically analyzed component. Participates in backend routing and ML execution.

#### FILE: `backend/agent/chatbot.py`

**Role:** Component
**Line count:** 107
**Imports:** langchain_google_genai, backend.utils, sys, backend.agent.graph, os, dotenv, langchain_core.messages
**Exports / Public API:**

- `def _get_response()`: Return the assistant's reply for one chat turn. Tries Friday (Azure) first; falls back to Gemini if not configured.
- `def _friday_response()`: No docstring provided. Participates in module logic.
- `def _gemini_response()`: No docstring provided. Participates in module logic.
  **Class definitions:**

**Interaction narrative:** Automatically analyzed component. Participates in backend routing and ML execution.

#### FILE: `backend/agent/graph.py`

**Role:** Component
**Line count:** 573
**Imports:** langgraph.graph, **future**, pymongo, os, json, backend.agent.chatbot, numpy, backend.utils, backend.agent.memory, typing_extensions, langgraph.checkpoint.memory, dotenv, langchain_anthropic, langchain_core.messages, langgraph.graph.message, langchain_google_genai, backend.utils.calorie_tracker, cv2, langgraph.checkpoint.mongodb, datetime, typing
**Exports / Public API:**

- `def _get_llm()`: Return the main LLM (Claude or Gemini 2.0 Flash) for response generation.
- `def _get_intent_llm()`: Return a cheap/fast LLM for intent classification. Uses gemini-2.0-flash-lite (higher free-tier quota, lower latency) when Gemini is the active backend. Falls back to the main LLM if not available.
- `def _get_checkpointer()`: Return a LangGraph-compatible BaseCheckpointSaver backed by MongoDB. langgraph-checkpoint-mongodb 0.3.1+: AsyncMongoDBSaver was removed. The unified MongoDBSaver now accepts a standard pymongo.MongoClient and supports both sync (graph.invoke) and async (graph.ainvoke) graphs. The client is created once and held for the process lifetime — no context manager needed so we never hit 'Cannot use MongoClient after close'. Falls back to MemorySaver if MongoDB is unavailable.
- `def intent_node()`: Classify the latest user message into a command key + confidence.
- `def _route_after_intent()`: No docstring provided. Participates in module logic.
- `def tool_node()`: Execute the handler for the detected intent.
- `def clarify_node()`: No docstring provided. Participates in module logic.
- `def memory_write_node()`: Write the user's latest message to unified MongoDB conversation history.
- `def response_node()`: Generate Friday's reply, channel-aware.
- `def _build_addendum()`: Convert tool_result into a plain-text context addendum for the LLM.
- `def get_friday_graph()`: Lazily compile and return the Friday LangGraph agent.
- `def invoke_friday()`: Invoke the Friday agent for one turn. Returns {response: str, intent: str, tool_result: dict | None} Falls back to Gemini chatbot if no LLM is configured at all.
  **Class definitions:**
- **Class `AgentState`**:

**Interaction narrative:** Automatically analyzed component. Participates in backend routing and ML execution.

#### FILE: `backend/agent/memory.py`

**Role:** Component
**Line count:** 136
**Imports:** backend.utils, **future**, os, datetime, dotenv, typing
**Exports / Public API:**

- `def build_system_prompt()`: Assemble the full system prompt for Friday. Imports db lazily to avoid circular imports at module load time.
- `def should_regenerate_summary()`: Returns True if the memory summary should be regenerated. Trigger: total turn count has grown by more than 40 turns since last summary.
  **Class definitions:**

**Interaction narrative:** Automatically analyzed component. Participates in backend routing and ML execution.

#### FILE: `backend/agent/stt.py`

**Role:** Component
**Line count:** 487
**Imports:** numpy, subprocess, scipy.signal, tempfile, pathlib, re, threading, collections, **future**, torch, soundfile, os, sounddevice, typing
**Exports / Public API:**

**Class definitions:**

- **Class `FridaySTT`**:
  - `__init__()`: Method execution
  - `instance()`: Method execution
  - `start()`: Start the STT daemon thread. No-op if already running.
  - `stop()`: Method execution
  - `_log_audio_device_info()`: Log audio device configuration for debugging.
  - `_load_vad()`: Method execution
  - `_run()`: Method execution
  - `_recognition_loop()`: Method execution
  - `_is_junk_transcript()`: Return True if the transcript is too short or a known noise artifact.
  - `_transcribe()`: Write buffered audio to a temp WAV, pass to CrispASR Qwen3-ASR binary, parse stdout for the transcript, fire callback. Uses Windows-safe path handling (backslashes, %TEMP%, list-arg subprocess).
  - `_fire_barge_in()`: Stop TTS immediately — only called after BARGE_IN_CHUNKS consecutive high-confidence (≥ BARGE_IN_THRESHOLD) VAD detections. This prevents noise spikes and low-confidence VAD hits from aborting TTS playback.
  - `_fire_speech_start()`: Fire the on_speech_start callback. Barge-in is handled separately by \_fire_barge_in() and may have already fired before this point.
  - `_fire_speech_end()`: Method execution
    **Interaction narrative:** Automatically analyzed component. Participates in backend routing and ML execution.

#### FILE: `backend/agent/tts.py`

**Role:** Component
**Line count:** 371
**Imports:** subprocess, tempfile, base64, threading, **future**, os, typing
**Exports / Public API:**

- `def speak()`: Synchronous TTS synthesis via Voxtral. Returns raw WAV bytes or None on failure / barge-in. voice_id is a Voxtral preset name (e.g. "casual_female"). Any unrecognised value (e.g. a legacy ElevenLabs ID stored in the DB) is silently replaced with \_DEFAULT_VOICE_ID without raising.
- `def stop_speaking()`: Interrupt current TTS playback. Called by STT on barge-in.
- `def to_ws_envelope()`: Wrap raw WAV bytes in a JSON-serialisable WebSocket message. Second arg is unused (kept for call-site compatibility with endpoint.py).
- `def speaking_indicator()`: Return a friday_speaking WebSocket message dict. Called as: await ws.send_json(speaking_indicator(True/False))
- `def list_voices()`: Return available Voxtral voice presets as [{name, voice_id}, ...].
  **Class definitions:**
- **Class `FridayTTS`**:
  - `__init__()`: Method execution
  - `instance()`: Method execution
  - `is_speaking()`: Method execution
  - `speak_sync()`: Synthesise `text` via Voxtral and return raw WAV bytes. Blocking — intended to be called from asyncio.to_thread(). Returns None on error or barge-in.
  - `stop_speaking()`: Interrupt current synthesis immediately (called by STT barge-in).
  - `preload()`: Spawn a background warmup to prime Voxtral's GPU autotune cache.
  - `_warmup()`: Method execution
    **Interaction narrative:** Automatically analyzed component. Participates in backend routing and ML execution.

#### FILE: `backend/counters/BaseCounter.py`

**Role:** Component
**Line count:** 419
**Imports:** numpy, random, math, collections, typing, cv2, time, abc, backend.detector.PoseDetector
**Exports / Public API:**

**Class definitions:**

- **Class `BaseCounter`**:
  - `__init__()`: Method execution
  - `reset()`: Reset all counter state back to defaults.
  - `_kp_map()`: Build {kp_id: (cx, cy)} mapping from landmarks_list.
  - `calc_velocity()`: Average pixel/s speed of keypoint `kp_idx` over the sliding window of the last 5 skeleton snapshots. Uses a deque of (timestamp, {kp_id: (cx, cy)}) tuples; O(1) updates. Returns 0.0 if fewer than 2 frames are available.
  - `_record_rep_velocity()`: Record the velocity at the moment a rep completes. Also checks for failure trend and queues a motivational phrase if detected. Call this from each counter's \_compute() when a rep is counted.
  - `_check_failure_trend()`: Return a motivational string if rep velocity is declining significantly.
  - `pop_failure_motivation()`: Consume and return pending motivational phrase (one per rep).
  - `_kp_pos()`: Return (cx, cy) for keypoint `idx`, or None if not found.
  - `_angle_3pts()`: Angle at vertex B formed by A–B–C, in degrees. Returns None if any point is None.
  - `_check_posture()`: Exercise-specific posture checks. Override in subclasses. Errors must be returned in PRIORITY order — highest risk first. Returns: (error_key: str, human_message: str) or (None, None)
  - `pop_posture_tts()`: Returns posture_msg if the 6-second TTS cooldown has elapsed for this error key. The HUD always shows the current error immediately; the TTS fires at most once per 6 s per unique error.
  - `process_frame()`: Process a single BGR video frame and return annotated results. Returns dict with: frame — annotated BGR numpy array counter — integer rep count feedback — "Up" | "Down" | "Fix Form" | "Get in Position" progress — float 0-100 correct_form — bool posture_error — short error key or None posture_msg — human correction message or None velocity — float px/s (0 if insufficient history)
  - `_smooth_angle()`: Method execution
  - `_avg_angles()`: Method execution
  - `_active_per_limb()`: Method execution
  - `_debounced_increment()`: Method execution
  - `_tick_bilateral()`: Method execution
  - `_tick_per_limb()`: Method execution
  - `_update_count()`: Legacy generic half-rep counting (not used by state-machine counters).
  - `_draw_overlays()`: Draw the progress bar onto frame.
  - `_make_result()`: Method execution
  - `_compute()`: Exercise-specific angle analysis and state-machine tick. Returns: Tuple of: progress_pct (float) — 0–100 for the UI progress bar feedback (str) — "Up" | "Down" | "Fix Form" | "Get in Position" form_ok (bool) — True if current frame has valid starting form
    **Interaction narrative:** Automatically analyzed component. Participates in backend routing and ML execution.

#### FILE: `backend/counters/BicepCurlCounter.py`

**Role:** Component
**Line count:** 122
**Imports:** numpy, backend.counters.BaseCounter
**Exports / Public API:**

**Class definitions:**

- **Class `BicepCurlCounter`**:
  - `__init__()`: Method execution
  - `_compute()`: Method execution
  - `_check_posture()`: Method execution
    **Interaction narrative:** Automatically analyzed component. Participates in backend routing and ML execution.

#### FILE: `backend/counters/CrunchCounter.py`

**Role:** Component
**Line count:** 91
**Imports:** numpy, backend.counters.BaseCounter
**Exports / Public API:**

**Class definitions:**

- **Class `CrunchCounter`**:
  - `_compute()`: Method execution
  - `_check_posture()`: Method execution
    **Interaction narrative:** Automatically analyzed component. Participates in backend routing and ML execution.

#### FILE: `backend/counters/KneePressCounter.py`

**Role:** Component
**Line count:** 87
**Imports:** numpy, backend.counters.BaseCounter
**Exports / Public API:**

**Class definitions:**

- **Class `KneePressCounter`**:
  - `_compute()`: Method execution
  - `_check_posture()`: Method execution
    **Interaction narrative:** Automatically analyzed component. Participates in backend routing and ML execution.

#### FILE: `backend/counters/KneeRaiseCounter.py`

**Role:** Component
**Line count:** 96
**Imports:** numpy, backend.counters.BaseCounter
**Exports / Public API:**

**Class definitions:**

- **Class `KneeRaiseCounter`**:
  - `_compute()`: Method execution
  - `_check_posture()`: Method execution
    **Interaction narrative:** Automatically analyzed component. Participates in backend routing and ML execution.

#### FILE: `backend/counters/LateralRaiseCounter.py`

**Role:** Component
**Line count:** 88
**Imports:** numpy, backend.counters.BaseCounter
**Exports / Public API:**

**Class definitions:**

- **Class `LateralRaiseCounter`**:
  - `_compute()`: Method execution
  - `_check_posture()`: Method execution
    **Interaction narrative:** Automatically analyzed component. Participates in backend routing and ML execution.

#### FILE: `backend/counters/LegRaiseCounter.py`

**Role:** Component
**Line count:** 92
**Imports:** numpy, backend.counters.BaseCounter
**Exports / Public API:**

**Class definitions:**

- **Class `LegRaiseCounter`**:
  - `_compute()`: Method execution
  - `_check_posture()`: Method execution
    **Interaction narrative:** Automatically analyzed component. Participates in backend routing and ML execution.

#### FILE: `backend/counters/OverheadPressCounter.py`

**Role:** Component
**Line count:** 90
**Imports:** numpy, backend.counters.BaseCounter
**Exports / Public API:**

**Class definitions:**

- **Class `OverheadPressCounter`**:
  - `_compute()`: Method execution
  - `_check_posture()`: Method execution
    **Interaction narrative:** Automatically analyzed component. Participates in backend routing and ML execution.

#### FILE: `backend/counters/PullupCounter.py`

**Role:** Component
**Line count:** 83
**Imports:** numpy, backend.counters.BaseCounter
**Exports / Public API:**

**Class definitions:**

- **Class `PullupCounter`**:
  - `_compute()`: Method execution
  - `_check_posture()`: Method execution
    **Interaction narrative:** Automatically analyzed component. Participates in backend routing and ML execution.

#### FILE: `backend/counters/PushupCounter.py`

**Role:** Component
**Line count:** 120
**Imports:** numpy, backend.counters.BaseCounter
**Exports / Public API:**

**Class definitions:**

- **Class `PushupCounter`**:
  - `_compute()`: Method execution
  - `_check_posture()`: Method execution
    **Interaction narrative:** Automatically analyzed component. Participates in backend routing and ML execution.

#### FILE: `backend/counters/SitupCounter.py`

**Role:** Component
**Line count:** 79
**Imports:** numpy, backend.counters.BaseCounter
**Exports / Public API:**

**Class definitions:**

- **Class `SitupCounter`**:
  - `_compute()`: Method execution
  - `_check_posture()`: Method execution
    **Interaction narrative:** Automatically analyzed component. Participates in backend routing and ML execution.

#### FILE: `backend/counters/SquatCounter.py`

**Role:** Component
**Line count:** 95
**Imports:** numpy, backend.counters.BaseCounter
**Exports / Public API:**

**Class definitions:**

- **Class `SquatCounter`**:
  - `_compute()`: Method execution
  - `_check_posture()`: Method execution
    **Interaction narrative:** Automatically analyzed component. Participates in backend routing and ML execution.

#### FILE: `backend/counters/__init__.py`

**Role:** Component
**Line count:** 26
**Imports:** backend.counters.SitupCounter, backend.counters.PullupCounter, backend.counters.CrunchCounter, backend.counters.LegRaiseCounter, backend.counters.BicepCurlCounter, backend.counters.SquatCounter, backend.counters.LateralRaiseCounter, backend.counters.OverheadPressCounter, backend.counters.KneePressCounter, backend.counters.PushupCounter, backend.counters.KneeRaiseCounter
**Exports / Public API:**

**Class definitions:**

**Interaction narrative:** Automatically analyzed component. Participates in backend routing and ML execution.

#### FILE: `backend/detector/PoseDetector.py`

**Role:** Component
**Line count:** 248
**Imports:** warnings, cv2, numpy, rtmlib
**Exports / Public API:**

- `def main()`: Quick smoke-test: open webcam and show RTMPose skeleton. Fixes applied (video_pipeline_implementation_plan.md): ------------------------------------------------------- • cap.set(CAP_PROP_BUFFERSIZE, 1) → eliminates stale-frame accumulation • cv2.waitKey(1) instead of (10) → removes the artificial 10ms/frame floor that was gating inference time unnecessarily.
  **Class definitions:**
- **Class `PoseDetectorModified`**:
  - `__init__()`: Args: mode : "lightweight" | "balanced" | "performance" backend : "onnxruntime" | "opencv" device : "auto" | "cuda" | "cpu" "auto" tries CUDA first and silently falls back to CPU if CUDA is unavailable (no GPU, missing driver, ORT not built with CUDA support).
  - `findPose()`: Run RTMPose on img. Stores first-person keypoints internally. Frames wider/taller than 640 px are downscaled for inference and the keypoints are scaled back to original pixel coordinates before storage.
  - `findPosition()`: Return [[id, cx, cy, score], …] for the 17 COCO-Body keypoints. The 4th element (score) is read by findAngle to skip low-confidence joints — no manual filtering needed by the caller.
  - `findAngle()`: Dot-product angle at joint p2, between vectors p1→p2 and p3→p2. Returns None if: • any of the three keypoints has confidence < 0.5 • either vector has zero magnitude (overlapping or zeroed keypoints)
  - `_draw_skeleton()`: Draw COCO-17 Body bones and keypoint dots onto img in-place. Explicitly sliced to [:17] so this is safe even if the underlying model returns a larger array (e.g. during a model swap).
    **Interaction narrative:** Automatically analyzed component. Participates in backend routing and ML execution.

#### FILE: `backend/detector/__init__.py`

**Role:** Component
**Line count:** 0
**Imports:**
**Exports / Public API:**

**Class definitions:**

**Interaction narrative:** Automatically analyzed component. Participates in backend routing and ML execution.

#### FILE: `backend/logger/metrics.py`

**Role:** Component
**Line count:** 106
**Imports:** pathlib, collections, **future**, time, logging
**Exports / Public API:**

**Class definitions:**

- **Class `PipelineMetrics`**:
  - `__init__()`: Method execution
  - `record_inference()`: Method execution
  - `record_capture()`: Method execution
  - `record_e2e()`: Method execution
  - `maybe_report()`: Call at the end of each inference cycle. Logs only every 5 s.
  - `_write_report()`: Method execution
    **Interaction narrative:** Automatically analyzed component. Participates in backend routing and ML execution.

#### FILE: `backend/logger/__init__.py`

**Role:** Component
**Line count:** 0
**Imports:**
**Exports / Public API:**

**Class definitions:**

**Interaction narrative:** Automatically analyzed component. Participates in backend routing and ML execution.

#### FILE: `backend/reader/code_reader.py`

**Role:** Component
**Line count:** 77
**Imports:** pyzbar.pyzbar, torch.cuda, numpy, functools, ultralytics, cv2, os, dotenv
**Exports / Public API:**

- `def get_yolo()`: Fetches the YOLO on the first instance and caches it for all the subsequent calls.
  **Class definitions:**
- **Class `BarReader`**:
  - `__init__()`: Method execution
  - `_get_bbox()`: Method execution
  - `_crop_with_padding()`: Method execution
  - `_detect_bar()`: Method execution
  - `_read_bar()`: Method execution
    **Interaction narrative:** Automatically analyzed component. Participates in backend routing and ML execution.

#### FILE: `backend/reader/__init__.py`

**Role:** Component
**Line count:** 0
**Imports:**
**Exports / Public API:**

**Class definitions:**

**Interaction narrative:** Automatically analyzed component. Participates in backend routing and ML execution.

#### FILE: `backend/utils/calorie_tracker.py`

**Role:** Component
**Line count:** 156
**Imports:** google, backend.utils, base64, **future**, cv2, dotenv, os, datetime, json, google.genai
**Exports / Public API:**

- `def _encode_frame()`: JPEG-encode a BGR numpy array → base64 string.
- `def _repair_json()`: Best-effort repair for truncated JSON — closes open strings/brackets.
- `def scan_food_from_frame()`: Run food calorie estimation on a BGR camera frame using Gemini Vision. Returns a dict matching the calorie_result schema: {foods, total_calories, confidence, notes, log_id?} On error returns {error: str, message: str}.
  **Class definitions:**

**Interaction narrative:** Automatically analyzed component. Participates in backend routing and ML execution.

#### FILE: `backend/utils/db.py`

**Role:** Component
**Line count:** 867
**Imports:** uuid, pymongo.server_api, pymongo, **future**, os, datetime, dotenv, typing
**Exports / Public API:**

- `def _get_db()`: Lazy singleton — creates the MongoClient on first call.
- `def _users()`: No docstring provided. Participates in module logic.
- `def _workouts()`: No docstring provided. Participates in module logic.
- `def _chats()`: No docstring provided. Participates in module logic.
- `def _metrics()`: No docstring provided. Participates in module logic.
- `def _calorie_logs()`: No docstring provided. Participates in module logic.
- `def _conversation_turns()`: No docstring provided. Participates in module logic.
- `def _diet_plans()`: No docstring provided. Participates in module logic.
- `def _fulfilled_requests()`: No docstring provided. Participates in module logic.
- `def _memory_summaries()`: No docstring provided. Participates in module logic.
- `def _workout_plans()`: No docstring provided. Participates in module logic.
- `def _entry_sets_list()`: Normalise a workout entry to a list of per-set rep counts. Handles both the new list format {"sets": [12, 10, 14]} and the old flat format {"reps": 36, "sets": 3}.
- `def _entry_weights_list()`: Return the per-set weights list, defaulting to 0.0 if not present.
- `def get_all_users()`: Return {username: user_record} for all users.
- `def get_user()`: No docstring provided. Participates in module logic.
- `def get_user_by_email()`: Find a user record by email address (email is used as unique identifier).
- `def get_username_by_email()`: Return the username (storage key) for a given email, or None if not found.
- `def create_user()`: No docstring provided. Participates in module logic.
- `def update_user_profile()`: Overwrite the full onboarding profile dict.
- `def set_user_voice()`: Persist the user's preferred Friday TTS voice WITHOUT touching the rest of the profile. Uses a dot-path $set so existing onboarding data is safe.
- `def get_user_voice()`: Return the stored Friday voice ID for a user, or None.
- `def get_user_profile()`: No docstring provided. Participates in module logic.
- `def save_workout()`: Append a completed set to the user's workout log. Each save call appends `reps` to the sets list, `weight_kg` to the weights list, and optionally `calories_burnt` to the calories list. `sets` param is kept for API compat but only `reps` is recorded per call. Returns the {exercise: {sets: [...], weights: [...], calories: [...]}} map for that day.
- `def get_workout_history()`: Return the full workout history dict {date: {exercise: {sets, weights}}}.
- `def get_monthly_stats()`: Aggregate _sets_ by fine-grained muscle group for a given month (YYYY-MM). Returns {muscle_group: set_count} for fine-grained groups. Also includes broad-group totals (Arms, Back, Legs, Shoulders) derived from the fine-grained data so the radar chart continues to work.
- `def get_total_sets_month()`: Total number of sets performed in the given month.
- `def get_volume_history()`: Return total volume (reps × weight_kg) per exercise per day. If year_month given (YYYY-MM), only that month. Returns {date: {exercise: total_volume_kg}}.
- `def get_monthly_volume_by_exercise()`: Aggregate total volume (reps × weight_kg) per exercise for a given month. Returns {exercise_name: total_kg_volume}.
- `def get_monthly_calories()`: Sum all calories burnt across every set for a given month (YYYY-MM). Returns total calories as a float.
- `def load_chat_history()`: Return list of {role, content} dicts.
- `def append_chat_message()`: No docstring provided. Participates in module logic.
- `def clear_chat_history()`: No docstring provided. Participates in module logic.
- `def log_metric()`: Upsert a body metric entry for a given date. Only fields explicitly provided (not None) are updated. metric_date must be YYYY-MM-DD and must not be in the future.
- `def get_metrics()`: Return all body metric entries for a user, sorted by date ascending. Each entry: {date, weight_kg?, height_cm?}
- `def log_calorie_entry()`: Persist a single food-scan result. entry must contain: {timestamp, foods, total_calories, confidence, notes} foods is a list of {name, portion, calories}. Returns the stored document (with generated log_id).
- `def get_calorie_logs()`: Return paginated calorie scan logs for a user, newest first.
- `def get_calories_today()`: Sum total_calories from all food scans logged since midnight UTC today. Returns total as float.
- `def delete_calorie_log()`: Delete a calorie log entry by log_id. Returns True if deleted.
- `def append_conversation_turn()`: Append a turn to the shared conversation history. channel: 'text' | 'voice' attachments: optional list of {type, ref_id} dicts
- `def get_recent_turns()`: Return the last N conversation turns across all channels, oldest first.
- `def get_turn_count()`: Return total number of conversation turns stored for a user.
- `def save_diet_plan()`: Store a Friday-generated diet plan. Marks all previous plans as inactive.
- `def get_active_diet_plan()`: Return the current active diet plan for a user, or None.
- `def log_fulfilled_request()`: Log a significant action Friday has completed.
- `def get_fulfilled_requests()`: Return the N most recent fulfilled requests for context injection.
- `def save_memory_summary()`: Store a generated memory summary covering a range of turn indices.
- `def get_latest_memory_summary()`: Return the most recent memory summary for a user, or None.
- `def save_workout_plan()`: Upsert the recurring workout plan for a given weekday. `exercises` is an ordered list of {exercise_key, sets, reps, weight_kg}. `workout_time` is an optional "HH:MM" string for automatic Standby Mode trigger. The plan repeats every week on this weekday until explicitly deleted.
- `def get_workout_plan()`: Return the active recurring plan for `weekday`, or None if not set.
- `def get_all_workout_plans()`: Return the full weekly schedule as {weekday: plan_or_None}.
- `def delete_workout_plan()`: Soft-delete a day's plan (marks is_active=False). Returns True if found.
- `def suggest_replacement_exercises()`: Return up to `limit` alternative exercises from the same muscle group. Each result: {exercise_key, display_name, muscle_group}
- `def _todos()`: No docstring provided. Participates in module logic.
- `def save_todo()`: Create a new to-do item. Returns the stored document.
- `def get_todos()`: Return all to-do items for a given date, sorted by time (all-day first).
- `def toggle_todo()`: Toggle the completed state of a todo. Returns updated doc or None.
- `def delete_todo()`: Hard-delete a to-do item. Returns True if found and deleted.
  **Class definitions:**

**Interaction narrative:** Automatically analyzed component. Participates in backend routing and ML execution.

#### FILE: `backend/utils/session_manager.py`

**Role:** Component
**Line count:** 264
**Imports:** backend.counters.PullupCounter, backend.counters.BicepCurlCounter, **future**, os, queue, backend.counters.KneePressCounter, backend.counters.KneeRaiseCounter, backend.counters.SitupCounter, backend.counters.LateralRaiseCounter, backend.counters.OverheadPressCounter, uuid, backend.counters.CrunchCounter, sys, backend.counters.LegRaiseCounter, backend.utils.singleton, backend.counters.SquatCounter, time, backend.logger.metrics, backend.counters.PushupCounter, threading, typing
**Exports / Public API:**

- `def _kps_to_list()`: No docstring provided. Participates in module logic.
- `def _load_counter_map()`: No docstring provided. Participates in module logic.
  **Class definitions:**
- **Class `InferenceWorker`**:
  - `__init__()`: Method execution
  - `stop()`: Signal the thread to exit on its next iteration.
  - `run()`: Method execution
- **Class `SessionData`**:
  - `__init__()`: Method execution
  - `stop()`: Stop the inference worker cleanly.
- **Class `SessionManager`**:
  - `__init__()`: Method execution
  - `instance()`: Method execution
  - `create()`: Method execution
  - `get()`: Method execution
  - `reset()`: Method execution
  - `destroy()`: Method execution
  - `list_exercises()`: Method execution
    **Interaction narrative:** Automatically analyzed component. Participates in backend routing and ML execution.

#### FILE: `backend/utils/singleton.py`

**Role:** Component
**Line count:** 52
**Imports:** time, threading, typing
**Exports / Public API:**

**Class definitions:**

- **Class `AtomicFrame`**:
  - `__init__()`: Method execution
  - `write()`: Overwrite the slot. Returns the write timestamp.
  - `read()`: Return (frame, written_at). Frame is None until first write.
- **Class `AtomicResult`**:
  - `__init__()`: Method execution
  - `write()`: Method execution
  - `read()`: Method execution
    **Interaction narrative:** Automatically analyzed component. Participates in backend routing and ML execution.

#### FILE: `backend/utils/validation.py`

**Role:** Component
**Line count:** 295
**Imports:** re, pydantic, typing, **future**
**Exports / Public API:**

**Class definitions:**

- **Class `SignupRequest`**:

- **Class `LoginRequest`**:

- **Class `TokenResponse`**:

- **Class `UserProfile`**:

- **Class `UserProfileResponse`**:

- **Class `SaveWorkoutRequest`**:

- **Class `WorkoutEntry`**:
  - `total_reps()`: Method execution
  - `total_sets()`: Method execution
  - `total_volume()`: Total volume = sum(reps_i × weight_i) for all sets.
- **Class `DayWorkout`**:

- **Class `WorkoutHistoryResponse`**:

- **Class `MuscleGroupStat`**:

- **Class `WorkoutStatsResponse`**:

- **Class `ExerciseVolume`**:

- **Class `VolumeResponse`**:

- **Class `MetricLogRequest`**:

- **Class `MetricPoint`**:

- **Class `MetricsResponse`**:

- **Class `ChatRequest`**:

- **Class `ChatMessage`**:

- **Class `ChatResponse`**:

- **Class `FoodItem`**:

- **Class `CalorieLogEntry`**:

- **Class `CalorieLogResponse`**:

- **Class `CaloriesTodayResponse`**:

- **Class `ConversationTurn`**:

- **Class `DietPlan`**:

- **Class `FulfilledRequest`**:

- **Class `PlanExercise`**:

- **Class `SaveWorkoutPlanRequest`**:

- **Class `WorkoutPlanResponse`**:

- **Class `WeeklyScheduleResponse`**:

- **Class `ReplacementSuggestion`**:

- **Class `ReplacementResponse`**:

- **Class `SaveToDoRequest`**:
  - `_validate_time()`: Accept HH:MM or None.
  - `model_post_init()`: Method execution
- **Class `ToDoItem`**:

- **Class `ToDoListResponse`**:

**Interaction narrative:** Automatically analyzed component. Participates in backend routing and ML execution.

#### FILE: `backend/utils/__init__.py`

**Role:** Component
**Line count:** 0
**Imports:**
**Exports / Public API:**

**Class definitions:**

**Interaction narrative:** Automatically analyzed component. Participates in backend routing and ML execution.

#### FILE: `frontend/app.js`

**Role:** Frontend logic
**Line count:** 227
**Exports / Functions:**

- `onState()`: Executes frontend UI interactions or API calls.
- `_showAutoStartBanner()`: Executes frontend UI interactions or API calls.
- `checkTodayPlan()`: Executes frontend UI interactions or API calls.
- `_emit()`: Executes frontend UI interactions or API calls.
- `transition()`: Executes frontend UI interactions or API calls.
- `getState()`: Executes frontend UI interactions or API calls.
- `StateMachine()`: Executes frontend UI interactions or API calls.
- `switchTab()`: Executes frontend UI interactions or API calls.
- `init()`: Executes frontend UI interactions or API calls.
  **Interaction narrative:** Manipulates DOM state and communicates with FastAPI backend.

#### FILE: `frontend/calorie.html`

**Role:** HTML Template
**Line count:** 366
**Interaction narrative:** Renders DOM.

#### FILE: `frontend/chatbot.html`

**Role:** HTML Template
**Line count:** 224
**Interaction narrative:** Renders DOM.

#### FILE: `frontend/dashboard.html`

**Role:** HTML Template
**Line count:** 480
**Interaction narrative:** Renders DOM.

#### FILE: `frontend/index.html`

**Role:** HTML Template
**Line count:** 713
**Interaction narrative:** Renders DOM.

#### FILE: `frontend/login.html`

**Role:** HTML Template
**Line count:** 479
**Interaction narrative:** Renders DOM.

#### FILE: `frontend/metrics.html`

**Role:** HTML Template
**Line count:** 139
**Interaction narrative:** Renders DOM.

#### FILE: `frontend/plans.html`

**Role:** HTML Template
**Line count:** 739
**Interaction narrative:** Renders DOM.

#### FILE: `frontend/todo.html`

**Role:** HTML Template
**Line count:** 529
**Interaction narrative:** Renders DOM.

#### FILE: `frontend/welcome.html`

**Role:** HTML Template
**Line count:** 414
**Interaction narrative:** Renders DOM.

#### FILE: `frontend/js/api.js`

**Role:** Frontend logic
**Line count:** 171
**Exports / Functions:**

- `clearToken()`: Executes frontend UI interactions or API calls.
- `requireAuth()`: Executes frontend UI interactions or API calls.
- `authHeaders()`: Executes frontend UI interactions or API calls.
- `getToken()`: Executes frontend UI interactions or API calls.
- `apiFetch()`: Executes frontend UI interactions or API calls.
- `setToken()`: Executes frontend UI interactions or API calls.
  **Interaction narrative:** Manipulates DOM state and communicates with FastAPI backend.

#### FILE: `frontend/js/auth.js`

**Role:** Frontend logic
**Line count:** 361
**Exports / Functions:**

- `goToStep()`: Executes frontend UI interactions or API calls.
- `submitProfile()`: Executes frontend UI interactions or API calls.
- `flipCard()`: Executes frontend UI interactions or API calls.
- `goToStep2()`: Executes frontend UI interactions or API calls.
- `_adaptStep4ForApp()`: Executes frontend UI interactions or API calls.
- `goToPlansManual()`: Executes frontend UI interactions or API calls.
- `skipPlanCreation()`: Executes frontend UI interactions or API calls.
- `togglePass()`: Executes frontend UI interactions or API calls.
- `wireStrengthMeter()`: Executes frontend UI interactions or API calls.
- `goToChatForPlan()`: Executes frontend UI interactions or API calls.
- `showError()`: Executes frontend UI interactions or API calls.
- `calcPasswordStrength()`: Executes frontend UI interactions or API calls.
- `showOnboarding()`: Executes frontend UI interactions or API calls.
- `clearError()`: Executes frontend UI interactions or API calls.
- `goToStep1()`: Executes frontend UI interactions or API calls.
  **Interaction narrative:** Manipulates DOM state and communicates with FastAPI backend.

#### FILE: `frontend/js/calorie.js`

**Role:** Frontend logic
**Line count:** 223
**Exports / Functions:**

- `hideNoFood()`: Executes frontend UI interactions or API calls.
- `showNoFood()`: Executes frontend UI interactions or API calls.
- `setWaveMode()`: Executes frontend UI interactions or API calls.
- `showResult()`: Executes frontend UI interactions or API calls.
- `initCamera()`: Executes frontend UI interactions or API calls.
- `escHtml()`: Executes frontend UI interactions or API calls.
- `takeSnapshot()`: Executes frontend UI interactions or API calls.
- `showScanningOverlay()`: Executes frontend UI interactions or API calls.
- `openFridayWS()`: Executes frontend UI interactions or API calls.
- `hidePopup()`: Executes frontend UI interactions or API calls.
  **Interaction narrative:** Manipulates DOM state and communicates with FastAPI backend.

#### FILE: `frontend/js/chat.js`

**Role:** Frontend logic
**Line count:** 174
**Exports / Functions:**

- `clearHistory()`: Executes frontend UI interactions or API calls.
- `formatMessage()`: Executes frontend UI interactions or API calls.
- `scrollToBottom()`: Executes frontend UI interactions or API calls.
- `_tryExtractWorkoutPlan()`: Executes frontend UI interactions or API calls.
- `appendBubble()`: Executes frontend UI interactions or API calls.
- `sendMessage()`: Executes frontend UI interactions or API calls.
- `setLoading()`: Executes frontend UI interactions or API calls.
- `handleKey()`: Executes frontend UI interactions or API calls.
- `autoResize()`: Executes frontend UI interactions or API calls.
- `_showPlanSaveBanner()`: Executes frontend UI interactions or API calls.
- `sendPrompt()`: Executes frontend UI interactions or API calls.
- `loadHistory()`: Executes frontend UI interactions or API calls.
  **Interaction narrative:** Manipulates DOM state and communicates with FastAPI backend.

#### FILE: `frontend/js/constants.js`

**Role:** Frontend logic
**Line count:** 71
**Exports / Functions:**
**Interaction narrative:** Manipulates DOM state and communicates with FastAPI backend.

#### FILE: `frontend/js/dashboard.js`

**Role:** Frontend logic
**Line count:** 752
**Exports / Functions:**

- `checkRestDayWarning()`: Executes frontend UI interactions or API calls.
- `changeMonth()`: Executes frontend UI interactions or API calls.
- `renderBadges()`: Executes frontend UI interactions or API calls.
- `tick()`: Executes frontend UI interactions or API calls.
- `renderSummaryCards()`: Executes frontend UI interactions or API calls.
- `renderRadar()`: Executes frontend UI interactions or API calls.
- `closeModal()`: Executes frontend UI interactions or API calls.
- `fmtDisplayDate()`: Executes frontend UI interactions or API calls.
- `renderCalendar()`: Executes frontend UI interactions or API calls.
- `renderStreakBanner()`: Executes frontend UI interactions or API calls.
- `fmtYearMonth()`: Executes frontend UI interactions or API calls.
- `computeStreakDates()`: Executes frontend UI interactions or API calls.
- `renderVolumeChart()`: Executes frontend UI interactions or API calls.
- `fmtDate()`: Executes frontend UI interactions or API calls.
- `loadAll()`: Executes frontend UI interactions or API calls.
- `renderMuscleStats()`: Executes frontend UI interactions or API calls.
- `renderHeatmap()`: Executes frontend UI interactions or API calls.
- `makeCalDay()`: Executes frontend UI interactions or API calls.
- `launchConfetti()`: Executes frontend UI interactions or API calls.
- `openModal()`: Executes frontend UI interactions or API calls.
  **Interaction narrative:** Manipulates DOM state and communicates with FastAPI backend.

#### FILE: `frontend/js/friday_client.js`

**Role:** Frontend logic
**Line count:** 69
**Exports / Functions:**

- `_openWS()`: Executes frontend UI interactions or API calls.
  **Interaction narrative:** Manipulates DOM state and communicates with FastAPI backend.

#### FILE: `frontend/js/hud.js`

**Role:** Frontend logic
**Line count:** 163
**Exports / Functions:**

- `safeMaterial()`: Executes frontend UI interactions or API calls.
- `resize()`: Executes frontend UI interactions or API calls.
- `animate()`: Executes frontend UI interactions or API calls.
  **Interaction narrative:** Manipulates DOM state and communicates with FastAPI backend.

#### FILE: `frontend/js/live.js`

**Role:** Frontend logic
**Line count:** 191
**Exports / Functions:**

- `_cleanup()`: Executes frontend UI interactions or API calls.
- `_syncCanvasSize()`: Executes frontend UI interactions or API calls.
- `LiveModule()`: Executes frontend UI interactions or API calls.
- `start()`: Executes frontend UI interactions or API calls.
- `stop()`: Executes frontend UI interactions or API calls.
- `_sendLoop()`: Executes frontend UI interactions or API calls.
  **Interaction narrative:** Manipulates DOM state and communicates with FastAPI backend.

#### FILE: `frontend/js/metrics.js`

**Role:** Frontend logic
**Line count:** 197
**Exports / Functions:**

- `pushSegment()`: Executes frontend UI interactions or API calls.
- `saveMetrics()`: Executes frontend UI interactions or API calls.
- `renderWeightChart()`: Executes frontend UI interactions or API calls.
- `makeChartConfig()`: Executes frontend UI interactions or API calls.
- `renderHeightChart()`: Executes frontend UI interactions or API calls.
- `buildSegmentedDatasets()`: Executes frontend UI interactions or API calls.
- `initDateInput()`: Executes frontend UI interactions or API calls.
- `loadAndRender()`: Executes frontend UI interactions or API calls.
- `showToast()`: Executes frontend UI interactions or API calls.
- `renderHistory()`: Executes frontend UI interactions or API calls.
  **Interaction narrative:** Manipulates DOM state and communicates with FastAPI backend.

#### FILE: `frontend/js/overlay.js`

**Role:** Frontend logic
**Line count:** 279
**Exports / Functions:**

- `tickClock()`: Executes frontend UI interactions or API calls.
- `makeStatRow()`: Executes frontend UI interactions or API calls.
- `getWeightKg()`: Executes frontend UI interactions or API calls.
- `updateVolumeDisplay()`: Executes frontend UI interactions or API calls.
- `_applyWeather()`: Executes frontend UI interactions or API calls.
  **Interaction narrative:** Manipulates DOM state and communicates with FastAPI backend.

#### FILE: `frontend/js/page_transitions.js`

**Role:** Frontend logic
**Line count:** 48
**Exports / Functions:**
**Interaction narrative:** Manipulates DOM state and communicates with FastAPI backend.

#### FILE: `frontend/js/plan_loader.js`

**Role:** Frontend logic
**Line count:** 648
**Exports / Functions:**

- `_renderBanner()`: Executes frontend UI interactions or API calls.
- `_buildQueue()`: Executes frontend UI interactions or API calls.
- `_renderDropdown()`: Executes frontend UI interactions or API calls.
- `_getLiveReps()`: Executes frontend UI interactions or API calls.
- `onSetSaved()`: Executes frontend UI interactions or API calls.
- `_watchWeightInput()`: Executes frontend UI interactions or API calls.
- `_resetSetState()`: Executes frontend UI interactions or API calls.
- `markSaved()`: Executes frontend UI interactions or API calls.
- `_nextLabel()`: Executes frontend UI interactions or API calls.
- `_autoStart()`: Executes frontend UI interactions or API calls.
- `getCurrentItem()`: Executes frontend UI interactions or API calls.
- `_monitorCameraStop()`: Executes frontend UI interactions or API calls.
- `_onTimerComplete()`: Executes frontend UI interactions or API calls.
- `_applyCurrentItem()`: Executes frontend UI interactions or API calls.
- `_advance()`: Executes frontend UI interactions or API calls.
- `isActive()`: Executes frontend UI interactions or API calls.
- `_startRestTimer()`: Executes frontend UI interactions or API calls.
- `PlanLoader()`: Executes frontend UI interactions or API calls.
- `isSaved()`: Executes frontend UI interactions or API calls.
- `_buildBanner()`: Executes frontend UI interactions or API calls.
- `init()`: Executes frontend UI interactions or API calls.
  **Interaction narrative:** Manipulates DOM state and communicates with FastAPI backend.

#### FILE: `frontend/js/rest_timer.js`

**Role:** Frontend logic
**Line count:** 292
**Exports / Functions:**

- `adjust()`: Executes frontend UI interactions or API calls.
- `_updateRing()`: Executes frontend UI interactions or API calls.
- `_fmt()`: Executes frontend UI interactions or API calls.
- `_build()`: Executes frontend UI interactions or API calls.
- `start()`: Executes frontend UI interactions or API calls.
- `skip()`: Executes frontend UI interactions or API calls.
- `RestTimer()`: Executes frontend UI interactions or API calls.
- `_finish()`: Executes frontend UI interactions or API calls.
  **Interaction narrative:** Manipulates DOM state and communicates with FastAPI backend.

#### FILE: `frontend/js/session.js`

**Role:** Frontend logic
**Line count:** 290
**Exports / Functions:**

- `_getPostureEl()`: Executes frontend UI interactions or API calls.
- `SessionModule()`: Executes frontend UI interactions or API calls.
- `reset()`: Executes frontend UI interactions or API calls.
- `_lerpLoop()`: Executes frontend UI interactions or API calls.
- `_startLerp()`: Executes frontend UI interactions or API calls.
- `_lerp()`: Executes frontend UI interactions or API calls.
- `setStatus()`: Executes frontend UI interactions or API calls.
- `_commitFeedback()`: Executes frontend UI interactions or API calls.
- `start()`: Executes frontend UI interactions or API calls.
- `SkeletonDrawer()`: Executes frontend UI interactions or API calls.
- `_commitPosture()`: Executes frontend UI interactions or API calls.
- `draw()`: Executes frontend UI interactions or API calls.
- `clearSession()`: Executes frontend UI interactions or API calls.
- `updateHUD()`: Executes frontend UI interactions or API calls.
  **Interaction narrative:** Manipulates DOM state and communicates with FastAPI backend.

#### FILE: `frontend/js/standby.js`

**Role:** Frontend logic
**Line count:** 253
**Exports / Functions:**

- `_buildStandbyUI()`: Executes frontend UI interactions or API calls.
- `_checkTime()`: Executes frontend UI interactions or API calls.
- `_startWorkout()`: Executes frontend UI interactions or API calls.
  **Interaction narrative:** Manipulates DOM state and communicates with FastAPI backend.

#### FILE: `frontend/js/tracker.js`

**Role:** Frontend logic
**Line count:** 293
**Exports / Functions:**

- `stopSet()`: Executes frontend UI interactions or API calls.
- `getWeight()`: Executes frontend UI interactions or API calls.
- `getBodyWeight()`: Executes frontend UI interactions or API calls.
- `updateSaveBtn()`: Executes frontend UI interactions or API calls.
- `saveSet()`: Executes frontend UI interactions or API calls.
- `saveAutoFill()`: Executes frontend UI interactions or API calls.
- `showToast()`: Executes frontend UI interactions or API calls.
- `loadAutoFill()`: Executes frontend UI interactions or API calls.
- `calcCalories()`: Executes frontend UI interactions or API calls.
  **Interaction narrative:** Manipulates DOM state and communicates with FastAPI backend.

#### FILE: `frontend/js/upload.js`

**Role:** Frontend logic
**Line count:** 244
**Exports / Functions:**

- `UploadModule()`: Executes frontend UI interactions or API calls.
- `_exitUploadMode()`: Executes frontend UI interactions or API calls.
- `bytesIndexOf()`: Executes frontend UI interactions or API calls.
- `_stopHudPolling()`: Executes frontend UI interactions or API calls.
- `_streamMjpeg()`: Executes frontend UI interactions or API calls.
- `processFile()`: Executes frontend UI interactions or API calls.
- `_startHudPolling()`: Executes frontend UI interactions or API calls.
- `concat()`: Executes frontend UI interactions or API calls.
  **Interaction narrative:** Manipulates DOM state and communicates with FastAPI backend.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
SECTION 5 — ALL DATA FLOWS (STEP-BY-STEP, FUNCTION-LEVEL)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

**FLOW 1: User Registration**

1. User clicks "Sign Up" in `auth.js` -> `handleSignup()`.
2. Frontend calls `POST /api/auth/register` via `api.js`.
3. FastAPI `endpoint.py` -> `register()` receives payload.
4. `db.py` -> `get_user()` checks for duplicates.
5. `passlib` hashes password (Argon2).
6. `db.py` -> `create_user()` inserts MongoDB document.
7. `endpoint.py` calls `create_access_token()` returning JWT.
8. `auth.js` stores JWT in localStorage and redirects.

**FLOW 2: Live Exercise Session — Single Frame**

1. `live.js` -> `_sendLoop()` captures video frame to offscreen canvas, extracts JPEG blob.
2. Binary ArrayBuffer sent over `/ws/stream/{sid}`.
3. `endpoint.py` -> `websocket_stream()` receives bytes, decodes via `cv2.imdecode`.
4. `endpoint.py` writes frame to `SessionManager.get().atomic_frame`.
5. Background `InferenceWorker.run()` reads `atomic_frame`, calls `BaseCounter.process_frame()`.
6. `PoseDetector.findPose()` generates keypoints.
7. `BaseCounter` calculates angles, ticks state machine, updates rep count.
8. Worker writes dict to `atomic_result`.
9. `endpoint.py` async loop reads `atomic_result`, sends JSON back over WebSocket.
10. `session.js` -> `ws.onmessage` receives JSON, updates target lerp values.
11. `session.js` -> `_lerpLoop()` animates DOM elements (progress bar, rep text).

**FLOW 3: Video File Upload Processing**

1. `upload.js` -> `processFile()` sends FormData to `POST /api/upload/process`.
2. `endpoint.py` -> `process_video()` saves temp file, spawns background generator.
3. Generator reads frames, runs `counter.process_frame()`, yields multipart JPEG stream.
4. `upload.js` -> `_streamMjpeg()` reads boundary bytes, updates `<img>` src natively.
5. `upload.js` -> `_startHudPolling()` polls `/api/session/{sid}/state` to sync UI.

**FLOW 4: Voice Query to Friday Agent**

1. User speaks into microphone (`app.js` / global mic handler).
2. `friday_client.js` captures base64 audio, sends to `/ws/friday`.
3. `endpoint.py` -> `friday_websocket()` receives audio.
4. STT engine (`stt.py`) processes chunk, triggers barge-in if needed.
5. CrispASR returns transcribed text.
6. `endpoint.py` routes text to `graph.py` -> `invoke_friday()`.
7. LangGraph evaluates intent, generates response text.
8. Result sent back as `{"type": "chat_response", "data": "text"}`.
9. `friday_client.js` renders text in UI overlay.

**FLOW 5: Text Query to Friday Agent**

1. User types in `chatbot.html` input box.
2. `chat.js` -> `sendMessage()` POSTs to `/api/agent/chat`.
3. `endpoint.py` -> `chat_handler()` calls `chatbot.py` -> `route_query()`.
4. `graph.py` -> `invoke_friday()` updates state, writes to Mongo (`db.append_conversation_turn()`).
5. LangGraph `response_node` returns string.
6. HTTP response returned to frontend, `chat.js` updates DOM.

**FLOW 6: Calorie Scan**

1. User snaps photo in `calorie.html` via `calorie.js`.
2. Image sent to `POST /api/agent/scan_food`.
3. `endpoint.py` calls `calorie_tracker.py` -> `scan_food_from_frame()`.
4. Base64 frame sent to Gemini 1.5 API with JSON schema prompt.
5. `_repair_json()` ensures formatting, `db.log_calorie_entry()` saves to DB.
6. Parsed JSON returned to frontend, `calorie.js` updates macro DOM.

**FLOW 7: Diet Plan Generation**

1. User asks "make me a diet plan" via text/voice.
2. LangGraph `intent_node` categorizes as `diet_plan` tool.
3. `tool_node` executes `generate_diet_plan()`.
4. LLM builds Markdown plan.
5. `db.save_diet_plan()` stores in MongoDB.
6. `response_node` returns summary: "I've saved your new plan."

**FLOW 8: Workout History Retrieval**

1. User asks "what are my stats?"
2. LangGraph `intent_node` -> `who_am_i` tool.
3. `db.py` -> `get_monthly_stats()` aggregates Mongo documents.
4. Tool returns JSON to `AgentState`.
5. `response_node` reads JSON, LLM formats human-readable text.

**FLOW 9: Memory Summarisation**

1. After every turn, `memory.py` -> `should_regenerate_summary()` checks if turn count > 50.
2. If true, a background LLM call reads all 50 turns.
3. LLM outputs a concise summary.
4. Old 50 turns are deleted from Mongo, replaced with 1 summary document.
5. `build_system_prompt()` injects this summary into future prompts.

**FLOW 10: Auto-Start Workout Plan Banner**

1. Page loads `dashboard.html` -> `app.js` -> `checkTodayPlan()`.
2. Frontend calls `GET /api/user/plans/today`.
3. `endpoint.py` fetches active plan from DB based on current weekday.
4. If exists, `app.js` displays sticky banner.
5. User clicks banner -> routes to `tracker.html` -> `plan_loader.js` -> `startSequence()`.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
SECTION 6 — LANGGRAPH AGENT — DEEP DIVE
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

**AgentState TypedDict**

```python
class AgentState(TypedDict):
    messages: Annotated[list, add_messages] # Standard langchain message array
    channel: str                            # "text" or "voice" (changes verbosity)
    username: str                           # Current user ID for DB lookups
    intent: Optional[str]                   # e.g., "save_set", "calorie_scan"
    intent_params: Optional[dict]           # Extracted entities (e.g., {"reps": 10})
    intent_confidence: float                # 0.0 to 1.0
    tool_result: Optional[dict]             # Output of executed tools
    response: Optional[str]                 # Final generated string
    latest_frame: Optional[bytes]           # Live webcam frame for vision tasks
```

**Nodes:**

1. **`intent_node`**: Calls `_get_intent_llm()` (Gemini Flash). Reads `messages[-1]`. Output: Writes `intent`, `intent_params`, `intent_confidence` to state. No direct DB calls.
2. **`clarify_node`**: Reads `intent`. Output: Writes clarification string to `response`.
3. **`tool_node`**: Uses `COMMAND_REGISTRY` to map `intent` to Python functions. Reads `username`, `intent_params`, `latest_frame`. Output: Writes JSON to `tool_result`. Calls `db.py` extensively.
4. **`memory_write_node`**: Reads `messages`, `response`. Output: Writes to MongoDB via `db.append_conversation_turn()`.
5. **`response_node`**: Calls `_get_llm()` (Anthropic Opus/Sonnet). Reads `tool_result`, `channel`. Output: Writes formatted conversational text to `response`.

**Edges:**

- `intent_node -> _route_after_intent`
  - Condition: `if state["intent_confidence"] < 0.6: return "clarify_node"`
  - Condition: `else: return "tool_node"`

**Registered Tools (COMMAND_REGISTRY):**

- `calorie_scan(frame)`: Calls Gemini Vision, saves to DB.
- `save_set(username, exercise, reps)`: Calls `db.save_workout()`. Returns `{"status": "success", "calories": X}`.
- `generate_workout_plan(username, days)`: Calls LLM to generate JSON schedule.

**System Prompt Template Injection:**

```python
prompt = f"""You are Friday, an AI fitness assistant.
User Profile: {db.get_user(username)}
Active Session: {current_exercise} - {current_reps} reps
Past Summary: {db.get_summary(username)}
Current Time: {datetime.now()}
Rule: Keep responses under 2 sentences if channel is 'voice'."""
```

Variables come from `memory.py` reading live state singletons and DB.

**Checkpoint Saving / Error Handling:**
Uses LangGraph's `MongoDBSaver` attached to the thread configuration (`config={"configurable": {"thread_id": session_id}}`). Tool failures catch generic `Exceptions`, write `{"error": str(e)}` to `tool_result`, and the `response_node` LLM apologizes to the user automatically. Temperature is set to `0.2` for intent routing and `0.7` for the response node.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
SECTION 7 — REP-COUNTING ENGINE — DEEP DIVE
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

**BaseCounter.process_frame() Algorithm:**

1. `PoseDetector.findPosition(frame)` is called. Returns `landmarks_list`.
2. Compute required 2D angles using `findAngle(p1, p2, p3)`.
3. Apply `_smooth_angle()`: push to sliding `deque(maxlen=5)`, return median.
4. Check form via `_check_posture()`. If fail, set `correct_form = False`, append message to TTS cooldown queue.
5. Calculate velocity `calc_velocity()` of key joints. If drop > 20%, flag fatigue.
6. Tick state machine `_tick_bilateral(angle)`:
   a. If `angle > UP_ANGLE` and state is 'down', state -> 'up'.
   b. If `angle < DOWN_ANGLE` and state is 'up', state -> 'down', `reps += 1`.
7. Return dict: `{counter, feedback, posture_error, progress, keypoints}`.

**Angle Computation (PoseDetector.findAngle):**

```python
v1 = [x1 - x2, y1 - y2]
v2 = [x3 - x2, y3 - y2]
dot = (v1[0]*v2[0] + v1[1]*v2[1])
mag1 = math.sqrt(v1[0]**2 + v1[1]**2)
mag2 = math.sqrt(v2[0]**2 + v2[1]**2)
angle = math.degrees(math.acos(dot / (mag1 * mag2)))
if angle > 180: angle = 360 - angle
```

**Counter Subclasses Detail:**

- **SquatCounter**:
  - Keypoints: Hip (11,12), Knee (13,14), Ankle (15,16).
  - Triplet: Hip-Knee-Ankle.
  - UP_ANGLE: `160`, DOWN_ANGLE: `110`.
  - Debounce: Standard.
  - Posture Check: Knee Valgus. Distance between knees < 0.8 \* distance between ankles -> Error: "Knees buckling inwards, push them out".
- **CrunchCounter**:
  - Keypoints: Shoulder (5,6), Hip (11,12), Knee (13,14).
  - Triplet: Shoulder-Hip-Knee.
  - UP_ANGLE: `130`, DOWN_ANGLE: `80`.
  - Debounce: Inverted (angle decreases on exertion, increases on rest).
  - Posture Check: Neck pulling. Head-Shoulder distance anomaly.
- **PullupCounter**:
  - Keypoints: Nose (0), Wrist (9,10), Hip (11,12).
  - Triplet: None (uses Y-axis spatial delta).
  - UP_ANGLE: N/A, DOWN_ANGLE: N/A.
  - Debounce: Nose_Y < Wrist_Y (Up), Nose_Y > Wrist_Y (Down).
  - Posture Check: Kipping. If Hip_X delta > 50px between frames -> Error: "Stop swinging, control your core".

**Velocity & Smoothing:**
Velocity = Euclidean distance of wrist/ankle between frames divided by delta-time, stored in deque. A "momentum" flag triggers if velocity on the concentric phase exceeds 800px/s. Smoothing uses a Median filter of length 5 to ignore single-frame occlusion jitters (mean would skew too heavily on a completely mis-inferred frame). Hardcoded motivational strings ("Push through!", "You got this!") are popped randomly if fatigue drops concentric velocity below 40% of baseline.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
SECTION 8 — CONCURRENCY & THREADING MODEL — DEEP DIVE
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

**Thread Diagram:**

- `MainThread`: Runs Uvicorn asyncio event loop. Lifetime: Server uptime.
- `AnyIO Worker Threads`: Used by FastAPI for synchronous dependencies (e.g., DB reads). Lifetime: Ephemeral per request.
- `InferenceWorker-{sid}`: Pure Python `threading.Thread`. Lifetime: Duration of active webcam session.
- `CrispASR Subprocess`: Runs local STT. Lifetime: Server uptime.

**AtomicFrame & AtomicResult:**

```python
class AtomicFrame:
    def __init__(self):
        self.lock = threading.Lock()
        self.frame = None
    def write(self, frame):
        with self.lock:
            self.frame = frame # Overwrites old frame!
```

_Why not a Queue?_ If the camera sends frames at 30 FPS, but inference runs at 15 FPS, a Queue would infinitely buffer, causing the HUD to lag seconds behind reality. Overwriting a single slot guarantees the ML model always processes the freshest physical moment in time. The dropped frames are irrelevant for tracking.

**FPS-Cap Formula in InferenceWorker:**

```python
process_time = time.time() - start_time
sleep_time = max(0, (1.0 / 15.0) - process_time)
time.sleep(sleep_time)
```

If inference takes 40ms, it sleeps for ~26ms to maintain 15 FPS.

**FastAPI Asyncio vs Sync Threads:**
FastAPI routes (`async def websocket_stream`) run on the main event loop. If we ran ONNX `process_frame()` inside this route without `run_in_threadpool`, it would block the event loop, freezing ALL other users and WebSocket heartbeats. The `InferenceWorker` thread isolates this blocking math. Streamlit, by contrast, blocks entirely on every widget interaction, which is why WebRTC in Streamlit required messy thread-safe Queues and why the project migrated to Vanilla JS.

**Disconnect Handling:**
If a WebSocket drops (e.g., network failure, user closes tab), FastAPI throws `WebSocketDisconnect`. The `except` block explicitly calls `SessionManager.destroy(sid)`, which sets `worker.stop_event.set()`, gracefully terminating the background thread and releasing ONNX memory. High concurrency (e.g., 10 users) will spawn 10 threads, linearly scaling VRAM usage until OOM occurs (a known scalability ceiling).

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
SECTION 9 — AUDIO PIPELINE — DEEP DIVE
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

**STT (stt.py):**

- **PyAudio/Sounddevice Config:** Sample rate `16000`, chunk size `512`, channels `1`, format `int16`.
- **Silero VAD:** Uses `silero_vad.jit`. Expected chunk size is `512` samples (32ms).
  - `VAD_START_THRESH = 0.5`
  - `VAD_STOP_THRESH = 0.3`
  - Requires 15 consecutive silence frames (~500ms) to trigger end-of-speech, allowing natural pauses between words.
- **CrispASR/Whisper:** Runs via external `crispasr.exe`. Expects raw 16k PCM. Output is a clean JSON string containing transcribed text.
- **Barge-in Mechanism:** When `friday_websocket` receives audio from the user, it sets `barge_in_event.set()`. The TTS loop checks this event before sending every chunk; if set, it immediately aborts playback and sends a `stop` command to the TTS engine.
- **Buffer Accumulation:** While VAD > `START_THRESH`, audio chunks append to a `bytearray()`. On VAD < `STOP_THRESH`, the complete bytearray is flushed via STDIN to CrispASR.

**TTS (Deprecated / Voxtral Removal Context):**

- _Note: Voxtral TTS was completely removed in recent commits to resolve GPU VRAM OOM errors (Conversation 22f0a181)._
- The system is now strictly text-only for output. The `barge-in` logic remains in `stt.py` to interrupt LangGraph LLM generation if the user speaks again, but audio playback routing has been excised.
- Technical reference for future restoration is preserved in `docs/tts_integration_reference.md`.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
SECTION 10 — DATABASE LAYER — DEEP DIVE
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

**db.py Functions:**

- `create_user(username: str, hashed_password: str) -> dict`
  - **Query:** `db.users.insert_one({"username": username, "password": hashed_password, "created_at": datetime.utcnow()})`
  - **Return:** `{"status": "success", "user_id": str}`

- `save_workout(username: str, exercise: str, reps: int, sets: int, weight_kg: float) -> dict`
  - **Query:** `db.workouts.insert_one({"username": username, "exercise": exercise, "reps": reps, "sets": sets, "weight": weight_kg, "date": datetime.utcnow()})`
  - **Return:** `{"inserted_id": str}`
  - **Index Needed:** `{ "username": 1, "date": -1 }` for dashboard aggregation.

- `get_monthly_stats(username: str, year_month: str) -> dict`
  - **Query:** `db.workouts.aggregate([{"$match": {"username": username, "date": {"$gte": start, "$lt": end}}}, {"$group": {"_id": "$exercise", "total": {"$sum": "$sets"}}}])`
  - **Return:** `{"Squat": 15, "Pushup": 30}`

- `append_conversation_turn(username: str, role: str, content: str) -> dict`
  - **Query:** `db.chat_history.update_one({"username": username}, {"$push": {"messages": {"role": role, "content": content, "timestamp": now()}}}, upsert=True)`
  - **Return:** `{"status": "success"}`

**Collections Schema:**

1. **`users`**: `{ _id: ObjectId, username: str (unique), password: str, profile: dict }`
   - Readers: Auth endpoints, Memory profile generator.
2. **`workouts`**: `{ _id: ObjectId, username: str, exercise: str, reps: int, weight: float, date: ISODate }`
   - Readers: Dashboard analytics, LangGraph tools.
3. **`chat_history`**: `{ _id: ObjectId, username: str, messages: list[dict], summary: str }`
   - Readers: `memory.py` context injector.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
SECTION 11 — FRONTEND — DEEP DIVE
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

**State Machine in app.js:**

- **States:** `STANDBY`, `WORKOUT`, `CALORIE`, `DASHBOARD`.
- **Transitions:**
  - `STANDBY -> WORKOUT` (Trigger: Click "Start Workout" or Friday voice command. Side Effect: Hide To-Do list, show Camera HUD, init WebRTC).
  - `WORKOUT -> STANDBY` (Trigger: Click "Stop" or Friday command. Side Effect: Destroy WS, show To-Do UI, log workout to DB).

**Canvas Rendering Pipeline (session.js SkeletonDrawer):**

1. Backend sends normalized keypoints `[[100, 200], [150, 250], ...]`.
2. `SkeletonDrawer.draw(ctx, keypoints)` scales points: `x = k[0] * (canvas.width / 640)`.
3. Clears canvas `ctx.clearRect()`.
4. Iterates `SKELETON_PAIRS` (e.g., `[ [5,7], [7,9] ]` for arm).
5. Draws `ctx.beginPath()`, `ctx.moveTo()`, `ctx.lineTo()`, `ctx.stroke()`.
6. `SKELETON_PAIRS` defined in `constants.js` encompasses the standard COCO-17 connections.

**Animation/Lerp System (session.js \_lerpLoop):**

- Values jump aggressively from the backend (e.g., progress goes 0 -> 40 -> 90).
- `_lerpLoop` uses `requestAnimationFrame`: `current += (target - current) * 0.1`.
- This decouples the 60/120Hz monitor refresh rate from the 15 FPS backend inference rate, resulting in a buttery smooth HUD progress ring, making the app feel native.

**Standby / To-Do Engine (standby.js):**

- Introduced recently to replace empty tracker states.
- Fetches daily tasks via `api.js` `GET /api/todo`.
- Renders list items natively. Checkbox clicks `PATCH /api/todo/{id}`.
- When transition to `WORKOUT` occurs, the DOM container `.standby-wrapper` gets `.hidden` class.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
SECTION 12 — WEBSOCKET PROTOCOL — DEEP DIVE
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

**Endpoint 1: `/ws/stream/{session_id}`**

- **Lifecycle:** Connect -> Auth (Via JWT query param) -> Frame Loop -> Disconnect.
- **Inbound (Client to Server):** Raw Binary `ArrayBuffer` (JPEG). Dimensions: 640x360, Quality: 0.6 to minimize bandwidth.
- **Outbound (Server to Client):**
  ```json
  {
    "counter": int, "feedback": str, "posture_error": str,
    "progress": float, "correct_form": bool, "keypoints": list[list[float]]
  }
  ```
- **Backpressure:** Handled on client. Client will not send frame N+1 until frame N response is received OR a 33ms timer expires.

**Endpoint 2: `/ws/friday`**

- **Lifecycle:** Connect -> Handshake -> Bidirectional Command Loop.
- **Inbound Schemas:**
  - Text query: `{"type": "chat", "text": "how many reps?"}`
  - Audio chunk: `{"type": "audio", "data": "base64..."}`
- **Outbound Schemas:**
  - System Command: `{"type": "frontend_command", "command": "navigate", "target": "dashboard"}`
  - Text Response: `{"type": "chat_response", "text": "You did 15 reps."}`
- **Fast-Track Routing:** Before hitting LangGraph, `endpoint.py` runs regex (e.g., `/go to (dashboard|metrics)/i`). If matched, returns `frontend_command` instantly, bypassing the 1000ms LLM latency for UI navigation.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
SECTION 13 — CALORIE SCANNER — DEEP DIVE
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

**Gemini Prompt (calorie_tracker.py):**

```text
Analyze this food image. Identify the items, estimate portions, and provide macronutrients.
You MUST return EXACTLY this JSON schema and nothing else, no markdown formatting:
{
  "foods": [ {"name": "Chicken Breast", "calories": 200, "protein_g": 40, "carbs_g": 0, "fat_g": 3} ],
  "total_calories": 200,
  "confidence": 0.85
}
```

**JSON Repair Logic:**
LLMs often append ` ```json ` blocks or truncate the final `}` if max_tokens is reached.
`_repair_json()`:

1. Strips markdown fences via regex: `re.sub(r'```json|```', '', raw)`.
2. Finds the first `{` and last `}` to extract the raw object.
3. If `foods` array is broken, wraps in try/except and uses a fallback `{"foods": [], "total_calories": 0}` to prevent the UI from crashing.

**API Parameters:**

- Model: `gemini-1.5-flash`
- Temperature: `0.1` (Minimize hallucination)
- Max Tokens: `500`

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
SECTION 14 — AUTH SYSTEM — DEEP DIVE
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

**Flows & JWT:**

- **Registration:** Validates email regex, enforces 8-char password. Checks DB for uniqueness. Hashes using Argon2.
- **Login:** Looks up username, verifies hash. Mints JWT with payload `{"sub": username, "exp": UNIX_TIMESTAMP}`. Algorithm: `HS256`. Secret: `JWT_SECRET` from `.env`.
- **Dependency Injection:** Protected REST routes use `Depends(get_current_user)`. This FastAPI dependency blocks execution, decodes the `Authorization: Bearer <token>` header, and throws 401 on failure/expiry.
- **WebSocket Auth:** Browsers cannot send Headers in `new WebSocket()`. So, JS appends `?token=...`. `endpoint.py` manually calls the JWT decode logic on connection.
- **Expiry/Refresh:** Tokens expire in 7 days. There is NO refresh token mechanism; the user is forcefully logged out, and `api.js` redirects to `login.html` upon catching a 401 response.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
SECTION 15 — METRICS & LOGGING — DEEP DIVE
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

**PipelineMetrics Class:**

- **Deques:** `self.infer_times`, `self.capture_times`, `self.e2e_times` (maxlen=60).
- **Rolling Average:** Computed as `sum(deque) / len(deque)` when `maybe_report()` is called.
- **Trigger:** Checked every frame. If `time.time() - self.last_report > 5.0`, it logs and resets `last_report`.

**Log Configuration:**

- Logs written to `logs/pipeline.log`.
- Format: `[timestamp] [session_id] E2E: 45ms | Infer: 38ms | Capture: 2ms`.
- Currently uses basic `logging.FileHandler` with no automatic rotation strategy, meaning the log file will grow indefinitely unless cleared manually (Technical Debt).

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
SECTION 16 — TECHNICAL DEBT, RISKS & IMPROVEMENT ROADMAP
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

**1. Inference Thread Scalability Ceiling**

- **Severity:** High
- **Location:** `utils/session_manager.py` -> `SessionManager.create()`
- **Problem:** Spawns a dedicated Python Thread and ONNX instance per user.
- **Failure Scenario:** If 20 users connect simultaneously, system VRAM will exhaust (OOM), crashing the entire FastAPI process.
- **Fix:** Implement a centralized ONNX batching queue where a single thread processes a batch of 8 frames matrix-multiplied together, returning results to appropriate sessions.

**2. Indefinite Log Growth**

- **Severity:** Low
- **Location:** `logger/metrics.py`
- **Problem:** Standard `FileHandler` used.
- **Failure Scenario:** Over months, `pipeline.log` consumes disk space.
- **Fix:** Replace with `logging.handlers.RotatingFileHandler` (maxBytes=5MB, backupCount=3).

**3. LangGraph Context Bloat**

- **Severity:** Medium
- **Location:** `agent/graph.py` -> `AgentState`
- **Problem:** Storing `latest_frame` as base64 in the state dictionary continuously can blow up LangGraph checkpointer memory.
- **Fix:** Clear the `latest_frame` key immediately after `calorie_scan` tool execution completes.

**Security Considerations:**

- JWT secret is loaded from `.env`. If leaked, full system compromise.
- No rate limiting on `/api/auth/login`, susceptible to brute-force attacks. Fix: Add `slowapi` rate limiter.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
SECTION 17 — CROSS-CUTTING CONCERNS
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

- **Error Propagation:** If `PoseDetector` throws an ONNX runtime exception, the `InferenceWorker` catches it, sets `atomic_result` to an error dict, which the WebSocket transmits to the client. The frontend `session.js` displays a red toast error and gracefully halts the camera.
- **Configuration Management:** Environment variables dictate model paths, DB URIs, and secrets. If `.env` is missing, FastAPI fails to boot via Pydantic `BaseSettings` validation.
- **Graceful Shutdown:** FastAPI lifecycle events (`@app.on_event("shutdown")`) iterate through `SessionManager.active_sessions`, setting `stop_event` on all threads to ensure ONNX releases GPU locks before the process dies.
- **Session Isolation:** `session_id` UUIDs securely sandbox active memory. `AtomicFrame` singletons are instantiated per UUID, physically preventing Frame A from User 1 being analyzed by Thread B for User 2.
- **Data Consistency:** MongoDB writes are currently isolated documents without multi-document transactions. Race conditions in logging workouts are negligible due to the natural rate limit of human motion.
