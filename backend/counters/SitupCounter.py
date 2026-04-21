"""
SitupCounter.py
---------------
Counts sit-up reps using shoulder-hip-ankle angle (bilateral).

Keypoints  : left  5-11-15   |  right  6-12-16
UP_ANGLE   : 160°  (lying flat)
DOWN_ANGLE : 145°  (torso raised to the top of the sit-up)
MODE       : bilateral

NOTE: The angle range is tight (160→145) because the shoulder-hip-ankle
angle changes only slightly during a sit-up. Adjust per your camera angle.
"""

import numpy as np
from counters.BaseCounter import BaseCounter
from PoseDetector import PoseDetector


class SitupCounter(BaseCounter):

    LEFT_KPS   = [5, 11, 15]
    RIGHT_KPS  = [6, 12, 16]
    UP_ANGLE   = 160
    DOWN_ANGLE = 145
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
