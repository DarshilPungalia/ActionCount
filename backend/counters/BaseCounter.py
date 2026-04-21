"""
BaseCounter.py
--------------
Abstract base class that owns all rep-counting logic.
Subclasses implement only _compute() with exercise-specific config.
"""

import time
from abc import ABC, abstractmethod
from collections import deque

import cv2
import numpy as np

from PoseDetector import PoseDetector


class BaseCounter(ABC):
    """
    Abstract rep counter.

    Counting modes
    --------------
    "bilateral" — both limbs move together; average angle drives the state
                  machine and a single counter increments per rep.
    "per_limb"  — each leg/arm counted independently; counter increments
                  each time either limb completes a rep.
    """

    def __init__(self, pose_detector: PoseDetector, smoothing_window: int = 5):
        self.detector         = pose_detector
        self.counter          = 0
        self.stage            = None                              # bilateral stage
        self.leg_stages       = {"left": None, "right": None}    # per-limb stages
        self.last_count_time  = 0.0
        self.MIN_REP_TIME     = 0.5                               # seconds debounce
        self._angle_history   = deque(maxlen=smoothing_window)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def reset(self) -> None:
        """Reset counter and all internal state."""
        self.counter         = 0
        self.stage           = None
        self.leg_stages      = {"left": None, "right": None}
        self._angle_history.clear()
        self.last_count_time = 0.0

    def process_frame(self, frame: np.ndarray) -> dict:
        """
        Main entry point — call once per video frame.

        Returns a result dict (see _make_result for schema).
        """
        self.detector.findPose(frame)
        kps = self.detector.findPosition(frame)
        if kps is None:
            return self._make_result(frame, angle=None)
        return self._compute(frame, kps)

    # ------------------------------------------------------------------
    # Smoothing
    # ------------------------------------------------------------------

    def _smooth_angle(self, angle: "float | None") -> "float | None":
        """
        Median-±2σ filter over the rolling angle history.

        With fewer than 3 values the raw angle is returned as-is.
        """
        if angle is None:
            return None
        self._angle_history.append(angle)
        if len(self._angle_history) < 3:
            return angle

        arr    = np.array(self._angle_history, dtype=float)
        median = np.median(arr)
        std    = np.std(arr)
        mask   = np.abs(arr - median) <= 2 * std
        kept   = arr[mask]
        return float(np.mean(kept)) if len(kept) > 0 else angle

    # ------------------------------------------------------------------
    # Debounce helpers
    # ------------------------------------------------------------------

    def _active_per_limb(self) -> bool:
        """True when the cooldown period has elapsed (per-limb gate)."""
        return time.time() - self.last_count_time >= self.MIN_REP_TIME

    def _debounced_increment(self) -> bool:
        """
        Increment counter only when cooldown has elapsed.

        Returns True if the counter was incremented, False otherwise.
        """
        if time.time() - self.last_count_time < self.MIN_REP_TIME:
            return False
        self.counter        += 1
        self.last_count_time = time.time()
        return True

    # ------------------------------------------------------------------
    # Stage machines
    # ------------------------------------------------------------------

    def _tick_bilateral(self, smoothed: float, up_angle: float, down_angle: float) -> None:
        """
        Two-stage (up / down) state machine for bilateral exercises.

        Works for both normal  (up_angle > down_angle, e.g. squats)
        and inverted (up_angle < down_angle, e.g. bicep curls) because
        the UP_ANGLE / DOWN_ANGLE configs already encode the direction.
        """
        if smoothed > up_angle:
            self.stage = "up"
        elif smoothed < down_angle and self.stage == "up":
            if self._debounced_increment():
                self.stage = "down"

    def _tick_per_limb(self, left_angle: float, right_angle: float,
                       up_angle: float, down_angle: float) -> None:
        """Drive per-limb state machines for both sides."""
        self._tick_one("left",  left_angle,  up_angle, down_angle)
        self._tick_one("right", right_angle, up_angle, down_angle)

    def _tick_one(self, side: str, angle: float, up_angle: float, down_angle: float) -> None:
        """Single-side state machine used by _tick_per_limb."""
        if angle > up_angle:
            self.leg_stages[side] = "up"
        elif angle < down_angle and self.leg_stages[side] == "up" and self._active_per_limb():
            self.counter         += 1
            self.last_count_time  = time.time()
            self.leg_stages[side] = "down"

    # ------------------------------------------------------------------
    # Unified update dispatcher
    # ------------------------------------------------------------------

    def _update_count(self, left_angle: float, right_angle: float,
                      up_angle: float, down_angle: float, mode: str) -> "float | None":
        """
        Route to the correct counting strategy and return the display angle.

        Parameters
        ----------
        mode : "bilateral" | "per_limb"
        """
        if mode == "bilateral":
            avg      = (left_angle + right_angle) / 2.0
            smoothed = self._smooth_angle(avg)
            if smoothed is not None:
                self._tick_bilateral(smoothed, up_angle, down_angle)
            return smoothed

        if mode == "per_limb":
            self._tick_per_limb(left_angle, right_angle, up_angle, down_angle)
            return (left_angle + right_angle) / 2.0

        raise ValueError(f"Unknown mode: {mode!r}. Expected 'bilateral' or 'per_limb'.")

    # ------------------------------------------------------------------
    # Rendering helpers
    # ------------------------------------------------------------------

    def _draw_overlays(self, frame: np.ndarray, angle: "float | None") -> np.ndarray:
        """Render HUD (rep count + current angle) onto *frame*."""
        # Semi-transparent HUD background
        overlay = frame.copy()
        cv2.rectangle(overlay, (0, 0), (240, 80), (0, 0, 0), cv2.FILLED)
        cv2.addWeighted(overlay, 0.55, frame, 0.45, 0, frame)

        font       = cv2.FONT_HERSHEY_SIMPLEX
        font_scale = 0.8
        thickness  = 2
        color      = (255, 255, 255)

        cv2.putText(frame, f"Reps  : {self.counter}", (10, 30),
                    font, font_scale, color, thickness, cv2.LINE_AA)
        if angle is not None:
            cv2.putText(frame, f"Angle : {int(angle)}", (10, 65),
                        font, font_scale, color, thickness, cv2.LINE_AA)
        return frame

    def _make_result(self, frame: np.ndarray, angle: "float | None") -> dict:
        """Build the standard result dict returned by process_frame."""
        return {
            "frame": frame,
            "count": self.counter,
            "angle": angle,
            "stage": self.stage,
        }

    # ------------------------------------------------------------------
    # Abstract method — subclasses must implement
    # ------------------------------------------------------------------

    @abstractmethod
    def _compute(self, frame: np.ndarray, kps: np.ndarray) -> dict:
        """
        Compute angles, update count, draw overlays, return _make_result().

        Parameters
        ----------
        frame : raw BGR frame (original resolution)
        kps   : (17, 2) COCO-17 keypoint array from PoseDetector.findPosition()
        """


