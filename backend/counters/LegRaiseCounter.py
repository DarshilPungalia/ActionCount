"""
LegRaiseCounter.py
------------------
Counts leg-raise reps using shoulder-hip-ankle angle (per_limb).

Keypoints  : left  5-11-15   |  right  6-12-16
UP_ANGLE   : 160°  (legs lowered — lying flat)
DOWN_ANGLE : 130°  (legs raised to ~45° or higher)
MODE       : per_limb

Each leg is tracked independently; every full single-leg raise counts.
"""

import numpy as np
from counters.BaseCounter import BaseCounter
from PoseDetector import PoseDetector


class LegRaiseCounter(BaseCounter):

    LEFT_KPS   = [5, 11, 15]
    RIGHT_KPS  = [6, 12, 16]
    UP_ANGLE   = 160
    DOWN_ANGLE = 130
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
