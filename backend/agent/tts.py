"""
tts.py
------
Text-to-Speech module for the Friday AI assistant.

Stack:
  - voxtral-mini-realtime-rs  : Rust inference binary (WGPU / CUDA)
  - Voxtral-4B Q4_0 GGUF      : ~2.67 GB, 9 languages, 20 voice presets
  - sounddevice               : chunked WAV playback with barge-in support

Flow:
  speak(text) → subprocess: voxtral speak --text ... --output tmp.wav
              → read WAV bytes → return to caller
  stop_speaking() → set stop event → kill subprocess + interrupt playback

Config (.env):
  VOXTRAL_BINARY      — path to voxtral.exe  (default: %USERPROFILE%\\voxtral-rs\\target\\release\\voxtral.exe)
  VOXTRAL_MODEL       — path to voxtral-tts-q4.gguf  (default: models/voxtral/voxtral-tts-q4.gguf)
  VOXTRAL_VOICE       — voice preset name  (default: casual_female)
  VOXTRAL_EULER_STEPS — diffusion steps 3-8  (default: 4, RTF ~1.24×)

Euler steps guide:
  8  = max quality,  RTF ~1.61×  (above real-time, adds latency)
  4  = recommended,  RTF ~1.24×  (voice assistant default)
  3  = real-time,    RTF ~1.0×   (latency-critical)

Exports used by endpoint.py:
  speak(text, voice_id)           — alias for FridayTTS.instance().speak_sync()
  to_ws_envelope(audio_bytes, _)  — wrap WAV bytes in tts_audio WS envelope
  speaking_indicator(active)      — return friday_speaking WS dict
  stop_speaking()                 — barge-in interrupt
  list_voices()                   — list voice presets
  VOICES                          — dict[name → preset_id]
  _DEFAULT_VOICE_ID               — str
"""

from __future__ import annotations

import base64
import os
import subprocess
import tempfile
import threading
from typing import Optional

_TAG = "[FridayTTS]"

# ── Voxtral binary + model paths ───────────────────────────────────────────────
# On Windows the binary is voxtral.exe; os.path.expandvars expands %USERPROFILE%
_USERPROFILE = os.environ.get("USERPROFILE", os.path.expanduser("~"))

VOXTRAL_BINARY: str = os.path.expandvars(
    os.path.expanduser(
        os.getenv(
            "VOXTRAL_BINARY",
            os.path.join(_USERPROFILE, "voxtral-rs", "target", "release", "voxtral.exe"),
        )
    )
)

VOXTRAL_MODEL: str = os.path.expandvars(
    os.path.expanduser(
        os.getenv(
            "VOXTRAL_MODEL",
            os.path.join("models", "voxtral", "voxtral-tts-q4.gguf"),
        )
    )
)

VOXTRAL_VOICE: str      = os.getenv("VOXTRAL_VOICE", "casual_female")
VOXTRAL_EULER_STEPS: int = int(os.getenv("VOXTRAL_EULER_STEPS", "4"))

# ── Voice registry (Voxtral preset names) ─────────────────────────────────────
# Keys = human-friendly display names shown in the UI
# Values = Voxtral --voice preset identifiers
VOICES: dict[str, str] = {
    # English
    "Casual Female":       "casual_female",
    "Casual Male":         "casual_male",
    "Professional Female": "professional_female",
    "Professional Male":   "professional_male",
    "Narrative Female":    "narrative_female",
    "Narrative Male":      "narrative_male",
    # French
    "FR Female":           "fr_female",
    "FR Male":             "fr_male",
    # German
    "DE Female":           "de_female",
    "DE Male":             "de_male",
    # Spanish
    "ES Female":           "es_female",
    "ES Male":             "es_male",
    # Italian
    "IT Female":           "it_female",
    "IT Male":             "it_male",
    # Portuguese
    "PT Female":           "pt_female",
    "PT Male":             "pt_male",
    # Dutch
    "NL Female":           "nl_female",
    "NL Male":             "nl_male",
    # Hindi
    "HI Female":           "hi_female",
    "HI Male":             "hi_male",
    # Arabic
    "AR Female":           "ar_female",
}

