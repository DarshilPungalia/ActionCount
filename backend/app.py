"""
app.py
------
FastAPI entry point for the ActionCount rep-counter backend.

Endpoints
---------
GET  /                          → serve frontend/index.html
GET  /exercises                 → list available exercise slugs
POST /session/start             → create a session, return session_id
POST /session/{sid}/reset       → reset rep count
POST /upload/process            → upload a video file, get back MJPEG stream
WS   /ws/stream/{session_id}    → live camera WebSocket

WebSocket binary protocol
--------------------------
Client → Server : raw JPEG bytes (one frame per message)
Server → Client : JSON  { count, angle, stage, keypoints, skipped }
"""

from __future__ import annotations

import asyncio
import os
import sys
import tempfile
import time
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Optional

import cv2
import numpy as np
import uvicorn
from fastapi import (
    FastAPI, File, Form, HTTPException,
    UploadFile, WebSocket, WebSocketDisconnect,
)
from fastapi.responses import HTMLResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

# ---------------------------------------------------------------------------
# Path setup — make backend/ importable as a package
# ---------------------------------------------------------------------------
BACKEND_DIR  = Path(__file__).parent.resolve()
FRONTEND_DIR = BACKEND_DIR.parent / "frontend"
ROOT_DIR     = BACKEND_DIR.parent

if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from PoseDetector   import PoseDetector        # noqa: E402
from session_manager import SessionManager      # noqa: E402

# ---------------------------------------------------------------------------
# App init
# ---------------------------------------------------------------------------

