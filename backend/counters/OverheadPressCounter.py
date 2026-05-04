"""
OverheadPressCounter.py
-----------------------
Counts overhead-press reps using hip-shoulder-elbow angle (bilateral).

Posture checks (priority order):
  1. Lower back arch    — Δx(shoulder, hip) large = spine not neutral
  2. Elbows flared      — elbow x significantly outside shoulder x
  3. Incomplete lockout — arm angle < 170° at top
  4. Uneven arms        — |left_wrist_y - right_wrist_y| > threshold

COCO-17:  Left:  hip=11, shoulder=5, elbow=7, wrist=9
          Right: hip=12, shoulder=6, elbow=8, wrist=10
"""

import numpy as np
from backend.counters.BaseCounter import BaseCounter


class OverheadPressCounter(BaseCounter):

    UP_ANGLE   = 150
    DOWN_ANGLE = 100

    _ARCH_THRESH    = 30   # px: shoulder-hip horizontal offset = back arching
    _FLARE_THRESH   = 35   # px: elbow outside shoulder = flared
    _LOCKOUT_THRESH = 170  # °: arm angle must reach this at top
    _UNEVEN_THRESH  = 20   # px: wrist height difference

    def _compute(self, frame: np.ndarray, landmarks_list: list) -> tuple:
        left_raw  = self.pose_detector.findAngle(frame, 11, 5, 7, landmarks_list, draw=True)
        right_raw = self.pose_detector.findAngle(frame, 12, 6, 8, landmarks_list, draw=False)

        avg_angle = self._avg_angles(left_raw, right_raw)
        if avg_angle is None:
            return self.progress_pct, self.exercise_feedback, self.correct_form

        progress_pct = float(np.interp(avg_angle, (self.DOWN_ANGLE, self.UP_ANGLE), (0, 100)))
        form_ok      = avg_angle < 110

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
        LS = self._kp_pos(lm, 5);  RS  = self._kp_pos(lm, 6)
        LE = self._kp_pos(lm, 7);  RE  = self._kp_pos(lm, 8)
        LW = self._kp_pos(lm, 9);  RW  = self._kp_pos(lm, 10)
        LH = self._kp_pos(lm, 11); RH  = self._kp_pos(lm, 12)

        # 1. Lower back arch — shoulder displaced from hip horizontally
        if LS and LH and RS and RH:
            l_arch = abs(LS[0] - LH[0])
            r_arch = abs(RS[0] - RH[0])
            if (l_arch + r_arch) / 2 > self._ARCH_THRESH:
                return "back_arch", "Engage core, keep spine neutral"

        # 2. Elbows flared outward
        if LS and LE and RS and RE:
            l_flare = abs(LE[0] - LS[0])
            r_flare = abs(RE[0] - RS[0])
            if max(l_flare, r_flare) > self._FLARE_THRESH:
                return "elbows_flare", "Keep elbows slightly forward"

        # 3. Incomplete lockout — check at top of press (stage == "up")
        if self.stage == "up":
            l_ang = self._angle_3pts(LH, LS, LE)
            r_ang = self._angle_3pts(RH, RS, RE)
            for ang in (l_ang, r_ang):
                if ang is not None and ang < self._LOCKOUT_THRESH:
                    return "incomplete_lockout", "Fully extend arms overhead"

        # 4. Uneven arms
        if LW and RW:
            if abs(LW[1] - RW[1]) > self._UNEVEN_THRESH:
                return "uneven_arms", "Lock both arms evenly"

        return None, None
