import math
import random
import time
import cv2
import numpy as np
from abc import ABC, abstractmethod
from collections import deque
from typing import Optional
from backend.detector.PoseDetector import PoseDetectorModified


class BaseCounter(ABC):
    """
    Abstract base class for all exercise counters.

    The base class handles:
      - Pose detection and landmark extraction
      - Stage-machine rep counting (up/down transitions with debounce)
      - Angle smoothing (median filter + outlier rejection + 5-frame mean)
      - Velocity tracking via a 5-frame sliding window (deque of skeletons)
      - Posture correction with exercise-specific priority ordering
      - Per-rep velocity history + failure-trend detection (motivational TTS)
      - CV2 overlay drawing (progress bar)
      - Thread-safe result packaging

    Subclasses implement `_compute()` AND optionally `_check_posture()`.
    """

    DEBOUNCE_SECONDS:    float = 0.5
    POSTURE_TTS_COOLDOWN: float = 6.0   # seconds between same-error TTS
    FAILURE_VELOCITY_DROP: float = 0.80  # 20% drop over 4 reps = near failure
    FAILURE_MIN_REPS:    int   = 4

    # ── Motivational phrases spoken when velocity decline detected ────────────
    _MOTIVATION_PHRASES = [
        "{n} more rep{s}! You've got this!",
        "Keep pushing — you're almost there!",
        "Don't stop now, you can do it!",
        "Come on! {n} more rep{s}!",
        "Dig deep, keep going!",
        "Push through it — almost done!",
    ]

    def __init__(self):
        self.pose_detector     = PoseDetectorModified(mode='lightweight')
        self.counter           = 0.0
        self.correct_form      = False
        self.exercise_feedback = "Get in Position"
        self.progress_pct      = 0.0

        # Stage-machine state
        self.stage       = None
        self.left_stage  = None
        self.right_stage = None

        # Debounce
        self._last_count_time: float = 0.0

        # Angle smoothing deques  {side: deque([raw_angles], maxlen=5)}
        self._angle_deques: dict = {
            "left":  deque(maxlen=5),
            "right": deque(maxlen=5),
        }

        # Legacy attribute kept for backward-compat
        self.movement_dir = 0

        # ── Velocity ──────────────────────────────────────────────────────────
        # Sliding window: deque of (timestamp, {kp_id: (cx, cy)})
        self._skeleton_window: deque = deque(maxlen=5)
        # Per-rep velocities for failure-trend detection
        self._rep_velocities: deque  = deque(maxlen=20)
        # Latest velocity value (exposed in result payload)
        self._last_velocity: float   = 0.0

        # ── Posture correction ────────────────────────────────────────────────
        self._posture_error: Optional[str] = None   # short key
        self._posture_msg:   Optional[str] = None   # human message
        # {error_key: last_tts_monotonic_time}
        self._posture_tts_cooldowns: dict  = {}

        # ── Failure motivation ────────────────────────────────────────────────
        self._failure_motivation:   Optional[str] = None
        self._last_motivation_rep:  int           = -1

    # ── Reset ─────────────────────────────────────────────────────────────────

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

        self._skeleton_window        = deque(maxlen=5)
        self._rep_velocities         = deque(maxlen=20)
        self._last_velocity          = 0.0
        self._posture_error          = None
        self._posture_msg            = None
        self._posture_tts_cooldowns  = {}
        self._failure_motivation     = None
        self._last_motivation_rep    = -1

    # ── Velocity helpers ──────────────────────────────────────────────────────

    @staticmethod
    def _kp_map(lm: list) -> dict:
        """Build {kp_id: (cx, cy)} mapping from landmarks_list."""
        return {entry[0]: (entry[1], entry[2]) for entry in lm}

    def calc_velocity(self, kp_idx: int) -> float:
        """
        Average pixel/s speed of keypoint `kp_idx` over the sliding window
        of the last 5 skeleton snapshots.

        Uses a deque of (timestamp, {kp_id: (cx, cy)}) tuples; O(1) updates.
        Returns 0.0 if fewer than 2 frames are available.
        """
        if len(self._skeleton_window) < 2:
            return 0.0
        speeds = []
        frames = list(self._skeleton_window)
        for i in range(1, len(frames)):
            t0, kpm0 = frames[i - 1]
            t1, kpm1 = frames[i]
            dt = t1 - t0
            if dt <= 0:
                continue
            p0 = kpm0.get(kp_idx)
            p1 = kpm1.get(kp_idx)
            if p0 and p1:
                d = math.hypot(p1[0] - p0[0], p1[1] - p0[1])
                speeds.append(d / dt)
        return float(np.mean(speeds)) if speeds else 0.0

    def _record_rep_velocity(self, kp_idx: int) -> None:
        """
        Record the velocity at the moment a rep completes.
        Also checks for failure trend and queues a motivational phrase if detected.
        Call this from each counter's _compute() when a rep is counted.
        """
        v = self.calc_velocity(kp_idx)
        self._last_velocity = v
        self._rep_velocities.append(v)

        motivation = self._check_failure_trend()
        current_rep = int(self.counter)
        if motivation and current_rep != self._last_motivation_rep:
            self._failure_motivation   = motivation
            self._last_motivation_rep  = current_rep

    def _check_failure_trend(self) -> Optional[str]:
        """Return a motivational string if rep velocity is declining significantly."""
        if len(self._rep_velocities) < self.FAILURE_MIN_REPS:
            return None
        recent = list(self._rep_velocities)[-4:]
        # Skip very slow exercises where velocity is near-zero (e.g. static holds)
        if recent[0] < 5.0:
            return None
        if recent[-1] < recent[0] * self.FAILURE_VELOCITY_DROP:
            n = random.randint(1, 2)
            phrase = random.choice(self._MOTIVATION_PHRASES)
            return phrase.format(n=n, s="s" if n > 1 else "")
        return None

    def pop_failure_motivation(self) -> Optional[str]:
        """Consume and return pending motivational phrase (one per rep)."""
        msg = self._failure_motivation
        self._failure_motivation = None
        return msg

    # ── Posture correction ────────────────────────────────────────────────────

    @staticmethod
    def _kp_pos(lm: list, idx: int) -> Optional[tuple]:
        """Return (cx, cy) for keypoint `idx`, or None if not found."""
        for entry in lm:
            if entry[0] == idx:
                return entry[1], entry[2]
        return None

    @staticmethod
    def _angle_3pts(a, b, c) -> Optional[float]:
        """Angle at vertex B formed by A–B–C, in degrees. Returns None if any point is None."""
        if a is None or b is None or c is None:
            return None
        ba = (a[0] - b[0], a[1] - b[1])
        bc = (c[0] - b[0], c[1] - b[1])
        dot     = ba[0] * bc[0] + ba[1] * bc[1]
        mag_ba  = math.hypot(*ba)
        mag_bc  = math.hypot(*bc)
        if mag_ba * mag_bc == 0:
            return None
        cos_a = max(-1.0, min(1.0, dot / (mag_ba * mag_bc)))
        return math.degrees(math.acos(cos_a))

    def _check_posture(self, frame: np.ndarray, lm: list) -> tuple:
        """
        Exercise-specific posture checks. Override in subclasses.
        Errors must be returned in PRIORITY order — highest risk first.

        Returns:
            (error_key: str, human_message: str) or (None, None)
        """
        return None, None

    def pop_posture_tts(self) -> Optional[str]:
        """
        Returns posture_msg if the 6-second TTS cooldown has elapsed for
        this error key. The HUD always shows the current error immediately;
        the TTS fires at most once per 6 s per unique error.
        """
        if not self._posture_error or not self._posture_msg:
            return None
        key  = self._posture_error
        now  = time.monotonic()
        last = self._posture_tts_cooldowns.get(key, 0.0)
        if now - last >= self.POSTURE_TTS_COOLDOWN:
            self._posture_tts_cooldowns[key] = now
            return self._posture_msg
        return None

    # ── Core frame processing ─────────────────────────────────────────────────

    def process_frame(self, frame: np.ndarray) -> dict:
        """
        Process a single BGR video frame and return annotated results.

        Returns dict with:
            frame        — annotated BGR numpy array
            counter      — integer rep count
            feedback     — "Up" | "Down" | "Fix Form" | "Get in Position"
            progress     — float 0-100
            correct_form — bool
            posture_error — short error key or None
            posture_msg   — human correction message or None
            velocity      — float px/s (0 if insufficient history)
        """
        if frame is None:
            return self._make_result(frame)

        frame          = self.pose_detector.findPose(frame, draw=True)
        landmarks_list = self.pose_detector.findPosition(frame, draw=False)

        if landmarks_list:
            # Snapshot skeleton for velocity window
            self._skeleton_window.append((time.monotonic(), self._kp_map(landmarks_list)))

            try:
                progress_pct, feedback, form_ok = self._compute(frame, landmarks_list)
                self.progress_pct      = float(np.clip(progress_pct, 0.0, 100.0))
                self.exercise_feedback = feedback

                if form_ok:
                    self.correct_form = True

                # Posture check — only once form is unlocked
                if self.correct_form:
                    err, msg = self._check_posture(frame, landmarks_list)
                    self._posture_error = err
                    self._posture_msg   = msg
                else:
                    self._posture_error = None
                    self._posture_msg   = None

                self._draw_overlays(frame, self.progress_pct)

            except (IndexError, ValueError, ZeroDivisionError, TypeError):
                pass

        return self._make_result(frame)

    # ── Angle smoothing ───────────────────────────────────────────────────────

    def _smooth_angle(self, side: str, raw_angle) -> float:
        if raw_angle is None:
            return None
        dq = self._angle_deques[side]
        dq.append(float(raw_angle))
        if len(dq) < 3:
            return float(raw_angle)
        vals   = np.array(list(dq), dtype=np.float64)
        median = np.median(vals)
        std    = np.std(vals)
        if std > 0:
            filtered = vals[np.abs(vals - median) <= 2 * std]
        else:
            filtered = vals
        return float(np.mean(filtered)) if len(filtered) > 0 else float(median)

    def _avg_angles(self, left_raw, right_raw):
        left  = self._smooth_angle("left",  left_raw)
        right = self._smooth_angle("right", right_raw)
        if left is None or right is None:
            return None
        return (left + right) / 2.0

    def _active_per_limb(self, left_raw, right_raw):
        return (
            self._smooth_angle("left",  left_raw),
            self._smooth_angle("right", right_raw),
        )

    # ── Stage-machine ticks ───────────────────────────────────────────────────

    def _debounced_increment(self) -> bool:
        now = time.monotonic()
        if now - self._last_count_time >= self.DEBOUNCE_SECONDS:
            self.counter         += 1
            self._last_count_time = now
            return True
        return False

    def _tick_bilateral(self, angle, up_angle: float, down_angle: float,
                         inverted: bool = False) -> bool:
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

    def _tick_per_limb(self, left_angle, right_angle, up_angle: float,
                        down_angle: float, inverted: bool = False) -> int:
        counted = 0

        def _tick_one(angle, current_stage):
            nonlocal counted
            if angle is None:
                return current_stage
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
        """Legacy generic half-rep counting (not used by state-machine counters)."""
        if progress_pct >= 98 and self.movement_dir == 0:
            self.counter      += 0.5
            self.movement_dir  = 1
        elif progress_pct <= 2 and self.movement_dir == 1:
            self.counter      += 0.5
            self.movement_dir  = 0

    # ── Overlay drawing ───────────────────────────────────────────────────────

    def _draw_overlays(self, frame: np.ndarray, progress_pct: float):
        """Draw the progress bar onto frame."""
        h, w = frame.shape[:2]
        if self.correct_form:
            bx1, bx2 = w - 50, w - 25
            bt, bb   = 60, h - 80
            filled   = int(np.interp(progress_pct, (0, 100), (bb, bt)))
            cv2.rectangle(frame, (bx1, bt), (bx2, bb), (30, 30, 40), cv2.FILLED)
            fill_g = int(np.interp(progress_pct, (0, 100), (80, 255)))
            fill_r = int(np.interp(progress_pct, (0, 100), (200, 0)))
            cv2.rectangle(frame, (bx1, filled), (bx2, bb), (fill_r, fill_g, 80), cv2.FILLED)
            cv2.rectangle(frame, (bx1, bt), (bx2, bb), (180, 180, 200), 1)
            cv2.putText(frame, f'{int(progress_pct)}%',
                        (bx1 - 8, bb + 22),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.5, (190, 190, 200), 1)

    # ── Result packaging ──────────────────────────────────────────────────────

    def _make_result(self, frame) -> dict:
        return {
            "frame":         frame,
            "counter":       int(self.counter),
            "feedback":      self.exercise_feedback,
            "progress":      self.progress_pct,
            "correct_form":  self.correct_form,
            "posture_error": self._posture_error,
            "posture_msg":   self._posture_msg,
            "velocity":      round(self._last_velocity, 1),
        }

    # ── Abstract interface ────────────────────────────────────────────────────

    @abstractmethod
    def _compute(self, frame: np.ndarray, landmarks_list: list) -> tuple:
        """
        Exercise-specific angle analysis and state-machine tick.

        Returns:
            Tuple of:
              progress_pct (float) — 0–100 for the UI progress bar
              feedback     (str)   — "Up" | "Down" | "Fix Form" | "Get in Position"
              form_ok      (bool)  — True if current frame has valid starting form
        """