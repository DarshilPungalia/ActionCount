"""
calorie_tracker.py
------------------
Sends a camera frame to Azure AI Foundry (vision model) → parses calorie JSON →
persists structured result to MongoDB. No images saved to disk.
"""

from __future__ import annotations

import base64
import json
import os
from datetime import datetime
from typing import Optional

import cv2
from dotenv import load_dotenv

load_dotenv()

_ENDPOINT = os.getenv("AZURE_FOUNDRY_ENDPOINT", "")
_API_KEY  = os.getenv("AZURE_FOUNDRY_API_KEY", "")
_MODEL    = os.getenv("AZURE_FOUNDRY_MODEL", "gpt-4o")
_TIMEOUT  = 8.0

_SYSTEM_PROMPT = (
    "You are a nutrition assistant. The user has taken a photo of food. "
    "Estimate the calorie content of everything visible in the image. "
    "Return ONLY valid JSON. No markdown. No explanation. "
    'Schema: {"foods": [{"name": string, "portion": string, "calories": number}], '
    '"total_calories": number, "confidence": "low"|"medium"|"high", "notes": string}'
)


def _encode_frame(frame_bgr) -> str:
    """JPEG-encode a BGR numpy array → base64 string."""
    ok, buf = cv2.imencode(".jpg", frame_bgr, [cv2.IMWRITE_JPEG_QUALITY, 85])
    if not ok:
        raise ValueError("Failed to JPEG-encode frame")
    return base64.b64encode(buf.tobytes()).decode("utf-8")


def scan_food_from_frame(frame_bgr, username: str) -> dict:
    """
    Run food calorie estimation on a camera frame.

    Returns a dict matching the calorie_result WebSocket schema:
      {foods, total_calories, confidence, notes}
    On error returns {error: str, message: str}.
    """
    if not _ENDPOINT or not _API_KEY:
        return {"error": "not_configured", "message": "Azure AI Foundry is not configured."}

    try:
        import httpx

        image_b64 = _encode_frame(frame_bgr)

        payload = {
            "model": _MODEL,
            "messages": [
                {"role": "system", "content": _SYSTEM_PROMPT},
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": "What are the estimated calories in this meal?"},
                        {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{image_b64}"}},
                    ],
                },
            ],
            "max_tokens": 512,
        }

        headers = {
            "api-key": _API_KEY,
            "Content-Type": "application/json",
        }

        # Azure AI Foundry endpoint format:
        # https://<resource>.openai.azure.com/openai/deployments/<model>/chat/completions?api-version=...
        url = f"{_ENDPOINT.rstrip('/')}/openai/deployments/{_MODEL}/chat/completions?api-version=2024-02-01"

        resp = httpx.post(url, json=payload, headers=headers, timeout=_TIMEOUT)
        resp.raise_for_status()

        content = resp.json()["choices"][0]["message"]["content"].strip()
        result  = json.loads(content)

    except httpx.TimeoutException:
        return {"error": "timeout", "message": "That took too long, try again."}
    except Exception as exc:
        print(f"[CalorieTracker] error: {exc}")
        return {"error": "scan_failed", "message": str(exc)}

    # Persist to MongoDB (best-effort — errors don't kill the result)
    try:
        from backend.utils import db  # noqa: PLC0415
        entry = {
            "timestamp":      datetime.utcnow().isoformat(),
            "foods":          result.get("foods", []),
            "total_calories": result.get("total_calories", 0),
            "confidence":     result.get("confidence", "low"),
            "notes":          result.get("notes", ""),
        }
        stored = db.log_calorie_entry(username, entry)
        result["log_id"] = stored.get("log_id")

        # Log as a fulfilled request
        food_names = ", ".join(f["name"] for f in result.get("foods", []))
        db.log_fulfilled_request(
            username, "calorie_scan",
            f"Scanned food: {food_names} ({result.get('total_calories', 0)} kcal)",
            stored.get("log_id"),
        )
    except Exception as exc:
        print(f"[CalorieTracker] DB write error: {exc}")

    return result
