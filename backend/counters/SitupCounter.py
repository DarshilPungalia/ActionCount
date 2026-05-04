"""
SitupCounter.py
---------------
Counts sit-up reps using shoulder-hip-ankle angle (bilateral).

Posture checks (priority order):
  1. Jerking upward     — high shoulder acceleration/velocity
  2. Pulling neck       — angle(nose, shoulder, hip) too acute
  3. Incomplete sit-up  — angle at top not small enough

COCO-17:  Left: shoulder=5, hip=11, ankle=15
          Right: shoulder=6, hip=12, ankle=16
          Nose: 0
"""

import numpy as np
from backend.counters.BaseCounter import BaseCounter


class SitupCounter(BaseCounter):

    UP_ANGLE   = 160
    DOWN_ANGLE = 145

    _JERK_THRESH       = 180   # px/s: shoulder velocity = jerking
    _NECK_THRESH       = 110   # °: angle(nose, shoulder, hip) below = neck pull
    _INCOMPLETE_THRESH = 155   # °: angle must go below this at top

    def _compute(self, frame: np.ndarray, landmarks_list: list) -> tuple:
        left_raw  = self.pose_detector.findAngle(frame, 5, 11, 15, landmarks_list, draw=True)
        right_raw = self.pose_detector.findAngle(frame, 6, 12, 16, landmarks_list, draw=False)

        avg_angle = self._avg_angles(left_raw, right_raw)
        if avg_angle is None:
            return self.progress_pct, self.exercise_feedback, self.correct_form

        progress_pct = float(np.interp(avg_angle, (self.DOWN_ANGLE, self.UP_ANGLE), (100, 0)))
        form_ok      = avg_angle > 155

        counted = self._tick_bilateral(avg_angle, self.UP_ANGLE, self.DOWN_ANGLE, inverted=False)
        if counted:
            self._record_rep_velocity(5)  # shoulder velocity

        if self.correct_form:
            if self.stage == "up" and self.counter > 0:
                feedback = "Up"
            elif self.stage == "down" or avg_angle <= self.DOWN_ANGLE or self.counter == 0:
                feedback = "Down"
            else:
                feedback = self.exercise_feedback
        else:
            feedback = "Get in Position" if form_ok else "Fix Form"

        return progress_pct, feedback, form_ok

    def _check_posture(self, frame, lm) -> tuple:
        LS = self._kp_pos(lm, 5);  RS  = self._kp_pos(lm, 6)
        LH = self._kp_pos(lm, 11); RH  = self._kp_pos(lm, 12)
        N  = self._kp_pos(lm, 0)

        # 1. Jerking upward — high shoulder velocity
        if self.calc_velocity(5) > self._JERK_THRESH:
            return "jerk_up", "Move in a controlled manner"

        # 2. Pulling neck — nose pulled too close to chest
        if N and LS and LH:
            neck_ang = self._angle_3pts(N, LS, LH)
            if neck_ang is not None and neck_ang < self._NECK_THRESH:
                return "neck_pull", "Avoid pulling neck, use core"

        # 3. Incomplete sit-up — at the "down" counted position, angle must be small
        if self.stage == "down":
            l_raw = self.pose_detector.findAngle(frame, 5, 11, 15, lm, draw=False)
            r_raw = self.pose_detector.findAngle(frame, 6, 12, 16, lm, draw=False)
            for ang in (l_raw, r_raw):
                if ang is not None and ang > self._INCOMPLETE_THRESH:
                    return "incomplete_situp", "Complete full sit-up"

        return None, None
