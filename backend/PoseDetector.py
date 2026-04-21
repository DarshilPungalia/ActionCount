"""
PoseDetector.py
---------------
Wraps RTMPose (via rtmlib) for keypoint inference.
No counting logic lives here.
"""

import math
import cv2
import numpy as np
from rtmlib import Wholebody


# COCO-17 skeleton connectivity pairs for visualisation
COCO_SKELETON = [
    (0, 1), (0, 2), (1, 3), (2, 4),          # head
    (5, 6),                                    # shoulders
    (5, 7), (7, 9),                            # left arm
    (6, 8), (8, 10),                           # right arm
    (5, 11), (6, 12),                          # torso
    (11, 12),                                  # hips
    (11, 13), (13, 15),                        # left leg
    (12, 14), (14, 16),                        # right leg
]

# Valid mode values passed through to rtmlib.Wholebody
# "lightweight" -> rtmpose-t  |  "balanced" -> rtmpose-s  |  "performance" -> rtmpose-m
_VALID_MODES = {"lightweight", "balanced", "performance"}


class PoseDetector:
    """Thin wrapper around rtmlib.Wholebody for single-person pose estimation."""

    def __init__(self, mode: str = "balanced", backend: str = "onnxruntime", device: str = "cpu"):
        """
        Parameters
        ----------
        mode    : "lightweight" | "balanced" | "performance"
        backend : "onnxruntime" | "openvino" | ...
        device  : "cpu" | "cuda"
        """
        if mode not in _VALID_MODES:
            mode = "balanced"
        self.model = Wholebody(
            mode=mode,
            backend=backend,
            device=device,
        )
        self.conf_threshold = 0.5

        # State filled by findPose(), consumed by findPosition()
        self._raw_keypoints = None
        self._scores = None
        self._scale_factor = 1.0

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def findPose(self, frame: np.ndarray) -> np.ndarray:
        """
        Run inference on *frame*.

        Resizes internally if either dimension > 640 px so the model
        stays fast, but always returns the ORIGINAL frame unchanged.
        """
        h, w = frame.shape[:2]
        if max(h, w) > 640:
            scale = min(640 / w, 640 / h)
            resized = cv2.resize(frame, (int(w * scale), int(h * scale)))
            self._scale_factor = scale
        else:
            resized = frame
            self._scale_factor = 1.0

        result = self.model(resized)

        # rtmlib may return (keypoints, scores) or a dict — handle both
        if isinstance(result, (tuple, list)) and len(result) == 2:
            self._raw_keypoints, self._scores = result
        else:
            self._raw_keypoints = None
            self._scores = None

        return frame  # original frame, untouched

    def findPosition(self, frame: np.ndarray) -> "np.ndarray | None":
        """
        Convert raw inference output to scaled COCO-17 keypoint array.

        RTMPose Wholebody returns 133 keypoints; the first 17 are the
        standard COCO-17 body joints used by all counters.

        Returns None if no person was detected.
        """
        if self._raw_keypoints is None or len(self._raw_keypoints) == 0:
            return None

        # Take the first 17 COCO-17 body keypoints only
        kps  = np.array(self._raw_keypoints[0][:17], dtype=float)   # (17, 2)
        conf = np.array(self._scores[0][:17],         dtype=float)   # (17,)

        # Zero out low-confidence keypoints
        low_conf_mask = conf < self.conf_threshold
        kps[low_conf_mask] = [0.0, 0.0]

        # Scale back to original frame resolution
        kps = kps / self._scale_factor

        return kps

    def findAngle(self, kps: np.ndarray, idx_a: int, idx_b: int, idx_c: int) -> "float | None":
        """
        Compute the interior angle at vertex *idx_b* (degrees).

        Returns None if any of the three points is missing ([0,0] or NaN).
        """
        a, b, c = kps[idx_a], kps[idx_b], kps[idx_c]

        # Reject zeroed / NaN points
        for pt in (a, b, c):
            if np.any(np.isnan(pt)) or (pt[0] == 0 and pt[1] == 0):
                return None

        ba = a - b
        bc = c - b

        norm_ba = np.linalg.norm(ba)
        norm_bc = np.linalg.norm(bc)
        if norm_ba == 0 or norm_bc == 0:
            return None

        cosine = np.dot(ba, bc) / (norm_ba * norm_bc)
        cosine = float(np.clip(cosine, -1.0, 1.0))
        return math.degrees(math.acos(cosine))

    def _draw_skeleton(self, frame: np.ndarray, kps: np.ndarray) -> np.ndarray:
        """
        Draw keypoints and skeleton lines on *frame* (in-place copy).
        Only draws points where x > 0 and y > 0.
        """
        frame = frame.copy()

        # Draw limb connections first (so circles sit on top)
        for i, j in COCO_SKELETON:
            if i < len(kps) and j < len(kps):
                xi, yi = int(kps[i][0]), int(kps[i][1])
                xj, yj = int(kps[j][0]), int(kps[j][1])
                if xi > 0 and yi > 0 and xj > 0 and yj > 0:
                    cv2.line(frame, (xi, yi), (xj, yj), (0, 255, 255), 2, cv2.LINE_AA)

        # Draw filled circles at each visible keypoint
        for idx, (x, y) in enumerate(kps):
            x, y = int(x), int(y)
            if x > 0 and y > 0:
                cv2.circle(frame, (x, y), 5, (0, 0, 255), cv2.FILLED)
                cv2.circle(frame, (x, y), 5, (255, 255, 255), 1, cv2.LINE_AA)

        return frame
