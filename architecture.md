# ActionCount Architectural Diagrams

This file contains ASCII representations of the architectural diagrams requested for the `CODEBASE_DEEP.md` documentation.

## Chapter 2 — System Architecture and Communication Protocol

### 2.1 — System Context Diagram (C4 Level 1)
```text
                     +---------------------------------------+
                     |         Privacy Boundary              |
                     |                                       |
  +--------+         |    +-----------------------------+    |         +-----------------+
  |        |         |    |                             |    |         |                 |
  |  User  |========>|    |     ActionCount System      |====|========>| MongoDB Atlas   |
  |        |         |    | (No raw video leaves here)  |    |         |                 |
  +--------+         |    +-----------------------------+    |         +-----------------+
                     |                  |                    |
                     |                  |                    |         +-----------------+
                     |                  |                    |         |                 |
                     |                  +====================|========>| Anthropic API   |
                     |                  |                    |         | (Claude 3.5)    |
                     |                  |                    |         +-----------------+
                     |                  |                    |
                     |                  |                    |         +-----------------+
                     |                  |                    |         |                 |
                     |                  +====================|========>| Google API      |
                     |                                       |         | (Gemini 1.5)    |
                     +---------------------------------------+         +-----------------+
```

### 2.1 — Container Diagram (C4 Level 2)
```text
 +-----------------------------------------------------------------------------------+
 |                                 Local Workstation                                 |
 |                                                                                   |
 |   +-----------------+            +--------------------------------------------+   |
 |   |                 | WebSocket  |              FastAPI / Uvicorn             |   |
 |   | Browser Client  |<==========>|                  Process                   |   |
 |   | (HTML/JS/CSS)   |            |                                            |   |
 |   +-----------------+            |   +------------------------------------+   |   |
 |            |                     |   |          Async Event Loop          |   |   |
 |            | Audio/Video Streams |   +------------------------------------+   |   |
 |            v                     |            ^                   ^           |   |
 |   +-----------------+            |            | Queue             | Queue     |   |
 |   |                 | IPC/Pipes  |            v                   v           |   |
 |   +-----------------+            |   +----------------+   +----------------+  |   |
 |   | Friday STT/TTS  |<==========>|   | InferenceWorker|   |  AnyIO Worker  |  |   |
 |   |   Daemons       |            |   |     Threads    |   |     Threads    |  |   |
 |   +-----------------+            |   +----------------+   +----------------+  |   |
 +----------------------------------+--------------------------------------------+---+
```

### 2.2 — Backend Component Diagram (C4 Level 3)
```text
 +-----------------------------------------------------------------------------------+
 |                             FastAPI / Uvicorn Process                             |
 |                                                                                   |
 |  +---------------+      +-------------------+      +---------------------------+  |
 |  |               |      |                   |      |                           |  |
 |  |  API Router   |----->| Thread Coordinator|----->|     Validation Layer      |  |
 |  | (/ws/stream)  |      |                   |      |                           |  |
 |  +---------------+      +-------------------+      +---------------------------+  |
 |          |                        |                              |                |
 |          v                        v                              v                |
 |  +---------------+      +-------------------+      +---------------------------+  |
 |  |               |      |                   |      |                           |  |
 |  | Vision Engine |----->| Exercise Counters |----->|     Persistence Layer     |  |
 |  | (YOLO/ONNX)   |      |   (Rep Logic)     |      |       (MongoDB)           |  |
 |  +---------------+      +-------------------+      +---------------------------+  |
 |                                                                  ^                |
 |  +---------------+      +-------------------+                    |                |
 |  |               |      |                   |                    |                |
 |  | Audio Pipeline|<---->| AI State Machine  |--------------------+                |
 |  | (VAD/STT/TTS) |      | (LangGraph/LLM)   |                                     |
 |  +---------------+      +-------------------+                                     |
 +-----------------------------------------------------------------------------------+
```

