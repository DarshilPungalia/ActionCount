"""
CrunchCounter.py
----------------
Counts crunch reps using shoulder-hip-ankle angle (bilateral, inverted).

COCO-17 keypoints:
  Left  : shoulder=5, hip=11, ankle=15
  Right : shoulder=6, hip=12, ankle=16

UP_ANGLE   : 150  (crunched / contracted)
DOWN_ANGLE : 170  (body flat / relaxed)
MODE       : bilateral, inverted=True

  stage='up'   when avg angle < 150 (crunched)
  stage='down' (+ count) when avg angle > 170 AND stage was 'up'
"""

import numpy as np
from backend.counters.BaseCounter import BaseCounter


class CrunchCounter(BaseCounter):

    UP_ANGLE   = 150
    DOWN_ANGLE = 170

    def _compute(self, frame: np.ndarray, landmarks_list: list) -> tuple:
        left_raw  = self.pose_detector.findAngle(frame, 5, 11, 15, landmarks_list, draw=True)
        right_raw = self.pose_detector.findAngle(frame, 6, 12, 16, landmarks_list, draw=False)

        avg_angle = self._avg_angles(left_raw, right_raw)
        if avg_angle is None:
            return self.progress_pct, self.exercise_feedback, self.correct_form

        progress_pct = float(np.interp(avg_angle, (self.UP_ANGLE, self.DOWN_ANGLE), (100, 0)))
        form_ok      = avg_angle > 165

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
    counter = CrunchCounter()
    cap = cv2.VideoCapture(0)
    while cap.isOpened():
        ret, frame = cap.read()
        if not ret:
            break
        result = counter.process_frame(frame)
        cv2.imshow("Crunch Counter", result["frame"])
        if cv2.waitKey(10) & 0xFF == ord("q"):
            break
    cap.release()
    cv2.destroyAllWindows()
