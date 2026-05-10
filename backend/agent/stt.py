"""
stt.py
------
Speech-to-Text daemon for the Friday AI assistant.

Stack:
  - sounddevice              : server microphone capture (native rate, float32)
  - scipy.signal             : polyphase resampling 44 100 Hz → 16 000 Hz
  - Silero VAD               : voice activity detection (speech onset / offset)
  - CrispASR + Qwen3-ASR-1.7B Q4_K : transcription (subprocess, per-utterance)

Flow:
  1. sounddevice InputStream reads float32 PCM at native 44 100 Hz
  2. scipy.signal.resample_poly resamples each chunk to 16 000 Hz
  3. Silero VAD scores each chunk → detects speech start / end
  4. On speech START  → fire on_speech_start() + WebSocket listening indicator
  5. On speech START while TTS active → call tts.stop_speaking() (barge-in)
  6. On speech END    → write temp WAV, run CrispASR subprocess, fire callback(transcript)

Callbacks supplied to start():
  callback(transcript: str)   — final recognised phrase
  on_speech_start()           — VAD detected speech onset
  on_speech_end()             — VAD detected end of utterance

Config (.env):
  CRISPASR_BINARY     — path to crispasr.exe (see friday_setup.ps1)
  QWEN3_ASR_MODEL     — path to qwen3-asr-1.7b-q4_k.gguf
  QWEN3_ASR_LANGUAGE  — transcription language (default: en)
"""

from __future__ import annotations

import threading
from numpy import ndarray
from typing import Callable, Optional

_TAG = "[FridaySTT]"

# ── Audio constants ───────────────────────────────────────────────────────────
SAMPLE_RATE          = 16_000    # Target rate for Silero VAD and Whisper
NATIVE_RATE          = 44_100    # Mic native rate (Windows WASAPI default)
CHUNK_DURATION_MS    = 32        # Chunk size in ms (Silero recommendation)
CHUNK_SAMPLES        = int(SAMPLE_RATE * CHUNK_DURATION_MS / 1000)   # 512  @ 16 kHz
NATIVE_CHUNK_SAMPLES = int(NATIVE_RATE * CHUNK_DURATION_MS / 1000)   # 1411 @ 44.1 kHz
SILENCE_CHUNKS       = 15        # ~480 ms of silence → finalize (was 22 / ~700 ms)
MIN_SPEECH_CHUNKS    = 2         # consecutive high-conf chunks to confirm speech onset
                                 # (was 5 / ~160 ms — too high, misses short single words)
LOOKBACK_CHUNKS      = 10        # rolling lookback window of ALL chunks kept before onset
                                 # (~320 ms) — guarantees sub-threshold onset phonemes are
                                 # captured even if they never cross SPEECH_THRESHOLD
SPEECH_THRESHOLD     = 0.5       # confidence required to enter speech state
SILENCE_THRESHOLD    = 0.35      # confidence below which silence is confirmed (hysteresis)

# ── Fix 1: Barge-in thresholds (decoupled from VAD onset) ────────────────────
# Barge-in requires sustained HIGH-confidence speech before killing TTS.
# This prevents noise spikes at 0.5–0.75 confidence from aborting playback.
BARGE_IN_THRESHOLD   = 0.80      # VAD confidence required to count toward barge-in
BARGE_IN_CHUNKS      = 3         # consecutive chunks above threshold before firing (~96 ms)

# ── Fix 2: Dynamic RMS gate ───────────────────────────────────────────────────
# Instead of a hardcoded 0.01 floor, we track ambient noise during silence and
# require speech to be RMS_SPEECH_MULTIPLIER × louder than that baseline.
RMS_FLOOR            = 0.002     # absolute minimum — below this is a dead/disconnected mic
RMS_SPEECH_MULTIPLIER = 3.0      # speech RMS must be this many times the ambient level
RMS_EMA_ALPHA        = 0.05      # EMA weight for ambient noise update (slow, stable)
RMS_AMBIENT_INIT     = 0.008     # conservative starting estimate

# ── Junk / noise transcript filter ───────────────────────────────────────────
# Catches short-clip noise artifacts that any ASR model (including Qwen3-ASR)
# may produce on sub-word audio, as well as legacy Whisper hallucinations.
_JUNK_TRANSCRIPTS: frozenset[str] = frozenset({
    "you", "thank you", "thanks", "bye", "goodbye", "ok", "okay",
    ".", "..", "...", "uh", "um", "hmm", "hm",
    "the", "a", "and", "subtitles by", "transcribed by",
    "www.", ".com", "amara.org", "like and subscribe",
})

