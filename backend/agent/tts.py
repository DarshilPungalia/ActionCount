"""
tts.py
------
Text-to-Speech module for the Friday AI assistant.

Stack:
  - voxtral-mini-realtime-rs  : Rust inference binary (WGPU / CUDA)
  - Voxtral-4B Q4_0 GGUF      : ~2.67 GB, 9 languages, 22 voice presets
  - sounddevice               : chunked WAV playback with barge-in support

Flow:
  speak(text) → subprocess: voxtral speak --text ... --gguf ... --voices-dir ... --output tmp.wav
              → read WAV bytes → return to caller
  stop_speaking() → set stop event → terminate subprocess

Config (.env):
  VOXTRAL_BINARY      — path to voxtral.exe
                        default: %USERPROFILE%\\voxtral-rs\\target\\release\\voxtral.exe
  VOXTRAL_MODEL       — path to GGUF file
                        default: models/voxtral/voxtral-tts-q4.gguf
  VOXTRAL_VOICES_DIR  — path to voice_embedding dir  (IMPORTANT: must be set)
                        default: models/voxtral/voice_embedding
  VOXTRAL_VOICE       — default voice preset name  (default: casual_female)
  VOXTRAL_EULER_STEPS — diffusion steps 3-8  (default: 4, RTF ~1.24x)

Euler steps guide:
  8  = max quality,  RTF ~1.61x  (above real-time, adds latency)
  4  = recommended,  RTF ~1.24x  (voice assistant default)
  3  = real-time,    RTF ~1.0x   (latency-critical)

Exports used by endpoint.py:
  speak(text, voice_id)           — sync synthesis, returns WAV bytes | None
  to_ws_envelope(audio_bytes, _)  — wrap WAV bytes in tts_audio WS envelope
  speaking_indicator(active)      — return friday_speaking WS dict
  stop_speaking()                 — barge-in interrupt
  list_voices()                   — list available voice presets
  VOICES                          — dict[display_name → preset_id]
  _DEFAULT_VOICE_ID               — str  (Voxtral preset name)
"""

from __future__ import annotations

import base64
import os
import subprocess
import tempfile
import threading
from typing import Optional

_TAG = "[FridayTTS]"

# ── Paths ──────────────────────────────────────────────────────────────────────
_USERPROFILE = os.environ.get("USERPROFILE", os.path.expanduser("~"))

VOXTRAL_BINARY: str = os.path.expandvars(os.path.expanduser(
    os.getenv(
        "VOXTRAL_BINARY",
        os.path.join(_USERPROFILE, "voxtral-rs", "target", "release", "voxtral.exe"),
    )
))

VOXTRAL_MODEL: str = os.path.expandvars(os.path.expanduser(
    os.getenv("VOXTRAL_MODEL", os.path.join("models", "voxtral", "voxtral-tts-q4.gguf"))
))

# Voice embeddings directory — must be passed via --voices-dir when using --gguf
VOXTRAL_VOICES_DIR: str = os.path.expandvars(os.path.expanduser(
    os.getenv("VOXTRAL_VOICES_DIR", os.path.join("models", "voxtral", "voice_embedding"))
))

VOXTRAL_VOICE: str       = os.getenv("VOXTRAL_VOICE", "casual_female")
VOXTRAL_EULER_STEPS: int = int(os.getenv("VOXTRAL_EULER_STEPS", "4"))

# ── Voice registry ─────────────────────────────────────────────────────────────
# Keys   = human-friendly display names shown in the UI / API
# Values = Voxtral --voice preset identifiers (filename stems in voice_embedding/)
VOICES: dict[str, str] = {
    # English
    "Casual Female":       "casual_female",
    "Casual Male":         "casual_male",
    "Cheerful Female":     "cheerful_female",
    "Neutral Female":      "neutral_female",
    "Neutral Male":        "neutral_male",
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
    "AR Male":             "ar_male",
}

# Set of valid preset IDs — used for fast O(1) lookup
_VALID_PRESETS: frozenset[str] = frozenset(VOICES.values())

_DEFAULT_VOICE_ID: str = os.getenv("VOXTRAL_VOICE", VOXTRAL_VOICE)


# ═══════════════════════════════════════════════════════════════════════════════
# FridayTTS — Singleton daemon
# ═══════════════════════════════════════════════════════════════════════════════

