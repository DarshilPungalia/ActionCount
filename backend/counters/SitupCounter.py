"""
SitupCounter.py
---------------
Counts sit-up reps using shoulder-hip-ankle angle (bilateral).

COCO-17 keypoints:
  Left  : shoulder=5, hip=11, ankle=15
  Right : shoulder=6, hip=12, ankle=16

UP_ANGLE   : 160°  (body flat on ground — starting / ending position)
DOWN_ANGLE : 145°  (torso raised toward knees)
MODE       : bilateral

Inverted=False — normal direction:
  stage='up'   when avg angle > 160 (body flat)
  stage='down' (+ count) when avg angle < 145 AND stage was 'up'

The tight 15° window captures the small range of motion in a sit-up.
Initial state is always "down" — user must lie flat first.
"""

import numpy as np
from backend.counters.BaseCounter import BaseCounter


class SitupCounter(BaseCounter):

    UP_ANGLE   = 160
    DOWN_ANGLE = 145

    def _compute(self, frame: np.ndarray, landmarks_list: list) -> tuple:
        left_raw  = self.pose_detector.findAngle(frame, 5, 11, 15, landmarks_list, draw=True)
        right_raw = self.pose_detector.findAngle(frame, 6, 12, 16, landmarks_list, draw=False)

        avg_angle = self._avg_angles(left_raw, right_raw)
        if avg_angle is None:
            return self.progress_pct, self.exercise_feedback, self.correct_form

        # 100% when body is flat (large angle), 0% when torso is raised (small angle)
        progress_pct = float(np.interp(avg_angle, (self.DOWN_ANGLE, self.UP_ANGLE), (100, 0)))
        form_ok      = avg_angle > 155   # must start lying flat

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
    counter = SitupCounter()
    cap = cv2.VideoCapture(0)
    while cap.isOpened():
        ret, frame = cap.read()
        if not ret:
            break
        result = counter.process_frame(frame)
        cv2.imshow("Sit-up Counter", result["frame"])
        if cv2.waitKey(10) & 0xFF == ord("q"):
            break
    cap.release()
    cv2.destroyAllWindows()
