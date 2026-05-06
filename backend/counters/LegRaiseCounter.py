"""
LegRaiseCounter.py
------------------
Counts leg-raise reps using hip-knee-ankle angle (per-limb).

Posture checks (priority order):
  1. Lower back arch   — angle(shoulder, hip, knee) opens up (back lifts off floor)
  2. Legs bent         — angle(hip, knee, ankle) < 160°
  3. Dropping legs fast — high downward ankle velocity  (lowest priority)
  4. Incomplete raise  — legs not reaching sufficient height

COCO-17:  Left leg: hip=11, knee=13, ankle=15
          Right leg: hip=12, knee=14, ankle=16
          Shoulder: 5 (L), 6 (R)
"""

import numpy as np
from backend.counters.BaseCounter import BaseCounter


class LegRaiseCounter(BaseCounter):

    UP_ANGLE   = 160
    DOWN_ANGLE = 110

    _BACK_ARCH_THRESH  = 170   # °: shoulder-hip-knee angle; above = back arching
    _BENT_LEG_THRESH   = 160   # °: hip-knee-ankle angle; below = legs too bent
    _DROP_SPEED_THRESH = 320   # px/s: downward ankle velocity (raised — lower priority)
    _RAISE_MARGIN      = 30    # px: ankle must rise above hip level

    def _compute(self, frame: np.ndarray, landmarks_list: list) -> tuple:
        left_raw  = self.pose_detector.findAngle(frame, 11, 13, 15, landmarks_list, draw=True)
        right_raw = self.pose_detector.findAngle(frame, 12, 14, 16, landmarks_list, draw=False)

        left_angle, right_angle = self._active_per_limb(left_raw, right_raw)

        available = [a for a in (left_angle, right_angle) if a is not None]
        if not available:
            return self.progress_pct, self.exercise_feedback, self.correct_form

        avg_angle    = sum(available) / len(available)
        progress_pct = float(np.interp(avg_angle, (self.DOWN_ANGLE, self.UP_ANGLE), (100, 0)))
        form_ok      = avg_angle > 140

        counted = self._tick_per_limb(left_angle, right_angle, self.UP_ANGLE, self.DOWN_ANGLE, inverted=False)
        if counted:
            self._record_rep_velocity(15)  # ankle velocity

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
        LA = self._kp_pos(lm, 15); RA  = self._kp_pos(lm, 16)

        # 1. Lower back arch — shoulder-hip-knee angle opens (back lifts)
        l_back = self._angle_3pts(LS, LH, LK)
        r_back = self._angle_3pts(RS, RH, RK)
        for ang in (l_back, r_back):
            if ang is not None and ang > self._BACK_ARCH_THRESH:
                return "back_arch", "Keep lower back pressed down"

        # 2. Legs bent too much
        l_leg = self._angle_3pts(LH, LK, LA)
        r_leg = self._angle_3pts(RH, RK, RA)
        for ang in (l_leg, r_leg):
            if ang is not None and ang < self._BENT_LEG_THRESH:
                return "bent_legs", "Keep legs straighter"

        # 3. Dropping legs fast — high downward ankle velocity (y increasing fast)
        ankle_vel = self.calc_velocity(15)
        if ankle_vel > self._DROP_SPEED_THRESH and self.stage == "up":
            return "drop_fast", "Lower legs slowly"

        # 4. Incomplete raise — at the counted (down) position, ankle above hip?
        if self.stage == "down" and LH and LA:
            if LA[1] > LH[1] - self._RAISE_MARGIN:   # ankle not high enough
                return "incomplete_raise", "Raise legs fully"

        return None, None
