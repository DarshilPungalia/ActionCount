"""
friday_tts.py
-------------
Azure Cognitive Services Text-to-Speech REST wrapper for the Friday AI assistant.

- `speak(text)` → raw MP3 bytes (sync, safe to call from a thread)
- `to_ws_envelope(mp3_bytes, text_hint)` → dict ready for WebSocket send_json

Config priority (set in .env):
  1. AZURE_TTS_REGION   — e.g. "eastus2"  (PREFERRED)
     + AZURE_TTS_KEY
     → uses https://<region>.tts.speech.microsoft.com/cognitiveservices/v1
  2. AZURE_TTS_ENDPOINT — custom endpoint (fallback)
     + AZURE_TTS_KEY
     → appends /cognitiveservices/v1 if it's a base URL

Failures are caught and logged — never crash the caller.
"""

from __future__ import annotations

import base64
import os
from typing import Optional

from dotenv import load_dotenv

load_dotenv()

_SPEECH_KEY  = os.getenv("AZURE_TTS_KEY", "")
_TTS_REGION  = os.getenv("AZURE_TTS_REGION", "")       # e.g. "eastus2"
_TTS_BASE    = os.getenv("AZURE_TTS_ENDPOINT", "").rstrip("/")
_VOICE       = os.getenv("AZURE_TTS_VOICE", "en-US-JennyNeural")

# Build the REST URL: prefer region-based URL (reliable), fall back to endpoint
if _TTS_REGION:
    _TTS_URL = f"https://{_TTS_REGION}.tts.speech.microsoft.com/cognitiveservices/v1"
    print(f"[FridayTTS] Using region-based URL: {_TTS_URL}")
elif _TTS_BASE:
    _TTS_URL = f"{_TTS_BASE}/cognitiveservices/v1"
    print(f"[FridayTTS] Using endpoint-based URL: {_TTS_URL}")
else:
    _TTS_URL = ""
    print("[FridayTTS] ⚠  No AZURE_TTS_REGION or AZURE_TTS_ENDPOINT set — TTS disabled")


def speak(text: str) -> Optional[bytes]:
    """
    Call Azure TTS to synthesise `text` → MP3 bytes.
    Returns None on failure (no crash, no fallback TTS).
    """
    if not _SPEECH_KEY:
        print("[FridayTTS] AZURE_TTS_KEY not set — skipping TTS")
        return None
    if not _TTS_URL:
        print("[FridayTTS] No TTS URL configured — skipping TTS")
        return None
    if not text or not text.strip():
        return None

    ssml = (
        f"<speak version='1.0' xmlns='http://www.w3.org/2001/10/synthesis' xml:lang='en-US'>"
        f"<voice name='{_VOICE}'>{text.strip()}</voice>"
        f"</speak>"
    )

    headers = {
        "Ocp-Apim-Subscription-Key": _SPEECH_KEY,
        "Content-Type": "application/ssml+xml",
        "X-Microsoft-OutputFormat": "audio-16khz-128kbitrate-mono-mp3",
        "User-Agent": "ActionCount-Friday",
    }

    try:
        import httpx
        print(f"[FridayTTS] POST {_TTS_URL} ({len(text)} chars)")
        resp = httpx.post(_TTS_URL, content=ssml.encode("utf-8"), headers=headers, timeout=15.0)
        resp.raise_for_status()
        print(f"[FridayTTS] ✅ Got {len(resp.content)} bytes of MP3")
        return resp.content

    except Exception as exc:
        print(f"[FridayTTS] ❌ Azure TTS error: {exc}")
        return None


def to_ws_envelope(mp3_bytes: bytes, text_hint: str = "") -> dict:
    """
    Package MP3 bytes into a WebSocket-safe JSON envelope.

    Schema:
      {"type": "friday_audio", "data": {"audio_b64": "<base64 mp3>", "text_hint": "..."}}
    """
    return {
        "type": "friday_audio",
        "data": {
            "audio_b64": base64.b64encode(mp3_bytes).decode("utf-8"),
            "text_hint": text_hint,
        },
    }


def speaking_indicator(active: bool) -> dict:
    """Return a `friday_speaking` WebSocket message."""
    return {"type": "friday_speaking", "data": {"active": active}}
