"""
session_manager.py
------------------
Singleton that manages per-session counter lifecycles.
Each session owns its own counter object so WebSocket handlers remain stateless.
"""

import uuid
import time
import sys
import os
from typing import Optional

# ---------------------------------------------------------------------------
# Lazy counter import — maps exercise slug → counter class
# ---------------------------------------------------------------------------
_COUNTER_MAP: dict = {}

def _load_counter_map():
    """Import all counter classes once and populate _COUNTER_MAP."""
    global _COUNTER_MAP
    if _COUNTER_MAP:
        return

    # Make sure the backend package root is on sys.path
    backend_dir = os.path.dirname(os.path.abspath(__file__))
    if backend_dir not in sys.path:
        sys.path.insert(0, backend_dir)

    from counters.SquatCounter        import SquatCounter
    from counters.PushupCounter       import PushupCounter
    from counters.BicepCurlCounter    import BicepCurlCounter
    from counters.PullupCounter       import PullupCounter
    from counters.LateralRaiseCounter import LateralRaiseCounter
    from counters.OverheadPressCounter import OverheadPressCounter
    from counters.SitupCounter        import SitupCounter
    from counters.CrunchCounter       import CrunchCounter
    from counters.LegRaiseCounter     import LegRaiseCounter
    from counters.KneeRaiseCounter    import KneeRaiseCounter
    from counters.KneePressCounter    import KneePressCounter

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


class SessionData:
    """All mutable state for a single active session."""

    def __init__(self, counter, exercise: str):
        self.counter    = counter
        self.exercise   = exercise

        # 30-FPS debounce
        self.last_process_time: float = 0.0

        # Last known result (returned on skipped frames)
        self.last_result: dict = {"count": 0, "angle": None, "stage": None, "keypoints": None}


class SessionManager:
    """
    Thread-safe (asyncio-safe) singleton session registry.

    Usage
    -----
    mgr = SessionManager.instance()
    sid = mgr.create("squat", detector)
    data = mgr.get(sid)
    mgr.reset(sid)
    mgr.destroy(sid)
    """

    _instance: Optional["SessionManager"] = None

    def __init__(self):
        self._sessions: dict[str, SessionData] = {}

    @classmethod
    def instance(cls) -> "SessionManager":
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    # ------------------------------------------------------------------

    def create(self, exercise: str, detector) -> str:
        """
        Create a new session for *exercise* using *detector*.

        Returns the new session_id (UUID string).
        Raises ValueError for unknown exercise slugs.
        """
        _load_counter_map()
        CounterClass = _COUNTER_MAP.get(exercise)
        if CounterClass is None:
            raise ValueError(
                f"Unknown exercise {exercise!r}. "
                f"Valid options: {sorted(_COUNTER_MAP)}"
            )
        counter   = CounterClass(pose_detector=detector)
        session_id = str(uuid.uuid4())
        self._sessions[session_id] = SessionData(counter, exercise)
        return session_id

    def get(self, session_id: str) -> SessionData:
        """Return SessionData or raise KeyError."""
        return self._sessions[session_id]

    def reset(self, session_id: str) -> None:
        """Reset the counter for *session_id*."""
        data = self._sessions[session_id]
        data.counter.reset()
        data.last_result = {"count": 0, "angle": None, "stage": None, "keypoints": None}

    def destroy(self, session_id: str) -> None:
        """Remove session (call on WebSocket disconnect)."""
        self._sessions.pop(session_id, None)

    def list_exercises(self) -> list[str]:
        _load_counter_map()
        return sorted(_COUNTER_MAP.keys())