### 2.3 — Frontend Component Diagram
```text
                           +------------------------+
                           |       app.js           |
                           | (Global State Machine) |
                           +------------------------+
                                        |
       +--------------------+-----------+-----------+--------------------+
       |                    |                       |                    |
       v                    v                       v                    v
 +-------------+     +-------------+         +-------------+      +--------------+
 |             |     |             |         |             |      |              |
 | session.js  |     |   live.js   |         |plan_loader.js|     |friday_client.js|
 | (Session    |     | (Video /    |         | (Workout    |      | (Voice / AI  |
 |  Manager)   |     |  Inference) |         |  Configs)   |      |  Interface)  |
 +-------------+     +-------------+         +-------------+      +--------------+
       |                    |                       |                    |
       +--------------------+-----------+-----------+--------------------+
                                        |
                                        v
                           +------------------------+
                           |     DOM / UI Layer     |
                           |  (HUD, Charts, To-Do)  |
                           +------------------------+
```

### 2.4 — Deployment Diagram
```text
 +-------------------------------------------------------------------------+
 |                      Windows / Linux Host Machine                       |
 |                                                                         |
 |  +-----------------------+     +-----------------------+                |
 |  |   Uvicorn Process     |     |   Streamlit Process   |                |
 |  |   (FastAPI Backend)   |     |   (Admin Dashboard)   |                |
 |  |   Port: 8000          |     |   Port: 8501          |                |
 |  +-----------------------+     +-----------------------+                |
 |            |                               |                            |
 |            | (Subprocess Pipe)             |                            |
 |            v                               |                            |
 |  +-----------------------+                 |                            |
 |  | CrispASR / Voxtral    |                 |                            |
 |  | Local STT/TTS Daemons |                 |                            |
 |  +-----------------------+                 |                            |
 +------------|-------------------------------|----------------------------+
              |                               |
              | Network                       | Network
              v                               v
 +-----------------------+        +-----------------------+
 |     MongoDB Atlas     |        |   LLM Providers API   |
 |   (Cloud Database)    |        | (Anthropic / Google)  |
 +-----------------------+        +-----------------------+
```

### 2.5 — WebSocket Protocol Sequence Diagram
```text
/ws/stream (Video Processing)
-----------------------------
Browser                    Server (FastAPI)               InferenceWorker
   |                              |                              |
   |--- Base64 Frame (Video) ---->|                              |
   |                              |--- AtomicFrame Queue ------->|
   |                              |                              |--- YOLO/ONNX Inference
   |                              |<-- AtomicResult Queue -------|
   |<-- Rep Count & Landmarks ----|                              |
   |                              |                              |

/ws/friday (Voice Agent)
-----------------------------
Browser               Server (FastAPI)   Friday STT/TTS    LangGraph      LLM API
   |                         |                 |               |             |
   |-- Audio Chunk (Blob) -->|                 |               |             |
   |                         |-- PCM Buffer -->| (STT)         |             |
   |                         |<-- Transcript --|               |             |
   |<-- "Thinking..." -------|                 |               |             |
   |                         |--- User Intent ---------------->|             |
   |                         |                 |               |--- Prompt ->|
   |                         |                 |               |<-- JSON ----|
   |                         |<-- Agent State / Tool Calls ----|             |
   |                         |--- Response Text->| (TTS)       |             |
   |                         |<-- Audio Stream --|             |             |
   |<-- Friday Audio Play ---|                 |               |             |
   |                         |                 |               |             |
```

## Chapter 4 — Data Flows

