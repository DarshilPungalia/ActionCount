"""
PushupCounter.py
----------------
Counts push-up reps using shoulder-elbow-wrist angle (bilateral).

Posture checks (priority order):
  1. Sagging hips    — angle(shoulder, hip, ankle) < 160°
  2. Piked hips      — angle(shoulder, hip, ankle) > 200°
  3. Head dropping   — nose_y well below shoulder_y
  4. Elbows flaring  — large lateral Δx(elbow, shoulder)
  5. Incomplete depth — elbow angle never < 90° at bottom
  6. Using momentum  — high shoulder velocity  (lowest priority)
  7. Uneven push     — left/right shoulder height mismatch

COCO-17:  Arms: shoulder 5/6, elbow 7/8, wrist 9/10
          Body: hip 11/12, ankle 15/16, nose 0
"""

import numpy as np
from backend.counters.BaseCounter import BaseCounter


class PushupCounter(BaseCounter):

    UP_ANGLE   = 160
    DOWN_ANGLE = 130

    _SAG_THRESH      = 160   # °: angle below this = hips sag
    _PIKE_THRESH     = 200   # °: angle above this = hips too high
    _HEAD_THRESH     = 40    # px: nose much lower (larger y) than shoulder
    _FLARE_THRESH    = 40    # px: elbow lateral offset from shoulder
    _DEPTH_THRESH    = 90    # °: elbow must reach this at bottom
    _MOMENTUM_THRESH = 320   # px/s: shoulder velocity (raised — lower priority)
    _UNEVEN_THRESH   = 20    # px: shoulder height difference

    def _compute(self, frame: np.ndarray, landmarks_list: list) -> tuple:
        left_raw  = self.pose_detector.findAngle(frame, 5,  7,  9,  landmarks_list, draw=True)
        right_raw = self.pose_detector.findAngle(frame, 6,  8,  10, landmarks_list, draw=False)

        avg_angle = self._avg_angles(left_raw, right_raw)
        if avg_angle is None:
            return self.progress_pct, self.exercise_feedback, self.correct_form

        progress_pct = float(np.interp(avg_angle, (self.DOWN_ANGLE, self.UP_ANGLE), (100, 0)))
        form_ok      = avg_angle > 140

        if avg_angle < self.DOWN_ANGLE:
            self.stage = "down"
        elif avg_angle > self.UP_ANGLE and self.stage == "down":
            self.stage = "up"
            if self._debounced_increment():
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
        LE = self._kp_pos(lm, 7);  RE  = self._kp_pos(lm, 8)
        LH = self._kp_pos(lm, 11); RH  = self._kp_pos(lm, 12)
        LA = self._kp_pos(lm, 15); RA  = self._kp_pos(lm, 16)
        N  = self._kp_pos(lm, 0)

        # 1. Sagging hips (image y-axis: larger y = lower in frame)
        l_ang = self._angle_3pts(LS, LH, LA)
        r_ang = self._angle_3pts(RS, RH, RA)
        body_ang = None
        if l_ang is not None and r_ang is not None:
            body_ang = (l_ang + r_ang) / 2
        elif l_ang is not None:
            body_ang = l_ang
        elif r_ang is not None:
            body_ang = r_ang

        if body_ang is not None:
            if body_ang < self._SAG_THRESH:
                return "hip_sag", "Keep body in straight line, engage core"
            if body_ang > self._PIKE_THRESH:
                return "hip_pike", "Lower hips to align body"

        # 3. Head dropping
        if N and LS and RS:
            shoulder_y = (LS[1] + RS[1]) / 2
            if N[1] - shoulder_y > self._HEAD_THRESH:
                return "head_drop", "Keep head neutral with spine"

        # 4. Elbows flaring outward
        if LS and LE and RS and RE:
            l_flare = abs(LE[0] - LS[0])
            r_flare = abs(RE[0] - RS[0])
            if max(l_flare, r_flare) > self._FLARE_THRESH:
                return "elbows_flare", "Keep elbows closer to body (~45°)"

        # 5. Incomplete depth — check during down phase
        if self.stage == "down":
            l_elbow = self.pose_detector.findAngle(frame, 5, 7, 9,  lm, draw=False)
            r_elbow = self.pose_detector.findAngle(frame, 6, 8, 10, lm, draw=False)
            for ang in (l_elbow, r_elbow):
                if ang is not None and ang > self._DEPTH_THRESH:
                    return "incomplete_depth", "Lower chest closer to ground"

        # 6. Using momentum
        if self.calc_velocity(5) > self._MOMENTUM_THRESH:
            return "momentum", "Control movement, avoid bouncing"

        # 7. Uneven push
        if LS and RS:
            if abs(LS[1] - RS[1]) > self._UNEVEN_THRESH:
                return "uneven_push", "Push evenly with both arms"

        return None, None