_DEFAULT_VOICE_ID: str = os.getenv("VOXTRAL_VOICE", VOXTRAL_VOICE)


# ═══════════════════════════════════════════════════════════════════════════════
# FridayTTS — Singleton daemon
# ═══════════════════════════════════════════════════════════════════════════════

class FridayTTS:
    """
    Singleton TTS daemon wrapping Voxtral Q4_0 GGUF via voxtral-mini-realtime-rs.

    speak_sync(text, voice)  — synthesize WAV → return bytes (blocking, thread-safe)
    stop_speaking()          — barge-in interrupt
    preload()                — background warmup (fires at module import)
    """

    _instance: Optional["FridayTTS"] = None

    def __init__(self) -> None:
        self._lock          = threading.Lock()
        self._stop_event    = threading.Event()
        self._speaking      = False
        self._current_proc: Optional[subprocess.Popen] = None

    @classmethod
    def instance(cls) -> "FridayTTS":
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    @property
    def is_speaking(self) -> bool:
        return self._speaking

    # ── Public: synchronous speak → returns WAV bytes ─────────────────────────

    def speak_sync(
        self,
        text: str,
        voice: str       = VOXTRAL_VOICE,
        euler_steps: int = VOXTRAL_EULER_STEPS,
    ) -> bytes | None:
        """
        Synthesise `text` via Voxtral and return raw WAV bytes.
        Blocking — intended to be called from asyncio.to_thread().
        Returns None on error or barge-in.
        """
        if not text or not text.strip():
            return None

        self._stop_event.clear()
        self._speaking = True
        tmp_wav = None

        try:
            tmp_wav = tempfile.mktemp(suffix=".wav", prefix="friday_tts_")

            cmd = [
                VOXTRAL_BINARY,
                "speak",
                "--text",        text,
                "--voice",       voice,
                "--gguf",        VOXTRAL_MODEL,
                "--euler-steps", str(euler_steps),
                "--output",      tmp_wav,
            ]

            preview = text[:60] + ("…" if len(text) > 60 else "")
            print(f"{_TAG} Synthesising [{voice}] ({euler_steps} steps): \"{preview}\"")

            # Launch Voxtral subprocess
            with self._lock:
                self._current_proc = subprocess.Popen(
                    cmd,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.PIPE,
                )

            _, stderr = self._current_proc.communicate()
            retcode   = self._current_proc.returncode

            with self._lock:
                self._current_proc = None

            if self._stop_event.is_set():
                print(f"{_TAG} Synthesis interrupted (barge-in).")
                return None

            if retcode != 0:
                err = stderr.decode(errors="replace")[:500] if stderr else ""
                print(f"{_TAG} ❌ Voxtral error (exit {retcode}): {err}")
                return None

            if not os.path.exists(tmp_wav):
                print(f"{_TAG} ❌ Output WAV not found at: {tmp_wav}")
                return None

            with open(tmp_wav, "rb") as f:
                wav_bytes = f.read()

            print(f"{_TAG} ✅ Synthesis complete — {len(wav_bytes):,} bytes")
            return wav_bytes

        except FileNotFoundError:
            print(
                f"{_TAG} ❌ Voxtral binary not found: {VOXTRAL_BINARY}\n"
                f"{_TAG}    Set VOXTRAL_BINARY in .env to the correct path."
            )
            return None
        except Exception as exc:
            print(f"{_TAG} ❌ TTS error: {exc}")
            return None
        finally:
            self._speaking = False
            if tmp_wav and os.path.exists(tmp_wav):
                try:
                    os.remove(tmp_wav)
                except OSError:
                    pass

    # ── Public: barge-in interrupt ────────────────────────────────────────────

    def stop_speaking(self) -> None:
        """Stop any ongoing synthesis and clear speaking state."""
        self._stop_event.set()
        self._speaking = False

        with self._lock:
            proc = self._current_proc
        if proc and proc.poll() is None:
            try:
                proc.terminate()
                proc.wait(timeout=2.0)
            except Exception:
                try:
                    proc.kill()
                except Exception:
                    pass

    # ── Warmup ────────────────────────────────────────────────────────────────

    def preload(self) -> None:
        """Spawn a background warmup synthesis to prime Voxtral's autotune cache."""
        threading.Thread(
            target=self._warmup, daemon=True, name="FridayTTS-warmup"
        ).start()

    def _warmup(self) -> None:
        print(f"{_TAG} 🔥 Warming up Voxtral binary …")
        tmp = tempfile.mktemp(suffix=".wav", prefix="friday_tts_warmup_")
        try:
            subprocess.run(
                [
                    VOXTRAL_BINARY, "speak",
                    "--text",        "Hello.",
                    "--voice",       VOXTRAL_VOICE,
                    "--gguf",        VOXTRAL_MODEL,
                    "--euler-steps", "3",
                    "--output",      tmp,
                ],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                timeout=120,
            )
            print(f"{_TAG} ✅ Voxtral warmup complete.")
        except FileNotFoundError:
            print(f"{_TAG} ⚠️  Voxtral binary not found — warmup skipped (non-fatal).")
        except Exception as exc:
            print(f"{_TAG} ⚠️  Warmup failed (non-fatal): {exc}")
        finally:
            try:
                if os.path.exists(tmp):
                    os.remove(tmp)
            except OSError:
                pass