class FridayTTS:
    """
    Singleton TTS daemon wrapping Voxtral Q4_0 GGUF via voxtral-mini-realtime-rs.

    speak_sync(text, voice)  — synthesize WAV → return bytes (blocking, thread-safe)
    stop_speaking()          — barge-in: terminates current subprocess instantly
    preload()                — background warmup fired at module import
    """

    _instance: Optional["FridayTTS"] = None

    def __init__(self) -> None:
        self._lock          = threading.Lock()
        self._stop_event    = threading.Event()
        self._speaking      = False
        # Protected by _lock — always access via local copy to avoid races
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
                "--voices-dir",  VOXTRAL_VOICES_DIR,
                "--euler-steps", str(euler_steps),
                "--output",      tmp_wav,
            ]

            preview = text[:60] + ("…" if len(text) > 60 else "")
            print(f"{_TAG} Synthesising [{voice}] ({euler_steps} steps): \"{preview}\"")

            # ── Launch subprocess, keep a LOCAL reference to avoid races ──────
            # Do NOT use self._current_proc directly after releasing the lock —
            # another thread (e.g. a second speak call or stop_speaking) may
            # overwrite it.  Always work with the local `proc` variable.
            proc = subprocess.Popen(
                cmd,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.PIPE,
            )
            with self._lock:
                self._current_proc = proc

            # Wait for synthesis to finish (or barge-in to kill it)
            _, stderr_bytes = proc.communicate()

            # Clear global reference — only if it still points to our proc
            with self._lock:
                if self._current_proc is proc:
                    self._current_proc = None

            # ── Check barge-in FIRST (returncode may be non-zero after kill) ──
            if self._stop_event.is_set():
                print(f"{_TAG} Synthesis interrupted (barge-in).")
                return None

            retcode = proc.returncode  # always use local proc ref

            if retcode != 0:
                err = ""
                if stderr_bytes:
                    # Decode with replacement to avoid cp1252 crashes on Windows
                    err = stderr_bytes.decode("utf-8", errors="replace").strip()
                print(f"{_TAG} ❌ Voxtral error (exit {retcode}): {err[:500]}")
                return None

            if not os.path.exists(tmp_wav):
                print(f"{_TAG} ❌ Output WAV not written: {tmp_wav}")
                return None

            with open(tmp_wav, "rb") as f:
                wav_bytes = f.read()

            print(f"{_TAG} [OK] Synthesis done -- {len(wav_bytes):,} bytes")
            return wav_bytes

        except FileNotFoundError:
            print(
                f"{_TAG} [ERR] Voxtral binary not found: {VOXTRAL_BINARY}\n"
                f"{_TAG}       Set VOXTRAL_BINARY in .env to the correct path."
            )
            return None
        except Exception as exc:
            print(f"{_TAG} [ERR] TTS error: {exc}")
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
        """Interrupt current synthesis immediately (called by STT barge-in)."""
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
        """Spawn a background warmup to prime Voxtral's GPU autotune cache."""
        threading.Thread(
            target=self._warmup, daemon=True, name="FridayTTS-warmup"
        ).start()

    def _warmup(self) -> None:
        print(f"{_TAG} [WARMUP] Warming up Voxtral binary ...")
        tmp = tempfile.mktemp(suffix=".wav", prefix="friday_tts_warmup_")
        try:
            result = subprocess.run(
                [
                    VOXTRAL_BINARY, "speak",
                    "--text",        "Hello.",
                    "--voice",       VOXTRAL_VOICE,
                    "--gguf",        VOXTRAL_MODEL,
                    "--voices-dir",  VOXTRAL_VOICES_DIR,
                    "--euler-steps", "3",
                    "--output",      tmp,
                ],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.PIPE,
                timeout=120,
            )
            if result.returncode == 0:
                print(f"{_TAG} [WARMUP] Voxtral warmup complete.")
            else:
                err = result.stderr.decode("utf-8", errors="replace").strip()[:300]
                print(f"{_TAG} [WARMUP] Warmup failed (non-fatal): {err}")
        except FileNotFoundError:
            print(f"{_TAG} [WARMUP] Voxtral binary not found -- warmup skipped.")
        except Exception as exc:
            print(f"{_TAG} [WARMUP] Warmup failed (non-fatal): {exc}")
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
    Returns raw WAV bytes or None on failure / barge-in.

    voice_id is a Voxtral preset name (e.g. "casual_female").
    Any unrecognised value (e.g. a legacy ElevenLabs ID stored in the DB)
    is silently replaced with _DEFAULT_VOICE_ID without raising.
    """
    if voice_id and voice_id in _VALID_PRESETS:
        voice = voice_id
    else:
        # Silently fall back — old ElevenLabs IDs in the DB are expected
        voice = _DEFAULT_VOICE_ID
    return FridayTTS.instance().speak_sync(text, voice=voice)


def stop_speaking() -> None:
    """Interrupt current TTS playback. Called by STT on barge-in."""
    FridayTTS.instance().stop_speaking()


def to_ws_envelope(audio_bytes: bytes, _text: str = "") -> dict:
    """
    Wrap raw WAV bytes in a JSON-serialisable WebSocket message.
    Second arg is unused (kept for call-site compatibility with endpoint.py).
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


# ── Auto-warmup at module import (background thread, non-blocking) ─────────────
# Skip warmup if VOXTRAL_WARMUP=false — avoids GPU load when TTS is enabled
# but warmup is undesirable (e.g. constrained VRAM at startup).
# Primary guard: tts.py is never imported at all when --use_tts=false.
_WARMUP_ENABLED = os.getenv("VOXTRAL_WARMUP", "true").lower() not in ("false", "0", "no", "off")
if _WARMUP_ENABLED:
    FridayTTS.instance().preload()