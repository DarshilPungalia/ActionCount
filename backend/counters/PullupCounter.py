"""
PullupCounter.py
----------------
Counts pull-up reps using shoulder-elbow-wrist angle (bilateral, inverted).

COCO-17 keypoints:
  Left arm  : shoulder=5, elbow=7, wrist=9
  Right arm : shoulder=6, elbow=8, wrist=10

UP_ANGLE   : 70°   (elbows bent — chin at bar)
DOWN_ANGLE : 140°  (arms extended — hanging position)
MODE       : bilateral, inverted=True

Inverted=True:
  stage='up'   when avg angle < 70  (fully contracted, chin over bar)
  stage='down' (+ count) when avg angle > 140 AND stage was 'up'

Initial state is always "down" (hanging) — user must pull up first.
"""

import numpy as np
from backend.counters.BaseCounter import BaseCounter


class PullupCounter(BaseCounter):

    UP_ANGLE   = 70
    DOWN_ANGLE = 140

    def _compute(self, frame: np.ndarray, landmarks_list: list) -> tuple:
        left_raw  = self.pose_detector.findAngle(frame, 5,  7,  9,  landmarks_list, draw=True)
        right_raw = self.pose_detector.findAngle(frame, 6,  8,  10, landmarks_list, draw=False)

        avg_angle = self._avg_angles(left_raw, right_raw)
        if avg_angle is None:
            return self.progress_pct, self.exercise_feedback, self.correct_form

        # 100% when fully pulled up (small angle), 0% when hanging (large angle)
        progress_pct = float(np.interp(avg_angle, (self.UP_ANGLE, self.DOWN_ANGLE), (100, 0)))
        form_ok      = avg_angle > 100   # hanging position unlocks form

        self._tick_bilateral(avg_angle, self.UP_ANGLE, self.DOWN_ANGLE, inverted=True)

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


if __name__ == "__main__":
    import cv2
    counter = PullupCounter()
    cap = cv2.VideoCapture(0)
    while cap.isOpened():
        ret, frame = cap.read()
        if not ret:
            break
        result = counter.process_frame(frame)
        cv2.imshow("Pull-up Counter", result["frame"])
        if cv2.waitKey(10) & 0xFF == ord("q"):
            break
    cap.release()
    cv2.destroyAllWindows()