### 4.2 — Live Inference Pipeline Flow Diagram
```text
+-----------------------+---------------------------+-----------------------------------+
|  Browser (live.js)    |    FastAPI Event Loop     |     InferenceWorker Thread        |
+-----------------------+---------------------------+-----------------------------------+
|                       |                           |                                   |
| 1. Capture WebCam     |                           |                                   |
|    Frame              |                           |                                   |
|          |            |                           |                                   |
|          v            |                           |                                   |
| 2. Send Base64 via    |                           |                                   |
|    WebSocket stream   |                           |                                   |
|          |            |                           |                                   |
|          +------------+-> 3. Receive Frame        |                                   |
|                       |             |             |                                   |
|                       |             v             |                                   |
|                       |   4. Create AtomicFrame   |                                   |
|                       |             |             |                                   |
|                       |             +-------------+-> 5. Extract from Input Queue     |
|                       |                           |             |                     |
|                       |                           |             v                     |
|                       |                           |   6. ONNX Model Inference         |
|                       |                           |      (Pose Estimation)            |
|                       |                           |             |                     |
|                       |                           |             v                     |
|                       |                           |   7. Apply Rep Counting Logic     |
|                       |                           |             |                     |
|                       |                           |             v                     |
|                       |                           |   8. Create AtomicResult          |
|                       |                           |             |                     |
|                       |   9. Read from Output  <--+-------------+                     |
|                       |      Queue                |                                   |
|                       |             |             |                                   |
|                       |             v             |                                   |
| 11. Parse JSON Result |   10. Send JSON over      |                                   |
|             ^         |       WebSocket           |                                   |
|             |         |                           |                                   |
|             +---------+-------------+             |                                   |
|                       |                           |                                   |
| 12. lerp loop updates |                           |                                   |
|     HUD & Skeleton    |                           |                                   |
+-----------------------+---------------------------+-----------------------------------+
```

### 4.3 — AI Agent Interaction Diagram
```text
     [Text Input]                               [Voice Input]
    (Chatbot UI)                                (Microphone)
         |                                           |
         v                                           v
   /ws/friday (Text)                          /ws/friday (Audio)
         |                                           |
         |                                           v
         |                                   +---------------+
         |                                   |  Friday STT   |
         |                                   |  (CrispASR)   |
         |                                   +---------------+
         |                                           |
         v                                           v
   +-------------------------------------------------------+
   |                FastAPI Message Router                 |
   |              (Normalizes User Intent)                 |
   +-------------------------------------------------------+
                              |
                              v
   +-------------------------------------------------------+
   |             LangGraph AI State Machine                |
   |             (Context, Tools, Routing)                 |
   +-------------------------------------------------------+
                              |
                     +--------+--------+
                     |                 |
                     v                 v
               +-----------+     +------------+
               | Claude 3.5|     | Gemini 1.5 |
               |  (Tools)  |     | (Fallback) |
               +-----------+     +------------+
                     |                 |
                     +--------+--------+
                              |
                              v
   +-------------------------------------------------------+
   |               FastAPI Response Handler                |
   +-------------------------------------------------------+
                              |
                 +------------+------------+
                 |                         |
                 v                         v
           [Text Output]           [Voice Output]
                 |                         |
                 |                 +---------------+
                 |                 |  Friday TTS   |
                 |                 |   (Voxtral)   |
                 |                 +---------------+
                 |                         |
                 +------------+------------+
                              |
                              v
                        [Browser UI]
                  (Toast, Audio, Chat Log)
```

## Chapter 5 — LangGraph Agent

### 5.1 — LangGraph State Machine DAG
```text
                 +-------------------+
                 |                   |
                 |   intent_node     |
                 | (Classify Input)  |
                 |                   |
                 +-------------------+
                           |
                           v
                 [Conditional Edge]
               /           |          \
              /            |           \
     Tool Call         Ambiguous        Standard Query
         |                 |                  |
         v                 v                  |
 +---------------+ +---------------+          |
 |               | |               |          |
 |  tool_node    | | clarify_node  |          |
 | (Execute DB)  | |(Ask for info) |          |
 |               | |               |          |
 +---------------+ +---------------+          |
         |                 |                  |
         +-----------------+------------------+
                           |
                           v
                 +-------------------+
                 |                   |
                 | memory_write_node |
                 |  (Update State)   |
                 |                   |
                 +-------------------+
                           |
                           v
                 +-------------------+
                 |                   |
                 |   response_node   |
                 | (Format Output)   |
                 |                   |
                 +-------------------+
```

