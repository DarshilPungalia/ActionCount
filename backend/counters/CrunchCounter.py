"""
CrunchCounter.py
----------------
Counts crunch reps using shoulder-hip-ankle angle (bilateral, inverted).

Keypoints  : left  5-11-15   |  right  6-12-16
UP_ANGLE   : 150°  (torso lifted — smaller angle triggers "up")
DOWN_ANGLE : 170°  (lying flat — larger angle = count fires)
MODE       : bilateral

INVERTED NOTE
-------------
UP_ANGLE < DOWN_ANGLE:
  - "up" stage when angle < 150° (crunch contracted)
  - Count fires when angle > 170° (fully reclined)
"""

import numpy as np
from counters.BaseCounter import BaseCounter
from PoseDetector import PoseDetector


class CrunchCounter(BaseCounter):

    LEFT_KPS   = [5, 11, 15]
    RIGHT_KPS  = [6, 12, 16]
    UP_ANGLE   = 150
    DOWN_ANGLE = 170
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