# ── CrispASR / Qwen3-ASR constants (Windows paths) ───────────────────────────
import os as _os
CRISPASR_BINARY    = _os.path.expanduser(
    _os.getenv("CRISPASR_BINARY",
               _os.path.join(_os.environ.get("USERPROFILE", "~"),
                             "crispasr", "build", "bin", "Release", "crispasr.exe"))
)
QWEN3_ASR_MODEL    = _os.path.expanduser(
    _os.getenv("QWEN3_ASR_MODEL",
               _os.path.join("models", "qwen3-asr", "qwen3-asr-1.7b-q4_k.gguf"))
)
QWEN3_ASR_LANGUAGE = _os.getenv("QWEN3_ASR_LANGUAGE", "en")


class FridaySTT:
    """Singleton Qwen3-ASR (via CrispASR) + Silero VAD continuous-recognition daemon."""

    _instance: Optional["FridaySTT"] = None

    def __init__(self):
        self._stop_event         = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self._callback: Optional[Callable[[str], None]] = None
        self._on_speech_start: Optional[Callable[[], None]] = None
        self._on_speech_end:   Optional[Callable[[], None]] = None

        # Lazy-loaded models
        self._vad_model     = None
        self._vad_utils     = None
        # No persistent ASR model — CrispASR is invoked as a subprocess per utterance

        # Fix 2: ambient RMS baseline, updated during silence periods
        self._ambient_rms: float = RMS_AMBIENT_INIT

        self._log_audio_device_info()

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
        print(f"{_TAG} Models : Silero VAD + Qwen3-ASR-1.7B Q4_K (CrispASR)")
        print(f"{_TAG} STT    : {CRISPASR_BINARY}")
        print(f"{_TAG} Model  : {QWEN3_ASR_MODEL}")
        print(f"{_TAG} Mic    : SERVER default audio device (sounddevice WASAPI)")

    def stop(self) -> None:
        print(f"{_TAG} Stop requested.")
        self._stop_event.set()

    # ── Audio device diagnostics ─────────────────────────────────────────────

    def _log_audio_device_info(self) -> None:
        """Log audio device configuration for debugging."""
        try:
            import sounddevice as sd  # noqa: PLC0415
            info = sd.query_devices(kind="input")
            print(f"{_TAG} === Audio Device Info ===")
            print(f"{_TAG} Device            : {info['name']}")
            print(f"{_TAG} Native sample rate : {info['default_samplerate']} Hz")
            print(f"{_TAG} Max input channels : {info['max_input_channels']}")
            print(f"{_TAG} Resampling         : {NATIVE_RATE} Hz → {SAMPLE_RATE} Hz")
            print(f"{_TAG} Native chunk       : {NATIVE_CHUNK_SAMPLES} samples (~{CHUNK_DURATION_MS} ms)")
            print(f"{_TAG} Resampled chunk    : {CHUNK_SAMPLES} samples (~{CHUNK_DURATION_MS} ms)")
            print(f"{_TAG} =========================")
        except Exception as exc:
            print(f"{_TAG} Could not query audio device: {exc}")

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

    # _load_whisper removed — CrispASR binary is invoked per-utterance in _transcribe.

    # ── Main loop ─────────────────────────────────────────────────────────────

    def _run(self) -> None:
        attempt = 0
        while not self._stop_event.is_set():
            attempt += 1
            print(f"{_TAG} Recognition loop attempt #{attempt}")
            try:
                self._load_vad()
                # Whisper removed — CrispASR binary is called per-utterance in _transcribe
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
        import numpy as np            # noqa: PLC0415
        import torch                  # noqa: PLC0415
        import sounddevice as sd      # noqa: PLC0415
        import scipy.signal as sps    # noqa: PLC0415

        (get_speech_timestamps, _, _, _, _) = self._vad_utils

        speech_buffer:      list[np.ndarray] = []
        silence_count:      int  = 0
        is_speaking:        bool = False
        speech_chunk_count: int  = 0

        # Rolling lookback — ALL chunks (regardless of VAD confidence) captured
        # unconditionally so that sub-threshold onset phonemes (e.g. the unvoiced
        # 's' in "stop", or the soft attack of any word) are always included when
        # speech is finally confirmed.  Replaces the old _pre_buffer which only
        # stored high-confidence chunks and therefore cut off word beginnings.
        from collections import deque as _deque  # noqa: PLC0415
        _lookback_buf: _deque = _deque(maxlen=LOOKBACK_CHUNKS)

        # Fix 1: barge-in state — tracked separately from VAD onset
        _barge_in_count: int  = 0
        _barge_in_fired: bool = False

        # Open stream at native rate; we resample each chunk to 16 kHz ourselves
        with sd.InputStream(
            samplerate=NATIVE_RATE,
            channels=1,
            dtype="float32",
            blocksize=NATIVE_CHUNK_SAMPLES,
        ) as stream:
            print(f"{_TAG} ✅ Audio stream opened: {NATIVE_RATE} Hz → {SAMPLE_RATE} Hz")

            while not self._stop_event.is_set():
                chunk_raw, overflowed = stream.read(NATIVE_CHUNK_SAMPLES)
                if overflowed:
                    print(f"{_TAG} ⚠️  Audio buffer overflow — CPU can't keep up")

                chunk_raw = chunk_raw.flatten()   # (NATIVE_CHUNK_SAMPLES, 1) → (N,)

                # Polyphase resample: 44100 → 16000 (ratio 160/441)
                chunk = sps.resample_poly(
                    chunk_raw,
                    up=SAMPLE_RATE,
                    down=NATIVE_RATE,
                ).astype(np.float32)
                # chunk is now exactly CHUNK_SAMPLES (512) at 16 kHz

                chunk_tensor = torch.from_numpy(chunk)
                confidence   = self._vad_model(chunk_tensor, SAMPLE_RATE).item()

                # Always add to lookback BEFORE any branching so that every
                # chunk — including sub-threshold onset phonemes — is available
                # when speech is confirmed a few chunks later.
                _lookback_buf.append(chunk)

                if confidence > SPEECH_THRESHOLD:
                    # ── Speech detected ───────────────────────────────────────

                    # Fix 1: barge-in requires sustained high-confidence speech.
                    # Accumulate a separate counter; only fire once per utterance.
                    if confidence >= BARGE_IN_THRESHOLD:
                        _barge_in_count += 1
                        if _barge_in_count >= BARGE_IN_CHUNKS and not _barge_in_fired:
                            _barge_in_fired = True
                            self._fire_barge_in()
                    else:
                        # Confidence is in SPEECH_THRESHOLD..BARGE_IN_THRESHOLD —
                        # valid speech but not strong enough to interrupt TTS.
                        _barge_in_count = 0

                    if not is_speaking:
                        speech_chunk_count += 1
                        if speech_chunk_count >= MIN_SPEECH_CHUNKS:
                            is_speaking   = True
                            silence_count = 0
                            # Seed speech_buffer from the full lookback window so that
                            # pre-onset audio (below VAD threshold) is always included.
                            # This is the fix for the first-word / single-word cutoff.
                            speech_buffer = list(_lookback_buf)
                            print(f"{_TAG} Speech STARTED (VAD confidence={confidence:.2f}, lookback={len(_lookback_buf)} chunks)")
                            self._fire_speech_start()
                    else:
                        speech_buffer.append(chunk)
                    silence_count = 0

                else:
                    # ── Silence / ambiguous detected ──────────────────────────
                    # Hysteresis band — ambiguous confidence while speaking → keep buffering
                    if is_speaking and confidence >= SILENCE_THRESHOLD:
                        speech_buffer.append(chunk)
                        continue

                    if not is_speaking:
                        speech_chunk_count = max(0, speech_chunk_count - 1)
                        # (lookback_buf self-manages via deque maxlen — no manual trim needed)

                        # Fix 2: calibrate ambient noise during confirmed silence
                        chunk_rms = float(np.sqrt(np.mean(chunk ** 2)))
                        self._ambient_rms = (
                            (1.0 - RMS_EMA_ALPHA) * self._ambient_rms
                            + RMS_EMA_ALPHA * chunk_rms
                        )
                        continue

                    # Definitive silence while speaking
                    speech_buffer.append(chunk)   # keep trailing silence for context
                    silence_count += 1

                    if silence_count >= SILENCE_CHUNKS:
                        print(f"{_TAG} 🔇 Speech ENDED — transcribing …")
                        self._fire_speech_end()

                        audio_np = np.concatenate(speech_buffer, axis=0)
                        speech_buffer      = []
                        _lookback_buf.clear()
                        silence_count      = 0
                        is_speaking        = False
                        speech_chunk_count = 0

                        # Fix 1: reset barge-in state for next utterance
                        _barge_in_count = 0
                        _barge_in_fired = False

                        self._transcribe(audio_np)

        print(f"{_TAG} Audio stream closed.")

    # ── Transcription ─────────────────────────────────────────────────────────

    def _is_junk_transcript(self, text: str) -> bool:
        """Return True if the transcript is too short or a known noise artifact."""
        t = text.lower().strip().strip(".,!?\"'")
        if len(t) < 3:
            return True
        if t in _JUNK_TRANSCRIPTS:
            return True
        if any(h in t for h in ("subtitle", "transcrib", "www.", ".com", "amara")):
            return True
        return False

    def _transcribe(self, audio_np: "ndarray") -> None:
        """
        Write buffered audio to a temp WAV, pass to CrispASR Qwen3-ASR binary,
        parse stdout for the transcript, fire callback.
        Uses Windows-safe path handling (backslashes, %TEMP%, list-arg subprocess).
        """
        import tempfile     # noqa: PLC0415
        import subprocess  # noqa: PLC0415
        import soundfile as sf  # noqa: PLC0415
        import numpy as np  # noqa: PLC0415
        import re           # noqa: PLC0415
        from pathlib import Path  # noqa: PLC0415

        try:
            duration_s = len(audio_np) / SAMPLE_RATE
            if duration_s < 0.4:
                print(f"{_TAG} Skipping short clip ({duration_s:.2f}s < 0.4s)")
                return

            # Dynamic RMS gate — skip near-silent clips regardless of VAD result
            rms = float(np.sqrt(np.mean(audio_np ** 2)))
            dynamic_threshold = max(RMS_FLOOR, self._ambient_rms * RMS_SPEECH_MULTIPLIER)
            if rms < dynamic_threshold:
                print(
                    f"{_TAG} Skipping low-energy clip "
                    f"(RMS={rms:.4f} < threshold={dynamic_threshold:.4f}, "
                    f"ambient={self._ambient_rms:.4f})"
                )
                return

            # ── 1. Write buffered audio to temp WAV ──────────────────────────
            # Use Path() to normalise backslashes on Windows; mktemp gives us
            # a path string — CrispASR needs to write to it, so we cannot use
            # mkstemp (which returns an open fd). Always clean up in finally.
            tmp_wav = str(Path(tempfile.mktemp(suffix=".wav", prefix="friday_stt_")))
            try:
                sf.write(tmp_wav, audio_np, SAMPLE_RATE)
            except Exception as exc:
                print(f"{_TAG} ❌ Failed to write temp WAV: {exc}")
                return

            # ── 2. Run CrispASR ──────────────────────────────────────────────
            # Pass args as a list (never shell=True) — handles spaces in Windows
            # paths correctly without manual quoting.
            cmd = [
                CRISPASR_BINARY,
                "--backend", "qwen3",
                "-m",        QWEN3_ASR_MODEL,
                "-f",        tmp_wav,
                "-l",        QWEN3_ASR_LANGUAGE,
                "--no-timestamps",
            ]

            try:
                result = subprocess.run(
                    cmd,
                    capture_output=True,
                    text=True,
                    timeout=30,
                )
            except subprocess.TimeoutExpired:
                print(f"{_TAG} ❌ CrispASR timed out after 30s")
                return
            except FileNotFoundError:
                print(f"{_TAG} ❌ CrispASR binary not found: {CRISPASR_BINARY}")
                return
            finally:
                # Always remove the temp WAV — do not leak files in %TEMP%
                try:
                    import os  # noqa: PLC0415
                    os.remove(tmp_wav)
                except OSError:
                    pass

            if result.returncode != 0:
                print(f"{_TAG} ❌ CrispASR error (code {result.returncode}):")
                print(result.stderr[:500])
                return

            # ── 3. Parse transcript from stdout ─────────────────────────────
            # Strip ANSI escape codes and progress lines (lines starting with '[')
            ansi_escape = re.compile(r'\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])')
            lines = result.stdout.strip().splitlines()
            text_lines = [
                ansi_escape.sub('', line).strip()
                for line in lines
                if line.strip() and not line.strip().startswith('[')
            ]
            text = " ".join(text_lines).strip()

            if not text:
                print(f"{_TAG} Empty transcript (silence / noise).")
                return

            if self._is_junk_transcript(text):
                print(f"{_TAG} 🚫 Junk transcript filtered: \"{text}\"")
                return

            word_count = len(text.split())
            print(f"{_TAG} Transcript ({word_count} words, {duration_s:.1f}s): \"{text}\"")

            if self._callback:
                try:
                    self._callback(text)
                except Exception as exc:
                    print(f"{_TAG} Transcript callback error: {exc}")

        except Exception as exc:
            print(f"{_TAG} Transcription error: {exc}")

    # ── Callbacks ─────────────────────────────────────────────────────────────

    def _fire_barge_in(self) -> None:
        """Stop TTS immediately — only called after BARGE_IN_CHUNKS consecutive
        high-confidence (≥ BARGE_IN_THRESHOLD) VAD detections. This prevents
        noise spikes and low-confidence VAD hits from aborting TTS playback."""
        print(f"{_TAG} ⏹️  Barge-in confirmed — stopping TTS.")
        try:
            from backend.agent.tts import stop_speaking  # noqa: PLC0415  (tts.py = FridayTTS shim)
            stop_speaking()
        except Exception:
            pass

    def _fire_speech_start(self) -> None:
        """Fire the on_speech_start callback. Barge-in is handled separately
        by _fire_barge_in() and may have already fired before this point."""
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