"""
PullupCounter.py
----------------
Counts pull-up reps using shoulder-elbow-wrist angle (bilateral, inverted).

Keypoints  : left  5-7-9   |  right  6-8-10
UP_ANGLE   : 70°   (elbows bent at the top of the pull-up)
DOWN_ANGLE : 140°  (arms extended at the hang position)
MODE       : bilateral

INVERTED NOTE
-------------
UP_ANGLE < DOWN_ANGLE:
  - "up" stage when angle drops below 70° (chin at bar, elbows fully bent)
  - Count fires when angle rises above 140° (arms extended back at bottom)
"""

import numpy as np
from counters.BaseCounter import BaseCounter
from PoseDetector import PoseDetector


class PullupCounter(BaseCounter):

    LEFT_KPS   = [5, 7, 9]
    RIGHT_KPS  = [6, 8, 10]
    UP_ANGLE   = 70
    DOWN_ANGLE = 140
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
