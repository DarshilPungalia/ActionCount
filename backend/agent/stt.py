"""
friday_stt.py
-------------
Azure Cognitive Services Speech SDK — continuous recognition daemon thread.

Uses a custom endpoint (services.ai.azure.com) instead of a region shorthand,
which is required for Azure AI Foundry / multi-service resources.

IMPORTANT — How the microphone works:
  The Azure Speech SDK captures audio from the SERVER'S default microphone,
  NOT the browser. The browser never requests mic access. The STT daemon runs
  as a background thread on the machine running endpoint.py.

Usage:
  stt = FridaySTT.instance()
  stt.start(on_transcript_callback)   # called once on app startup
  stt.stop()                          # called on app shutdown

Callbacks:
  on_transcript(transcript: str)               — final recognized phrase
  on_speech_start()                            — Azure VAD detected speech onset
  on_speech_end()                              — Azure VAD detected end of utterance

Required env vars:
  AZURE_STT_KEY         — API key for the princedastan Azure resource
  AZURE_STT_ENDPOINT    — e.g. https://princedastan.services.ai.azure.com
"""

from __future__ import annotations

import os
import threading
from typing import Callable, Optional

from dotenv import load_dotenv

load_dotenv()

_SPEECH_KEY   = os.getenv("AZURE_STT_KEY", "")
_STT_ENDPOINT = os.getenv(
    "AZURE_STT_ENDPOINT",
    "https://princedastan.services.ai.azure.com",
).rstrip("/")

_TAG = "[FridaySTT]"


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
            print(f"{_TAG} AZURE_STT_KEY not set — STT disabled. "
                  "Voice commands will NOT work.")
            return
        if self._thread and self._thread.is_alive():
            print(f"{_TAG} Daemon already running — ignoring duplicate start()")
            return

        self._callback       = callback
        self._on_speech_start = on_speech_start
        self._on_speech_end   = on_speech_end
        self._stop_event.clear()
        self._thread = threading.Thread(
            target=self._run, daemon=True, name="FridaySTT-daemon"
        )
        self._thread.start()
        print(f"{_TAG} Daemon started.")
        print(f"{_TAG} Endpoint : {_STT_ENDPOINT}")
        print(f"{_TAG} Language : en-US")
        print(f"{_TAG} Mic      : SERVER default audio device "
              "(browser does NOT need microphone permission)")
        print(f"{_TAG} VAD      : Azure built-in — speaks only after silence "
              "detection (~500 ms quiet = end of utterance)")

    def stop(self) -> None:
        """Signal the daemon to exit."""
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
            except Exception as exc:
                print(f"{_TAG} ❌ Error in recognition loop: {exc}")
                wait = min(3.0 * attempt, 30.0)   # backoff up to 30 s
                print(f"{_TAG} Retrying in {wait:.0f}s …")
                self._stop_event.wait(timeout=wait)
        print(f"{_TAG} Daemon exited cleanly.")

    def _recognition_loop(self) -> None:
        import azure.cognitiveservices.speech as speechsdk

        # SDK v1.49.1: SpeechConfig.__init__ accepts endpoint= + subscription=
        # directly — there is no from_endpoint() class method in this version.
        cfg = speechsdk.SpeechConfig(
            endpoint=_STT_ENDPOINT,
            subscription=_SPEECH_KEY,
        )
        cfg.speech_recognition_language = "en-US"

        # Lower end-of-speech silence threshold so the agent responds faster.
        # Default is 1500 ms; 800 ms is a good balance for fitness commands.
        cfg.set_property(
            speechsdk.PropertyId.SpeechServiceConnection_EndSilenceTimeoutMs,
            "800",
        )
        # Initial silence before first word (2 s)
        cfg.set_property(
            speechsdk.PropertyId.SpeechServiceConnection_InitialSilenceTimeoutMs,
            "2000",
        )

        recognizer = speechsdk.SpeechRecognizer(speech_config=cfg)
        done = threading.Event()

        # ── Event handlers ────────────────────────────────────────────────────

        def _on_session_started(evt: speechsdk.SessionEventArgs) -> None:
            print(f"{_TAG} ✅ Azure session started — now listening on server mic")

        def _on_session_stopped(evt: speechsdk.SessionEventArgs) -> None:
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
            print(f"{_TAG} 🔇 Speech ENDED (VAD offset — waiting for transcript)")
            if self._on_speech_end:
                try:
                    self._on_speech_end()
                except Exception as exc:
                    print(f"{_TAG} on_speech_end callback error: {exc}")

        def _on_recognizing(evt: speechsdk.SpeechRecognitionEventArgs) -> None:
            """Partial (in-progress) result — useful for debugging latency."""
            partial = evt.result.text.strip()
            if partial:
                print(f"{_TAG} … partial: \"{partial}\"")

        def _on_recognized(evt: speechsdk.SpeechRecognitionEventArgs) -> None:
            text = evt.result.text.strip()
            if not text:
                print(f"{_TAG} ⚠  Recognized empty text (background noise / silence)")
                return
            word_count = len(text.split())
            print(f"{_TAG} ✔  Recognized ({word_count} word{'s' if word_count != 1 else ''}): \"{text}\"")
            print(f"{_TAG} → Dispatching transcript to Friday agent …")
            if self._callback:
                try:
                    self._callback(text)
                except Exception as exc:
                    print(f"{_TAG} ❌ Transcript callback error: {exc}")

        def _on_canceled(evt: speechsdk.SpeechRecognitionCanceledEventArgs) -> None:
            reason = getattr(evt, "reason", "unknown")
            error_code = getattr(evt, "error_code", None)
            error_details = getattr(evt, "error_details", "")
            print(f"{_TAG} ❌ Recognition canceled — reason={reason} "
                  f"error_code={error_code} details={error_details!r}")
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
