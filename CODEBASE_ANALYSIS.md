### META
- **Project Name:** ActionCount
- **Version:** 1.0.0 (Assumed)
- **License:** Proprietary/Internal (Assumed)
- **One-line Description:** A local-first, AI-powered fitness tracker featuring real-time rep counting via computer vision, a dynamic interactive HUD, and a multi-modal LangGraph-driven voice assistant (Friday).
- **Primary Language(s) & Frameworks:** Python (FastAPI, Streamlit, LangGraph, RTMPose), JavaScript (Vanilla JS), HTML5/CSS3.
- **Entry Points:** `backend/app.py` (Streamlit UI), `backend/endpoint.py` (FastAPI backend), `frontend/index.html` (Vanilla JS Dashboard Entry).

---

### TECH STACK

| Name | Version | Role/Why it's used |
|---|---|---|
| **FastAPI** | Latest | Core asynchronous API server for the backend, serving REST endpoints and WebSockets for the Friday AI. |
| **Uvicorn** | [standard] | High-performance ASGI server for running the FastAPI application. |
| **Streamlit** | Latest | Alternative/Legacy Python-based frontend interface for the fitness platform. |
| **PyMongo** | [srv] | MongoDB driver for persisting user accounts, workout logs, chat history, and metrics. |
| **Passlib / Argon2** | Latest | Secure password hashing and verification. |
| **Jose** | Latest | JSON Web Token (JWT) creation and validation for secure user authentication. |
| **RTMPose / rtmlib** | Latest | Lightweight, real-time pose estimation library running via ONNX Runtime for extracting human skeletal keypoints from video frames. |
| **ONNX Runtime** | GPU | Hardware-accelerated inference engine for RTMPose. |
| **OpenCV** | python | Video frame processing, capture, and rendering. |
| **LangGraph** | Latest | Orchestrates the Friday AI state machine, managing conversation history, intent routing, and tool execution. |
| **Langchain** | Latest | Core framework for integrating with LLM providers (Gemini, Anthropic). |
| **Silero VAD** | Latest | Voice Activity Detection running locally via PyTorch to segment audio for speech-to-text. |
| **CrispASR (Qwen3)** | Local Bin | Ultra-fast local Speech-To-Text processing via a standalone executable (Windows). |
| **Voxtral** | Local Bin | High-fidelity local Text-To-Speech generation via a standalone Rust/C++ executable. |
| **Vanilla JS / HTML / CSS** | HTML5 | Frontend architecture prioritizing zero-build-step simplicity and maximum performance, interacting with the backend via REST and WebSockets. |

---

### FOLDER STRUCTURE

```
ActionCount/
├── backend/
│   ├── agent/
│   ├── counters/
│   ├── detector/
│   ├── logger/
│   └── utils/
├── frontend/
│   ├── css/
│   ├── img/
│   ├── js/
│   └── static/
│       ├── data/
│       └── img/
├── models/
└── target/
```

- **`ActionCount/`**
  - **Purpose**: Root directory containing the primary environment setup scripts, documentation, and entry folders for frontend and backend.
- **`backend/`**
  - **Purpose**: Core Python application holding the FastAPI server, Streamlit UI, database integration, and all business logic.
- **`backend/agent/`**
  - **Purpose**: Contains the Friday AI assistant implementation, including LangGraph orchestration, STT, TTS, and prompt memory.
- **`backend/counters/`**
  - **Purpose**: Contains individual class modules for every supported exercise. Each class parses skeletal keypoints and tracks reps/form.
- **`backend/detector/`**
  - **Purpose**: Contains the RTMPose wrapper classes responsible for executing frame inference.
- **`backend/logger/`**
  - **Purpose**: Contains custom performance profiling and telemetry for the computer vision pipeline.
- **`backend/utils/`**
  - **Purpose**: Common helpers including MongoDB access, session state management, calorie processing, and Pydantic validation schemas.
- **`frontend/`**
  - **Purpose**: The Vanilla JS/HTML frontend interface for the platform, acting as the primary presentation layer for the user.
- **`frontend/css/`**
  - **Purpose**: Contains component-specific or global CSS styling rules.
- **`frontend/img/`**
  - **Purpose**: Static assets for the frontend UI.
- **`frontend/js/`**
  - **Purpose**: Contains vanilla JavaScript modules handling API communication, state management, modal logic, and WebRTC streaming.
- **`frontend/static/data/`**
  - **Purpose**: Static configuration data, including the mapping paths for the SVG muscle heatmap.
- **`frontend/static/img/`**
  - **Purpose**: Secondary image storage, specifically holding `muscle_map.svg`.
- **`models/`**
  - **Purpose**: Stores the downloaded `.onnx` and `.gguf` weight files for RTMPose and local STT/TTS binaries.
- **`target/`**
  - **Purpose**: Build directory for compiled local binaries (e.g., Rust components for Voxtral/CrispASR).

---

### FILE-BY-FILE BREAKDOWN

#### `backend/app.py`
- **Type**: entry point / component
- **Purpose**: Streamlit-based web UI entry point handling legacy session state, camera upload routing, and dashboard elements.
- **Key Logic**:
  - Sets up Streamlit layout and session states for JWT tokens and workout plans.
  - Instantiates `ExerciseVideoProcessor` for WebRTC live camera tracking.
  - Handles the UI components for rendering chat, settings, and historical charts.
- **Dependencies**: `streamlit`, `streamlit_webrtc`, `backend.utils.db`, `backend.counters.*`.
- **Notes/Debt**: Legacy UI layer; much of its logic is duplicated or migrating to the Vanilla JS `frontend/` implementation.

