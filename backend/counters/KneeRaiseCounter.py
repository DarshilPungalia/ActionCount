"""
KneeRaiseCounter.py
-------------------
Counts knee-raise reps using hip-knee-ankle angle (per-limb).

Posture checks (priority order):
  1. Leaning backward  — Δx(shoulder, hip) increases (torso tilts back)
  2. Swinging legs     — oscillating Δx(knee) between frames
  3. Uneven raise      — |left_knee_y - right_knee_y| > threshold
  4. Incomplete height — knee_y not reaching hip_y level at top

COCO-17:  Left leg: hip=11, knee=13, ankle=15
          Right leg: hip=12, knee=14, ankle=16
          Shoulder: 5 (L), 6 (R)
"""

import numpy as np
from backend.counters.BaseCounter import BaseCounter


class KneeRaiseCounter(BaseCounter):

    UP_ANGLE   = 160
    DOWN_ANGLE = 110

    _LEAN_THRESH     = 30   # px: shoulder-hip horizontal offset = leaning
    _SWING_THRESH    = 20   # px: knee horizontal oscillation
    _UNEVEN_THRESH   = 25   # px: knee height difference
    _HEIGHT_MARGIN   = 10   # px: knee must reach above hip_y at top

    def _compute(self, frame: np.ndarray, landmarks_list: list) -> tuple:
        left_raw  = self.pose_detector.findAngle(frame, 11, 13, 15, landmarks_list, draw=True)
        right_raw = self.pose_detector.findAngle(frame, 12, 14, 16, landmarks_list, draw=False)

        left_angle, right_angle = self._active_per_limb(left_raw, right_raw)

        available = [a for a in (left_angle, right_angle) if a is not None]
        if not available:
            return self.progress_pct, self.exercise_feedback, self.correct_form

        avg_angle    = sum(available) / len(available)
        progress_pct = float(np.interp(avg_angle, (self.DOWN_ANGLE, self.UP_ANGLE), (100, 0)))
        form_ok      = avg_angle > 130

        counted = self._tick_per_limb(left_angle, right_angle, self.UP_ANGLE, self.DOWN_ANGLE, inverted=False)
        if counted:
            self._record_rep_velocity(13)  # knee velocity

        if self.correct_form:
            active_stage = self.left_stage or self.right_stage
            if active_stage == "up" and self.counter > 0:
                feedback = "Up"
            elif active_stage == "down" or avg_angle <= self.DOWN_ANGLE or self.counter == 0:
                feedback = "Down"
            else:
                feedback = self.exercise_feedback
        else:
            feedback = "Get in Position" if form_ok else "Fix Form"

        return progress_pct, feedback, form_ok

    def _check_posture(self, frame, lm) -> tuple:
        LS = self._kp_pos(lm, 5);  RS  = self._kp_pos(lm, 6)
        LH = self._kp_pos(lm, 11); RH  = self._kp_pos(lm, 12)
        LK = self._kp_pos(lm, 13); RK  = self._kp_pos(lm, 14)

        # 1. Leaning backward — shoulder drifts behind hip
        if LS and LH and RS and RH:
            l_lean = LH[0] - LS[0]   # positive = shoulder behind hip
            r_lean = RS[0] - RH[0]
            if max(l_lean, r_lean) > self._LEAN_THRESH:
                return "lean_back", "Keep torso upright"

        # 2. Swinging legs — knee oscillates horizontally between frames
        if len(self._skeleton_window) >= 2 and LK and RK:
            prev_map = list(self._skeleton_window)[-2][1]
            prev_lk  = prev_map.get(13)
            prev_rk  = prev_map.get(14)
            if prev_lk and abs(LK[0] - prev_lk[0]) > self._SWING_THRESH:
                return "swing_legs", "Avoid swinging, control movement"
            if prev_rk and abs(RK[0] - prev_rk[0]) > self._SWING_THRESH:
                return "swing_legs", "Avoid swinging, control movement"

        # 3. Uneven raise
        if LK and RK:
            if abs(LK[1] - RK[1]) > self._UNEVEN_THRESH:
                return "uneven_raise", "Lift both legs evenly"

        # 4. Incomplete knee height — knee must reach hip level
        if self.stage == "down":  # "down" = knee raised in KneeRaise
            if LH and LK and LK[1] > LH[1] + self._HEIGHT_MARGIN:
                return "incomplete_height", "Raise knees higher"
            if RH and RK and RK[1] > RH[1] + self._HEIGHT_MARGIN:
                return "incomplete_height", "Raise knees higher"

        return None, None
