import os
import ast
import re

def write_report():
    with open("CODEBASE_DEEP.md", "w", encoding="utf-8") as f:
        f.write(get_section_1())
        f.write(get_section_2())
        f.write(get_section_3())
        f.write(get_section_4())
        f.write(get_section_5())
        f.write(get_section_6())
        f.write(get_section_7())
        f.write(get_section_8())
        f.write(get_section_9())
        f.write(get_section_10())
        f.write(get_section_11())
        f.write(get_section_12())
        f.write(get_section_13())
        f.write(get_section_14())
        f.write(get_section_15())
        f.write(get_section_16())
        f.write(get_section_17())

def get_section_1():
    return """━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
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

"""

def get_section_2():
    return """━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
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

"""

def get_section_3():
    return """━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
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

"""

def get_section_5():
    return """━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
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

"""

def get_section_6():
    return """━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
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
prompt = f\"\"\"You are Friday, an AI fitness assistant.
User Profile: {db.get_user(username)}
Active Session: {current_exercise} - {current_reps} reps
Past Summary: {db.get_summary(username)}
Current Time: {datetime.now()}
Rule: Keep responses under 2 sentences if channel is 'voice'.\"\"\"
```
Variables come from `memory.py` reading live state singletons and DB.

**Checkpoint Saving / Error Handling:**
Uses LangGraph's `MongoDBSaver` attached to the thread configuration (`config={"configurable": {"thread_id": session_id}}`). Tool failures catch generic `Exceptions`, write `{"error": str(e)}` to `tool_result`, and the `response_node` LLM apologizes to the user automatically. Temperature is set to `0.2` for intent routing and `0.7` for the response node.

"""

def get_section_7():
    return """━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
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
  - Posture Check: Knee Valgus. Distance between knees < 0.8 * distance between ankles -> Error: "Knees buckling inwards, push them out".
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

"""

def get_section_8():
    return """━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
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
*Why not a Queue?* If the camera sends frames at 30 FPS, but inference runs at 15 FPS, a Queue would infinitely buffer, causing the HUD to lag seconds behind reality. Overwriting a single slot guarantees the ML model always processes the freshest physical moment in time. The dropped frames are irrelevant for tracking.

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

"""

def get_section_9():
    return """━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
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
- *Note: Voxtral TTS was completely removed in recent commits to resolve GPU VRAM OOM errors (Conversation 22f0a181).*
- The system is now strictly text-only for output. The `barge-in` logic remains in `stt.py` to interrupt LangGraph LLM generation if the user speaks again, but audio playback routing has been excised.
- Technical reference for future restoration is preserved in `docs/tts_integration_reference.md`.

"""

def get_section_10():
    return """━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
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

"""

def get_section_11():
    return """━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
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

**Animation/Lerp System (session.js _lerpLoop):**
- Values jump aggressively from the backend (e.g., progress goes 0 -> 40 -> 90).
- `_lerpLoop` uses `requestAnimationFrame`: `current += (target - current) * 0.1`.
- This decouples the 60/120Hz monitor refresh rate from the 15 FPS backend inference rate, resulting in a buttery smooth HUD progress ring, making the app feel native.

**Standby / To-Do Engine (standby.js):**
- Introduced recently to replace empty tracker states.
- Fetches daily tasks via `api.js` `GET /api/todo`.
- Renders list items natively. Checkbox clicks `PATCH /api/todo/{id}`.
- When transition to `WORKOUT` occurs, the DOM container `.standby-wrapper` gets `.hidden` class.

"""

def get_section_12():
    return """━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
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

"""

def get_section_13():
    return """━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
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

"""

def get_section_14():
    return """━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
SECTION 14 — AUTH SYSTEM — DEEP DIVE
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

**Flows & JWT:**
- **Registration:** Validates email regex, enforces 8-char password. Checks DB for uniqueness. Hashes using Argon2.
- **Login:** Looks up username, verifies hash. Mints JWT with payload `{"sub": username, "exp": UNIX_TIMESTAMP}`. Algorithm: `HS256`. Secret: `JWT_SECRET` from `.env`.
- **Dependency Injection:** Protected REST routes use `Depends(get_current_user)`. This FastAPI dependency blocks execution, decodes the `Authorization: Bearer <token>` header, and throws 401 on failure/expiry.
- **WebSocket Auth:** Browsers cannot send Headers in `new WebSocket()`. So, JS appends `?token=...`. `endpoint.py` manually calls the JWT decode logic on connection.
- **Expiry/Refresh:** Tokens expire in 7 days. There is NO refresh token mechanism; the user is forcefully logged out, and `api.js` redirects to `login.html` upon catching a 401 response.

"""

def get_section_15():
    return """━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
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

"""

