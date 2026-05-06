"""
calorie_tracker.py
------------------
Sends a camera frame to Gemini Vision (gemini-2.0-flash) → parses calorie JSON →
persists structured result to MongoDB. No images saved to disk.

Environment variables (.env):
  GOOGLE_API_KEY  — required (same key used by the chatbot and Friday agent)
"""

from __future__ import annotations

import base64
import json
import os
from datetime import datetime

import cv2
from dotenv import load_dotenv

load_dotenv()

_GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY", "")
_MODEL          = "gemini-2.0-flash"
_TIMEOUT        = 30.0   # seconds; vision calls can be slower than text

_SYSTEM_PROMPT = (
    "You are a nutrition assistant. The user has taken a photo of food. "
    "Estimate the calorie content of everything visible in the image. "
    "Return ONLY valid JSON — no markdown, no explanation. "
    'Schema: {"foods": [{"name": string, "portion": string, "calories": number}], '
    '"total_calories": number, "confidence": "low"|"medium"|"high", "notes": string}'
)


def _encode_frame(frame_bgr) -> str:
    """JPEG-encode a BGR numpy array → base64 string."""
    ok, buf = cv2.imencode(".jpg", frame_bgr, [cv2.IMWRITE_JPEG_QUALITY, 85])
    if not ok:
        raise ValueError("Failed to JPEG-encode frame")
    return base64.b64encode(buf.tobytes()).decode("utf-8")



def _repair_json(raw: str) -> str:
    """Best-effort repair for truncated JSON — closes open strings/brackets."""
    raw = raw.strip()
    # Close an unterminated string literal first
    in_str = False
    escape = False
    for ch in raw:
        if escape:     escape = False; continue
        if ch == '\\': escape = True;  continue
        if ch == '"': in_str = not in_str
    if in_str:
        raw += '"'
    # Close unclosed brackets/braces
    depth: list[str] = []
    in_str = False
    escape = False
    for ch in raw:
        if escape:     escape = False; continue
        if ch == '\\': escape = True;  continue
        if ch == '"': in_str = not in_str; continue
        if in_str: continue
        if ch in ('{', '['):   depth.append('}' if ch == '{' else ']')
        elif ch in ('}', ']') and depth: depth.pop()
    raw += ''.join(reversed(depth))
    return raw


def scan_food_from_frame(frame_bgr, username: str) -> dict:
    """
    Run food calorie estimation on a BGR camera frame using Gemini Vision.

    Returns a dict matching the calorie_result schema:
      {foods, total_calories, confidence, notes, log_id?}
    On error returns {error: str, message: str}.
    """
    if not _GOOGLE_API_KEY:
        return {
            "error":   "not_configured",
            "message": "GOOGLE_API_KEY is not set in .env.",
        }

    raw = ""
    try:
        from google import genai                          
        from google.genai import types as genai_types    

        client = genai.Client(api_key=_GOOGLE_API_KEY)

        image_b64  = _encode_frame(frame_bgr)
        image_part = genai_types.Part.from_bytes(
            data=base64.b64decode(image_b64),
            mime_type="image/jpeg",
        )

        response = client.models.generate_content(
            model=_MODEL,
            contents=[_SYSTEM_PROMPT, image_part],
            config=genai_types.GenerateContentConfig(
                temperature=0.2,
                max_output_tokens=1024,   # was 512 — caused truncation
            ),
        )

        raw = response.text.strip()

        # Strip markdown fences if the model wraps JSON in ```json … ```
        if raw.startswith("```"):
            raw = raw.split("```")[1]
            if raw.startswith("json"):
                raw = raw[4:]
            raw = raw.strip()

        # Attempt to parse; if it fails, try JSON repair before giving up
        try:
            result = json.loads(raw)
        except json.JSONDecodeError:
            repaired = _repair_json(raw)
            try:
                result = json.loads(repaired)
                print(f"[CalorieTracker] JSON was truncated — repaired and parsed successfully.")
            except json.JSONDecodeError as exc2:
                print(f"[CalorieTracker] JSON parse error (even after repair): {exc2}\nRaw: {raw!r}")
                return {"error": "parse_failed", "message": "Could not parse nutrition data from image."}

    except Exception as exc:
        print(f"[CalorieTracker] Gemini error: {exc}")
        return {"error": "scan_failed", "message": str(exc)}

    # ── Persist to MongoDB (best-effort) ──────────────────────────────────────
    try:
        from backend.utils import db

        entry = {
            "timestamp":      datetime.utcnow().isoformat(),
            "foods":          result.get("foods", []),
            "total_calories": result.get("total_calories", 0),
            "confidence":     result.get("confidence", "low"),
            "notes":          result.get("notes", ""),
        }
        stored = db.log_calorie_entry(username, entry)
        result["log_id"] = stored.get("log_id")

        food_names = ", ".join(f["name"] for f in result.get("foods", []))
        db.log_fulfilled_request(
            username, "calorie_scan",
            f"Scanned: {food_names} ({result.get('total_calories', 0)} kcal)",
            stored.get("log_id"),
        )
    except Exception as exc:
        print(f"[CalorieTracker] DB write error: {exc}")

    return result
