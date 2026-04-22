"""
SquatCounter.py
---------------
Counts squat reps using hip-knee-ankle angle (bilateral).

COCO-17 keypoints:
  Left leg  : hip=11, knee=13, ankle=15
  Right leg : hip=12, knee=14, ankle=16

UP_ANGLE   : 160°  (standing — legs nearly straight)
DOWN_ANGLE : 110°  (knees bent past threshold)
MODE       : bilateral

Count-at-up — rep is completed when returning to standing:
  stage='down' when avg angle < DOWN_ANGLE (squatting)
  stage='up' (+ count) when avg angle > UP_ANGLE AND stage was 'down'

Initial state is always "down" — user must squat first, then stand to count.
"""

import numpy as np
from backend.counters.BaseCounter import BaseCounter


class SquatCounter(BaseCounter):

    UP_ANGLE   = 160
    DOWN_ANGLE = 110

    def _compute(self, frame: np.ndarray, landmarks_list: list) -> tuple:
        left_raw  = self.pose_detector.findAngle(frame, 11, 13, 15, landmarks_list, draw=True)
        right_raw = self.pose_detector.findAngle(frame, 12, 14, 16, landmarks_list, draw=False)

        avg_angle = self._avg_angles(left_raw, right_raw)
        if avg_angle is None:
            return self.progress_pct, self.exercise_feedback, self.correct_form

        progress_pct = float(np.interp(avg_angle, (self.DOWN_ANGLE, self.UP_ANGLE), (100, 0)))
        form_ok      = avg_angle > 130   # standing position unlocks form

        # Count-at-up: rep completes when the user returns to standing.
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
    counter = SquatCounter()
    cap = cv2.VideoCapture(0)
    while cap.isOpened():
        ret, frame = cap.read()
        if not ret:
            break
        result = counter.process_frame(frame)
        cv2.imshow("Squat Counter", result["frame"])
        if cv2.waitKey(10) & 0xFF == ord("q"):
            break
    cap.release()
    cv2.destroyAllWindows()
