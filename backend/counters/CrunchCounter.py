"""
CrunchCounter.py
----------------
Counts crunch reps using shoulder-hip-ankle angle (bilateral, inverted).

Posture checks (priority order):
  1. Lower back lifting  — sudden upward hip movement (Δy)
  2. Excessive neck flex — angle(nose, shoulder, hip) too acute
  3. Using momentum      — high shoulder velocity  (lowest priority)
  4. Incomplete lift     — insufficient angle reduction at top

COCO-17:  Left: shoulder=5, hip=11, ankle=15
          Right: shoulder=6, hip=12, ankle=16
          Nose: 0
"""

import numpy as np
from backend.counters.BaseCounter import BaseCounter


class CrunchCounter(BaseCounter):

    UP_ANGLE   = 150
    DOWN_ANGLE = 170

    _NECK_FLEX_THRESH   = 120   # °: angle(nose, shoulder, hip) below this = neck pull
    _MOMENTUM_THRESH    = 250   # px/s: shoulder upward speed (raised — lower priority)
    _BACK_LIFT_THRESH   = 15    # px: hip y decrease vs previous window frame
    _INCOMPLETE_THRESH  = 155   # °: angle must drop below UP_ANGLE significantly

    def _compute(self, frame: np.ndarray, landmarks_list: list) -> tuple:
        left_raw  = self.pose_detector.findAngle(frame, 5, 11, 15, landmarks_list, draw=True)
        right_raw = self.pose_detector.findAngle(frame, 6, 12, 16, landmarks_list, draw=False)

        avg_angle = self._avg_angles(left_raw, right_raw)
        if avg_angle is None:
            return self.progress_pct, self.exercise_feedback, self.correct_form

        progress_pct = float(np.interp(avg_angle, (self.UP_ANGLE, self.DOWN_ANGLE), (100, 0)))
        form_ok      = avg_angle > 165

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
        LS = self._kp_pos(lm, 5);  RS  = self._kp_pos(lm, 6)
        LH = self._kp_pos(lm, 11); RH  = self._kp_pos(lm, 12)
        N  = self._kp_pos(lm, 0)

        # 1. Lower back lifting — hip rises off floor (y decreases in image coords)
        if len(self._skeleton_window) >= 2:
            prev_map = list(self._skeleton_window)[-2][1]
            prev_lh  = prev_map.get(11)
            prev_rh  = prev_map.get(12)
            if LH and prev_lh and abs(prev_lh[1] - LH[1]) > self._BACK_LIFT_THRESH:
                return "back_lift", "Keep lower back pressed down"
            if RH and prev_rh and abs(prev_rh[1] - RH[1]) > self._BACK_LIFT_THRESH:
                return "back_lift", "Keep lower back pressed down"

        # 2. Excessive neck flexion — nose pulled too far toward chest
        if N and LS and LH:
            neck_ang = self._angle_3pts(N, LS, LH)
            if neck_ang is not None and neck_ang < self._NECK_FLEX_THRESH:
                return "neck_pull", "Keep neck neutral, avoid pulling head"

        # 3+4. Incomplete lift checked before momentum (structural > speed)
        if self.stage == "up":
            l_raw = self.pose_detector.findAngle(frame, 5, 11, 15, lm, draw=False)
            r_raw = self.pose_detector.findAngle(frame, 6, 12, 16, lm, draw=False)
            for ang in (l_raw, r_raw):
                if ang is not None and ang > self._INCOMPLETE_THRESH:
                    return "incomplete_lift", "Lift upper body fully"

        # 3. Using momentum — lowest priority
        if self.calc_velocity(5) > self._MOMENTUM_THRESH:
            return "momentum", "Lift slowly using abs"

        return None, None
