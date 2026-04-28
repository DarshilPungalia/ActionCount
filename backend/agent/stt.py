"""
friday_stt.py
-------------
Azure Cognitive Services Speech SDK — continuous recognition daemon thread.

IMPORTANT — How audio capture works:
  The Azure Speech SDK captures audio from the SERVER'S default microphone,
  NOT the browser. No browser mic permission is ever requested.
  The daemon runs as a background thread on the machine running endpoint.py.

Config priority (set in .env):
  1. AZURE_STT_REGION   — e.g. "eastus"  (PREFERRED — most reliable)
     + AZURE_STT_KEY
  2. AZURE_STT_ENDPOINT — custom endpoint, e.g. https://NAME.cognitiveservices.azure.com
     + AZURE_STT_KEY

  NOTE: .services.ai.azure.com (AI Foundry REST) does NOT work with the
  Speech SDK WebSocket protocol. Use a region or .cognitiveservices.azure.com.

Callbacks supplied to start():
  callback(transcript: str)   — final recognised phrase
  on_speech_start()           — Azure VAD detected speech onset
  on_speech_end()             — Azure VAD detected end of utterance
"""

from __future__ import annotations

import os
import threading
from typing import Callable, Optional

from dotenv import load_dotenv

load_dotenv()

_SPEECH_KEY    = os.getenv("AZURE_STT_KEY", "")
_STT_REGION    = os.getenv("AZURE_STT_REGION", "")          # e.g. "eastus"
_STT_ENDPOINT  = os.getenv("AZURE_STT_ENDPOINT", "").rstrip("/")

_TAG = "[FridaySTT]"


def _build_speech_config(speechsdk):
    """
    Build SpeechConfig using the best available credentials.

    Priority:
      1. Region  — speechsdk.SpeechConfig(subscription=key, region=region)
      2. Endpoint — speechsdk.SpeechConfig(subscription=key, endpoint=url)
         NOTE: endpoint must be .cognitiveservices.azure.com, not .services.ai.azure.com
    """
    if _STT_REGION:
        print(f"{_TAG} Config  : region={_STT_REGION!r} (recommended)")
        cfg = speechsdk.SpeechConfig(subscription=_SPEECH_KEY, region=_STT_REGION)
    elif _STT_ENDPOINT:
        # Warn if endpoint looks like the AI Foundry REST domain which won't work
        if "services.ai.azure.com" in _STT_ENDPOINT:
            print(
                f"{_TAG} ⚠  WARNING: AZURE_STT_ENDPOINT looks like an AI Foundry REST "
                f"URL ({_STT_ENDPOINT!r}). The Speech SDK needs a region or a "
                f".cognitiveservices.azure.com endpoint. Set AZURE_STT_REGION instead."
            )
        print(f"{_TAG} Config  : endpoint={_STT_ENDPOINT!r}")
        cfg = speechsdk.SpeechConfig(subscription=_SPEECH_KEY, endpoint=_STT_ENDPOINT)
    else:
        raise RuntimeError(
            "Neither AZURE_STT_REGION nor AZURE_STT_ENDPOINT is set. "
            "Add AZURE_STT_REGION=<your-region> (e.g. eastus) to your .env file."
        )

    cfg.speech_recognition_language = "en-US"
    return cfg


