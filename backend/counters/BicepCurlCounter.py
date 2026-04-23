"""
BicepCurlCounter.py
-------------------
Counts bicep curl reps using shoulder-elbow-wrist angle.
Each arm is tracked independently — a rep counts when either arm completes a
full down → up → down cycle. Works correctly for:
  - Single-arm workouts (one arm always occluded)
  - Front-view where one arm may be low-confidence
  - Both arms curling simultaneously (counts 2 per double curl)

COCO-17 keypoints:
  Left arm  : shoulder=5, elbow=7, wrist=9
  Right arm : shoulder=6, elbow=8, wrist=10

UP_ANGLE   : 50°   (fully curled — relaxed to handle front-view where the
                     shoulder-elbow-wrist angle can collapse to ~10-20°)
DOWN_ANGLE : 150°  (arm sufficiently extended — < 180° so normal extension
                     always registers as "down")
MODE       : per-limb, inverted=True

Cycle per arm: down → up → down  (each completion = +1 rep)
  Initial left_stage = right_stage = 'down'
"""

import numpy as np
from backend.counters.BaseCounter import BaseCounter


class BicepCurlCounter(BaseCounter):

    UP_ANGLE   = 50
    DOWN_ANGLE = 150

    def __init__(self):
        super().__init__()
        # Both arms start extended (down) so first curl up → back down counts
        self.left_stage  = "down"
        self.right_stage = "down"

    def _compute(self, frame, landmarks_list) -> tuple:
        left_raw  = self.pose_detector.findAngle(frame, 5,  7,  9,  landmarks_list, draw=True)
        right_raw = self.pose_detector.findAngle(frame, 6,  8,  10, landmarks_list, draw=False)

        # Smooth each side independently — neither arm blocks the other
        left  = self._smooth_angle("left",  left_raw)
        right = self._smooth_angle("right", right_raw)

        # Need at least one arm to do anything
        if left is None and right is None:
            return self.progress_pct, self.exercise_feedback, self.correct_form

        # Each arm gets its own state machine tick; shared counter incremented per arm per rep
        self._tick_per_limb(left, right, self.UP_ANGLE, self.DOWN_ANGLE, inverted=True)

        # Progress bar: use whichever arm(s) are visible
        if left is not None and right is not None:
            display_angle = (left + right) / 2.0
        elif left is not None:
            display_angle = left
        else:
            display_angle = right

        # 100% = fully curled (small angle), 0% = arm extended (large angle)
        progress_pct = float(np.interp(display_angle, (self.UP_ANGLE, self.DOWN_ANGLE), (100, 0)))

        # form_ok latches correct_form=True once any arm is reasonably extended
        form_ok = display_angle > 100

        # Feedback: "Up" if either arm is curled, "Down" otherwise
        if self.correct_form:
            if self.left_stage == "up" or self.right_stage == "up":
                feedback = "Up"
            else:
                feedback = "Down"
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