"""
metrics.py
----------
Non-blocking pipeline latency instrumentation.

Tracks per-phase timings via deques and writes a summary to
logs/pipeline.log every REPORT_INTERVAL_S seconds.

Usage
-----
    from backend.metrics import PipelineMetrics
    metrics = PipelineMetrics()

    t0 = time.monotonic()
    # ... inference ...
    metrics.record_inference(time.monotonic() - t0)

    # Call from a timer or end of InferenceWorker loop:
    metrics.maybe_report()
"""

from __future__ import annotations

import logging
import os
import time
from collections import deque
from pathlib import Path

# ── Log file setup ─────────────────────────────────────────────────────────────
LOGS_DIR = Path(__file__).parent.parent / "logs"
LOGS_DIR.mkdir(exist_ok=True)

_file_handler = logging.FileHandler(LOGS_DIR / "pipeline.log", encoding="utf-8")
_file_handler.setFormatter(logging.Formatter("%(asctime)s  %(message)s",
                                              datefmt="%Y-%m-%d %H:%M:%S"))

_logger = logging.getLogger("actioncount.pipeline")
_logger.setLevel(logging.INFO)
_logger.addHandler(_file_handler)
_logger.propagate = False  # don't bubble up to root logger / Uvicorn

REPORT_INTERVAL_S: float = 5.0
WINDOW: int = 60           # rolling window of frames


class PipelineMetrics:
    """
    Lightweight, non-blocking latency tracker.

    Records
    -------
    - inference_ms  : time inside counter.process_frame() (RTMPose + counter logic)
    - capture_ms    : time to decode the incoming JPEG in the WebSocket handler
    - e2e_ms        : elapsed from frame written to AtomicFrame → result written to AtomicResult

    Thread-safety
    -------------
    Each InferenceWorker owns one PipelineMetrics instance — no shared state,
    no locks needed.
    """

    def __init__(self, session_id: str = ""):
        self.session_id      = session_id
        self.inference_times: deque[float] = deque(maxlen=WINDOW)
        self.capture_times:   deque[float] = deque(maxlen=WINDOW)
        self.e2e_times:       deque[float] = deque(maxlen=WINDOW)
        self._last_report     = time.monotonic()
        self._frame_count     = 0

    # ── Record helpers ─────────────────────────────────────────────────────────

    def record_inference(self, elapsed_s: float) -> None:
        self.inference_times.append(elapsed_s)
        self._frame_count += 1

    def record_capture(self, elapsed_s: float) -> None:
        self.capture_times.append(elapsed_s)

    def record_e2e(self, elapsed_s: float) -> None:
        self.e2e_times.append(elapsed_s)

    # ── Reporting ──────────────────────────────────────────────────────────────

    def maybe_report(self) -> None:
        """Call at the end of each inference cycle. Logs only every 5 s."""
        now = time.monotonic()
        if now - self._last_report < REPORT_INTERVAL_S:
            return
        self._last_report = now
        self._write_report()

    def _write_report(self) -> None:
        def avg_ms(buf: deque) -> float:
            return (sum(buf) / len(buf) * 1000) if buf else 0.0

        infer_ms  = avg_ms(self.inference_times)
        cap_ms    = avg_ms(self.capture_times)
        e2e_ms    = avg_ms(self.e2e_times)
        infer_fps = (1000 / infer_ms) if infer_ms > 0 else 0.0

        tag = f"[{self.session_id[:8]}]" if self.session_id else "[global]"
        _logger.info(
            "%s  frames=%d | inference=%.1fms (%.1f fps) | "
            "capture=%.1fms | e2e=%.1fms",
            tag, self._frame_count, infer_ms, infer_fps, cap_ms, e2e_ms,
        )
