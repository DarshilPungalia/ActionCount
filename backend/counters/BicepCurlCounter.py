"""
BicepCurlCounter.py
-------------------
Counts bicep-curl reps using shoulder-elbow-wrist angle (bilateral, inverted).

Keypoints  : left  5-7-9   |  right  6-8-10
UP_ANGLE   : 60°   (arm fully curled — small angle = "up" position)
DOWN_ANGLE : 160°  (arm fully extended — large angle = "down" / rest)
MODE       : bilateral

INVERTED NOTE
-------------
UP_ANGLE < DOWN_ANGLE, so:
  - Stage "up"  is set when angle < UP_ANGLE  (arm curled)
  - Count fires when angle > DOWN_ANGLE while stage == "up" (arm drops back)
The _tick_bilateral logic in BaseCounter handles this automatically.
"""

import numpy as np
from counters.BaseCounter import BaseCounter
from PoseDetector import PoseDetector


class BicepCurlCounter(BaseCounter):

    LEFT_KPS   = [5, 7, 9]
    RIGHT_KPS  = [6, 8, 10]
    UP_ANGLE   = 60
    DOWN_ANGLE = 160
    MODE       = "bilateral"

    def _compute(self, frame: np.ndarray, kps: np.ndarray) -> dict:
        left_angle  = self.detector.findAngle(kps, *self.LEFT_KPS)
        right_angle = self.detector.findAngle(kps, *self.RIGHT_KPS)

        if left_angle is None or right_angle is None:
            return self._make_result(frame, angle=None)

        angle = self._update_count(
            left_angle, right_angle,
            self.UP_ANGLE, self.DOWN_ANGLE,
            self.MODE,
        )

        frame = self.detector._draw_skeleton(frame, kps)
        frame = self._draw_overlays(frame, angle)
        return self._make_result(frame, angle)
