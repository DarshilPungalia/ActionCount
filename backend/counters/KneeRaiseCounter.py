"""
KneeRaiseCounter.py
-------------------
Counts knee-raise reps using hip-knee-ankle angle (per_limb).

Keypoints  : left  11-13-15   |  right  12-14-16
UP_ANGLE   : 160°  (leg extended / standing)
DOWN_ANGLE : 110°  (knee raised to roughly 90°)
MODE       : per_limb

Each knee raise is counted independently, so alternating knees
accumulate in the same counter.
"""

import numpy as np
from counters.BaseCounter import BaseCounter
from PoseDetector import PoseDetector


class KneeRaiseCounter(BaseCounter):

    LEFT_KPS   = [11, 13, 15]
    RIGHT_KPS  = [12, 14, 16]
    UP_ANGLE   = 160
    DOWN_ANGLE = 110
    MODE       = "per_limb"

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
