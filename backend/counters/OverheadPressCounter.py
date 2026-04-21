"""
OverheadPressCounter.py
-----------------------
Counts overhead-press reps using hip-shoulder-elbow angle (bilateral).

Keypoints  : left  11-5-7   |  right  12-6-8
UP_ANGLE   : 150°  (arms extended overhead)
DOWN_ANGLE : 100°  (bar / dumbbells at shoulder level)
MODE       : bilateral
"""

import numpy as np
from counters.BaseCounter import BaseCounter
from PoseDetector import PoseDetector


class OverheadPressCounter(BaseCounter):

    LEFT_KPS   = [11, 5, 7]
    RIGHT_KPS  = [12, 6, 8]
    UP_ANGLE   = 150
    DOWN_ANGLE = 100
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
