"""
SquatCounter.py
---------------
Counts squat reps using hip-knee-ankle angle (bilateral).

Posture checks (priority order):
  1. Knee valgus   — knee collapses inward vs ankle alignment
  2. Forward lean  — large Δx(shoulder, hip)
  3. Uneven squat  — |left_hip_y - right_hip_y| > threshold
  4. Not enough depth — hip not reaching knee level at bottom

COCO-17:  Left leg: hip=11, knee=13, ankle=15
          Right leg: hip=12, knee=14, ankle=16
          Shoulder: 5 (L), 6 (R)
"""

import numpy as np
from backend.counters.BaseCounter import BaseCounter


class SquatCounter(BaseCounter):

    UP_ANGLE   = 160
    DOWN_ANGLE = 110

    _VALGUS_THRESH   = 20   # px: knee inward relative to ankle
    _LEAN_THRESH     = 35   # px: shoulder-hip horizontal offset
    _UNEVEN_THRESH   = 20   # px: L vs R hip height difference
    _DEPTH_MARGIN    = 15   # px: hip must be at or below knee_y

    def _compute(self, frame: np.ndarray, landmarks_list: list) -> tuple:
        left_raw  = self.pose_detector.findAngle(frame, 11, 13, 15, landmarks_list, draw=True)
        right_raw = self.pose_detector.findAngle(frame, 12, 14, 16, landmarks_list, draw=False)

        avg_angle = self._avg_angles(left_raw, right_raw)
        if avg_angle is None:
            return self.progress_pct, self.exercise_feedback, self.correct_form

        progress_pct = float(np.interp(avg_angle, (self.DOWN_ANGLE, self.UP_ANGLE), (100, 0)))
        form_ok      = avg_angle > 130

        if avg_angle < self.DOWN_ANGLE:
            self.stage = "down"
        elif avg_angle > self.UP_ANGLE and self.stage == "down":
            self.stage = "up"
            if self._debounced_increment():
                self._record_rep_velocity(11)  # hip velocity

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
        LH  = self._kp_pos(lm, 11); RH  = self._kp_pos(lm, 12)
        LK  = self._kp_pos(lm, 13); RK  = self._kp_pos(lm, 14)
        LA  = self._kp_pos(lm, 15); RA  = self._kp_pos(lm, 16)
        LS  = self._kp_pos(lm, 5);  RS  = self._kp_pos(lm, 6)

        # 1. Knee valgus — knee x significantly inside ankle x
        # Left leg: normally knee_x ~ ankle_x; valgus → knee moves right (knee_x > ankle_x)
        # Right leg: normally knee_x ~ ankle_x; valgus → knee moves left (knee_x < ankle_x)
        if LK and LA and RK and RA:
            l_valgus = LK[0] - LA[0]   # positive = left knee medialised
            r_valgus = RA[0] - RK[0]   # positive = right knee medialised
            if l_valgus > self._VALGUS_THRESH or r_valgus > self._VALGUS_THRESH:
                return "knee_valgus", "Keep knees aligned with toes"

        # 2. Forward lean — shoulder significantly ahead of hip horizontally
        if LS and LH and RS and RH:
            l_lean = abs(LS[0] - LH[0])
            r_lean = abs(RS[0] - RH[0])
            if (l_lean + r_lean) / 2 > self._LEAN_THRESH:
                return "forward_lean", "Keep chest upright"

        # 3. Uneven squat — hip height asymmetry
        if LH and RH:
            if abs(LH[1] - RH[1]) > self._UNEVEN_THRESH:
                return "uneven_squat", "Distribute weight evenly"

        # 4. Not enough depth — at bottom of squat, hip should be near/below knee
        if self.stage == "down" and LH and LK and RH and RK:
            l_depth = LH[1] - LK[1]   # positive = hip above knee (image y-down)
            r_depth = RH[1] - RK[1]
            if l_depth < -self._DEPTH_MARGIN or r_depth < -self._DEPTH_MARGIN:
                return "shallow_squat", "Go deeper into squat"

        return None, None
