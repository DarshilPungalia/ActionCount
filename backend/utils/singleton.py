import threading
import time
from typing import Optional

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
