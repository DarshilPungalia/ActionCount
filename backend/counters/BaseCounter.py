import time
import cv2
import numpy as np
from abc import ABC, abstractmethod
from collections import deque
from backend.PoseDetector import PoseDetectorModified


class BaseCounter(ABC):
    """
    Abstract base class for all exercise counters.

    The base class handles:
      - MediaPipe pose detection and landmark extraction
      - Stage-machine rep counting (up/down transitions with debounce)
      - Angle smoothing (median filter + outlier rejection + 5-frame mean)
      - CV2 overlay drawing (progress bar, rep counter, feedback badge)
      - Thread-safe result packaging for Streamlit / WebRTC consumers

    Subclasses implement only `_compute()`, returning:
      (progress_pct: float, feedback: str, form_ok: bool)
    """

    DEBOUNCE_SECONDS: float = 0.5

    def __init__(self):
        self.pose_detector    = PoseDetectorModified(mode='lightweight')
        self.counter          = 0.0
        self.correct_form     = False
        self.exercise_feedback = "Get in Position"
        self.progress_pct     = 0.0

        # Stage-machine state
        self.stage       = None         # bilateral  ("up" | "down" | None)
        self.left_stage  = None         # per-limb left
        self.right_stage = None         # per-limb right

        # Debounce
        self._last_count_time: float = 0.0

        # Smoothing deques  {side: deque([raw_angles], maxlen=5)}
        self._angle_deques: dict = {
            "left":  deque(maxlen=5),
            "right": deque(maxlen=5),
        }

        # Legacy attribute kept for backward-compat (not used in new counters)
        self.movement_dir = 0

    def reset(self):
        """Reset all counter state back to defaults."""
        self.counter           = 0.0
        self.movement_dir      = 0
        self.correct_form      = False
        self.exercise_feedback = "Get in Position"
        self.progress_pct      = 0.0
        self.stage             = None
        self.left_stage        = None
        self.right_stage       = None
        self._last_count_time  = 0.0
        self._angle_deques     = {"left": deque(maxlen=5), "right": deque(maxlen=5)}

    def process_frame(self, frame: np.ndarray) -> dict:
        """
        Process a single BGR video frame and return annotated results.

        Args:
            frame: BGR image as a numpy array (from OpenCV or av.VideoFrame).

        Returns:
            dict with keys:
                frame       — annotated BGR numpy array
                counter     — integer rep count
                feedback    — "Up" | "Down" | "Fix Form" | "Get in Position"
                progress    — float 0-100
                correct_form — bool
        """
        if frame is None:
            return self._make_result(frame)

        frame = self.pose_detector.findPose(frame, draw=True)
        landmarks_list = self.pose_detector.findPosition(frame, draw=False)

        if landmarks_list:
            try:
                progress_pct, feedback, form_ok = self._compute(frame, landmarks_list)
                self.progress_pct      = float(np.clip(progress_pct, 0.0, 100.0))
                self.exercise_feedback = feedback

                if form_ok:
                    self.correct_form = True

                self._draw_overlays(frame, self.progress_pct)

            except (IndexError, ValueError, ZeroDivisionError, TypeError):
                # Landmarks partially out of frame or None angle
                pass

        return self._make_result(frame)

    def _smooth_angle(self, side: str, raw_angle) -> float:
        """
        Smooth a raw joint angle using (plan §3):
          1. Append new angle to the deque
          2. Compute median and std of the deque
          3. Remove values more than 2 std-devs from the median
          4. Return mean of remaining values

        Special cases:
          - raw_angle is None  → return None so the caller can skip the frame
          - deque has < 3 values → return the raw_angle unchanged (not enough
            history to filter reliably)

        Args:
            side:      "left" or "right"
            raw_angle: freshly computed angle in degrees, or None

        Returns:
            Smoothed angle in degrees, or None if raw_angle is None.
        """
        if raw_angle is None:
            return None

        dq = self._angle_deques[side]
        dq.append(float(raw_angle))

        # Not enough history — return raw value unchanged (plan §3)
        if len(dq) < 3:
            return float(raw_angle)

        vals = np.array(list(dq), dtype=np.float64)
        median = np.median(vals)
        std    = np.std(vals)
        if std > 0:
            filtered = vals[np.abs(vals - median) <= 2 * std]
        else:
            filtered = vals

        return float(np.mean(filtered)) if len(filtered) > 0 else float(median)

    def _avg_angles(self, left_raw, right_raw):
        """
        Smooth both sides and return their bilateral average.
        Returns None if either side is uncomputable (low-confidence / occluded).
        Plan §6: callers should early-return and skip the frame when None.
        """
        left  = self._smooth_angle("left",  left_raw)
        right = self._smooth_angle("right", right_raw)
        if left is None or right is None:
            return None
        return (left + right) / 2.0

    def _active_per_limb(self, left_raw, right_raw):
        """
        Smooth both sides for per-limb counters.
        Returns (left_angle, right_angle) where either may be None.
        The tick helpers already handle None silently, so callers only need
        to guard the progress-bar / active_angle calculation.
        """
        return (
            self._smooth_angle("left",  left_raw),
            self._smooth_angle("right", right_raw),
        )

    def _debounced_increment(self) -> bool:
        """
        Increment self.counter by 1 only if ≥ DEBOUNCE_SECONDS have elapsed
        since the last count.  Returns True if the count was incremented.
        """
        now = time.monotonic()
        if now - self._last_count_time >= self.DEBOUNCE_SECONDS:
            self.counter         += 1
            self._last_count_time = now
            return True
        return False

    def _tick_bilateral(
        self,
        angle,
        up_angle: float,
        down_angle: float,
        inverted: bool = False,
    ) -> bool:
        """
        Advance the bilateral stage machine and count reps.

        Normal  (inverted=False):
            stage='up'   when angle > up_angle
            stage='down' (+ count) when angle < down_angle AND stage was 'up'

        Inverted (inverted=True):
            stage='up'   when angle < up_angle   (e.g. fully curled)
            stage='down' (+ count) when angle > down_angle AND stage was 'up'

        Returns True if a rep was just counted, False otherwise.
        Returns False immediately if angle is None (low-confidence keypoint).
        """
        if angle is None:
            return False

        if not inverted:
            if angle > up_angle:
                self.stage = "up"
            elif angle < down_angle and self.stage == "up":
                self.stage = "down"
                return self._debounced_increment()
        else:
            if angle < up_angle:
                self.stage = "up"
            elif angle > down_angle and self.stage == "up":
                self.stage = "down"
                return self._debounced_increment()
        return False

    def _tick_per_limb(
        self,
        left_angle,
        right_angle,
        up_angle: float,
        down_angle: float,
        inverted: bool = False,
    ) -> int:
        """
        Advance independent left & right stage machines.
        Each completed cycle increments the shared counter.
        None angles are silently skipped (low-confidence keypoint).

        Returns the number of reps counted this frame (0, 1, or 2).
        """
        counted = 0

        def _tick_one(angle, current_stage):
            nonlocal counted
            if angle is None:
                return current_stage   # skip — bad keypoint
            if not inverted:
                if angle > up_angle:
                    return "up"
                elif angle < down_angle and current_stage == "up":
                    if self._debounced_increment():
                        counted += 1
                    return "down"
            else:
                if angle < up_angle:
                    return "up"
                elif angle > down_angle and current_stage == "up":
                    if self._debounced_increment():
                        counted += 1
                    return "down"
            return current_stage

        self.left_stage  = _tick_one(left_angle,  self.left_stage)
        self.right_stage = _tick_one(right_angle, self.right_stage)
        return counted

    def _update_count(self, progress_pct: float):
        """
        Legacy generic half-rep counting.
        A full rep = progress crossing 98% then dropping below 2%.
        Not used by the new state-machine counters.
        """
        if progress_pct >= 98 and self.movement_dir == 0:
            self.counter      += 0.5
            self.movement_dir  = 1
        elif progress_pct <= 2 and self.movement_dir == 1:
            self.counter      += 0.5
            self.movement_dir  = 0

    def _draw_overlays(self, frame: np.ndarray, progress_pct: float):
        """Draw the progress bar, rep counter box, and feedback badge onto frame."""
        h, w = frame.shape[:2]

        # ── Progress bar (right edge) ─────────────────────────────────────────
        if self.correct_form:
            bx1, bx2 = w - 50, w - 25
            bt, bb   = 60, h - 80
            filled   = int(np.interp(progress_pct, (0, 100), (bb, bt)))

            # Track background
            cv2.rectangle(frame, (bx1, bt), (bx2, bb), (30, 30, 40), cv2.FILLED)
            # Filled bar (colour interpolated green→red)
            fill_g = int(np.interp(progress_pct, (0, 100), (80, 255)))
            fill_r = int(np.interp(progress_pct, (0, 100), (200, 0)))
            cv2.rectangle(frame, (bx1, filled), (bx2, bb), (fill_r, fill_g, 80), cv2.FILLED)
            # Border
            cv2.rectangle(frame, (bx1, bt), (bx2, bb), (180, 180, 200), 1)
            # Percentage label
            cv2.putText(frame, f'{int(progress_pct)}%',
                        (bx1 - 8, bb + 22),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.5, (190, 190, 200), 1)

        # ── Feedback badge (top-left) ─────────────────────────────────────────
        badge_colours = {
            "Up":               (0, 230, 118),
            "Down":             (0, 170, 255),
            "Fix Form":         (0, 80,  255),
            "Get in Position":  (180, 180, 180),
        }
        fb_col = badge_colours.get(self.exercise_feedback, (180, 180, 180))
        cv2.rectangle(frame, (0, 0), (235, 50), (18, 18, 28), cv2.FILLED)
        cv2.rectangle(frame, (0, 0), (235, 50), fb_col, 2)
        cv2.putText(frame, self.exercise_feedback,
                    (10, 35),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.95, fb_col, 2)

    def _make_result(self, frame) -> dict:
        return {
            "frame":        frame,
            "counter":      int(self.counter),
            "feedback":     self.exercise_feedback,
            "progress":     self.progress_pct,
            "correct_form": self.correct_form,
        }

    @abstractmethod
    def _compute(self, frame: np.ndarray, landmarks_list: list) -> tuple:
        """
        Exercise-specific angle analysis and state-machine tick.

        Args:
            frame:          BGR image (may draw additional lines/circles on it).
            landmarks_list: List of [id, cx, cy] from PoseDetectorModified.

        Returns:
            Tuple of:
              progress_pct (float) — 0–100 for the UI progress bar
              feedback     (str)   — "Up" | "Down" | "Fix Form" | "Get in Position"
              form_ok      (bool)  — True if current frame has valid starting form
        """
        ...