"""
LateralRaiseCounter.py
----------------------
Counts lateral-raise reps using hip-shoulder-elbow angle (bilateral).

Posture checks (priority order):
  1. Leaning torso       — Δx(shoulder, hip) significant
  2. Raising above shoulder — wrist_y < shoulder_y (in image coords, wrist rises above)
  3. Elbows too bent/straight — arm angle outside 130–175°
  4. Uneven arms         — |left_wrist_y - right_wrist_y| > threshold

COCO-17:  Left:  hip=11, shoulder=5, elbow=7, wrist=9
          Right: hip=12, shoulder=6, elbow=8, wrist=10
"""

import numpy as np
from backend.counters.BaseCounter import BaseCounter


class LateralRaiseCounter(BaseCounter):

    UP_ANGLE   = 80
    DOWN_ANGLE = 30

    _LEAN_THRESH    = 25   # px: shoulder-hip horizontal offset
    _ELBOW_MIN      = 130  # °: too bent
    _ELBOW_MAX      = 175  # °: too straight
    _UNEVEN_THRESH  = 25   # px: wrist height difference

    def _compute(self, frame: np.ndarray, landmarks_list: list) -> tuple:
        left_raw  = self.pose_detector.findAngle(frame, 11, 5, 7, landmarks_list, draw=True)
        right_raw = self.pose_detector.findAngle(frame, 12, 6, 8, landmarks_list, draw=False)

        avg_angle = self._avg_angles(left_raw, right_raw)
        if avg_angle is None:
            return self.progress_pct, self.exercise_feedback, self.correct_form

        progress_pct = float(np.interp(avg_angle, (self.DOWN_ANGLE, self.UP_ANGLE), (0, 100)))
        form_ok      = avg_angle < 40

        counted = self._tick_bilateral(avg_angle, self.UP_ANGLE, self.DOWN_ANGLE, inverted=False)
        if counted:
            self._record_rep_velocity(9)  # wrist velocity

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
        LS  = self._kp_pos(lm, 5);  RS  = self._kp_pos(lm, 6)
        LE  = self._kp_pos(lm, 7);  RE  = self._kp_pos(lm, 8)
        LW  = self._kp_pos(lm, 9);  RW  = self._kp_pos(lm, 10)
        LH  = self._kp_pos(lm, 11); RH  = self._kp_pos(lm, 12)

        # 1. Leaning torso
        if LS and LH and RS and RH:
            l_lean = abs(LS[0] - LH[0])
            r_lean = abs(RS[0] - RH[0])
            if (l_lean + r_lean) / 2 > self._LEAN_THRESH:
                return "lean_torso", "Keep torso upright"

        # 2. Raising above shoulder (wrist rises above shoulder in image = lower y value)
        if LW and LS and LW[1] < LS[1] - 10:
            return "above_shoulder", "Stop at shoulder height"
        if RW and RS and RW[1] < RS[1] - 10:
            return "above_shoulder", "Stop at shoulder height"

        # 3. Elbows too bent or straight
        l_elbow = self._angle_3pts(LS, LE, LW)
        r_elbow = self._angle_3pts(RS, RE, RW)
        for ang in (l_elbow, r_elbow):
            if ang is not None and not (self._ELBOW_MIN <= ang <= self._ELBOW_MAX):
                return "elbow_angle", "Maintain slight elbow bend"

        # 4. Uneven arms
        if LW and RW:
            if abs(LW[1] - RW[1]) > self._UNEVEN_THRESH:
                return "uneven_arms", "Raise both arms evenly"

        return None, None
