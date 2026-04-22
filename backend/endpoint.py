"""
endpoint.py
-----------
FastAPI entry point for the ActionCount rep-counter backend.

Endpoints
---------
GET  /                          → serve frontend/index.html
GET  /exercises                 → list available exercise slugs
POST /session/start             → create a session, return session_id
GET  /session/{sid}/state       → poll current counter state (for upload HUD)
POST /session/{sid}/reset       → reset rep count
POST /upload/process            → upload a video file, get back MJPEG stream
WS   /ws/stream/{session_id}    → live camera WebSocket

WebSocket binary protocol
--------------------------
Client → Server : raw JPEG bytes (one frame per message)
Server → Client : JSON  { counter, feedback, progress, correct_form, keypoints, skipped }
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

for p in (str(BACKEND_DIR), str(ROOT_DIR)):
    if p not in sys.path:
        sys.path.insert(0, p)

from backend.session_manager import SessionManager  # noqa: E402

# ---------------------------------------------------------------------------
# App init
# ---------------------------------------------------------------------------

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Warm up the session manager on startup."""
    mgr = SessionManager.instance()
    print("[ActionCount] SessionManager ready.")
    yield
    print("[ActionCount] Shutdown complete.")

app = FastAPI(title="ActionCount", version="2.0.0", lifespan=lifespan)

# Serve frontend static files at /static
if FRONTEND_DIR.exists():
    app.mount("/static", StaticFiles(directory=str(FRONTEND_DIR)), name="static")

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
TARGET_FPS   = 30
MIN_FRAME_MS = 1000 / TARGET_FPS   # ≈ 33.3 ms

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
        sid = mgr.create(body.exercise)   # BaseCounter owns its own PoseDetectorModified
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return StartSessionResponse(session_id=sid, exercise=body.exercise)


@app.get("/session/{session_id}/state")
async def get_session_state(session_id: str):
    """Return the current counter state for a session (used for HUD polling)."""
    mgr = SessionManager.instance()
    try:
        session = mgr.get(session_id)
    except KeyError:
        raise HTTPException(status_code=404, detail=f"Session {session_id!r} not found")
    return session.last_result


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
        session = mgr.get(sid)
        cap     = cv2.VideoCapture(tmp_path)

        src_fps   = cap.get(cv2.CAP_PROP_FPS) or 30.0
        frame_sec = 1.0 / src_fps

        try:
            while cap.isOpened():
                t0 = asyncio.get_event_loop().time()

                ret, frame = await asyncio.to_thread(cap.read)
                if not ret:
                    break

                # process_frame handles pose detection + overlay drawing
                result = session.counter.process_frame(frame)

                annotated = result["frame"]

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
    2. Server decodes → runs process_frame (pose + counter) → returns JSON.
    3. Client renders the stats panel and draws its own skeleton overlay
       using the returned keypoints array.

    JSON response keys
    ------------------
    counter      : int   — total rep count this session
    feedback     : str   — "Up" | "Down" | "Fix Form" | "Get in Position"
    progress     : float — 0–100 exercise progress percentage
    correct_form : bool  — True once valid starting form is detected
    keypoints    : list  — [[x, y], …] for 17 COCO keypoints (processing res)
                           or null if no person detected
    skipped      : bool  — True when frame was dropped for FPS throttling
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
            data = await websocket.receive_bytes()

            now_ms  = time.time() * 1000
            elapsed = now_ms - (session.last_process_time * 1000 if session.last_process_time else 0)

            # FPS cap — return cached result if running too fast
            if session.last_process_time and elapsed < MIN_FRAME_MS:
                await websocket.send_json({**session.last_result, "skipped": True})
                continue

            session.last_process_time = time.time()

            # Decode JPEG → BGR numpy array
            frame = _decode_jpeg(data)
            if frame is None:
                await websocket.send_json({"error": "invalid frame"})
                continue

            # Full inference via process_frame (pose + counter + overlays)
            result = session.counter.process_frame(frame)

            # Extract keypoints from the internal detector for client-side overlay
            kps_list = None
            kps_raw  = session.counter.pose_detector._keypoints
            if kps_raw is not None:
                kps_list = _kps_to_list(kps_raw)

            payload = {
                "counter":      result["counter"],
                "feedback":     result["feedback"],
                "progress":     round(result["progress"], 1),
                "correct_form": result["correct_form"],
                "keypoints":    kps_list,
                "skipped":      False,
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
    return cv2.imdecode(arr, cv2.IMREAD_COLOR)   # may be None if decode fails


def _kps_to_list(kps: np.ndarray) -> list:
    """Convert (17, 2) numpy array to JSON-serialisable list of [x, y] pairs."""
    return [[round(float(x), 2), round(float(y), 2)] for x, y in kps]


# ---------------------------------------------------------------------------
# Run
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    uvicorn.run("endpoint:app", host="0.0.0.0", port=8000, reload=True)
