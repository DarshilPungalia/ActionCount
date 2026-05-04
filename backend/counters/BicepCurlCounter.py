"""
BicepCurlCounter.py
-------------------
Counts bicep curl reps using shoulder-elbow-wrist angle (per-limb).

Posture checks (priority order):
  1. Leaning back / swinging   — large Δx(shoulder, hip) → safety
  2. Elbows flaring outward    — |Δx(elbow, shoulder)| > threshold
  3. Elbows moving forward     — Δx(elbow, shoulder) increases vs prev frame
  4. Using momentum            — high wrist velocity spike
  5. Incomplete extension      — arm angle < 150° at bottom
  6. Uneven reps               — |left_angle - right_angle| > 25°

COCO-17:  Left arm: shoulder=5, elbow=7, wrist=9
          Right arm: shoulder=6, elbow=8, wrist=10
          Hip: 11 (L), 12 (R)
"""

import numpy as np
from backend.counters.BaseCounter import BaseCounter


class BicepCurlCounter(BaseCounter):

    UP_ANGLE   = 50
    DOWN_ANGLE = 150

    # Posture thresholds
    _LEAN_THRESH      = 30   # px: large shoulder-hip Δx = leaning
    _FLARE_THRESH     = 35   # px: elbow significantly outside shoulder
    _MOMENTUM_THRESH  = 180  # px/s: high wrist velocity = using momentum
    _EXTEND_THRESH    = 150  # °: arm must reach this at bottom
    _ASYMMETRY_THRESH = 25   # °: difference between arms

    def __init__(self):
        super().__init__()
        self.left_stage  = "down"
        self.right_stage = "down"

    def _compute(self, frame, landmarks_list) -> tuple:
        left_raw  = self.pose_detector.findAngle(frame, 5,  7,  9,  landmarks_list, draw=True)
        right_raw = self.pose_detector.findAngle(frame, 6,  8,  10, landmarks_list, draw=False)

        left  = self._smooth_angle("left",  left_raw)
        right = self._smooth_angle("right", right_raw)

        if left is None and right is None:
            return self.progress_pct, self.exercise_feedback, self.correct_form

        counted = self._tick_per_limb(left, right, self.UP_ANGLE, self.DOWN_ANGLE, inverted=True)
        if counted:
            self._record_rep_velocity(9)  # wrist velocity

        if left is not None and right is not None:
            display_angle = (left + right) / 2.0
        elif left is not None:
            display_angle = left
        else:
            display_angle = right

        progress_pct = float(np.interp(display_angle, (self.UP_ANGLE, self.DOWN_ANGLE), (100, 0)))
        form_ok = display_angle > 100

        if self.correct_form:
            if self.left_stage == "up" or self.right_stage == "up":
                feedback = "Up"
            else:
                feedback = "Down"
        else:
            feedback = "Get in Position" if form_ok else "Fix Form"

        return progress_pct, feedback, form_ok

    def _check_posture(self, frame, lm) -> tuple:
        LS = self._kp_pos(lm, 5);  RS = self._kp_pos(lm, 6)
        LE = self._kp_pos(lm, 7);  RE = self._kp_pos(lm, 8)
        LH = self._kp_pos(lm, 11); RH = self._kp_pos(lm, 12)

        # 1. Leaning back — shoulder moves away from hip horizontally
        if LS and LH and RS and RH:
            lean = abs(((LS[0]-LH[0]) + (RS[0]-RH[0])) / 2)
            if lean > self._LEAN_THRESH:
                return "lean_back", "Keep torso stable, avoid swinging"

        # 2. Elbows flaring outward
        if LS and LE and RS and RE:
            l_flare = LE[0] - LS[0]   # positive = elbow outside left shoulder
            r_flare = RS[0] - RE[0]   # positive = elbow outside right shoulder
            if max(l_flare, r_flare) > self._FLARE_THRESH:
                return "elbows_flare", "Tuck elbows inward"

        # 3. Elbows moving forward (elbow x drifts ahead of shoulder x)
        if LS and LE and RS and RE:
            l_fwd = LE[0] - LS[0]
            r_fwd = RE[0] - RS[0]
            if abs(l_fwd) > self._FLARE_THRESH or abs(r_fwd) > self._FLARE_THRESH:
                return "elbows_forward", "Keep elbows fixed close to torso"

        # 4. Using momentum — high wrist velocity
        wrist_vel = self.calc_velocity(9)
        if wrist_vel > self._MOMENTUM_THRESH:
            return "momentum", "Slow down, use controlled movement"

        # 5. Incomplete extension — check at bottom of curl
        if (self.left_stage == "down" or self.right_stage == "down"):
            LW = self._kp_pos(lm, 9);  RW = self._kp_pos(lm, 10)
            l_ang = self._angle_3pts(LS, LE, LW)
            r_ang = self._angle_3pts(RS, RE, RW)
            for ang in (l_ang, r_ang):
                if ang is not None and ang < self._EXTEND_THRESH:
                    return "incomplete_ext", "Fully extend arms at bottom"

        # 6. Uneven reps — angle asymmetry
        l_raw = self.pose_detector.findAngle(frame, 5, 7, 9, lm, draw=False)
        r_raw = self.pose_detector.findAngle(frame, 6, 8, 10, lm, draw=False)
        if l_raw is not None and r_raw is not None:
            if abs(l_raw - r_raw) > self._ASYMMETRY_THRESH:
                return "uneven_reps", "Maintain symmetry between arms"

        return None, None