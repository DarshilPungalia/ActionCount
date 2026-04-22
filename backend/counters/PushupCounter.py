"""
PushupCounter.py
----------------
Counts push-up reps using shoulder-elbow-wrist angle (bilateral).

COCO-17 keypoints:
  Left arm  : shoulder=5, elbow=7, wrist=9
  Right arm : shoulder=6, elbow=8, wrist=10

UP_ANGLE   : 160°  (arms extended at the top)
DOWN_ANGLE : 130°  (elbows bent at the bottom, chest lowered)
MODE       : bilateral

Count-at-up — rep is completed when returning to arms extended:
  stage='down' when avg angle < DOWN_ANGLE (chest lowered)
  stage='up' (+ count) when avg angle > UP_ANGLE AND stage was 'down'

Initial state is always "down" — user must lower first, then extend to count.
"""

import numpy as np
from backend.counters.BaseCounter import BaseCounter


class PushupCounter(BaseCounter):

    UP_ANGLE   = 160
    DOWN_ANGLE = 130

    def _compute(self, frame: np.ndarray, landmarks_list: list) -> tuple:
        left_raw  = self.pose_detector.findAngle(frame, 5,  7,  9,  landmarks_list, draw=True)
        right_raw = self.pose_detector.findAngle(frame, 6,  8,  10, landmarks_list, draw=False)

        avg_angle = self._avg_angles(left_raw, right_raw)
        if avg_angle is None:
            return self.progress_pct, self.exercise_feedback, self.correct_form

        progress_pct = float(np.interp(avg_angle, (self.DOWN_ANGLE, self.UP_ANGLE), (100, 0)))
        form_ok      = avg_angle > 140   # arms must be reasonably extended to start

        # Count-at-up: rep completes when the user pushes back up.
        # stage='down' is set at the bottom; count fires on the return up.
        if avg_angle < self.DOWN_ANGLE:
            self.stage = "down"
        elif avg_angle > self.UP_ANGLE and self.stage == "down":
            self.stage = "up"
            self._debounced_increment()

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
    counter = PushupCounter()
    cap = cv2.VideoCapture(0)
    while cap.isOpened():
        ret, frame = cap.read()
        if not ret:
            break
        result = counter.process_frame(frame)
        cv2.imshow("Push-up Counter", result["frame"])
        if cv2.waitKey(10) & 0xFF == ord("q"):
            break
    cap.release()
    cv2.destroyAllWindows()
