import cv2
import numpy as np

# COCO-17 skeleton connections for visualisation 
# Each tuple is (joint_a_idx, joint_b_idx)
_COCO_SKELETON = [
    (0, 1), (0, 2), (1, 3), (2, 4),       # head
    (5, 6),                                 # shoulder–shoulder
    (5, 7), (7, 9),                         # left arm
    (6, 8), (8, 10),                        # right arm
    (5, 11), (6, 12),                       # torso sides
    (11, 12),                               # hip–hip
    (11, 13), (13, 15),                     # left leg
    (12, 14), (14, 16),                     # right leg
]

_CONF_THRESHOLD    = 0.5   
_MAX_INFERENCE_DIM = 640   


class PoseDetectorModified:
    """
    Pose detector backed by RTMPose via rtmlib.Wholebody.

    The public API is identical to the old MediaPipe version so every
    exercise counter and app.py can keep working without changes:

        findPose(img, draw=True)
            Run RTMPose inference on the frame; optionally draw the COCO-17
            skeleton.  Stores keypoints internally.  Returns the (annotated) img.

        findPosition(img, draw=False)
            Return [[id, cx, cy, score], …] for all 17 COCO keypoints.
            score is the raw RTMPose confidence (0–1).  Keypoints with
            score < 0.5 are kept in the list but flagged — findAngle will
            skip them automatically.

        findAngle(img, p1, p2, p3, landmarks_list, draw=True)
            Dot-product angle at joint p2; returns None when any of the three
            keypoints is low-confidence or the vectors degenerate.
    """

    def __init__(self, mode: str = "balanced",
                 backend: str = "onnxruntime",
                 device: str = "cpu"):
        """
        Args:
            mode    : "lightweight" | "balanced" | "performance"
            backend : "onnxruntime" | "opencv"
            device  : "cpu" | "cuda"
        """
        from rtmlib import Wholebody  
        self._model     = Wholebody(mode=mode, backend=backend, device=device)
        self._keypoints = None   
        self._scores    = None      

    # ──────────────────────────────────────────────────────────────────────────
    # Public API
    # ──────────────────────────────────────────────────────────────────────────

    def findPose(self, img: np.ndarray, draw: bool = True) -> np.ndarray:
        """
        Run RTMPose on img.  Stores first-person keypoints internally.

        Frames wider/taller than 640 px are downscaled for inference and the
        keypoints are scaled back to original pixel coordinates before storage.
        """
        h, w = img.shape[:2]

        # ── Downscale for inference if needed ─────────────────────────────────
        scale = min(1.0, _MAX_INFERENCE_DIM / max(h, w))
        if scale < 1.0:
            infer_img = cv2.resize(img, (int(w * scale), int(h * scale)))
        else:
            infer_img = img

        # Returns: keypoints (N, 17, 2), scores (N, 17)
        keypoints, scores = self._model(infer_img)

        if keypoints is None or len(keypoints) == 0:
            self._keypoints = None
            self._scores    = None
            return img

        kps = keypoints[0].astype(np.float32).copy()   
        scr = scores[0].astype(np.float32).copy()       

        if scale < 1.0:
            kps /= scale  

        # Filter low-confidence keypoint 
        for i in range(len(scr)):
            if scr[i] < _CONF_THRESHOLD:
                kps[i] = [0.0, 0.0]

        self._keypoints = kps
        self._scores    = scr

        if draw:
            self._draw_skeleton(img, kps, scr)

        return img

    def findPosition(self, img: np.ndarray, draw: bool = False) -> list:
        """
        Return [[id, cx, cy, score], …] for all 17 COCO keypoints.

        The 4th element (score) is read by findAngle to skip low-confidence
        joints — no manual filtering needed by the caller.
        """
        landmarks_list = []
        if self._keypoints is None:
            return landmarks_list

        for idx, (pt, score) in enumerate(zip(self._keypoints, self._scores)):
            cx, cy = int(pt[0]), int(pt[1])
            landmarks_list.append([idx, cx, cy, float(score)])
            if draw and score >= _CONF_THRESHOLD:
                cv2.circle(img, (cx, cy), 5, (255, 0, 0), cv2.FILLED)

        return landmarks_list

    def findAngle(self, img: np.ndarray,
                  p1: int, p2: int, p3: int,
                  landmarks_list: list,
                  draw: bool = True):
        """
        Dot-product angle at joint p2, between vectors p1→p2 and p3→p2.

        Returns None if:
          • any of the three keypoints has confidence < 0.5
          • either vector has zero magnitude (overlapping or zeroed keypoints)
        """
        # Reject low-confidence joints
        for p in (p1, p2, p3):
            if len(landmarks_list[p]) >= 4 and landmarks_list[p][3] < _CONF_THRESHOLD:
                return None

        x1, y1 = landmarks_list[p1][1], landmarks_list[p1][2]
        x2, y2 = landmarks_list[p2][1], landmarks_list[p2][2]
        x3, y3 = landmarks_list[p3][1], landmarks_list[p3][2]

        ba = np.array([x1 - x2, y1 - y2], dtype=np.float64)
        bc = np.array([x3 - x2, y3 - y2], dtype=np.float64)

        if np.any(np.isnan(np.concatenate([ba, bc]))) \
                or np.linalg.norm(ba) == 0 \
                or np.linalg.norm(bc) == 0:
            return None

        cosine_angle = np.dot(ba, bc) / (np.linalg.norm(ba) * np.linalg.norm(bc))
        cosine_angle = np.clip(cosine_angle, -1.0, 1.0)
        angle = np.degrees(np.arccos(cosine_angle))

        if draw:
            cv2.line(img, (x1, y1), (x2, y2), (255, 255, 255), 3)
            cv2.line(img, (x3, y3), (x2, y2), (255, 255, 255), 3)
            cv2.circle(img, (x1, y1), 10, (0, 0, 255), cv2.FILLED)
            cv2.circle(img, (x1, y1), 15, (0, 0, 255), 2)
            cv2.circle(img, (x2, y2), 10, (0, 0, 255), cv2.FILLED)
            cv2.circle(img, (x2, y2), 15, (0, 0, 255), 2)
            cv2.circle(img, (x3, y3), 10, (0, 0, 255), cv2.FILLED)
            cv2.circle(img, (x3, y3), 15, (0, 0, 255), 2)
            cv2.putText(img, str(int(angle)), (x2 - 50, y2 + 50),
                        cv2.FONT_HERSHEY_PLAIN, 2, (0, 0, 255), 2)

        return angle

    def _draw_skeleton(self, img: np.ndarray,
                       kps: np.ndarray, scores: np.ndarray):
        """Draw COCO-17 bones and keypoint dots onto img in-place."""
        for i, j in _COCO_SKELETON:
            if scores[i] >= _CONF_THRESHOLD and scores[j] >= _CONF_THRESHOLD:
                pt1 = (int(kps[i][0]), int(kps[i][1]))
                pt2 = (int(kps[j][0]), int(kps[j][1]))
                cv2.line(img, pt1, pt2, (0, 255, 0), 2)

        for pt, score in zip(kps, scores):
            if score >= _CONF_THRESHOLD:
                cv2.circle(img, (int(pt[0]), int(pt[1])), 4, (0, 0, 255), cv2.FILLED)


def main():
    """
    Quick smoke-test: open webcam and show RTMPose skeleton.

    Fixes applied (video_pipeline_implementation_plan.md):
    -------------------------------------------------------
    • cap.set(CAP_PROP_BUFFERSIZE, 1)  → eliminates stale-frame accumulation
    • cv2.waitKey(1) instead of (10)   → removes the artificial 10ms/frame floor
      that was gating inference time unnecessarily.
    """
    detector = PoseDetectorModified()
    cap = cv2.VideoCapture(0)
    # Fix: buffer=1 ensures we always process the latest frame, never a stale one
    cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
    while cap.isOpened():
        ret, img = cap.read()
        if ret:
            img = detector.findPose(img, draw=True)
            cv2.imshow("RTMPose", img)
        # Fix: waitKey(1) instead of waitKey(10) — reduces artificial floor from 10ms to ~1ms
        if cv2.waitKey(1) & 0xFF == ord("q"):
            break
    cap.release()
    cv2.destroyAllWindows()


if __name__ == "__main__":
    main()