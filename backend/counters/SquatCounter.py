"""
SquatCounter.py
---------------
Counts squat reps using hip-knee-ankle angle (bilateral).

Keypoints  : left  11-13-15  |  right  12-14-16
UP_ANGLE   : 160°  (standing — legs nearly straight)
DOWN_ANGLE : 110°  (at the bottom of the squat)
MODE       : bilateral
"""

import numpy as np
from counters.BaseCounter import BaseCounter
from PoseDetector import PoseDetector


class SquatCounter(BaseCounter):

    LEFT_KPS   = [11, 13, 15]
    RIGHT_KPS  = [12, 14, 16]
    UP_ANGLE   = 160
    DOWN_ANGLE = 110
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