#### `backend/endpoint.py`
- **Type**: entry point / service
- **Purpose**: Main FastAPI application serving the REST API endpoints and managing the WebSocket server for the Friday AI.
- **Key Logic**:
  - Exposes REST endpoints for auth (`/api/auth/login`), profile (`/api/user/profile`), workout syncing, and body metrics.
  - Handles a WebSocket route (`/ws/{session_id}`) for WebRTC signaling and coordinate offloading from the frontend.
  - Implements a fast-path regex command interceptor (`_FAST_PATH_RULES`) to catch vocal triggers like "save set" without LLM overhead.
- **Dependencies**: `fastapi`, `backend.utils.db`, `backend.utils.session_manager`, `backend.agent.stt`, `backend.agent.graph`.
- **Notes/Debt**: The fast-path regex is a hardcoded workaround to mitigate STT-to-LLM latency for core voice commands.

#### `backend/requirements.txt`
- **Type**: config
- **Purpose**: Python dependency manifest for pip.
- **Key Logic**:
  - Lists packages for FastAPI, PyMongo, Streamlit, LangGraph, and ONNX Runtime.
- **Dependencies**: None.
- **Notes/Debt**: Local models (CrispASR/Voxtral) operate as standalone executables but require `sounddevice` / `scipy` as I/O bridges.

#### `backend/agent/chatbot.py`
- **Type**: service
- **Purpose**: Central router for chatbot interactions, determining whether to invoke Friday (LangGraph) or fallback to Gemini.
- **Key Logic**:
  - Instantiates `run_friday_graph` for stateful interactions if environment supports it.
  - Manages standard stateless text responses as a fallback using `langchain_google_genai`.
- **Dependencies**: `backend.agent.graph`, `backend.agent.memory`.
- **Notes/Debt**: None.

#### `backend/agent/graph.py`
- **Type**: service
- **Purpose**: Defines and executes the LangGraph state machine orchestrating Friday's intent detection and multi-step tool logic.
- **Key Logic**:
  - Defines `AgentState` schema to carry conversation context, user profile, and active images.
  - Implements nodes for intent routing (`_route_intent`), direct conversation (`_chat_node`), and tool execution (`_tool_node`).
  - Calls external APIs (like Gemini Vision for calorie tracking) based on tool binding outputs.
- **Dependencies**: `langgraph`, `langchain_anthropic`, `backend.utils.db`, `backend.utils.calorie_tracker`.
- **Notes/Debt**: Needs monitoring for context window bloating due to storing base64 frames in state.

#### `backend/agent/memory.py`
- **Type**: utility
- **Purpose**: Responsible for generating the dynamic system prompt injected into Friday.
- **Key Logic**:
  - Pulls user profile, active workout plans, recent history, and live session state (e.g. current reps).
  - Condenses context into a single structured text string to guide the LLM's persona.
- **Dependencies**: `backend.utils.db`, `backend.utils.session_manager`.
- **Notes/Debt**: None.

#### `backend/agent/stt.py`
- **Type**: service
- **Purpose**: Manages the local-first Speech-To-Text pipeline utilizing Silero VAD and CrispASR.
- **Key Logic**:
  - Captures local microphone audio via `sounddevice` and buffers it into memory.
  - Evaluates frames using `Silero VAD` with a dual-threshold hysteresis mechanism (Start/Stop threshold).
  - Streams segmented VAD chunks via an asynchronous subprocess to the `crispasr.exe` backend for low-latency transcription.
- **Dependencies**: `sounddevice`, `numpy`, `torchaudio`, `subprocess`.
- **Notes/Debt**: Very sensitive to hardware noise gates; the `VAD_START_THRESH` might require calibration on different microphones.

#### `backend/agent/tts.py`
- **Type**: service
- **Purpose**: Handles local Text-To-Speech playback via the Voxtral native backend.
- **Key Logic**:
  - Buffers textual sentences and streams them to the `voxtral-mini-realtime-rs` subprocess via HTTP or standard pipes.
  - Includes `stop()` capability for barge-in interruptions when the user speaks over Friday.
- **Dependencies**: `subprocess`, `httpx`.
- **Notes/Debt**: Operates out-of-process via standard API calls, creating a minor overhead but isolating memory usage.

#### `backend/counters/BaseCounter.py`
- **Type**: utility
- **Purpose**: Abstract base class providing common mechanics for state-machine rep counting, velocity tracking, and form feedback.
- **Key Logic**:
  - Exposes `process_frame()` which calls the RTMPose detector and calculates joint angles.
  - Implements `_check_failure_trend()` to detect velocity drop-offs, indicating fatigue, and triggering motivation TTS.
  - Handles basic posture correction queues that feed into `SessionManager`'s TTS pipeline.
- **Dependencies**: `backend.detector.PoseDetector`, `numpy`.
- **Notes/Debt**: None.

#### `backend/counters/BicepCurlCounter.py`
- **Type**: model
- **Purpose**: Analyzes frames and counts reps for Bicep Curls.
- **Key Logic**:
  - Calculates elbow flexion angles.
  - Checks for leaning (shoulder-hip delta), elbows flaring, or momentum cheating (high wrist velocity).
- **Dependencies**: `backend.counters.BaseCounter`.
- **Notes/Debt**: None.

#### `backend/counters/CrunchCounter.py`
- **Type**: model
- **Purpose**: Analyzes frames and counts reps for Crunches.
- **Key Logic**:
  - Tracks shoulder-hip-ankle angles (bilateral inverted).
  - Validates lower back positioning to prevent injury.
- **Dependencies**: `backend.counters.BaseCounter`.
- **Notes/Debt**: None.

