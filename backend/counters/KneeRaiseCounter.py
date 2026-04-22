"""
KneeRaiseCounter.py
-------------------
Counts knee-raise reps using hip-knee-ankle angle (per_limb).

COCO-17 keypoints:
  Left leg  : hip=11, knee=13, ankle=15
  Right leg : hip=12, knee=14, ankle=16

UP_ANGLE   : 160°  (leg extended / standing)
DOWN_ANGLE : 80°   (knee raised to roughly 90°+)
MODE       : per_limb

Each knee raise is counted independently; alternating knees accumulate
in the same counter.

Inverted=False:
  stage='up'   when angle > 160 (leg extended)
  stage='down' (+ count) when angle < 80 AND stage was 'up'
"""

import numpy as np
from backend.counters.BaseCounter import BaseCounter


class KneeRaiseCounter(BaseCounter):

    UP_ANGLE   = 160
    DOWN_ANGLE = 110

    def _compute(self, frame: np.ndarray, landmarks_list: list) -> tuple:
        left_raw  = self.pose_detector.findAngle(frame, 11, 13, 15, landmarks_list, draw=True)
        right_raw = self.pose_detector.findAngle(frame, 12, 14, 16, landmarks_list, draw=False)

        left_angle, right_angle = self._active_per_limb(left_raw, right_raw)

        available = [a for a in (left_angle, right_angle) if a is not None]
        if not available:
            return self.progress_pct, self.exercise_feedback, self.correct_form

        avg_angle    = sum(available) / len(available)
        progress_pct = float(np.interp(avg_angle, (self.DOWN_ANGLE, self.UP_ANGLE), (100, 0)))
        form_ok      = avg_angle > 130   # must start with legs extended

        self._tick_per_limb(left_angle, right_angle, self.UP_ANGLE, self.DOWN_ANGLE, inverted=False)

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


if __name__ == "__main__":
    import cv2
    counter = KneeRaiseCounter()
    cap = cv2.VideoCapture(0)
    while cap.isOpened():
        ret, frame = cap.read()
        if not ret:
            break
        result = counter.process_frame(frame)
        cv2.imshow("Knee Raise Counter", result["frame"])
        if cv2.waitKey(10) & 0xFF == ord("q"):
            break
    cap.release()
    cv2.destroyAllWindows()
