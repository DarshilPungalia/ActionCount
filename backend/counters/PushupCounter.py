"""
PushupCounter.py
----------------
Counts push-up reps using shoulder-elbow-wrist angle (bilateral).

Keypoints  : left  5-7-9   |  right  6-8-10
UP_ANGLE   : 160°  (arms extended at the top)
DOWN_ANGLE : 130°  (arms bent at the bottom)
MODE       : bilateral
"""

import numpy as np
from counters.BaseCounter import BaseCounter
from PoseDetector import PoseDetector


class PushupCounter(BaseCounter):

    LEFT_KPS   = [5, 7, 9]
    RIGHT_KPS  = [6, 8, 10]
    UP_ANGLE   = 160
    DOWN_ANGLE = 130
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