# Shared pose detector — loaded once at startup
_detector: Optional[PoseDetector] = None

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Load the pose detector once at startup; clean up on shutdown."""
    global _detector
    _detector = PoseDetector(mode="balanced", backend="onnxruntime", device="cpu")
    print("[ActionCount] PoseDetector initialised.")
    yield
    _detector = None
    print("[ActionCount] Shutdown complete.")

app = FastAPI(title="ActionCount", version="1.0.0", lifespan=lifespan)

# Serve frontend static files at /static
if FRONTEND_DIR.exists():
    app.mount("/static", StaticFiles(directory=str(FRONTEND_DIR)), name="static")

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
PROCESS_W    = 480    # width sent from client for inference
PROCESS_H    = 270    # height sent from client for inference (16:9)
TARGET_FPS   = 30
MIN_FRAME_MS = 1000 / TARGET_FPS           # ≈ 33.3 ms

# ---------------------------------------------------------------------------
# Pydantic models
# ---------------------------------------------------------------------------
class StartSessionRequest(BaseModel):
    exercise: str   # e.g. "squat"

class StartSessionResponse(BaseModel):
    session_id: str
    exercise:   str

# ---------------------------------------------------------------------------
# Routes — static / meta
# ---------------------------------------------------------------------------

@app.get("/", response_class=HTMLResponse)
async def root():
    """Serve the frontend index.html."""
    html_path = FRONTEND_DIR / "index.html"
    if html_path.exists():
        return HTMLResponse(content=html_path.read_text(encoding="utf-8"))
    return HTMLResponse("<h1>Frontend not found. Place files in frontend/</h1>", status_code=404)


@app.get("/exercises")
async def list_exercises():
    """Return the list of supported exercise slugs."""
    mgr = SessionManager.instance()
    return {"exercises": mgr.list_exercises()}

# ---------------------------------------------------------------------------
# Session management
# ---------------------------------------------------------------------------

@app.post("/session/start", response_model=StartSessionResponse)
async def start_session(body: StartSessionRequest):
    """Create a new rep-counter session."""
    mgr = SessionManager.instance()
    try:
        sid = mgr.create(body.exercise, _detector)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return StartSessionResponse(session_id=sid, exercise=body.exercise)


@app.post("/session/{session_id}/reset")
async def reset_session(session_id: str):
    """Reset the rep count for an existing session."""
    mgr = SessionManager.instance()
    try:
        mgr.reset(session_id)
    except KeyError:
        raise HTTPException(status_code=404, detail=f"Session {session_id!r} not found")
    return {"status": "reset", "session_id": session_id}

# ---------------------------------------------------------------------------
# Video upload endpoint
# ---------------------------------------------------------------------------

@app.post("/upload/process")
async def upload_process(
    file: UploadFile = File(...),
    exercise: str    = Form(...),
):
    """
    Accept an uploaded video file.
    Process it with the chosen exercise counter.
    Stream back an MJPEG response (displayable in <img src=…> or via fetch).
    """
    mgr = SessionManager.instance()

    # Write upload to a temp file so OpenCV can open it
    suffix = Path(file.filename).suffix or ".mp4"
    with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
        tmp.write(await file.read())
        tmp_path = tmp.name

    # Create a dedicated session for this upload
    try:
        sid = mgr.create(exercise, _detector)
    except ValueError as e:
        os.unlink(tmp_path)
        raise HTTPException(status_code=400, detail=str(e))

    async def _generate_mjpeg():
        session = mgr.get(sid)
        cap     = cv2.VideoCapture(tmp_path)

        # Read source FPS for pacing; fall back to 30 if unreadable
        src_fps   = cap.get(cv2.CAP_PROP_FPS) or 30.0
        frame_sec = 1.0 / src_fps

        try:
            while cap.isOpened():
                t0 = asyncio.get_event_loop().time()

                # cap.read() is blocking — run in thread pool
                ret, frame = await asyncio.to_thread(cap.read)
                if not ret:
                    break

                # Run full inference on every frame
                result = session.counter.process_frame(frame)

                annotated = result["frame"]

                # Encode frame as JPEG (also blocking — run in thread)
                ok, buf = await asyncio.to_thread(
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

                # Pace output to match source video FPS
                elapsed = asyncio.get_event_loop().time() - t0
                sleep_s = max(0.0, frame_sec - elapsed)
                if sleep_s > 0:
                    await asyncio.sleep(sleep_s)
        finally:
            cap.release()
            os.unlink(tmp_path)
            mgr.destroy(sid)

    return StreamingResponse(
        _generate_mjpeg(),
        media_type="multipart/x-mixed-replace; boundary=frame",
    )

# ---------------------------------------------------------------------------
# WebSocket — live camera feed
# ---------------------------------------------------------------------------

@app.websocket("/ws/stream/{session_id}")
async def ws_stream(websocket: WebSocket, session_id: str):
    """
    Binary WebSocket endpoint for live camera rep counting.

    Frame flow
    ----------
    1. Client sends a binary message: raw JPEG bytes at processing resolution.
    2. Server decodes → runs pose pipeline → returns JSON result.
    3. Client draws the skeleton overlay at display resolution.
    """
    mgr = SessionManager.instance()
    try:
        session = mgr.get(session_id)
    except KeyError:
        await websocket.close(code=4004)
        return

    await websocket.accept()
    try:
        while True:
            # Receive binary JPEG frame from client
            data = await websocket.receive_bytes()

            now_ms = time.time() * 1000
            elapsed = now_ms - (session.last_process_time * 1000 if session.last_process_time else 0)

            # FPS cap — return last result if we're running too fast
            if session.last_process_time and elapsed < MIN_FRAME_MS:
                await websocket.send_json({**session.last_result, "skipped": True})
                continue

            session.last_process_time = time.time()

            # Decode JPEG → BGR numpy array
            frame = _decode_jpeg(data)
            if frame is None:
                await websocket.send_json({"error": "invalid frame"})
                continue

            # Run full inference on every frame
            det = session.counter.detector
            det.findPose(frame)
            kps = det.findPosition(frame)

            if kps is not None:
                result = session.counter._compute(frame, kps)
            else:
                result = session.counter._make_result(frame, angle=None)
                kps    = None

            # Build JSON response (no annotated frame on the hot path —
            # client draws its own overlay using the returned keypoints)
            kps_list = _kps_to_list(kps)
            payload  = {
                "count":     result["count"],
                "angle":     round(result["angle"], 1) if result["angle"] is not None else None,
                "stage":     result["stage"],
                "keypoints": kps_list,
                "skipped":   False,
            }
            session.last_result = payload
            await websocket.send_json(payload)

    except WebSocketDisconnect:
        pass
    finally:
        mgr.destroy(session_id)

# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

def _decode_jpeg(data: bytes) -> Optional[np.ndarray]:
    """Decode a JPEG byte buffer to a BGR numpy array."""
    arr = np.frombuffer(data, dtype=np.uint8)
    if arr.size == 0:
        return None
    frame = cv2.imdecode(arr, cv2.IMREAD_COLOR)
    return frame  # may be None if decode fails


def _kps_to_list(kps: Optional[np.ndarray]) -> Optional[list]:
    """Convert (17,2) numpy array to JSON-serialisable list of [x, y] pairs."""
    if kps is None:
        return None
    return [[round(float(x), 2), round(float(y), 2)] for x, y in kps]


# ---------------------------------------------------------------------------
# Run
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    uvicorn.run("app:app", host="0.0.0.0", port=8000, reload=True)