#### `backend/counters/KneePressCounter.py`
- **Type**: model
- **Purpose**: Analyzes frames and counts reps for Knee Presses.
- **Key Logic**:
  - Calculates hip-knee-ankle angles per limb.
  - Ensures torso remains upright and prevents leg swinging.
- **Dependencies**: `backend.counters.BaseCounter`.
- **Notes/Debt**: None.

#### `backend/counters/KneeRaiseCounter.py`
- **Type**: model
- **Purpose**: Analyzes frames and counts reps for Knee Raises.
- **Key Logic**:
  - Tracks knee oscillation to catch swinging legs.
  - Verifies knee ascends beyond hip level for a valid rep.
- **Dependencies**: `backend.counters.BaseCounter`.
- **Notes/Debt**: None.

#### `backend/counters/LateralRaiseCounter.py`
- **Type**: model
- **Purpose**: Analyzes frames and counts reps for Lateral Raises.
- **Key Logic**:
  - Ensures wrist y-coordinate aligns correctly relative to shoulder height.
  - Checks elbow bend angles to prevent locked joints.
- **Dependencies**: `backend.counters.BaseCounter`.
- **Notes/Debt**: None.

#### `backend/counters/LegRaiseCounter.py`
- **Type**: model
- **Purpose**: Analyzes frames and counts reps for Leg Raises.
- **Key Logic**:
  - Verifies lower back remains planted (detects arching).
  - Detects if legs drop too rapidly via ankle velocity thresholds.
- **Dependencies**: `backend.counters.BaseCounter`.
- **Notes/Debt**: None.

#### `backend/counters/OverheadPressCounter.py`
- **Type**: model
- **Purpose**: Analyzes frames and counts reps for Overhead Presses.
- **Key Logic**:
  - Analyzes hip-shoulder-elbow angles.
  - Validates elbow lockout at the apex and prevents excessive back arch.
- **Dependencies**: `backend.counters.BaseCounter`.
- **Notes/Debt**: None.

#### `backend/counters/PullupCounter.py`
- **Type**: model
- **Purpose**: Analyzes frames and counts reps for Pull-Ups.
- **Key Logic**:
  - Validates nose height vs wrist height to identify half-reps.
  - Identifies kipping by measuring horizontal hip displacement between frames.
- **Dependencies**: `backend.counters.BaseCounter`.
- **Notes/Debt**: None.

#### `backend/counters/PushupCounter.py`
- **Type**: model
- **Purpose**: Analyzes frames and counts reps for Push-Ups.
- **Key Logic**:
  - Inspects body line alignment (detects sagging or piked hips).
  - Checks if elbows break a 90-degree threshold at the bottom.
- **Dependencies**: `backend.counters.BaseCounter`.
- **Notes/Debt**: None.

#### `backend/counters/SitupCounter.py`
- **Type**: model
- **Purpose**: Analyzes frames and counts reps for Sit-Ups.
- **Key Logic**:
  - Tracks shoulder and hip angles.
  - Flags excessive neck pulling via head-shoulder orientation.
- **Dependencies**: `backend.counters.BaseCounter`.
- **Notes/Debt**: None.

#### `backend/counters/SquatCounter.py`
- **Type**: model
- **Purpose**: Analyzes frames and counts reps for Squats.
- **Key Logic**:
  - Measures hip depth relative to knee line.
  - Tracks knee valgus (knees buckling inward) via knee-to-ankle alignment.
- **Dependencies**: `backend.counters.BaseCounter`.
- **Notes/Debt**: None.

#### `backend/detector/PoseDetector.py`
- **Type**: service
- **Purpose**: Core interface for running RTMPose on incoming video frames.
- **Key Logic**:
  - Initializes `rtmlib.PoseTracker` and handles BGR-to-RGB conversion.
  - Computes exact joint angles using arc-cosine vectors.
  - Draws visual overlays (skeleton, bounding boxes) on the frame.
- **Dependencies**: `rtmlib`, `cv2`, `numpy`.
- **Notes/Debt**: Instantiation is heavy; intended to be preserved as a singleton per worker thread.

#### `backend/logger/metrics.py`
- **Type**: utility
- **Purpose**: Non-blocking pipeline latency instrumentation.
- **Key Logic**:
  - Uses `collections.deque` to measure end-to-end processing time (capture -> inference).
  - Silently drops telemetry logs into `logs/pipeline.log`.
- **Dependencies**: `logging`, `collections`.
- **Notes/Debt**: None.

#### `backend/utils/calorie_tracker.py`
- **Type**: service
- **Purpose**: Interfaces with Gemini Vision to extract nutritional data from images.
- **Key Logic**:
  - Base64 encodes uploaded frames and passes them to the Gemini API.
  - Parses JSON results with a robust error-recovery mechanism using regex fallback if JSON is truncated.
- **Dependencies**: `google.generativeai`, `backend.utils.db`.
- **Notes/Debt**: The JSON repair regex (`re.search`) is a workaround for LLM parsing instability.

#### `backend/utils/db.py`
- **Type**: utility
- **Purpose**: MongoDB persistence layer wrapping all direct CRUD operations.
- **Key Logic**:
  - Defines fine-to-broad muscle mapping dicts (`EXERCISE_MUSCLE_MAP`).
  - Contains all accessors for user creation, workout logging, metrics logging, and conversation turns.
- **Dependencies**: `pymongo`, `datetime`.
- **Notes/Debt**: Some legacy document mapping schema overrides exist for backward compatibility with older UI clients.