# ═══════════════════════════════════════════════════════════════════════════════
# Module-level convenience functions — these are what endpoint.py imports
# ═══════════════════════════════════════════════════════════════════════════════

def speak(text: str, voice_id: Optional[str] = None) -> bytes | None:
    """
    Synchronous TTS synthesis via Voxtral.
    Returns raw WAV bytes or None on failure.
    Called from endpoint.py via asyncio.to_thread(tts_speak, text, voice_id).

    voice_id here is a Voxtral preset name string (e.g. "casual_female").
    Falls back to VOXTRAL_VOICE env var if None.
    """
    voice = voice_id or _DEFAULT_VOICE_ID
    # Validate: only accept known preset values to guard against injection
    known_presets = set(VOICES.values())
    if voice not in known_presets:
        print(f"{_TAG} ⚠️  Unknown voice preset {voice!r} — falling back to {_DEFAULT_VOICE_ID!r}")
        voice = _DEFAULT_VOICE_ID
    return FridayTTS.instance().speak_sync(text, voice=voice)


def stop_speaking() -> None:
    """Interrupt current TTS playback. Called by STT on barge-in."""
    FridayTTS.instance().stop_speaking()


def to_ws_envelope(audio_bytes: bytes, _text: str = "") -> dict:
    """
    Wrap raw WAV bytes in a JSON-serialisable WebSocket message.
    Signature: to_ws_envelope(mp3, response_text) — second arg unused,
    kept for call-site compatibility with endpoint.py.
    """
    return {
        "type": "tts_audio",
        "data": {
            "audio": base64.b64encode(audio_bytes).decode("utf-8"),
            "mime":  "audio/wav",
        },
    }


def speaking_indicator(active: bool) -> dict:
    """
    Return a friday_speaking WebSocket message dict.
    Called as: await ws.send_json(speaking_indicator(True/False))
    """
    return {
        "type": "friday_speaking",
        "data": {"active": active},
    }


def list_voices() -> list[dict]:
    """Return available Voxtral voice presets as [{name, voice_id}, ...]."""
    return [{"name": k, "voice_id": v} for k, v in VOICES.items()]


# ── Auto-warmup at module import (background, non-blocking) ───────────────────
FridayTTS.instance().preload()