### 5.2 — Hot-Path Interceptor Decision Tree
```text
                      [Incoming Message]
                      (e.g., "Save set")
                              |
                              v
                    +-------------------+
                    |   Regex Matcher   |
                    |  (Fast Router)    |
                    +-------------------+
                              |
                  +-----------+-----------+
                 /                         \
           Match Found?                No Match?
               /                             \
              v                               v
    +-------------------+           +-------------------+
    |                   |           |                   |
    | Direct DB Call &  |           | Full LangGraph    |
    | State Update      |           | Invocation        |
    | (< 100 ms)        |           | (800 - 1200 ms)   |
    |                   |           |                   |
    +-------------------+           +-------------------+
```

## Chapter 6 — Rep-Counting Engine

### 6.1 — Keypoint Diagram
```text
           (0) Nose
            |
            |
    (6) -- (5)
   R.Sh    L.Sh
    |       |
    |       |
   (8)     (7)
 R.Elb   L.Elb
    |       |
    |       |
  (10)     (9)
 R.Wri   L.Wri
    |       |
  (12) -- (11)
  R.Hip   L.Hip
    |       |
    |       |
  (14)    (13)
 R.Knee  L.Knee
    |       |
    |       |
  (16)    (15)
 R.Ank   L.Ank

Example Triplet (Bicep Curl):
Shoulder (5) -> Elbow (7) -> Wrist (9)
```

### 6.2 — State Machine + Angle Threshold Diagram
```text
               +--------------------------------------+
               |                                      |
               |               UP State               |
               |                                      |
               +--------------------------------------+
                  ^                                |
                  |                                |
  [Angle > 160°]  |                                | [Angle < 110°]
  [Median Filter] |                                | [Median Filter]
                  |                                v
               +--------------------------------------+
               |                                      |
               |              DOWN State              |
               |           (Trigger rep++)            |
               +--------------------------------------+
```

## Chapter 7 — Concurrency, Threading, and Audio Pipeline

### 7.1 — Threading Model Diagram
```text
                      Time --->

Main Asyncio Loop | --- [Task A] --- [ws_recv] --- [ws_send] --- [Task B] --->
(FastAPI)         |        |             |              ^
                  |        |             v Queue        | Queue
AnyIO Worker      | -------|------- [DB Read/Write] ----|-------------------->
Threads           |        |                            |
                  |        v AtomicFrame                | AtomicResult
InferenceWorker   | --- [Wait] --- [ONNX Process] --- [Format] --- [Wait] --->
Thread            |
                  |        Pipe                          Pipe
STT/TTS Daemons   | --- [Wait] --- [STT/TTS Inference]-[Emit Result] -------->
(CrispASR/Voxtral)|
```

### 7.3 — Audio Pipeline Flow Diagram
```text
  [Microphone]
       |
       v
  [sounddevice] (512-sample chunks)
       |
       v
  [Silero VAD] (Voice Activity Detection)
       |
       +---> [Silence/Noise] ---> (Discard)
       |
       v (Speech Detected)
  [bytearray Buffer] (Pre-buffer + Hysteresis)
       |
       v (Pipe/Stdin)
  [CrispASR Subprocess] (Local Whisper/C++)
       |
       v (Pipe/Stdout)
  [JSON Transcript] (e.g., {"text": "start workout"})
       |
       v
  [Junk Filter] (Hallucination removal)
       |
       v
  [Intent Pipeline / Hot-Path] ---> [Barge-in Interrupt Branch]
       |
       v (Response text)
  [Voxtral Subprocess] (Local TTS Engine)
       |
       v (Audio Stream)
  [WebSocket to Browser] ---> [Audio Playback]
```