#### `backend/utils/session_manager.py`
- **Type**: service
- **Purpose**: Thread-safe singleton registry that manages per-user session memory and concurrent pose inference.
- **Key Logic**:
  - Spawns a daemon `InferenceWorker` thread to decouple RTMPose ML inference from WebSocket I/O loop.
  - Implements a single-slot buffer (`AtomicFrame`) so the model only processes the freshest frame available.
- **Dependencies**: `threading`, `queue`, `backend.utils.singleton`.
- **Notes/Debt**: Ensures the fast pipeline anti-pattern is fixed by never buffering stale frames.

#### `backend/utils/singleton.py`
- **Type**: utility
- **Purpose**: Provides atomic single-slot registers (`AtomicFrame`, `AtomicResult`) for lock-free thread coordination.
- **Key Logic**:
  - Write over-writes the existing variable within a thread lock to ensure the ML thread reads fresh frames.
- **Dependencies**: `threading`.
- **Notes/Debt**: None.

#### `backend/utils/validation.py`
- **Type**: config
- **Purpose**: Centralized Pydantic models validating all FastAPI incoming payloads and output schemas.
- **Key Logic**:
  - Includes robust regex matching constraints and type guarantees for Authentication, Profiles, and Chat history.
- **Dependencies**: `pydantic`.
- **Notes/Debt**: None.

#### `frontend/index.html`
- **Type**: component
- **Purpose**: Main entry point for the Vanilla JS application.
- **Key Logic**:
  - Imports all primary modules and manages the foundational layout.
- **Dependencies**: CSS and JS bundles.
- **Notes/Debt**: None.

#### `frontend/dashboard.html`
- **Type**: component
- **Purpose**: HTML layout for the user dashboard displaying metrics and SVG heatmaps.
- **Key Logic**:
  - Contains Canvas elements for Chart.js and containers for dynamically injected SVGs.
- **Dependencies**: `dashboard.js`.
- **Notes/Debt**: None.

#### `frontend/login.html`
- **Type**: component
- **Purpose**: Authentication gateway and user sign-up layout.
- **Key Logic**:
  - Defines the flipping card UI for Login vs Signup.
  - Implements the DOM for the multi-step onboarding modal.
- **Dependencies**: `auth.js`.
- **Notes/Debt**: None.

#### `frontend/tracker.html`
- **Type**: component
- **Purpose**: (Wait - assumed from context) Core workout interface.
- **Key Logic**:
  - Video feed containers, live rep counter overlay, dynamic form guidance text.
- **Dependencies**: `tracker.js`.
- **Notes/Debt**: None.

#### `frontend/welcome.html`
- **Type**: component
- **Purpose**: Intermediate post-login landing page acknowledging onboarding completion.
- **Key Logic**: Provides quick actions to start workout or configure plans.
- **Dependencies**: `page_transitions.js`.
- **Notes/Debt**: None.

#### `frontend/calorie.html`
- **Type**: component
- **Purpose**: HTML page for scanning food.
- **Key Logic**: Provides video stream capture specific to static plate/food recognition.
- **Dependencies**: `calorie.js`.
- **Notes/Debt**: None.

#### `frontend/chatbot.html`
- **Type**: component
- **Purpose**: Dedicated page for full-screen Friday AI text interactions.
- **Key Logic**: Renders chat history and handles input boxes.
- **Dependencies**: `chat.js`.
- **Notes/Debt**: None.

#### `frontend/metrics.html`
- **Type**: component
- **Purpose**: UI for viewing and entering body metrics (weight, height).
- **Key Logic**: Input forms mapped to the API logs.
- **Dependencies**: `metrics.js`.
- **Notes/Debt**: None.

#### `frontend/plans.html`
- **Type**: component
- **Purpose**: UI for defining weekly workout plans.
- **Key Logic**: Drag and drop lists or structured form fields to attach exercise slugs to specific days.
- **Dependencies**: `plan_loader.js`.
- **Notes/Debt**: None.

#### `frontend/css/main.css`
- **Type**: config
- **Purpose**: Core style specifications for generic components.
- **Key Logic**: Defines standard buttons, flex layouts, typography scales.
- **Dependencies**: None.
- **Notes/Debt**: None.

#### `frontend/styles.css`
- **Type**: config
- **Purpose**: Detailed stylistic overlays, glassmorphism logic, and animations.
- **Key Logic**: Contains highly specialized UI aesthetics, z-indexing, and keyframe animations for the HUD.
- **Dependencies**: None.
- **Notes/Debt**: Overlaps slightly with `main.css`.

#### `frontend/js/api.js`
- **Type**: service
- **Purpose**: Generic fetch wrappers abstracting all backend REST calls.
- **Key Logic**:
  - Handles JWT Bearer token retrieval and injection.
  - Implements uniform error trapping for HTTP responses.
- **Dependencies**: None.
- **Notes/Debt**: None.

#### `frontend/js/auth.js`
- **Type**: script
- **Purpose**: Handlers for login form submissions and user onboarding states.
- **Key Logic**:
  - Executes password strength logic.
  - Mutates DOM steps during the 4-phase onboarding sequence.
- **Dependencies**: `api.js`.
- **Notes/Debt**: None.

#### `frontend/js/calorie.js`
- **Type**: script
- **Purpose**: Handlers for snapping a picture and invoking the calorie tracking API.
- **Key Logic**: Manages canvas captures and API polling.
- **Dependencies**: `api.js`.
- **Notes/Debt**: None.

#### `frontend/js/chat.js`
- **Type**: script
- **Purpose**: Manages UI state for the AI Chatbot window.
- **Key Logic**: Appends chat bubbles and auto-scrolls to the bottom.
- **Dependencies**: `api.js`.
- **Notes/Debt**: None.

