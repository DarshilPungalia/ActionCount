"""
LateralRaiseCounter.py
----------------------
Counts lateral-raise reps using hip-shoulder-elbow angle (bilateral).

COCO-17 keypoints:
  Left  : hip=11, shoulder=5, elbow=7
  Right : hip=12, shoulder=6, elbow=8

UP_ANGLE   : 80°   (arms raised to shoulder height)
DOWN_ANGLE : 30°   (arms hanging by side)
MODE       : bilateral

Inverted=False — normal direction:
  stage='up'   when avg angle > 80 (arms raised)
  stage='down' (+ count) when avg angle < 30 AND stage was 'up'

form_ok requires arms to be down (angle < 40) to establish the starting
position before any raise is counted.
Initial state is always "down" — user must raise arms first.
"""

import numpy as np
from backend.counters.BaseCounter import BaseCounter


class LateralRaiseCounter(BaseCounter):

    UP_ANGLE   = 80
    DOWN_ANGLE = 30

    def _compute(self, frame: np.ndarray, landmarks_list: list) -> tuple:
        left_raw  = self.pose_detector.findAngle(frame, 11, 5, 7, landmarks_list, draw=True)
        right_raw = self.pose_detector.findAngle(frame, 12, 6, 8, landmarks_list, draw=False)

        avg_angle = self._avg_angles(left_raw, right_raw)
        if avg_angle is None:
            return self.progress_pct, self.exercise_feedback, self.correct_form

        progress_pct = float(np.interp(avg_angle, (self.DOWN_ANGLE, self.UP_ANGLE), (0, 100)))
        form_ok      = avg_angle < 40   # start with arms down to unlock

        self._tick_bilateral(avg_angle, self.UP_ANGLE, self.DOWN_ANGLE, inverted=False)

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


if __name__ == "__main__":
    import cv2
    counter = LateralRaiseCounter()
    cap = cv2.VideoCapture(0)
    while cap.isOpened():
        ret, frame = cap.read()
        if not ret:
            break
        result = counter.process_frame(frame)
        cv2.imshow("Lateral Raise Counter", result["frame"])
        if cv2.waitKey(10) & 0xFF == ord("q"):
            break
    cap.release()
    cv2.destroyAllWindows()
