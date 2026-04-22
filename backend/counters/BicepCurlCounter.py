"""
BicepCurlCounter.py
-------------------
Counts bicep curl reps using shoulder-elbow-wrist angle (bilateral, inverted).

COCO-17 keypoints:
  Left arm  : shoulder=5, elbow=7, wrist=9
  Right arm : shoulder=6, elbow=8, wrist=10

UP_ANGLE   : 60°   (fully curled — arm contracted)
DOWN_ANGLE : 160°  (arm straight — fully extended)
MODE       : bilateral, inverted=True

Inverted=True:
  stage='up'   when avg angle < 60  (fully curled)
  stage='down' (+ count) when avg angle > 160 AND stage was 'up'

Initial state is always "down" (arm extended) — user must curl up first.
"""

import numpy as np
from backend.counters.BaseCounter import BaseCounter


class BicepCurlCounter(BaseCounter):

    UP_ANGLE   = 60
    DOWN_ANGLE = 160

    def _compute(self, frame, landmarks_list) -> tuple:
        left_raw  = self.pose_detector.findAngle(frame, 5,  7,  9,  landmarks_list, draw=True)
        right_raw = self.pose_detector.findAngle(frame, 6,  8,  10, landmarks_list, draw=False)

        avg_angle = self._avg_angles(left_raw, right_raw)
        if avg_angle is None:
            return self.progress_pct, self.exercise_feedback, self.correct_form

        # 100% = fully curled (small angle), 0% = arm straight (large angle)
        progress_pct = float(np.interp(avg_angle, (self.UP_ANGLE, self.DOWN_ANGLE), (100, 0)))
        form_ok      = avg_angle > 120   # arm must start reasonably extended

        self._tick_bilateral(avg_angle, self.UP_ANGLE, self.DOWN_ANGLE, inverted=True)

        if self.correct_form:
            if self.stage == "up" and self.counter > 0:
                # "Up" = curled — only show after at least one full rep
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
    counter = BicepCurlCounter()
    cap = cv2.VideoCapture(0)
    while cap.isOpened():
        ret, frame = cap.read()
        if not ret:
            break
        result = counter.process_frame(frame)
        cv2.imshow("Bicep Curl Counter", result["frame"])
        if cv2.waitKey(10) & 0xFF == ord("q"):
            break
    cap.release()
    cv2.destroyAllWindows()