#### `frontend/js/constants.js`
- **Type**: utility
- **Purpose**: Global constant definitions (enums, standard string keys).
- **Key Logic**: Shared dictionary references for multiple JS files.
- **Dependencies**: None.
- **Notes/Debt**: None.

#### `frontend/js/dashboard.js`
- **Type**: script
- **Purpose**: Renders visual analytics on the dashboard.
- **Key Logic**:
  - Instantiates `Chart.js` radar and bar charts.
  - Injects `muscle_map.svg` dynamically and calculates opacity/fill colours per SVG path based on workout volume.
  - Manages gamification logic (streak calculation, badge un-locking).
- **Dependencies**: `Chart.js`, `api.js`.
- **Notes/Debt**: Complex DOM logic tightly coupled with specific HTML IDs.

#### `frontend/js/hud.js`
- **Type**: script
- **Purpose**: Manages real-time visual updates for the in-workout heads-up display.
- **Key Logic**: Formats text outputs and applies color-coded form feedback logic to the DOM.
- **Dependencies**: None.
- **Notes/Debt**: None.

#### `frontend/js/live.js`
- **Type**: script
- **Purpose**: Handles WebRTC setup for live camera feeds.
- **Key Logic**: Prompts for `getUserMedia` permissions and streams the feed into a local HTML5 video element.
- **Dependencies**: `session.js`.
- **Notes/Debt**: None.

#### `frontend/js/metrics.js`
- **Type**: script
- **Purpose**: Logic layer for the body metrics chart and input table.
- **Key Logic**: Pulls `/api/metrics` and formats date-based visualizations.
- **Dependencies**: `api.js`.
- **Notes/Debt**: None.

#### `frontend/js/overlay.js`
- **Type**: script
- **Purpose**: Manages pop-ups and full-screen overlays (modals).
- **Key Logic**: Toggles `.open` / `.hidden` state classes on DOM elements.
- **Dependencies**: None.
- **Notes/Debt**: None.

#### `frontend/js/page_transitions.js`
- **Type**: utility
- **Purpose**: Implements smooth SPA-like fade transitions.
- **Key Logic**: Intercepts standard link clicks to play an exit animation before navigating.
- **Dependencies**: None.
- **Notes/Debt**: None.

#### `frontend/js/plan_loader.js`
- **Type**: script
- **Purpose**: Drives the automatic sequence execution for weekly workout plans.
- **Key Logic**: Reads JSON workout plans, auto-configures the camera, and forces rest timers between scheduled sets.
- **Dependencies**: `api.js`, `rest_timer.js`.
- **Notes/Debt**: None.

#### `frontend/js/rest_timer.js`
- **Type**: script
- **Purpose**: Standalone logic for the on-screen countdown timer during workout rests.
- **Key Logic**: Standard `setInterval` with a visual radial progress bar update.
- **Dependencies**: None.
- **Notes/Debt**: None.

#### `frontend/js/session.js`
- **Type**: script
- **Purpose**: Coordinates the state link between the frontend and the backend WebSocket stream.
- **Key Logic**:
  - Implements `requestAnimationFrame` lerping logic for smooth rep counter transitions to avoid UI jitter.
  - `SkeletonDrawer` class plots incoming X/Y keypoint arrays onto the HTML5 Canvas context.
- **Dependencies**: `api.js`.
- **Notes/Debt**: None.

#### `frontend/js/tracker.js`
- **Type**: script
- **Purpose**: Logic handling user interaction to manually save sets or stop the camera.
- **Key Logic**:
  - Implements the `saveSet()` function bridging the current HUD counter values into the `Workout.save()` API call.
  - Implements smart auto-fill using `localStorage` for returning equipment weights.
- **Dependencies**: `api.js`.
- **Notes/Debt**: None.

#### `frontend/js/upload.js`
- **Type**: script
- **Purpose**: Logic for handling file uploads (analyzing pre-recorded videos).
- **Key Logic**: Reads a local file, generates a blob, and posts it to the backend analysis endpoint.
- **Dependencies**: `api.js`.
- **Notes/Debt**: None.

#### `frontend/js/app.js`
- **Type**: component
- **Purpose**: Master orchestrator file for vanilla JS bootstrapping.
- **Key Logic**: Registers event listeners on DOM load and sets up global state.
- **Dependencies**: None.
- **Notes/Debt**: None.

#### `frontend/img/muscle_map.svg`
- **Type**: model (asset)
- **Purpose**: A blank SVG anatomical map used to visually display muscular engagement.
- **Key Logic**: Paths have defined IDs matching strings managed in `dashboard.js`.
- **Dependencies**: None.
- **Notes/Debt**: None.

#### `frontend/static/data/paths.json`
- **Type**: config
- **Purpose**: Mapping configuration for the SVG.
- **Key Logic**: Maps specific `path` XML element IDs in the SVG to textual muscle group names.
- **Dependencies**: None.
- **Notes/Debt**: None.

#### `friday_setup.ps1`
- **Type**: script
- **Purpose**: Automated PowerShell script to deploy and configure the environment on Windows.
- **Key Logic**: Checks and downloads specific models (CrispASR, Voxtral, RTMPose) to the `target/` and `models/` directories.
- **Dependencies**: Powershell.
- **Notes/Debt**: None.

#### `friday_unified_implementation_plan.md`
- **Type**: config
- **Purpose**: Technical specification documentation artifact.
- **Key Logic**: Outlines the detailed technical requirements to migrate from Azure to local STT/TTS.
- **Dependencies**: None.
- **Notes/Debt**: None.


## DEEP DIVE

### 1. Function Signatures

