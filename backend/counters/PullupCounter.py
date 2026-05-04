"""
PullupCounter.py
----------------
Counts pull-up reps using shoulder-elbow-wrist angle (bilateral, inverted).

Posture checks (priority order):
  1. Kipping          — oscillating Δx(hip) between frames = swinging
  2. Uneven pulling   — left vs right elbow angle mismatch > 20°
  3. Half reps        — nose not reaching wrist height at top

COCO-17:  Left arm: shoulder=5, elbow=7, wrist=9
          Right arm: shoulder=6, elbow=8, wrist=10
          Hip: 11 (L), 12 (R), Nose: 0
"""

import numpy as np
from backend.counters.BaseCounter import BaseCounter


class PullupCounter(BaseCounter):

    UP_ANGLE   = 70
    DOWN_ANGLE = 140

    _KIPPING_THRESH  = 25   # px: hip horizontal oscillation between frames
    _UNEVEN_THRESH   = 20   # °: elbow angle difference between arms
    _CHIN_MARGIN     = 20   # px: nose must be at or above wrist level (lower y)

    def _compute(self, frame: np.ndarray, landmarks_list: list) -> tuple:
        left_raw  = self.pose_detector.findAngle(frame, 5,  7,  9,  landmarks_list, draw=True)
        right_raw = self.pose_detector.findAngle(frame, 6,  8,  10, landmarks_list, draw=False)

        avg_angle = self._avg_angles(left_raw, right_raw)
        if avg_angle is None:
            return self.progress_pct, self.exercise_feedback, self.correct_form

        progress_pct = float(np.interp(avg_angle, (self.UP_ANGLE, self.DOWN_ANGLE), (100, 0)))
        form_ok      = avg_angle > 100

        counted = self._tick_bilateral(avg_angle, self.UP_ANGLE, self.DOWN_ANGLE, inverted=True)
        if counted:
            self._record_rep_velocity(5)  # shoulder velocity

        if self.correct_form:
            if self.stage == "up" and self.counter > 0:
                feedback = "Up"
            elif self.stage == "down" or avg_angle >= self.DOWN_ANGLE or self.counter == 0:
                feedback = "Down"
            else:
                feedback = self.exercise_feedback
        else:
            feedback = "Get in Position" if form_ok else "Fix Form"

        return progress_pct, feedback, form_ok

    def _check_posture(self, frame, lm) -> tuple:
        LH = self._kp_pos(lm, 11); RH  = self._kp_pos(lm, 12)
        N  = self._kp_pos(lm, 0)
        LW = self._kp_pos(lm, 9);  RW  = self._kp_pos(lm, 10)
        LS = self._kp_pos(lm, 5);  RS  = self._kp_pos(lm, 6)
        LE = self._kp_pos(lm, 7);  RE  = self._kp_pos(lm, 8)

        # 1. Kipping — hip oscillates horizontally
        if len(self._skeleton_window) >= 2 and LH:
            prev_map = list(self._skeleton_window)[-2][1]
            prev_lh  = prev_map.get(11)
            if prev_lh and abs(LH[0] - prev_lh[0]) > self._KIPPING_THRESH:
                return "kipping", "Avoid swinging, control body"

        # 2. Uneven pulling — elbow angle mismatch
        l_ang = self.pose_detector.findAngle(frame, 5, 7, 9,  lm, draw=False)
        r_ang = self.pose_detector.findAngle(frame, 6, 8, 10, lm, draw=False)
        if l_ang is not None and r_ang is not None:
            if abs(l_ang - r_ang) > self._UNEVEN_THRESH:
                return "uneven_pull", "Pull evenly with both arms"

        # 3. Half reps — nose must reach wrist height at top
        if self.stage == "up" and N and LW and RW:
            wrist_y = (LW[1] + RW[1]) / 2
            if N[1] > wrist_y + self._CHIN_MARGIN:   # nose below wrist level
                return "half_rep", "Complete full range of motion"

        return None, None
