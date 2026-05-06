"""
friday_tts.py
-------------
Text-to-Speech for the Friday AI assistant using ElevenLabs Streaming API.

Dependencies:
  pip install httpx

Environment variables (.env):
  ELEVENLABS_API_KEY   — required
  ELEVENLABS_VOICE_ID  — optional, overrides the default voice (Rachel)

Public API (unchanged from Kokoro version):
  speak(text, voice_id)         → raw MP3 bytes (streamed & concatenated)
  to_ws_envelope(mp3, hint)     → WebSocket JSON envelope {type: friday_audio}
  speaking_indicator(active)    → WebSocket JSON envelope {type: friday_speaking}
  stop_speaking()               → signal barge-in: abort current stream mid-chunk

Failures are caught and logged — never crash the caller.
"""

from __future__ import annotations

import base64
import os
import threading
from typing import Optional

_TAG = "[FridayTTS/ElevenLabs]"

# ── ElevenLabs voice catalogue ────────────────────────────────────────────────
# Only FREE premade voices are listed here — library/cloned voices require a
# paid subscription. Set ELEVENLABS_VOICE_ID in .env to use your own voice.
VOICES: dict[str, str] = {
    # ElevenLabs built-in premade voices (free on all plans)
    "Rachel": "21m00Tcm4TlvDq8ikWAM",   # calm, female
    "Adam":   "pNInz6obpgDQGcFmaJgB",   # deep, male
    "Antoni": "ErXwobaYiN019PkySvjV",   # well-rounded, male
    "Elli":   "MF3mGyEYCl7XYWbV9V6O",   # emotional, female
    "Josh":   "TxGEqnHWrfWFTfGW9XjX",   # deep, male
    "Arnold": "VR6AewLTigWG4xSOukaG",   # crispy, male
}

_DEFAULT_VOICE_ID: str = (
    os.getenv("ELEVENLABS_VOICE_ID")
    or VOICES["Rachel"]          # free premade voice fallback
)

_API_KEY: Optional[str] = os.getenv("ELEVENLABS_API_KEY")

_EL_BASE   = "https://api.elevenlabs.io/v1"
_MODEL_ID  = "eleven_multilingual_v2"
_CHUNK_SZ  = 4096   # bytes per read from the streaming response

# ── Global stop flag for barge-in support ────────────────────────────────────
_stop_event = threading.Event()
_speaking   = threading.Event()   # set while a speak() call is active


# ── Public helpers ─────────────────────────────────────────────────────────────

def stop_speaking() -> None:
    """
    Signal the TTS stream to abort after the current chunk.
    Called by STT when VAD detects speech onset while agent is speaking (barge-in).
    """
    _stop_event.set()
    print(f"{_TAG} ⏹  Barge-in signal — aborting stream.")


def is_speaking() -> bool:
    """Return True while a speak() call is currently in progress."""
    return _speaking.is_set()


def speak(
    text: str,
    voice_id: Optional[str] = None,
    *,
    stability: float = 0.50,
    similarity_boost: float = 0.75,
    style: float = 0.0,
    use_speaker_boost: bool = True,
) -> Optional[bytes]:
    """
    Synthesise `text` via ElevenLabs streaming API → raw MP3 bytes.

    - Streams the response and concatenates chunks.
    - Respects `_stop_event` for barge-in interruption between chunks.
    - Returns combined MP3 bytes, or None on failure / empty output.

    Args:
        text:              Text to synthesise.
        voice_id:          ElevenLabs voice ID; defaults to ELEVENLABS_VOICE_ID env var
                           or Sebastian (1SaGpH4wLZDmppsPYVpx).
        stability:         Voice stability (0–1). Higher = more consistent.
        similarity_boost:  Voice clarity / similarity (0–1).
        style:             Speaking style exaggeration (0–1, 0 = off).
        use_speaker_boost: Boost speaker similarity. Recommended True.
    """
    if not text or not text.strip():
        return None

    if not _API_KEY:
        print(f"{_TAG} ❌ ELEVENLABS_API_KEY not set — skipping TTS.")
        return None

    vid = voice_id or _DEFAULT_VOICE_ID
    url = f"{_EL_BASE}/text-to-speech/{vid}/stream"

    payload = {
        "text":    text.strip(),
        "model_id": _MODEL_ID,
        "voice_settings": {
            "stability":          stability,
            "similarity_boost":   similarity_boost,
            "style":              style,
            "use_speaker_boost":  use_speaker_boost,
        },
    }
    headers = {
        "xi-api-key":   _API_KEY,
        "Content-Type": "application/json",
        "Accept":       "audio/mpeg",
    }

    _stop_event.clear()
    _speaking.set()

    mp3_chunks: list[bytes] = []
    try:
        import httpx  # noqa: PLC0415

        print(f"{_TAG} Synthesising {len(text)} chars, voice={vid!r} …")
        with httpx.stream(
            "POST",
            url,
            json=payload,
            headers=headers,
            timeout=30.0,
        ) as resp:
            if resp.status_code != 200:
                body = resp.read().decode("utf-8", errors="replace")
                print(f"{_TAG} ❌ ElevenLabs HTTP {resp.status_code}: {body[:200]}")
                return None

            for chunk in resp.iter_bytes(chunk_size=_CHUNK_SZ):
                if _stop_event.is_set():
                    print(f"{_TAG} ⏹  Stopped mid-stream (barge-in).")
                    break
                if chunk:
                    mp3_chunks.append(chunk)

    except Exception as exc:
        print(f"{_TAG} ❌ Streaming error: {exc}")
        return None
    finally:
        _speaking.clear()

    if not mp3_chunks:
        print(f"{_TAG} ⚠  No audio chunks received.")
        return None

    combined = b"".join(mp3_chunks)
    print(f"{_TAG} ✅ Received {len(combined):,} bytes of MP3 audio.")
    return combined


# ── WebSocket envelope helpers (same public API as before) ────────────────────

def to_ws_envelope(mp3_bytes: bytes, text_hint: str = "") -> dict:
    """
    Package MP3 bytes into a WebSocket-safe JSON envelope.

    Schema:
      {"type": "friday_audio", "data": {"audio_b64": "<base64 mp3>",
                                        "text_hint": "...",
                                        "mime": "audio/mpeg"}}

    Frontend plays this via:
      new Audio('data:audio/mpeg;base64,' + audio_b64)
    """
    return {
        "type": "friday_audio",
        "data": {
            "audio_b64": base64.b64encode(mp3_bytes).decode("utf-8"),
            "text_hint": text_hint,
            "mime":      "audio/mpeg",
        },
    }


def speaking_indicator(active: bool) -> dict:
    """Return a `friday_speaking` WebSocket message."""
    return {"type": "friday_speaking", "data": {"active": active}}


def list_voices() -> dict[str, str]:
    """Return the built-in voice name → voice_id mapping."""
    return dict(VOICES)
