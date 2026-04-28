from pyzbar.pyzbar import decode
from ultralytics import YOLO
from torch.cuda import is_available
from functools import cache
import numpy as np
import cv2
from dotenv import load_dotenv
import os

load_dotenv()
_YOLO_PATH = os.getenv("BAR_YOLO_PATH")

@cache
def get_yolo():
    """
    Fetches the YOLO on the first instance and caches it for all the subsequent calls.
    """
    model = YOLO.from_pretrained(_YOLO_PATH)
    return model


class BarReader():
    def __init__(self):
        self.device = "cuda" if is_available() else "cpu"
        self.model = get_yolo()

    @staticmethod
    def _get_bbox(results):
        x1, y1, x2, y2 = None, None, None, None

        for r in results:
            for box in r.boxes:
                x1, y1, x2, y2 = box.xyxy[0].tolist()
                
        return x1, y1, x2, y2    

    @staticmethod
    def _crop_with_padding(frame, box, padding=20):
        x1, y1, x2, y2 = box
        h, w = frame.shape[:2]

        # Clamp to image boundaries
        x1 = max(0, x1 - padding)
        y1 = max(0, y1 - padding)
        x2 = min(w, x2 + padding)
        y2 = min(h, y2 + padding)

        return frame[x1:x2][y1:y2]    

    def _detect_bar(self, frame: np.ndarray):
        if not isinstance(frame, np.ndarray):
            frame = np.array(frame)
        
        results = self.model.predict(frame)
        x1, y1, x2, y2 = self._get_bbox(results)

        cropped_frame = self._crop_with_padding(frame, (x1, y1, x2, y2), padding=0)

        return cropped_frame

    def _read_bar(self, frame: np.ndarray):
        if not isinstance(frame, np.ndarray):
            frame = np.array(frame)

        cropped_frame = self._detect_bar(frame=frame)
        gray = cv2.cvtColor(cropped_frame, cv2.COLOR_RGB2GRAY)

        barcodes = decode(gray)

        for barcode in barcodes:
            barcode_data = barcode.data.decode("utf-8")
            barcode_type = barcode.type

            print("Barcode Data:", barcode_data)
            print("Barcode Type:", barcode_type)

    