"""
friday_stt.py
-------------
Speech-to-Text daemon for the Friday AI assistant.

Stack:
  - PyAudio         : server microphone capture
  - Silero VAD      : voice activity detection (speech onset / offset)
  - openai/whisper-large-v3-turbo (HuggingFace transformers) : transcription

Flow:
  1. PyAudio loop reads raw PCM in small chunks (512 samples @ 16 kHz)
  2. Silero VAD scores each chunk → detects speech start / end
  3. On speech START  → fire on_speech_start() + WebSocket listening indicator
  4. On speech START while TTS active → call tts.stop_speaking() (barge-in)
  5. On speech END    → fire on_speech_end(), pass buffered audio to Whisper
  6. Whisper returns transcript → fire callback(transcript)

Callbacks supplied to start():
  callback(transcript: str)   — final recognised phrase
  on_speech_start()           — VAD detected speech onset
  on_speech_end()             — VAD detected end of utterance

Config (.env):
  No Azure keys needed. Model is downloaded automatically by HuggingFace cache.
"""

from __future__ import annotations

import threading
from numpy import ndarray
from typing import Callable, Optional

_TAG = "[FridaySTT]"

# ── Audio constants ───────────────────────────────────────────────────────────
SAMPLE_RATE    = 16_000          # Silero VAD and Whisper both require 16 kHz
CHUNK_SAMPLES  = 512             # ~32 ms per chunk at 16 kHz (Silero recommendation)
SILENCE_CHUNKS = 25              # ~800 ms of silence after speech ends → finalize
MIN_SPEECH_CHUNKS = 5            # ignore bursts shorter than ~160 ms (noise gate)


class FridaySTT:
    """Singleton Whisper + Silero VAD continuous-recognition daemon."""

    _instance: Optional["FridaySTT"] = None

    def __init__(self):
        self._stop_event         = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self._callback: Optional[Callable[[str], None]] = None
        self._on_speech_start: Optional[Callable[[], None]] = None
        self._on_speech_end:   Optional[Callable[[], None]] = None

        # Lazy-loaded models
        self._vad_model    = None
        self._vad_utils    = None
        self._whisper_pipe = None

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
        print(f"{_TAG} Models : Silero VAD + openai/whisper-large-v3-turbo")
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

    def _load_whisper(self):
        if self._whisper_pipe is not None:
            return
        print(f"{_TAG} Loading openai/whisper-large-v3-turbo …")
        import torch  # noqa: PLC0415
        from transformers import (  # noqa: PLC0415
            AutoModelForSpeechSeq2Seq,
            AutoProcessor,
            pipeline,
        )
        device      = "cuda:0" if torch.cuda.is_available() else "cpu"
        torch_dtype = torch.float16 if torch.cuda.is_available() else torch.float32
        model_id    = "openai/whisper-large-v3-turbo"

        model = AutoModelForSpeechSeq2Seq.from_pretrained(
            model_id,
            dtype=torch_dtype,           # use 'dtype' not deprecated 'torch_dtype'
            low_cpu_mem_usage=True,
            use_safetensors=True,
        )
        model.to(device)

        # Force English-only decoding; clear cached forced_decoder_ids to avoid
        # the duplicate SuppressTokensLogitsProcessor warning.
        model.generation_config.forced_decoder_ids = None
        model.generation_config.language = "english"
        model.generation_config.task     = "transcribe"

        processor = AutoProcessor.from_pretrained(model_id)

        # NOTE: do NOT pass generate_kwargs here — set per-call in _transcribe
        self._whisper_pipe = pipeline(
            "automatic-speech-recognition",
            model=model,
            tokenizer=processor.tokenizer,
            feature_extractor=processor.feature_extractor,
            torch_dtype=torch_dtype,
            device=device,
        )
        print(f"{_TAG} ✅ Whisper loaded on {device} — forced language: English.")

    # ── Main loop ─────────────────────────────────────────────────────────────

    def _run(self) -> None:
        attempt = 0
        while not self._stop_event.is_set():
            attempt += 1
            print(f"{_TAG} Recognition loop attempt #{attempt}")
            try:
                self._load_vad()
                self._load_whisper()
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
                            print(f"{_TAG} 🎙  Speech STARTED (VAD confidence={confidence:.2f})")
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
        try:
            duration_s = len(audio_np) / SAMPLE_RATE
            if duration_s < 0.4:
                print(f"{_TAG} Skipping short clip ({duration_s:.2f}s < 0.4s)")
                return

            result = self._whisper_pipe(
                {"array": audio_np, "sampling_rate": SAMPLE_RATE},
                generate_kwargs={"language": "english", "task": "transcribe"},
            )
            text = (result.get("text") or "").strip()
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
            print(f"{_TAG} Whisper transcription error: {exc}")

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
