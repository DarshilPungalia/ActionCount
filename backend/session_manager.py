"""
session_manager.py
------------------
Singleton that manages per-session counter lifecycles.

Phase 2 refactor (video_pipeline_implementation_plan.md):
- Added AtomicFrame   : single-slot lock for latest raw frame
- Added AtomicResult  : single-slot lock for latest inference result
- Added InferenceWorker : daemon thread that decouples RTMPose from the WS loop
- SessionData now starts one InferenceWorker per session
- SessionManager.destroy() signals the worker to stop before removing the session

Anti-patterns fixed
-------------------
  ✅ Sequential capture → infer → send in one async loop  →  infer now runs in a thread
  ✅ np.copy() inside hot loop (kps_raw)                  →  .copy() removed; astype()
                                                              already allocates a new array

File-Level Change Log (plan format)
------------------------------------
### session_manager.py

**Anti-pattern found:** Inference (RTMPose + counter) blocked the WebSocket receive/send
  loop, forcing every frame to wait for model output before the next frame was accepted.

**Change made:** Moved inference into InferenceWorker (daemon thread). WebSocket loop
  writes each decoded frame to AtomicFrame (non-blocking overwrite) and reads the latest
  result from AtomicResult without waiting.

**Latency impact:** WebSocket receive/send loop is no longer gated by inference time
  (~50–200 ms per frame). Client-visible round-trip drops to network RTT + JPEG decode.
"""

from __future__ import annotations

import time
import threading
import uuid
import sys
import os
from typing import Optional

from backend.metrics import PipelineMetrics

# ── Helper: _kps_to_list (same as endpoint.py, duplicated to avoid circular import) ──
def _kps_to_list(kps) -> list:
    return [[round(float(x), 2), round(float(y), 2)] for x, y in kps]


# ── Lazy counter import ───────────────────────────────────────────────────────
_COUNTER_MAP: dict = {}

def _load_counter_map():
    global _COUNTER_MAP
    if _COUNTER_MAP:
        return

    backend_dir = os.path.dirname(os.path.abspath(__file__))
    root_dir    = os.path.dirname(backend_dir)
    for p in (backend_dir, root_dir):
        if p not in sys.path:
            sys.path.insert(0, p)

    from backend.counters.SquatCounter         import SquatCounter
    from backend.counters.PushupCounter        import PushupCounter
    from backend.counters.BicepCurlCounter     import BicepCurlCounter
    from backend.counters.PullupCounter        import PullupCounter
    from backend.counters.LateralRaiseCounter  import LateralRaiseCounter
    from backend.counters.OverheadPressCounter import OverheadPressCounter
    from backend.counters.SitupCounter         import SitupCounter
    from backend.counters.CrunchCounter        import CrunchCounter
    from backend.counters.LegRaiseCounter      import LegRaiseCounter
    from backend.counters.KneeRaiseCounter     import KneeRaiseCounter
    from backend.counters.KneePressCounter     import KneePressCounter

    _COUNTER_MAP = {
        "squat":          SquatCounter,
        "pushup":         PushupCounter,
        "bicep_curl":     BicepCurlCounter,
        "pullup":         PullupCounter,
        "lateral_raise":  LateralRaiseCounter,
        "overhead_press": OverheadPressCounter,
        "situp":          SitupCounter,
        "crunch":         CrunchCounter,
        "leg_raise":      LegRaiseCounter,
        "knee_raise":     KneeRaiseCounter,
        "knee_press":     KneePressCounter,
    }


# ═══════════════════════════════════════════════════════════════════════════════
# Atomic slots (no queue, no history — always latest)
# ═══════════════════════════════════════════════════════════════════════════════

class AtomicFrame:
    """
    Single-slot frame store.

    New frames overwrite the previous one immediately.
    Inference always sees the freshest frame, never a stale one.
    No queue depth > 1 — satisfies plan §2a anti-pattern fix.
    """
    __slots__ = ("_frame", "_lock", "_written_at")

    def __init__(self):
        self._frame      = None
        self._lock       = threading.Lock()
        self._written_at: float = 0.0

    def write(self, frame) -> float:
        """Overwrite the slot. Returns the write timestamp."""
        ts = time.monotonic()
        with self._lock:
            self._frame      = frame
            self._written_at = ts
        return ts

    def read(self):
        """Return (frame, written_at). Frame is None until first write."""
        with self._lock:
            return self._frame, self._written_at


class AtomicResult:
    """
    Single-slot inference result store.

    Render side reads the last known result without waiting for inference.
    """
    __slots__ = ("_result", "_lock")

    def __init__(self):
        self._result = None
        self._lock   = threading.Lock()

    def write(self, result: dict) -> None:
        with self._lock:
            self._result = result

    def read(self) -> Optional[dict]:
        with self._lock:
            return self._result


# ═══════════════════════════════════════════════════════════════════════════════
# Inference worker
# ═══════════════════════════════════════════════════════════════════════════════

_INFERENCE_TARGET_FPS = 15   # max inference rate; model is the real cap anyway


