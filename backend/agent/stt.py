"""
friday_stt.py
-------------
Speech-to-Text daemon for the Friday AI assistant.

Stack:
  - PyAudio         : server microphone capture
  - Silero VAD      : voice activity detection (speech onset / offset)
  - NVIDIA Parakeet TDT 0.6B v2 (via NeMo) : transcription

Flow:
  1. PyAudio loop reads raw PCM in small chunks (512 samples @ 16 kHz)
  2. Silero VAD scores each chunk → detects speech start / end
  3. On speech START  → fire on_speech_start() + WebSocket listening indicator
  4. On speech START while TTS active → call tts.stop_speaking() (barge-in)
  5. On speech END    → fire on_speech_end(), pass buffered audio to Parakeet
  6. Parakeet returns transcript → fire callback(transcript)

Callbacks supplied to start():
  callback(transcript: str)   — final recognised phrase
  on_speech_start()           — VAD detected speech onset
  on_speech_end()             — VAD detected end of utterance

Config (.env):
  No API keys needed. Model is downloaded once via HuggingFace / NGC cache.
"""

from __future__ import annotations

import threading
import tempfile
import os
from numpy import ndarray
from typing import Callable, Optional

_TAG = "[FridaySTT]"

# ── Audio constants ───────────────────────────────────────────────────────────
SAMPLE_RATE       = 16_000   # Silero VAD and Parakeet both require 16 kHz
CHUNK_SAMPLES     = 512      # ~32 ms per chunk at 16 kHz (Silero recommendation)
SILENCE_CHUNKS    = 25       # ~800 ms of silence → finalise utterance
MIN_SPEECH_CHUNKS = 5        # ignore bursts shorter than ~160 ms (noise gate)

_PARAKEET_MODEL = "nvidia/parakeet-tdt-0.6b-v2"