**`backend/detector/PoseDetector.py`**
- `__init__(self, mode: str = "balanced", backend: str = "onnxruntime", device: str = "auto") -> None`: Initializes the RTMPose model via rtmlib.
- `findPose(self, img: np.ndarray, draw: bool = True) -> np.ndarray`: Runs inference on a single frame, storing keypoints and returning the annotated image.
- `findPosition(self, img: np.ndarray, draw: bool = False) -> list`: Returns `[[id, cx, cy, score], …]` for the 17 COCO keypoints.
- `findAngle(self, img: np.ndarray, p1: int, p2: int, p3: int, landmarks_list: list, draw: bool = True) -> float | None`: Computes the 2D dot-product angle at joint `p2`.
- `_draw_skeleton(self, img: np.ndarray, kps: np.ndarray, scores: np.ndarray) -> None`: Overlays the COCO-17 skeleton lines on the image.

**`backend/counters/BaseCounter.py`**
- `reset(self) -> None`: Resets all state-machine properties, deques, and rep counts.
- `_kp_map(lm: list) -> dict`: Static helper converting `landmarks_list` into a `{id: (cx, cy)}` map.
- `calc_velocity(self, kp_idx: int) -> float`: Averages pixel/s speed of a given keypoint over a 5-frame sliding window.
- `_record_rep_velocity(self, kp_idx: int) -> None`: Records velocity at rep completion and checks for failure trends.
- `_check_failure_trend(self) -> Optional[str]`: Analyzes recent rep velocities; returns a motivational phrase if a 20% drop is detected.
- `pop_failure_motivation(self) -> Optional[str]`: Consumes and returns any pending motivational TTS phrase.
- `_check_posture(self, frame: np.ndarray, lm: list) -> tuple`: Abstract stub for exercise-specific posture checks.
- `pop_posture_tts(self) -> Optional[str]`: Returns posture error string if the 6-second TTS cooldown has elapsed.
- `process_frame(self, frame: np.ndarray) -> dict`: Core pipeline method calling RTMPose, computing angles, and returning the UI payload.
- `_smooth_angle(self, side: str, raw_angle) -> float`: Applies a median filter + standard deviation outlier rejection to raw angles.
- `_tick_bilateral(self, angle, up_angle: float, down_angle: float, inverted: bool = False) -> bool`: Advances the unified state machine ("up"/"down") and increments reps.
- `_tick_per_limb(self, left_angle, right_angle, up_angle: float, down_angle: float, inverted: bool = False) -> int`: Advances state machines independently for alternating-limb exercises.
- `_compute(self, frame: np.ndarray, landmarks_list: list) -> tuple`: Abstract interface for subclass logic; returns `(progress, feedback, correct_form)`.

**`backend/utils/session_manager.py`**
- `InferenceWorker.__init__(self, counter, atomic_frame: AtomicFrame, atomic_result: AtomicResult, metrics: PipelineMetrics, tts_queue: queue.Queue, session_id: str) -> None`: Sets up the daemon inference thread.
- `InferenceWorker.stop(self) -> None`: Signals the worker thread to terminate cleanly.
- `InferenceWorker.run(self) -> None`: Main loop; reads frames, runs inference, and writes results atomically at 15 FPS.
- `SessionManager.create(self, exercise: str) -> str`: Instantiates a new SessionData + InferenceWorker and returns a UUID.
- `SessionManager.get(self, session_id: str) -> SessionData`: Retrieves the active session.
- `SessionManager.reset(self, session_id: str) -> None`: Resets the rep counter for an active session.
- `SessionManager.destroy(self, session_id: str) -> None`: Stops the worker thread and drops the session.

**`backend/utils/db.py`**
- `get_user(username: str) -> Optional[dict]`: Retrieves user document minus ID and username.
- `create_user(username: str, hashed_password: str, email: Optional[str] = None) -> dict`: Upserts a new auth record.
- `update_user_profile(username: str, profile: dict) -> bool`: Replaces the onboarding profile dictionary.
- `save_workout(username: str, exercise: str, reps: int, sets: int, workout_date: Optional[str] = None, weight_kg: Optional[float] = None, calories_burnt: Optional[float] = None) -> dict`: Pushes a new set to the daily workout log.
- `get_monthly_stats(username: str, year_month: Optional[str] = None) -> dict[str, int]`: Aggregates set counts by fine/broad muscle groups.
- `get_monthly_calories(username: str, year_month: Optional[str] = None) -> float`: Sums up all burnt calories for the month.
- `append_chat_message(username: str, role: str, content: str) -> None`: Appends to legacy chat history (capped at 100).
- `log_calorie_entry(username: str, entry: dict) -> dict`: Inserts a food scan document.
- `append_conversation_turn(username: str, role: str, content: str, channel: str = "text", attachments: Optional[list] = None) -> dict`: Unified LangGraph memory log.
- `save_diet_plan(username: str, title: str, content: str) -> dict`: Saves AI-generated diet plan and deactivates old ones.
- `save_workout_plan(username: str, weekday: str, exercises: list[dict]) -> dict`: Upserts a recurring weekly exercise plan.