class FridaySTT:
    """Singleton Azure Speech continuous-recognition daemon."""

    _instance: Optional["FridaySTT"] = None

    def __init__(self):
        self._stop_event   = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self._callback: Optional[Callable[[str], None]] = None
        self._on_speech_start: Optional[Callable[[], None]] = None
        self._on_speech_end:   Optional[Callable[[], None]] = None

    @classmethod
    def instance(cls) -> "FridaySTT":
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    # ── Public API ────────────────────────────────────────────────────────────

    def start(
        self,
        callback: Callable[[str], None],
        on_speech_start: Optional[Callable[[], None]] = None,
        on_speech_end:   Optional[Callable[[], None]] = None,
    ) -> None:
        """Start the STT daemon thread. No-op if already running."""
        if not _SPEECH_KEY:
            print(f"{_TAG} AZURE_STT_KEY not set — STT disabled. Voice commands will NOT work.")
            return
        if not (_STT_REGION or _STT_ENDPOINT):
            print(f"{_TAG} Neither AZURE_STT_REGION nor AZURE_STT_ENDPOINT set — STT disabled.")
            print(f"{_TAG} Add AZURE_STT_REGION=eastus (or your region) to .env")
            return
        if self._thread and self._thread.is_alive():
            print(f"{_TAG} Daemon already running — ignoring duplicate start()")
            return

        self._callback        = callback
        self._on_speech_start = on_speech_start
        self._on_speech_end   = on_speech_end
        self._stop_event.clear()
        self._thread = threading.Thread(
            target=self._run, daemon=True, name="FridaySTT-daemon"
        )
        self._thread.start()
        print(f"{_TAG} Daemon started.")
        print(f"{_TAG} Mic     : SERVER default audio device (no browser permission needed)")
        print(f"{_TAG} VAD     : Azure built-in — agent responds after ~500 ms silence")

    def stop(self) -> None:
        print(f"{_TAG} Stop requested.")
        self._stop_event.set()

    # ── Internal ──────────────────────────────────────────────────────────────

    def _run(self) -> None:
        attempt = 0
        while not self._stop_event.is_set():
            attempt += 1
            print(f"{_TAG} Recognition loop attempt #{attempt}")
            try:
                self._recognition_loop()
                # Only reset if we were deliberately stopped
                if self._stop_event.is_set():
                    break
            except Exception as exc:
                print(f"{_TAG} ❌ Error in recognition loop: {exc}")
                wait = min(5.0, 2.0 + attempt * 0.5)   # gentle backoff, cap at 5s
                print(f"{_TAG} Retrying in {wait:.1f}s …")
                self._stop_event.wait(timeout=wait)
        print(f"{_TAG} Daemon exited cleanly.")

    def _recognition_loop(self) -> None:
        import azure.cognitiveservices.speech as speechsdk

        cfg = _build_speech_config(speechsdk)

        # Explicit default-mic AudioConfig avoids silent failures on some Windows configs
        audio_cfg = speechsdk.audio.AudioConfig(use_default_microphone=True)
        recognizer = speechsdk.SpeechRecognizer(speech_config=cfg, audio_config=audio_cfg)

        done = threading.Event()

        # ── Event handlers ────────────────────────────────────────────────────

        def _on_session_started(evt) -> None:
            print(f"{_TAG} ✅ Azure session started — listening on server mic")

        def _on_session_stopped(evt) -> None:
            print(f"{_TAG} ⏹  Azure session stopped")
            done.set()

        def _on_speech_start_detected(evt) -> None:
            print(f"{_TAG} 🎙  Speech STARTED (VAD onset)")
            if self._on_speech_start:
                try:
                    self._on_speech_start()
                except Exception as exc:
                    print(f"{_TAG} on_speech_start callback error: {exc}")

        def _on_speech_end_detected(evt) -> None:
            print(f"{_TAG} 🔇 Speech ENDED (VAD silence — waiting for transcript)")
            if self._on_speech_end:
                try:
                    self._on_speech_end()
                except Exception as exc:
                    print(f"{_TAG} on_speech_end callback error: {exc}")

        def _on_recognizing(evt) -> None:
            """Partial result — shows words as they stream in."""
            partial = (evt.result.text or "").strip()
            if partial:
                print(f"{_TAG} … partial: \"{partial}\"")

        def _on_recognized(evt) -> None:
            text = (evt.result.text or "").strip()
            if not text:
                print(f"{_TAG} ⚠  Empty recognition (silence / background noise)")
                return
            word_count = len(text.split())
            print(f"{_TAG} ✔  Recognized ({word_count} word{'s' if word_count != 1 else ''}): \"{text}\"")
            print(f"{_TAG} → Dispatching to Friday agent …")
            if self._callback:
                try:
                    self._callback(text)
                except Exception as exc:
                    print(f"{_TAG} ❌ Transcript callback error: {exc}")

        def _on_canceled(evt) -> None:
            reason = "unknown"
            code   = "N/A"
            detail = ""
            try:
                cd     = evt.result.cancellation_details
                reason = str(cd.reason)
                detail = cd.error_details or ""        # the actual error message string
                # error_code attribute name varies by SDK version
                for attr in ("error_code", "ErrorCode", "cancellation_error_code"):
                    if hasattr(cd, attr):
                        code = str(getattr(cd, attr))
                        break
            except Exception as e1:
                detail = f"(could not read cancellation_details: {e1})"

            print(f"{_TAG} ❌ Recognition canceled")
            print(f"{_TAG}    reason       : {reason}")
            print(f"{_TAG}    error_code   : {code}")
            print(f"{_TAG}    error_details: {detail or '(none)'}")

            if "Error" in reason:
                if not detail:
                    print(f"{_TAG} 💡 CancellationReason.Error with no details = microphone issue")
                    print(f"{_TAG}    → Windows Settings > Privacy > Microphone > Allow desktop apps")
                    print(f"{_TAG}    → Or no microphone connected to this machine")
                    print(f"{_TAG}    → Or mic locked by Teams/Zoom/Discord")
                elif "AuthenticationFailure" in detail or "Unauthorized" in detail:
                    print(f"{_TAG} 💡 Auth failure — double-check AZURE_STT_KEY in .env")
                elif "connection" in detail.lower() or "network" in detail.lower():
                    print(f"{_TAG} 💡 Network issue — check internet connectivity")
                else:
                    print(f"{_TAG} 💡 Error detail above should indicate the cause")
            done.set()

        # ── Wire up events ────────────────────────────────────────────────────
        recognizer.session_started.connect(_on_session_started)
        recognizer.session_stopped.connect(_on_session_stopped)
        recognizer.speech_start_detected.connect(_on_speech_start_detected)
        recognizer.speech_end_detected.connect(_on_speech_end_detected)
        recognizer.recognizing.connect(_on_recognizing)
        recognizer.recognized.connect(_on_recognized)
        recognizer.canceled.connect(_on_canceled)

        print(f"{_TAG} Starting continuous recognition …")
        recognizer.start_continuous_recognition()

        # Block until stop requested or session ends
        while not self._stop_event.is_set() and not done.is_set():
            done.wait(timeout=0.5)

        print(f"{_TAG} Stopping continuous recognition …")
        recognizer.stop_continuous_recognition()