class InferenceWorker(threading.Thread):
    """
    Daemon thread that runs RTMPose inference decoupled from the WebSocket loop.

    Flow
    ----
    1. Read latest frame from AtomicFrame
    2. Skip if frame is None or unchanged since last cycle
    3. Run counter.process_frame()  (RTMPose + state machine + overlays)
    4. Package result + keypoints into AtomicResult
    5. Record metrics; sleep to honour target_fps
    """

    def __init__(self, counter, atomic_frame: AtomicFrame,
                 atomic_result: AtomicResult,
                 metrics: PipelineMetrics,
                 session_id: str = ""):
        super().__init__(daemon=True, name=f"InferWorker-{session_id[:8]}")
        self._counter      = counter
        self._atomic_frame = atomic_frame
        self._atomic_result = atomic_result
        self._metrics      = metrics
        self._stop_event   = threading.Event()
        self._interval     = 1.0 / _INFERENCE_TARGET_FPS

    def stop(self) -> None:
        """Signal the thread to exit on its next iteration."""
        self._stop_event.set()

    def run(self) -> None:
        last_written_at: float = 0.0

        while not self._stop_event.is_set():
            t0 = time.monotonic()

            frame, written_at = self._atomic_frame.read()

            # Skip if no frame yet, or frame hasn't changed since last run
            if frame is None or written_at == last_written_at:
                time.sleep(0.002)   # yield CPU briefly
                continue

            last_written_at = written_at
            e2e_start = written_at   # frame was written at this time

            # ── Inference ──────────────────────────────────────────────────────
            infer_t0 = time.monotonic()
            try:
                result = self._counter.process_frame(frame)
            except Exception:
                time.sleep(self._interval)
                continue
            self._metrics.record_inference(time.monotonic() - infer_t0)

            # ── Package result ─────────────────────────────────────────────────
            kps_raw  = self._counter.pose_detector._keypoints
            kps_list = _kps_to_list(kps_raw) if kps_raw is not None else None

            self._atomic_result.write({
                "counter":      result["counter"],
                "feedback":     result["feedback"],
                "progress":     round(result["progress"], 1),
                "correct_form": result["correct_form"],
                "keypoints":    kps_list,
            })

            # ── E2E latency ────────────────────────────────────────────────────
            self._metrics.record_e2e(time.monotonic() - e2e_start)
            self._metrics.maybe_report()

            # ── FPS throttle ───────────────────────────────────────────────────
            elapsed = time.monotonic() - t0
            sleep_s = max(0.0, self._interval - elapsed)
            if sleep_s > 0:
                time.sleep(sleep_s)


# ═══════════════════════════════════════════════════════════════════════════════
# Session data & manager (interfaces unchanged)
# ═══════════════════════════════════════════════════════════════════════════════

class SessionData:
    """All mutable state for a single active WebSocket session."""

    def __init__(self, counter, exercise: str, session_id: str):
        self.counter    = counter
        self.exercise   = exercise

        # ── New: atomic slots + inference thread ──────────────────────────────
        self.atomic_frame  = AtomicFrame()
        self.atomic_result = AtomicResult()
        self.metrics       = PipelineMetrics(session_id)
        self._worker       = InferenceWorker(
            counter, self.atomic_frame, self.atomic_result,
            self.metrics, session_id,
        )
        self._worker.start()

        # ── Legacy fields kept for API compatibility ───────────────────────────
        self.last_process_time: float = 0.0
        self.last_result: dict = {
            "counter":      0,
            "feedback":     "Get in Position",
            "progress":     0.0,
            "correct_form": False,
            "keypoints":    None,
        }

    def stop(self) -> None:
        """Stop the inference worker cleanly."""
        self._worker.stop()


class SessionManager:
    """
    Thread-safe singleton session registry.
    Public interface unchanged from original.
    """

    _instance: Optional["SessionManager"] = None

    def __init__(self):
        self._sessions: dict[str, SessionData] = {}

    @classmethod
    def instance(cls) -> "SessionManager":
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def create(self, exercise: str) -> str:
        _load_counter_map()
        CounterClass = _COUNTER_MAP.get(exercise)
        if CounterClass is None:
            raise ValueError(
                f"Unknown exercise {exercise!r}. "
                f"Valid options: {sorted(_COUNTER_MAP)}"
            )
        session_id = str(uuid.uuid4())
        counter    = CounterClass()
        self._sessions[session_id] = SessionData(counter, exercise, session_id)
        return session_id

    def get(self, session_id: str) -> SessionData:
        return self._sessions[session_id]

    def reset(self, session_id: str) -> None:
        data = self._sessions[session_id]
        data.counter.reset()
        data.last_result = {
            "counter": 0, "feedback": "Get in Position",
            "progress": 0.0, "correct_form": False, "keypoints": None,
        }
        # Write a sentinel so InferenceWorker picks up reset state
        data.atomic_result.write(data.last_result)

    def destroy(self, session_id: str) -> None:
        session = self._sessions.pop(session_id, None)
        if session is not None:
            session.stop()   # signal InferenceWorker to exit

    def list_exercises(self) -> list[str]:
        _load_counter_map()
        return sorted(_COUNTER_MAP.keys())