**`backend/agent/graph.py`**
- `_get_llm() -> ChatAnthropic | ChatGoogleGenerativeAI`: Instantiates the primary LLM (Claude, fallback Gemini).
- `_get_intent_llm() -> ChatAnthropic | ChatGoogleGenerativeAI`: Instantiates the fast routing LLM (Gemini Flash Lite or Claude).
- `_get_checkpointer() -> MongoDBSaver | MemorySaver`: Connects the LangGraph checkpointer to MongoDB.
- `intent_node(state: AgentState) -> dict`: Classifies user input into a tool/command key.
- `_route_after_intent(state: AgentState) -> str`: Edge conditional; routes to `clarify_node` if confidence < 0.6, else `tool_node`.
- `tool_node(state: AgentState) -> dict`: Executes the intent action (e.g., calling calorie API, generating plans).
- `clarify_node(state: AgentState) -> dict`: Emits a clarification request for uncertain intents.
- `memory_write_node(state: AgentState) -> dict`: Logs the user's raw message to MongoDB.
- `response_node(state: AgentState) -> dict`: Generates the final spoken/textual reply using context + tool results.
- `invoke_friday(username: str, message: str, channel: str = "text", latest_frame: Optional[bytes] = None) -> dict`: External entry point to run the graph.

**`backend/agent/memory.py`**
- `build_system_prompt(username: str, channel: str = "text", current_exercise: Optional[str] = None, current_reps: Optional[int] = None) -> str`: Assembles the master context prompt combining user profile, active plans, runtime state, and history.
- `should_regenerate_summary(username: str) -> bool`: Evaluates if the raw message count has grown enough to trigger a new AI summary.

**`backend/utils/calorie_tracker.py`**
- `_encode_frame(frame_bgr: np.ndarray) -> str`: JPEG-compresses and base64 encodes an OpenCV frame.
- `_repair_json(raw: str) -> str`: Fallback mechanism to close truncated strings/brackets from LLM output.
- `scan_food_from_frame(frame_bgr: np.ndarray, username: str) -> dict`: Invokes Gemini Vision on a frame and logs the result to DB.

### 2. LangGraph Graph Detail

**StateGraph (AgentState TypedDict)**
```python
class AgentState(TypedDict):
    messages:          Annotated[list, add_messages]
    channel:           str            # "text" | "voice"
    username:          str
    intent:            Optional[str]
    intent_params:     Optional[dict]
    intent_confidence: float
    tool_result:       Optional[dict]
    response:          Optional[str]
    latest_frame:      Optional[bytes]
```

**Nodes & Purpose**
- **`intent_node`**: Uses a fast LLM to parse user input into a specific intent (e.g., `"save_set"`).
- **`clarify_node`**: Intervenes when intent confidence is low to prompt the user.
- **`tool_node`**: Executes backend actions based on intent (DB reads, Calorie scans, Plan generation).
- **`memory_write_node`**: Persists the conversation turn to MongoDB.
- **`response_node`**: The final LLM pass synthesizing system prompt + tool results into a channel-appropriate output.

**Edges**
- `START -> intent_node`
- `intent_node -> [conditional: _route_after_intent]`
  - Condition: `intent_confidence < 0.6` -> `clarify_node`
  - Condition: `intent_confidence >= 0.6` -> `tool_node`
- `clarify_node -> memory_write_node`
- `tool_node -> memory_write_node`
- `memory_write_node -> response_node`
- `response_node -> END`

**Tools Registered (COMMAND_REGISTRY)**
- `calorie_scan`: Capture frame → AI vision → estimate calories.
- `calories_today`: Sum today's food scan calories.
- `calorie_history`: Summarize recent food scans.
- `who_am_i`: Read back user profile + stats.
- `status`: System health summary.
- `overlay_toggle`: Toggle HUD.
- `screenshot`: Save camera frame.
- `diet_plan`: Generate personalised diet plan.
- `generate_workout_plan`: Generate a weekly workout plan.
- `save_workout_plan`: Save generated plan to DB.
- `reset_reps`, `start_camera`, `stop_camera`, `save_set`, `next_set`, `stop_set`: Control camera and sets.
- `chat`: General conversation.

### 3. Counter State Machine Details

The `BaseCounter` implementations use standardized angles for stage-machine debouncing (`_tick_bilateral` or `_tick_per_limb`):

- **SquatCounter**: `UP_ANGLE = 160`, `DOWN_ANGLE = 110`. Posture: knee valgus (knee vs ankle alignment), hip vs knee depth, back lean.
- **PushupCounter**: `UP_ANGLE = 160`, `DOWN_ANGLE = 130`. Posture: hip sagging, piking (hip angle < 140), elbow depth.
- **SitupCounter**: `UP_ANGLE = 160`, `DOWN_ANGLE = 145`. Posture: excessive neck pulling, torso jerking.
- **PullupCounter**: `UP_ANGLE = 70`, `DOWN_ANGLE = 140`. Posture: kipping (horizontal displacement), chin over bar.
- **OverheadPressCounter**: `UP_ANGLE = 150`, `DOWN_ANGLE = 100`. Posture: back arching, full lockout.
- **LateralRaiseCounter**: `UP_ANGLE = 80`, `DOWN_ANGLE = 30`. Posture: shoulder shrugging, locked elbows.
- **LegRaiseCounter**: `UP_ANGLE = 160`, `DOWN_ANGLE = 110`. Posture: lower back arching, fast drop velocity.
- **KneeRaiseCounter**: `UP_ANGLE = 160`, `DOWN_ANGLE = 110`. Posture: torso leaning, leg swinging.

*(All counters use a global `DEBOUNCE_SECONDS = 0.5` inherited from `BaseCounter` to prevent rapid double-counting.)*

### 4. Frontend File Breakdown

#### `frontend/js/live.js`
- **Purpose**: Controls WebRTC webcam capture and MJPEG binary streaming.
- **Key Functions**:
  - `start()`: Requests `getUserMedia()`, establishes `/ws/stream/{sid}` connection, and begins the 30 FPS transmit loop.
  - `_sendLoop(ts)`: Uses `requestAnimationFrame` to draw the video element to an offscreen canvas, extracts a JPEG blob, and sends the raw `ArrayBuffer` over WebSocket.
  - `stop()`: Halts the RAF loop, closes the WebSocket, and releases video tracks.