class FridaySTT:
    """Singleton Parakeet TDT + Silero VAD continuous-recognition daemon."""

    _instance: Optional["FridaySTT"] = None

    def __init__(self):
        self._stop_event          = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self._callback: Optional[Callable[[str], None]] = None
        self._on_speech_start: Optional[Callable[[], None]] = None
        self._on_speech_end:   Optional[Callable[[], None]] = None

        # Lazy-loaded models
        self._vad_model   = None
        self._vad_utils   = None
        self._asr_model   = None   # NeMo ASRModel

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
        if self._thread and self._thread.is_alive():
            print(f"{_TAG} Daemon already running — ignoring duplicate start().")
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
        print(f"{_TAG} Models : Silero VAD + {_PARAKEET_MODEL}")
        print(f"{_TAG} Mic    : SERVER default audio device (PyAudio)")

    def stop(self) -> None:
        print(f"{_TAG} Stop requested.")
        self._stop_event.set()

    # ── Model loading ─────────────────────────────────────────────────────────

    def _load_vad(self):
        if self._vad_model is not None:
            return
        print(f"{_TAG} Loading Silero VAD …")
        import torch  # noqa: PLC0415
        torch.set_num_threads(1)
        self._vad_model, self._vad_utils = torch.hub.load(
            repo_or_dir="snakers4/silero-vad",
            model="silero_vad",
            trust_repo=True,
        )
        print(f"{_TAG} ✅ Silero VAD loaded.")

    def _load_parakeet(self):
        if self._asr_model is not None:
            return
        print(f"{_TAG} Loading {_PARAKEET_MODEL} (NeMo) …")
        import nemo.collections.asr as nemo_asr  # noqa: PLC0415
        self._asr_model = nemo_asr.models.ASRModel.from_pretrained(
            model_name=_PARAKEET_MODEL
        )
        self._asr_model.eval()
        print(f"{_TAG} ✅ Parakeet TDT loaded.")

    # ── Main loop ─────────────────────────────────────────────────────────────

    def _run(self) -> None:
        attempt = 0
        while not self._stop_event.is_set():
            attempt += 1
            print(f"{_TAG} Recognition loop attempt #{attempt}")
            try:
                self._load_vad()
                self._load_parakeet()
                self._recognition_loop()
                if self._stop_event.is_set():
                    break
            except Exception as exc:
                print(f"{_TAG} ❌ Error in recognition loop: {exc}")
                wait = min(5.0, 2.0 + attempt * 0.5)
                print(f"{_TAG} Retrying in {wait:.1f}s …")
                self._stop_event.wait(timeout=wait)
        print(f"{_TAG} Daemon exited cleanly.")

    def _recognition_loop(self) -> None:
        import numpy as np  # noqa: PLC0415
        import pyaudio      # noqa: PLC0415

        (get_speech_timestamps, _, _, _, _) = self._vad_utils

        pa     = pyaudio.PyAudio()
        stream = pa.open(
            format=pyaudio.paInt16,
            channels=1,
            rate=SAMPLE_RATE,
            input=True,
            frames_per_buffer=CHUNK_SAMPLES,
        )

        print(f"{_TAG} ✅ Mic stream open — listening …")

        speech_buffer:      list[np.ndarray] = []
        silence_count:      int  = 0
        is_speaking:        bool = False
        speech_chunk_count: int  = 0

        try:
            while not self._stop_event.is_set():
                raw   = stream.read(CHUNK_SAMPLES, exception_on_overflow=False)
                chunk = np.frombuffer(raw, dtype=np.int16).astype(np.float32) / 32768.0

                # Silero VAD confidence for this chunk
                import torch  # noqa: PLC0415
                chunk_tensor = torch.from_numpy(chunk)
                confidence   = self._vad_model(chunk_tensor, SAMPLE_RATE).item()

                if confidence > 0.5:
                    # ── Speech detected ───────────────────────────────────────
                    if not is_speaking:
                        speech_chunk_count += 1
                        if speech_chunk_count >= MIN_SPEECH_CHUNKS:
                            is_speaking   = True
                            silence_count = 0
                            print(f"{_TAG} 🎙️  Speech STARTED (VAD confidence={confidence:.2f})")
                            self._fire_speech_start()
                    speech_buffer.append(chunk)
                    silence_count = 0

                else:
                    # ── Silence detected ──────────────────────────────────────
                    if not is_speaking:
                        speech_chunk_count = max(0, speech_chunk_count - 1)
                        continue

                    speech_buffer.append(chunk)   # keep trailing silence for context
                    silence_count += 1

                    if silence_count >= SILENCE_CHUNKS:
                        print(f"{_TAG} 🔇 Speech ENDED — transcribing …")
                        self._fire_speech_end()

                        audio_np = np.concatenate(speech_buffer, axis=0)
                        speech_buffer      = []
                        silence_count      = 0
                        is_speaking        = False
                        speech_chunk_count = 0

                        self._transcribe(audio_np)

        finally:
            stream.stop_stream()
            stream.close()
            pa.terminate()
            print(f"{_TAG} Mic stream closed.")

    # ── Transcription ─────────────────────────────────────────────────────────

    def _transcribe(self, audio_np: "ndarray") -> None:
        """
        Parakeet TDT transcription.

        NeMo's ASRModel.transcribe() accepts file paths, so we write the
        PCM buffer to a temporary WAV file and pass it in — no disk clutter
        because we delete it immediately after.
        """
        import numpy as np       # noqa: PLC0415
        import soundfile as sf   # noqa: PLC0415

        try:
            duration_s = len(audio_np) / SAMPLE_RATE
            if duration_s < 0.4:
                print(f"{_TAG} Skipping short clip ({duration_s:.2f}s < 0.4s)")
                return

            # Write to a temp WAV file (Parakeet needs a file path)
            with tempfile.NamedTemporaryFile(
                suffix=".wav", delete=False, prefix="friday_stt_"
            ) as tmp:
                tmp_path = tmp.name

            try:
                sf.write(tmp_path, audio_np, SAMPLE_RATE, subtype="PCM_16")
                outputs = self._asr_model.transcribe([tmp_path])
                # Parakeet returns a list of Hypothesis objects; .text is the field
                text = (outputs[0].text if outputs else "").strip()
            finally:
                try:
                    os.unlink(tmp_path)
                except OSError:
                    pass

            if not text:
                print(f"{_TAG} Empty transcript (silence / noise).")
                return

            word_count = len(text.split())
            print(f"{_TAG} Transcript ({word_count} words): \"{text}\"")

            if self._callback:
                try:
                    self._callback(text)
                except Exception as exc:
                    print(f"{_TAG} Transcript callback error: {exc}")

        except Exception as exc:
            print(f"{_TAG} Parakeet transcription error: {exc}")

    # ── Callbacks ─────────────────────────────────────────────────────────────

    def _fire_speech_start(self) -> None:
        # Barge-in: stop TTS if it's currently speaking
        try:
            from backend.agent.tts import stop_speaking  # noqa: PLC0415
            stop_speaking()
        except Exception:
            pass

        if self._on_speech_start:
            try:
                self._on_speech_start()
            except Exception as exc:
                print(f"{_TAG} on_speech_start callback error: {exc}")

    def _fire_speech_end(self) -> None:
        if self._on_speech_end:
            try:
                self._on_speech_end()
            except Exception as exc:
                print(f"{_TAG} on_speech_end callback error: {exc}")