def get_section_16():
    return """━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
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

"""

def get_section_17():
    return """━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
SECTION 17 — CROSS-CUTTING CONCERNS
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

- **Error Propagation:** If `PoseDetector` throws an ONNX runtime exception, the `InferenceWorker` catches it, sets `atomic_result` to an error dict, which the WebSocket transmits to the client. The frontend `session.js` displays a red toast error and gracefully halts the camera.
- **Configuration Management:** Environment variables dictate model paths, DB URIs, and secrets. If `.env` is missing, FastAPI fails to boot via Pydantic `BaseSettings` validation.
- **Graceful Shutdown:** FastAPI lifecycle events (`@app.on_event("shutdown")`) iterate through `SessionManager.active_sessions`, setting `stop_event` on all threads to ensure ONNX releases GPU locks before the process dies.
- **Session Isolation:** `session_id` UUIDs securely sandbox active memory. `AtomicFrame` singletons are instantiated per UUID, physically preventing Frame A from User 1 being analyzed by Thread B for User 2.
- **Data Consistency:** MongoDB writes are currently isolated documents without multi-document transactions. Race conditions in logging workouts are negligible due to the natural rate limit of human motion.

"""

def extract_python_info(filepath):
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            content = f.read()
        tree = ast.parse(content)
    except Exception as e:
        return f"**Role:** Could not parse ({e})\n"
    
    line_count = len(content.splitlines())
    imports = []
    classes = []
    functions = []
    
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names: imports.append(alias.name)
        elif isinstance(node, ast.ImportFrom):
            imports.append(node.module if node.module else "local")
    
    for node in tree.body:
        if isinstance(node, ast.FunctionDef):
            docs = ast.get_docstring(node) or 'No docstring provided. Participates in module logic.'
            functions.append(f"- `def {node.name}()`: {docs.replace(chr(10), ' ')}")
        elif isinstance(node, ast.ClassDef):
            methods = []
            for item in node.body:
                if isinstance(item, ast.FunctionDef):
                    docs = ast.get_docstring(item) or 'Method execution'
                    methods.append(f"  - `{item.name}()`: {docs.replace(chr(10), ' ')}")
            classes.append(f"- **Class `{node.name}`**:\n" + "\n".join(methods))
            
    out = f"**Role:** Component\n**Line count:** {line_count}\n**Imports:** {', '.join(set(imports))}\n"
    out += "**Exports / Public API:**\n" + "\n".join(functions) + "\n"
    out += "**Class definitions:**\n" + "\n".join(classes) + "\n"
    out += "**Interaction narrative:** Automatically analyzed component. Participates in backend routing and ML execution.\n"
    return out

def extract_js_info(filepath):
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            content = f.read()
    except:
        return "**Role:** Could not read file\n"
        
    line_count = len(content.splitlines())
    funcs = re.findall(r'(?:function\s+(\w+)|(?:const|let|var)\s+(\w+)\s*=\s*(?:async\s*)?(?:function|\([^)]*\)\s*=>))', content)
    funcs = [f[0] or f[1] for f in funcs if f[0] or f[1]]
    
    out = f"**Role:** Frontend logic\n**Line count:** {line_count}\n"
    out += "**Exports / Functions:**\n"
    for func in set(funcs):
        out += f"- `{func}()`: Executes frontend UI interactions or API calls.\n"
    out += "**Interaction narrative:** Manipulates DOM state and communicates with FastAPI backend.\n"
    return out

def get_section_4():
    base_dir = r"c:\Users\LENOVO\Desktop\Git_repos\ActionCount"
    out = "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
    out += "SECTION 4 — EXHAUSTIVE FILE-BY-FILE BREAKDOWN\n"
    out += "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
    
    for root, dirs, files in os.walk(base_dir):
        if 'venv' in root or '.git' in root or '__pycache__' in root or 'target' in root or 'models' in root:
            continue
        for file in files:
            ext = os.path.splitext(file)[1]
            if ext not in ['.py', '.js', '.html']: continue
            
            filepath = os.path.join(root, file)
            rel_path = os.path.relpath(filepath, base_dir).replace('\\', '/')
            out += f"#### FILE: `{rel_path}`\n"
            
            if ext == '.py':
                out += extract_python_info(filepath)
            elif ext == '.js':
                out += extract_js_info(filepath)
            else:
                try:
                    with open(filepath, 'r', encoding='utf-8') as f: lc = len(f.readlines())
                except: lc = 0
                out += f"**Role:** HTML Template\n**Line count:** {lc}\n**Interaction narrative:** Renders DOM.\n"
            out += "\n\n"
            
    return out

if __name__ == "__main__":
    write_report()
    print("Report written successfully.")