- **WebSocket Messages**:
  - **Sent**: Binary `ArrayBuffer` containing JPEG frame data.
  - **Received**: JSON string containing `{ counter, feedback, progress, correct_form, keypoints }`.

#### `frontend/js/session.js`
- **Purpose**: Wraps backend session API calls and orchestrates smooth HUD animations.
- **Key Functions**:
  - `start(exercise)`: POSTs to `/session/start`.
  - `reset()`: POSTs to `/session/{sid}/reset`.
  - `updateHUD(data)`: Debounces and sets target state for the Rep and Progress UI.
  - `_lerpLoop()`: RAF-based linear interpolation function driving the smooth UI transition of rep counts and progress bars.
  - `SkeletonDrawer.draw()`: Maps normalized backend keypoint arrays to canvas drawing paths using `SKELETON_PAIRS`.

#### `frontend/js/upload.js`
- **Purpose**: Manages drag-and-drop pre-recorded video analysis.
- **Key Functions**:
  - `processFile(file)`: POSTs a FormData blob to `/upload/process`.
  - `_streamMjpeg(body, signal)`: Reads a `multipart/x-mixed-replace` chunk stream, slicing boundaries to render live JPEG outputs natively in the DOM.
  - `_startHudPolling()`: Long-polls `/session/{sid}/state` for HUD synchronization during upload.

#### `frontend/js/constants.js`
- **Purpose**: Global DOM element references and shared mutable state.
- **Key Variables**: `TARGET_FPS = 30`, `PROCESS_W = 640`, `PROCESS_H = 360`, `SKELETON_PAIRS` array, and static references like `repCount`, `btnStartCamera`, and `sessionId`.

#### `frontend/app.js`
- **Purpose**: Orchestrator for tab navigation and high-level camera State Machine.
- **Key Functions**:
  - `switchTab(mode)`: Navigates between 'camera' and 'upload', stopping background streams accordingly.
  - `StateMachine.transition(next)`: Hardened orchestrator ensuring the camera is only started in `ACTIVE` or `WORKOUT` modes, preventing stray WebRTC handles.
  - `checkTodayPlan()`: Auto-prompts a workout start sequence if an active weekly plan exists for the current day.

### 5. WebSocket Protocol

**1. Inference Stream (`/ws/stream/{session_id}`)**
- **Lifecycle**: Connect → Open Camera → Stream frames → Close.
- **Inbound (Binary)**: Raw JPEG `ArrayBuffer` sent from frontend `live.js`.
- **Outbound (JSON)**:
  ```json
  {
    "counter": 5,
    "feedback": "Up",
    "posture_error": "piking",
    "posture_msg": "Lower your hips to form a straight line.",
    "velocity": 34.5,
    "progress": 85.0,
    "correct_form": true,
    "keypoints": [[124, 234], [130, 240]]
  }
  ```

**2. Friday Voice Assistant (`/ws/friday`)**
- **Lifecycle**: Connect → Authenticate via query param `?token=` → Stream JSON envelopes.
- **Audio Transport**: Uses base64 encoded chunks wrapped in JSON for bidirectional audio (frontend sends microphone data, backend sends TTS).
- **Outbound Event Schemas**:
  - **TTS Chunk**: `{"type": "tts_chunk", "data": {"audio_b64": "..."}}`
  - **Speaking Indicator**: `{"type": "friday_speaking", "data": {"active": true}}`
  - **Command Trigger**: `{"type": "frontend_command", "data": {"command": "save_set"}}`

### 6. Auth Flow

- **Password Hashing**: Uses `passlib` with Argon2 (`CryptContext(schemes=["argon2"])`).
- **JWT Payload**: Contains standard `{ "sub": "username", "exp": 1234567890 }`. Expiry is configured via `ACCESS_TOKEN_EXPIRE_MINUTES` (defaults to 10080 / 7 days).
- **Validation**: Protected endpoints use `Depends(_get_current_user)`, which invokes `OAuth2PasswordBearer`. It extracts the token, decodes it via `jose.jwt`, and verifies the `sub` exists in the MongoDB `users` collection before yielding the username.

### 7. Concurrency Model

The inference pipeline fundamentally decouples the I/O-bound WebSocket event loop from the CPU-bound ONNX model execution:

- **Data Structures**: `AtomicFrame` and `AtomicResult` (defined in `singleton.py`) are lock-protected single-slot variables. When a new frame arrives via WS, it overwrites the slot.
- **Thread Lifecycle**: `SessionManager` spawns a dedicated `InferenceWorker` `threading.Thread` per active `session_id`.
- **Worker Execution**: The worker reads `AtomicFrame`, executes `counter.process_frame()`, packages the payload, and writes to `AtomicResult` while adhering to a strict `~15 FPS` sleep cadence to prevent starving the server. If the user stops the session, `session.stop()` sets a `threading.Event()` to cleanly exit the thread.

### 8. logger/metrics.py

- **Collection**: `PipelineMetrics` tracks system latencies locally within each `InferenceWorker`.
- **Metrics Tracked**:
  - `inference_ms`: Total time spent inside RTMPose + Counter math.
  - `capture_ms`: Time required to decode the JPEG payload.
  - `e2e_ms`: Total wall-clock time from the frame arriving to the result being packed.
- **Reporting**: Stores rolling windows using `collections.deque(maxlen=60)`. Every 5 seconds (`REPORT_INTERVAL_S`), it logs the averaged throughput to `logs/pipeline.log` utilizing standard Python `logging`.
