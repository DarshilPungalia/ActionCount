"""
friday_stt.py
-------------
Azure Cognitive Services Speech SDK — continuous recognition daemon thread.

Uses a custom endpoint (services.ai.azure.com) instead of a region shorthand,
which is required for Azure AI Foundry / multi-service resources.

Usage:
  stt = FridaySTT.instance()
  stt.start(on_transcript_callback)   # called once on app startup
  stt.stop()                          # called on app shutdown

The callback receives: callback(transcript: str)
Errors are retried silently — the daemon never crashes the main process.

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


class FridaySTT:
    """Singleton Azure Speech continuous-recognition daemon."""

    _instance: Optional["FridaySTT"] = None

    def __init__(self):
        self._stop_event   = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self._callback: Optional[Callable[[str], None]] = None

    @classmethod
    def instance(cls) -> "FridaySTT":
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    # ── Public API ────────────────────────────────────────────────────────────

    def start(self, callback: Callable[[str], None]) -> None:
        """Start the STT daemon thread. No-op if already running."""
        if not _SPEECH_KEY:
            print("[FridaySTT] AZURE_STT_KEY not set — STT disabled")
            return
        if self._thread and self._thread.is_alive():
            return

        self._callback  = callback
        self._stop_event.clear()
        self._thread = threading.Thread(
            target=self._run, daemon=True, name="FridaySTT-daemon"
        )
        self._thread.start()
        print(f"[FridaySTT] Started continuous recognition via {_STT_ENDPOINT}")

    def stop(self) -> None:
        """Signal the daemon to exit."""
        self._stop_event.set()

    # ── Internal ──────────────────────────────────────────────────────────────

    def _run(self) -> None:
        while not self._stop_event.is_set():
            try:
                self._recognition_loop()
            except Exception as exc:
                print(f"[FridaySTT] error (will retry): {exc}")
                # Brief pause before retry to avoid spinning on repeated failure
                self._stop_event.wait(timeout=3.0)

    def _recognition_loop(self) -> None:
        import azure.cognitiveservices.speech as speechsdk

        # SDK v1.49.1: SpeechConfig.__init__ accepts endpoint= + subscription=
        # directly — there is no from_endpoint() class method in this version.
        cfg = speechsdk.SpeechConfig(
            endpoint=_STT_ENDPOINT,
            subscription=_SPEECH_KEY,
        )
        cfg.speech_recognition_language = "en-US"
        recognizer = speechsdk.SpeechRecognizer(speech_config=cfg)

        done = threading.Event()

        def _on_recognized(evt: speechsdk.SpeechRecognitionEventArgs) -> None:
            text = evt.result.text.strip()
            if text and self._callback:
                try:
                    self._callback(text)
                except Exception as exc:
                    print(f"[FridaySTT] callback error: {exc}")

        def _on_canceled(evt: speechsdk.SessionEventArgs) -> None:
            done.set()

        def _on_stopped(evt: speechsdk.SessionEventArgs) -> None:
            done.set()

        recognizer.recognized.connect(_on_recognized)
        recognizer.session_stopped.connect(_on_stopped)
        recognizer.canceled.connect(_on_canceled)

        recognizer.start_continuous_recognition()

        # Block until stop requested or session ends
        while not self._stop_event.is_set() and not done.is_set():
            done.wait(timeout=0.5)

        recognizer.stop_continuous_recognition()
