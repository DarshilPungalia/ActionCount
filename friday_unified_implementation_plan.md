# Friday — Unified STT + TTS Implementation Plan
> STT: `cstr/qwen3-asr-1.7b-GGUF` Q4_K via CrispASR (replaces Whisper)  
> TTS: `TrevorJS/voxtral-tts-q4-gguf` Q4_0 via voxtral-mini-realtime-rs  
> STT file: `backend/agent/friday_stt.py` (modify existing)  
> TTS file: `backend/agent/friday_tts.py` (create new)  
> Pass this document to Claude Code to implement everything in order.

---

## Context

Friday is a real-time AI voice assistant. The current STT stack (PyAudio + Silero VAD +
Whisper via HuggingFace Transformers) produces correct transcriptions only ~1 in 5
utterances due to multiple confirmed bugs and a hardware mismatch (mic native rate
44,100 Hz, stream opened at 16,000 Hz).

This plan does two things:

1. **Fixes all STT bugs** in `friday_stt.py` (Fixes 1–7)
2. **Replaces Whisper** with Qwen3-ASR-1.7B Q4_K via CrispASR C++ binary (Fix 8)
3. **Creates `friday_tts.py`** wrapping Voxtral Q4_0 via voxtral-mini-realtime-rs Rust binary

Both AI models run as subprocesses — they load GGUF from disk, run inference, and exit.
This means they never hold VRAM simultaneously, keeping the full stack within the
RTX 4050's 6 GB budget alongside RTMLib and OpenGL.

### VRAM Budget

| Component | VRAM | Residency |
|---|---|---|
| RTMLib pipeline | ~0.8–1.5 GB | Permanent |
| OpenGL rendering | ~0.3–0.8 GB | Permanent |
| Qwen3-ASR Q4_K (peak, per utterance) | ~1.4 GB | Subprocess — loads/exits |
| Voxtral Q4_0 (peak, per synthesis) | ~2.67 GB | Subprocess — loads/exits |
| Driver overhead | ~0.3 GB | Permanent |
| **Peak total (TTS synthesis)** | **~4.1–5.3 GB** | ✅ Within 6 GB |

---

## Part A — Prerequisites (One-Time Manual Setup)

Complete all prerequisites before running any code changes.
Verify each step passes before proceeding to the next.

---

### Prereq 1 — Build CrispASR (STT Runtime)

```bash
# Clone CrispASR
git clone https://github.com/CrispStrobe/CrispASR ~/crispasr
cd ~/crispasr

# Build with CUDA support (required for RTX 4050)
cmake -B build -DCMAKE_BUILD_TYPE=Release -DGGML_CUDA=ON
cmake --build build -j$(nproc) --target whisper-cli

# Verify binary exists
ls -lh ~/crispasr/build/bin/crispasr
```

> If CUDA build fails, try without `-DGGML_CUDA=ON` first to confirm the base
> build works, then re-add CUDA. Common fix: ensure `CUDA_HOME` is set.
> `export CUDA_HOME=/usr/local/cuda`

### Prereq 2 — Download Qwen3-ASR Q4_K GGUF

```bash
pip install huggingface_hub

python -c "
from huggingface_hub import hf_hub_download
path = hf_hub_download(
    repo_id='cstr/qwen3-asr-1.7b-GGUF',
    filename='qwen3-asr-1.7b-q4_k.gguf',
    local_dir='models/qwen3-asr'
)
print(f'Downloaded to: {path}')
"
# Model lands at: models/qwen3-asr/qwen3-asr-1.7b-q4_k.gguf (~1.33 GB)
```

### Prereq 3 — Verify CrispASR + Qwen3-ASR Works

```bash
# Download a test WAV (JFK sample bundled with CrispASR)
cp ~/crispasr/samples/jfk.wav /tmp/test.wav

# Run transcription — expected output includes "ask not what your country can do for you"
~/crispasr/build/bin/crispasr \
    --backend qwen3 \
    -m models/qwen3-asr/qwen3-asr-1.7b-q4_k.gguf \
    -f /tmp/test.wav \
    -l en
```

Expected output (Q4_K):
```
And so, my fellow Americans, ask not what your country can do for you;
ask what you can do for your country.
```

If this passes, STT runtime is confirmed working. Proceed.

### Prereq 4 — Build voxtral-mini-realtime-rs (TTS Runtime)

```bash
# Install Rust if not present
curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh
source $HOME/.cargo/env

# Clone and build
git clone https://github.com/TrevorJS/voxtral-mini-realtime-rs ~/voxtral-rs
cd ~/voxtral-rs

# Build with WGPU (vendor-agnostic GPU — works on RTX 4050 via Vulkan/CUDA)
cargo build --release --features "wgpu,cli,hub"

# Verify binary
ls -lh ~/voxtral-rs/target/release/voxtral

# Check available voices and options
~/voxtral-rs/target/release/voxtral speak --help
```

### Prereq 5 — Download Voxtral Q4_0 GGUF

```bash
python -c "
from huggingface_hub import hf_hub_download
path = hf_hub_download(
    repo_id='TrevorJS/voxtral-tts-q4-gguf',
    filename='voxtral-tts-q4.gguf',
    local_dir='models/voxtral'
)
print(f'Downloaded to: {path}')
"
# Model lands at: models/voxtral/voxtral-tts-q4.gguf (~2.67 GB)
```

### Prereq 6 — Verify Voxtral TTS Works

```bash
~/voxtral-rs/target/release/voxtral speak \
    --text "Friday TTS verification test." \
    --voice casual_female \
    --gguf models/voxtral/voxtral-tts-q4.gguf \
    --euler-steps 4 \
    --output /tmp/voxtral_test.wav

ls -lh /tmp/voxtral_test.wav   # must be non-zero
aplay /tmp/voxtral_test.wav    # must play audible speech
```

### Prereq 7 — Add to `.env`

```env
# STT — Qwen3-ASR via CrispASR
CRISPASR_BINARY=~/crispasr/build/bin/crispasr
QWEN3_ASR_MODEL=models/qwen3-asr/qwen3-asr-1.7b-q4_k.gguf
QWEN3_ASR_LANGUAGE=en

# TTS — Voxtral via voxtral-mini-realtime-rs
VOXTRAL_BINARY=~/voxtral-rs/target/release/voxtral
VOXTRAL_MODEL=models/voxtral/voxtral-tts-q4.gguf
VOXTRAL_VOICE=casual_female
VOXTRAL_EULER_STEPS=4
```

### Prereq 8 — Install Python Dependencies

```bash
pip install sounddevice>=0.4.6 soundfile>=0.12.1 scipy>=1.11.0

# Verify
python -c "import sounddevice, soundfile, scipy; print('All deps OK')"
```

---

## Part B — STT Fixes: `backend/agent/friday_stt.py`

Apply fixes in order 1 → 8. Each fix is independently testable.
Do not skip ahead — later fixes depend on earlier ones.

---

### Fix 1 — VAD Pre-Buffer (Critical)

**Problem:** During the `MIN_SPEECH_CHUNKS` confirmation window (~160ms), audio chunks
are counted but the first word's audio is lost before `is_speaking` is set to True.

**Changes to `_recognition_loop`:**

Add `_pre_buffer: list[np.ndarray] = []` alongside `speech_buffer` at the top of the loop.

Replace the existing `if confidence > 0.5` block:

```python
if confidence > SPEECH_THRESHOLD:
    if not is_speaking:
        speech_chunk_count += 1
        _pre_buffer.append(chunk)
        if speech_chunk_count >= MIN_SPEECH_CHUNKS:
            is_speaking   = True
            silence_count = 0
            speech_buffer.extend(_pre_buffer)   # flush pre-speech in
            _pre_buffer = []
            print(f"{_TAG} 🎙  Speech STARTED (VAD confidence={confidence:.2f})")
            self._fire_speech_start()
    else:
        speech_buffer.append(chunk)
    silence_count = 0
```

In the `else` (silence) branch, keep a rolling pre-buffer window:

```python
else:
    if not is_speaking:
        speech_chunk_count = max(0, speech_chunk_count - 1)
        _pre_buffer = _pre_buffer[-(MIN_SPEECH_CHUNKS):]
        continue
    # ... silence / finalization logic continues below
```

**Expected outcome:** First word of every utterance is captured.

---

### Fix 2 — Dual-Threshold VAD Hysteresis (Critical)

**Problem:** Single threshold `0.5` for both speech onset and offset causes early
termination on borderline speech (quiet voice, slight distance, accents).

Add two module-level constants below `MIN_SPEECH_CHUNKS`:

```python
SPEECH_THRESHOLD  = 0.5    # enter speech state
SILENCE_THRESHOLD = 0.35   # exit speech state (hysteresis gap)
```

Replace every `confidence > 0.5` with `confidence > SPEECH_THRESHOLD`.

Add hysteresis band in the silence branch:

```python
else:
    # Hysteresis: ambiguous confidence (0.35–0.50) while speaking → keep buffering
    if is_speaking and confidence >= SILENCE_THRESHOLD:
        speech_buffer.append(chunk)
        continue

    if not is_speaking:
        speech_chunk_count = max(0, speech_chunk_count - 1)
        _pre_buffer = _pre_buffer[-(MIN_SPEECH_CHUNKS):]
        continue

    # Definitive silence while speaking
    speech_buffer.append(chunk)
    silence_count += 1

    if silence_count >= SILENCE_CHUNKS:
        # ... existing finalization block unchanged
```

**Expected outcome:** Soft-spoken or accented speech no longer triggers premature cutoff.

---

### Fix 3 — Empty Transcript Filter (High Priority)

**Problem:** Short noise clips produce empty or garbage transcripts that reach the agent.
Note: with Qwen3-ASR replacing Whisper (Fix 8), classic Whisper hallucinations are gone,
but short-clip noise can still produce empty or minimal output from any ASR model.

Add module-level constant:

```python
_JUNK_TRANSCRIPTS: frozenset[str] = frozenset({
    "you", "thank you", "thanks", "bye", "goodbye", "ok", "okay",
    ".", "..", "...", "uh", "um", "hmm", "hm", "the", "a", "and",
})
```

Add private method:

```python
def _is_junk_transcript(self, text: str) -> bool:
    """Return True if transcript is too short or a known noise artifact."""
    t = text.lower().strip().strip(".,!?\"'")
    if len(t) < 3:
        return True
    if t in _JUNK_TRANSCRIPTS:
        return True
    return False
```

In `_transcribe`, after stripping text:

```python
text = (result_text or "").strip()
if not text:
    print(f"{_TAG} Empty transcript — skipping.")
    return
if self._is_junk_transcript(text):
    print(f"{_TAG} 🚫 Junk transcript filtered: \"{text}\"")
    return
```

**Expected outcome:** Sub-word noise artifacts never reach the agent callback.

---

### Fix 4 — Reduce Silence Finalization Delay (Medium Priority)

**Problem:** `SILENCE_CHUNKS = 25` (~800ms) makes the assistant feel sluggish.

Update constant:

```python
SILENCE_CHUNKS = 15   # ~480 ms — was 25 (~800 ms)
```

**Expected outcome:** Utterances finalized ~320ms faster.

---

### Fix 5 — Move All Imports Outside the Hot Loop (Medium Priority)

**Problem:** `import torch` fires inside the `while` loop ~31×/second.

Move all method-level imports to the top of `_recognition_loop`, before the loop:

```python
def _recognition_loop(self) -> None:
    import numpy as np
    import torch
    import sounddevice as sd      # replaces pyaudio (Fix 7)
    import scipy.signal as sps    # for resampling (Fix 7)
    ...
    while not self._stop_event.is_set():
        # no imports here
```

Remove `import torch` from inside the `while` loop body.

**Expected outcome:** Cleaner hot path, no repeated module lookups.

---

### Fix 6 — Device Diagnostic Logging (Low Priority)

**Problem:** Audio device identity and native sample rate are never logged.

Add at the top of `_recognition_loop`, after imports, before opening the stream:

```python
device_info = sd.query_devices(kind="input")
print(f"{_TAG} Default input device  : {device_info['name']}")
print(f"{_TAG} Native sample rate    : {device_info['default_samplerate']} Hz")
print(f"{_TAG} Max input channels    : {device_info['max_input_channels']}")
print(f"{_TAG} Capture rate          : {NATIVE_RATE} Hz → resampling to {SAMPLE_RATE} Hz")
```

**Expected outcome:** Device info visible in logs at every startup.

---

### Fix 7 — Replace PyAudio with sounddevice + Native Rate Resampling (Critical)

**Problem:** Mic native rate is confirmed 44,100 Hz. PyAudio opens stream requesting
16,000 Hz and silently delivers mis-labeled data. Silero VAD receives chunks 2.75×
too long; ASR receives mis-sampled audio. Root cause of 1/5 accuracy.

#### Step 7a — Add Constants

Below the existing `MIN_SPEECH_CHUNKS` block:

```python
NATIVE_RATE          = 44_100
NATIVE_CHUNK_SAMPLES = int(CHUNK_SAMPLES * NATIVE_RATE / SAMPLE_RATE)  # = 1411
# sps.resample_poly uses exact 160/441 rational ratio (GCD=100) — no approximation
```

#### Step 7b — Replace Stream Open

Remove:
```python
pa     = pyaudio.PyAudio()
stream = pa.open(
    format=pyaudio.paInt16,
    channels=1,
    rate=SAMPLE_RATE,
    input=True,
    frames_per_buffer=CHUNK_SAMPLES,
)
```

Replace with:
```python
stream = sd.InputStream(
    samplerate=NATIVE_RATE,
    channels=1,
    dtype="float32",
    blocksize=NATIVE_CHUNK_SAMPLES,
)
stream.start()
print(f"{_TAG} ✅ Mic stream open — listening …")
```

#### Step 7c — Replace Per-Chunk Read + Add Resampling

Remove:
```python
raw   = stream.read(CHUNK_SAMPLES, exception_on_overflow=False)
chunk = np.frombuffer(raw, dtype=np.int16).astype(np.float32) / 32768.0
```

Replace with:
```python
raw, overflowed = stream.read(NATIVE_CHUNK_SAMPLES)
if overflowed:
    print(f"{_TAG} ⚠️  Audio buffer overflow — some samples dropped.")
chunk = raw.flatten()                                   # float32, [-1.0, 1.0]
chunk = sps.resample_poly(chunk, SAMPLE_RATE, NATIVE_RATE)  # 44100 → 16000 Hz
```

#### Step 7d — Replace Cleanup

Remove:
```python
finally:
    stream.stop_stream()
    stream.close()
    pa.terminate()
    print(f"{_TAG} Mic stream closed.")
```

Replace with:
```python
finally:
    stream.stop()
    stream.close()
    print(f"{_TAG} Mic stream closed.")
```

#### Step 7e — Remove PyAudio

Remove `import pyaudio` from `_recognition_loop`.
Run `grep -r "pyaudio" backend/` — if no other file uses it, remove from `requirements.txt`.

#### Step 7f — Update `requirements.txt`

```
# Remove:
pyaudio

# Add (if not already present):
sounddevice>=0.4.6
scipy>=1.11.0
```

**Expected outcome:** Silero VAD and ASR receive correctly-sampled 16kHz mono audio.
Detection rate improves from 1/5 to 4/5+ before even applying Fix 8.

---

### Fix 8 — Replace Whisper with Qwen3-ASR Q4_K via CrispASR (Major)

**Problem:** Whisper runs as an in-process HuggingFace pipeline holding ~3.0 GB VRAM
permanently. Replacing it with Qwen3-ASR Q4_K via CrispASR subprocess frees ~1.6 GB
VRAM, improves accuracy (1.68% WER vs Whisper's ~7%), and removes PyTorch from the
STT runtime path entirely.

#### Step 8a — Add New Constants

Add below the `NATIVE_RATE` block:

```python
import os as _os
CRISPASR_BINARY   = _os.path.expanduser(_os.getenv("CRISPASR_BINARY", "~/crispasr/build/bin/crispasr"))
QWEN3_ASR_MODEL   = _os.path.expanduser(_os.getenv("QWEN3_ASR_MODEL",  "models/qwen3-asr/qwen3-asr-1.7b-q4_k.gguf"))
QWEN3_ASR_LANGUAGE = _os.getenv("QWEN3_ASR_LANGUAGE", "en")
```

#### Step 8b — Remove Whisper Loading

Remove the entire `_load_whisper` method:
```python
def _load_whisper(self):   # DELETE THIS ENTIRE METHOD
    ...
```

Remove the `self._whisper_pipe = None` line from `__init__`.

Remove the `self._load_whisper()` call from `_run`.

#### Step 8c — Replace `_transcribe` Method

Remove the existing `_transcribe` method entirely and replace with:

```python
def _transcribe(self, audio_np: "np.ndarray") -> None:
    """
    Write buffered audio to a temp WAV, pass to CrispASR Qwen3-ASR binary,
    parse stdout for the transcript, fire callback.
    """
    import tempfile    # noqa: PLC0415
    import subprocess  # noqa: PLC0415
    import soundfile as sf  # noqa: PLC0415
    import numpy as np  # noqa: PLC0415

    try:
        duration_s = len(audio_np) / SAMPLE_RATE
        if duration_s < 0.4:
            print(f"{_TAG} Skipping short clip ({duration_s:.2f}s < 0.4s)")
            return

        # ── 1. Write buffered audio to temp WAV ─────────────────────────────
        tmp_wav = tempfile.mktemp(suffix=".wav", prefix="friday_stt_")
        try:
            sf.write(tmp_wav, audio_np, SAMPLE_RATE)
        except Exception as exc:
            print(f"{_TAG} ❌ Failed to write temp WAV: {exc}")
            return

        # ── 2. Run CrispASR ──────────────────────────────────────────────────
        cmd = [
            CRISPASR_BINARY,
            "--backend", "qwen3",
            "-m", QWEN3_ASR_MODEL,
            "-f", tmp_wav,
            "-l", QWEN3_ASR_LANGUAGE,
            "--no-timestamps",     # clean text output only
        ]

        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=30,        # hard timeout — prevent stalls
            )
        except subprocess.TimeoutExpired:
            print(f"{_TAG} ❌ CrispASR timed out after 30s")
            return
        except FileNotFoundError:
            print(f"{_TAG} ❌ CrispASR binary not found: {CRISPASR_BINARY}")
            return
        finally:
            # Always clean up temp file
            try:
                import os  # noqa: PLC0415
                os.remove(tmp_wav)
            except OSError:
                pass

        if result.returncode != 0:
            print(f"{_TAG} ❌ CrispASR error (code {result.returncode}):")
            print(result.stderr[:500])
            return

        # ── 3. Parse transcript from stdout ─────────────────────────────────
        # CrispASR outputs one transcript line to stdout — strip ANSI codes and
        # progress lines (lines starting with '[' are progress/debug, not text)
        import re  # noqa: PLC0415
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
```

#### Step 8d — Update `_load_vad` — Keep It

The Silero VAD model loading stays exactly as-is. Only Whisper is removed.

#### Step 8e — Update `_run` Method

Remove the `self._load_whisper()` call. The `_run` loop should now only call
`self._load_vad()` before entering `_recognition_loop`:

```python
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
```

#### Step 8f — Update Startup Logging

In `start()`, update the model log line:

```python
print(f"{_TAG} Models : Silero VAD + Qwen3-ASR-1.7B Q4_K (CrispASR)")
print(f"{_TAG} STT    : {CRISPASR_BINARY}")
print(f"{_TAG} Model  : {QWEN3_ASR_MODEL}")
```

#### Step 8g — Update `requirements.txt`

```
# Remove (no longer needed for STT):
transformers
torch          # only remove if not used elsewhere in the project
accelerate     # only remove if not used elsewhere

# Add:
soundfile>=0.12.1   # for writing temp WAV in _transcribe
```

**Expected outcome:**
- Whisper no longer loaded — ~3.0 GB VRAM freed permanently
- CrispASR Q4_K used per utterance — ~1.4 GB peak VRAM, released after each call
- Transcription accuracy improves to 4/5+ (Q4_K WER ~1.68% on clean English)
- Startup log shows `Qwen3-ASR-1.7B Q4_K (CrispASR)` instead of `whisper-large-v3`

---

## Part C — TTS: Create `backend/agent/friday_tts.py`

Create this file from scratch. Wire into Friday only after smoke tests pass.

---

### Step C1 — Module Header + Constants

```python
"""
friday_tts.py
-------------
TTS daemon for the Friday AI assistant.

Stack:
  - voxtral-mini-realtime-rs  : Rust inference binary (WGPU)
  - Voxtral-4B Q4_0 GGUF      : 2.67 GB, 9 languages, 20 voice presets
  - sounddevice               : chunked audio playback with barge-in support

Flow:
  speak(text) → write temp WAV via Rust binary → stream via sounddevice
  stop_speaking() → set stop event → kill subprocess + interrupt playback
"""

from __future__ import annotations

import os
import threading
import tempfile
import subprocess
from enum import Enum
from typing import Optional

_TAG = "[FridayTTS]"

VOXTRAL_BINARY      = os.path.expanduser(os.getenv("VOXTRAL_BINARY", "~/voxtral-rs/target/release/voxtral"))
VOXTRAL_MODEL       = os.path.expanduser(os.getenv("VOXTRAL_MODEL",  "models/voxtral/voxtral-tts-q4.gguf"))
VOXTRAL_VOICE       = os.getenv("VOXTRAL_VOICE", "casual_female")
VOXTRAL_EULER_STEPS = int(os.getenv("VOXTRAL_EULER_STEPS", "4"))

# Euler steps guide:
#   8 = max quality,    RTF ~1.61x  (above real-time, adds latency)
#   4 = recommended,    RTF ~1.24x  (voice assistant default)
#   3 = real-time,      RTF ~1.0x   (latency-critical scenarios)
```

---

### Step C2 — Voice Preset Enum

```python
class VoxtralVoice(str, Enum):
    # English
    CASUAL_FEMALE       = "casual_female"
    CASUAL_MALE         = "casual_male"
    PROFESSIONAL_FEMALE = "professional_female"
    PROFESSIONAL_MALE   = "professional_male"
    NARRATIVE_FEMALE    = "narrative_female"
    NARRATIVE_MALE      = "narrative_male"
    # French
    FR_FEMALE = "fr_female"
    FR_MALE   = "fr_male"
    # German
    DE_FEMALE = "de_female"
    DE_MALE   = "de_male"
    # Spanish
    ES_FEMALE = "es_female"
    ES_MALE   = "es_male"
    # Italian
    IT_FEMALE = "it_female"
    IT_MALE   = "it_male"
    # Portuguese
    PT_FEMALE = "pt_female"
    PT_MALE   = "pt_male"
    # Dutch
    NL_FEMALE = "nl_female"
    NL_MALE   = "nl_male"
    # Hindi
    HI_FEMALE = "hi_female"
    HI_MALE   = "hi_male"
    # Arabic
    AR_FEMALE = "ar_female"
```

> **Note to Claude Code:** Run `$VOXTRAL_BINARY speak --help` after building to
> confirm exact voice preset names. Update enum values to match if they differ.

---

### Step C3 — `FridayTTS` Class

```python
class FridayTTS:
    """
    Singleton TTS daemon wrapping Voxtral Q4_0 GGUF via voxtral-mini-realtime-rs.

    speak(text)      — synthesize and play (non-blocking)
    stop_speaking()  — barge-in interrupt
    is_speaking      — property
    preload()        — background warmup
    """

    _instance: Optional["FridayTTS"] = None

    def __init__(self):
        self._lock             = threading.Lock()
        self._playback_thread: Optional[threading.Thread] = None
        self._current_proc:    Optional[subprocess.Popen] = None
        self._stop_event       = threading.Event()
        self._speaking         = False

    @classmethod
    def instance(cls) -> "FridayTTS":
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    @property
    def is_speaking(self) -> bool:
        return self._speaking
```

---

### Step C4 — `speak()` Method

```python
    def speak(
        self,
        text: str,
        voice: str       = VOXTRAL_VOICE,
        euler_steps: int = VOXTRAL_EULER_STEPS,
        blocking: bool   = False,
    ) -> None:
        if not text or not text.strip():
            return

        self.stop_speaking()
        self._stop_event.clear()
        self._speaking = True

        if blocking:
            self._synthesize_and_play(text, voice, euler_steps)
        else:
            self._playback_thread = threading.Thread(
                target=self._synthesize_and_play,
                args=(text, voice, euler_steps),
                daemon=True,
                name="FridayTTS-playback",
            )
            self._playback_thread.start()
```

---

### Step C5 — `_synthesize_and_play()` Method

```python
    def _synthesize_and_play(self, text: str, voice: str, euler_steps: int) -> None:
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
            print(f"{_TAG} Synthesizing [{voice}]: \"{preview}\"")

            # ── Synthesis ────────────────────────────────────────────────────
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
                return

            if retcode != 0:
                print(f"{_TAG} ❌ Voxtral error (code {retcode}):")
                print(stderr.decode(errors="replace")[:500])
                return

            if not os.path.exists(tmp_wav):
                print(f"{_TAG} ❌ Output WAV not found: {tmp_wav}")
                return

            # ── Playback ─────────────────────────────────────────────────────
            self._play_wav(tmp_wav)

        except Exception as exc:
            print(f"{_TAG} ❌ TTS error: {exc}")
        finally:
            self._speaking = False
            if tmp_wav and os.path.exists(tmp_wav):
                try:
                    os.remove(tmp_wav)
                except OSError:
                    pass
```

---

### Step C6 — `_play_wav()` with Barge-In Support

```python
    def _play_wav(self, wav_path: str) -> None:
        """Stream WAV in 100ms chunks — checks stop_event between chunks."""
        try:
            import soundfile   as sf  # noqa: PLC0415
            import sounddevice as sd  # noqa: PLC0415

            data, samplerate = sf.read(wav_path, dtype="float32")
            if data.ndim == 1:
                data = data.reshape(-1, 1)

            CHUNK_FRAMES = samplerate // 10   # 100ms

            with sd.OutputStream(samplerate=samplerate, channels=data.shape[1]) as stream:
                offset = 0
                while offset < len(data):
                    if self._stop_event.is_set():
                        print(f"{_TAG} Playback stopped (barge-in).")
                        break
                    chunk = data[offset : offset + CHUNK_FRAMES]
                    stream.write(chunk)
                    offset += CHUNK_FRAMES

        except Exception as exc:
            print(f"{_TAG} ❌ Playback error: {exc}")
```

---

### Step C7 — `stop_speaking()` Method

```python
    def stop_speaking(self) -> None:
        self._stop_event.set()
        self._speaking = False

        with self._lock:
            if self._current_proc and self._current_proc.poll() is None:
                try:
                    self._current_proc.terminate()
                    self._current_proc.wait(timeout=2.0)
                except Exception:
                    try:
                        self._current_proc.kill()
                    except Exception:
                        pass
                self._current_proc = None

        if self._playback_thread and self._playback_thread.is_alive():
            self._playback_thread.join(timeout=1.5)
```

---

### Step C8 — Background Warmup

```python
    def preload(self) -> None:
        """Fire a silent warmup synthesis to prime Voxtral's autotune cache."""
        threading.Thread(
            target=self._warmup, daemon=True, name="FridayTTS-warmup"
        ).start()

    def _warmup(self) -> None:
        print(f"{_TAG} 🔥 Warming up Voxtral binary …")
        try:
            tmp = tempfile.mktemp(suffix=".wav", prefix="friday_tts_warmup_")
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
            if os.path.exists(tmp):
                os.remove(tmp)
            print(f"{_TAG} ✅ Voxtral warmup complete.")
        except Exception as exc:
            print(f"{_TAG} ⚠️  Warmup failed (non-fatal): {exc}")
```

---

### Step C9 — Module-Level Convenience Functions + Auto-Warmup

```python
# Module-level convenience wrappers (used by FridaySTT barge-in)
def stop_speaking() -> None:
    FridayTTS.instance().stop_speaking()


def speak(text: str, **kwargs) -> None:
    FridayTTS.instance().speak(text, **kwargs)


# Auto-warmup at module import — fires in background, does not block startup
FridayTTS.instance().preload()
```

---

### Step C10 — Update `friday_stt.py` Barge-In Import

In `friday_stt.py`, `_fire_speech_start` already imports:
```python
from backend.agent.tts import stop_speaking
```

If a `backend/agent/tts.py` re-export shim exists, add to it:
```python
from backend.agent.friday_tts import speak, stop_speaking
```

If no shim exists, update the import in `friday_stt.py` directly to:
```python
from backend.agent.friday_tts import stop_speaking
```

---

## Part D — Smoke Tests

Run in order. Each must pass before the next. Do not skip.

### STT Smoke Tests

```bash
# D1 — sounddevice and scipy installed
python -c "import sounddevice, scipy; print('STT deps OK')"

# D2 — CrispASR binary accessible
$CRISPASR_BINARY --help

# D3 — Qwen3-ASR model file exists
ls -lh models/qwen3-asr/qwen3-asr-1.7b-q4_k.gguf

# D4 — End-to-end transcription from WAV
$CRISPASR_BINARY --backend qwen3 \
    -m models/qwen3-asr/qwen3-asr-1.7b-q4_k.gguf \
    -f ~/crispasr/samples/jfk.wav -l en --no-timestamps
# Expected: "...ask not what your country can do for you..."

# D5 — FridaySTT module imports cleanly
python -c "from backend.agent.friday_stt import FridaySTT; print('STT import OK')"

# D6 — Device diagnostic at startup (check logs show 44100 Hz → 16000 Hz)
python -c "
import time
from backend.agent.friday_stt import FridaySTT
stt = FridaySTT.instance()
stt.start(callback=lambda t: print(f'GOT: {t}'))
time.sleep(5)
stt.stop()
"
# Expected log lines:
# [FridaySTT] Default input device : <your mic name>
# [FridaySTT] Native sample rate   : 44100.0 Hz
# [FridaySTT] Capture rate         : 44100 Hz → resampling to 16000 Hz
```

### TTS Smoke Tests

```bash
# D7 — Voxtral binary accessible
$VOXTRAL_BINARY --help
$VOXTRAL_BINARY speak --help   # confirm voice preset names

# D8 — Voxtral model file exists
ls -lh models/voxtral/voxtral-tts-q4.gguf

# D9 — Direct synthesis (bypass Python)
$VOXTRAL_BINARY speak \
    --text "Friday is online." \
    --voice casual_female \
    --gguf models/voxtral/voxtral-tts-q4.gguf \
    --euler-steps 4 \
    --output /tmp/friday_direct_test.wav
aplay /tmp/friday_direct_test.wav

# D10 — FridayTTS module imports cleanly
python -c "from backend.agent.friday_tts import FridayTTS, speak; print('TTS import OK')"

# D11 — Python end-to-end TTS
python -c "
from backend.agent.friday_tts import speak
import time
speak('Voxtral TTS integration successful.')
time.sleep(6)
"

# D12 — Barge-in test
python -c "
from backend.agent.friday_tts import speak, stop_speaking
import time
speak('This is a long sentence that should be interrupted before it finishes.')
time.sleep(1.5)
stop_speaking()
print('Barge-in OK')
time.sleep(1)
"

# D13 — Full pipeline: STT → mock agent → TTS
python -c "
import time
from backend.agent.friday_stt import FridaySTT
from backend.agent.friday_tts import speak

def on_transcript(text):
    print(f'Transcript: {text}')
    speak(f'I heard you say: {text}')

stt = FridaySTT.instance()
stt.start(callback=on_transcript)
print('Speak now — you have 15 seconds.')
time.sleep(15)
stt.stop()
"
```

---

## Part E — VRAM Verification

Run after full Friday stack is running (RTMLib + OpenGL + STT + TTS active):

```bash
# During idle (between utterances)
nvidia-smi --query-gpu=memory.used,memory.free --format=csv,noheader

# During TTS synthesis (peak load)
watch -n 0.5 "nvidia-smi --query-gpu=memory.used,memory.free --format=csv,noheader"
```

Expected readings:

| State | Expected VRAM used |
|---|---|
| Idle (RTMLib + OpenGL only) | ~1.1–2.3 GB |
| During STT (Qwen3-ASR subprocess) | +~1.4 GB → ~2.5–3.7 GB |
| During TTS (Voxtral subprocess) | +~2.67 GB → ~3.8–5.0 GB |
| Both simultaneously (barge-in) | ~4.5–5.8 GB |

If TTS peak exceeds 5.8 GB, reduce Euler steps to 3 in `.env`:
```
VOXTRAL_EULER_STEPS=3
```

---

## Summary of All Changes

### `friday_stt.py` Changes

| Fix | Location | Change | Priority |
|---|---|---|---|
| 1 | `_recognition_loop` | VAD pre-buffer — recover first word | 🔴 Critical |
| 2 | Constants + loop | Dual-threshold VAD hysteresis | 🔴 Critical |
| 3 | `_transcribe` + new method | Junk transcript filter | 🟠 High |
| 4 | Module constant | `SILENCE_CHUNKS` 800ms → 480ms | 🟡 Medium |
| 5 | `_recognition_loop` | Move all imports outside hot loop | 🟡 Medium |
| 6 | `_recognition_loop` startup | Device diagnostic logging | 🟢 Low |
| 7 | Constants + loop + cleanup | Replace PyAudio with sounddevice + 44.1kHz resample | 🔴 Critical |
| 8 | `_transcribe` + `_run` + `_load_whisper` | Replace Whisper with Qwen3-ASR via CrispASR | 🔴 Major |

### New Files

| File | Action |
|---|---|
| `backend/agent/friday_tts.py` | Create — Voxtral TTS daemon |
| `backend/agent/tts.py` | Create or update — re-export shim |

### Config Changes

| File | Change |
|---|---|
| `requirements.txt` | Remove: `pyaudio`, optionally `transformers`, `torch`. Add: `sounddevice`, `scipy`, `soundfile` |
| `.env` | Add: `CRISPASR_BINARY`, `QWEN3_ASR_MODEL`, `QWEN3_ASR_LANGUAGE`, `VOXTRAL_BINARY`, `VOXTRAL_MODEL`, `VOXTRAL_VOICE`, `VOXTRAL_EULER_STEPS` |

---

## Final Acceptance Criteria

- [ ] Startup logs: device name, `44100 Hz → 16000 Hz`, `Qwen3-ASR-1.7B Q4_K (CrispASR)`
- [ ] Single short words ("yes", "stop", "Friday") transcribed correctly on first attempt
- [ ] Speaking a full sentence produces correct transcript 4/5 times or better
- [ ] TTS speaks audibly within 1 second of agent response on warm calls
- [ ] Barge-in stops TTS playback within 200ms of speech onset
- [ ] No `pyaudio` anywhere in `friday_stt.py`
- [ ] No `import torch` or `import pyaudio` inside the `while` loop body
- [ ] `nvidia-smi` shows idle VRAM < 3.5 GB (Whisper no longer resident)
- [ ] Peak VRAM during TTS synthesis < 5.8 GB

---

## Notes for Claude Code

**Order matters:** Apply Part B fixes 1→8 in sequence. Part C (TTS) can be done in
parallel with B but must not be wired in until D5 (STT import smoke test) passes.

**Do not touch:**
- `FridaySTT` public API: `start()`, `stop()`, `instance()`
- `_fire_speech_start()` WebSocket / barge-in logic (except updating the import path)
- `_load_vad()` — Silero VAD stays unchanged
- All existing `print` log lines — only add new ones

**Key implementation details:**
- `sounddevice.InputStream` yields `float32` in `[-1.0, 1.0]` — do NOT divide by 32768
- `sps.resample_poly(chunk, 16000, 44100)` uses exact 160/441 rational ratio (GCD=100)
- CrispASR stdout may contain ANSI escape codes and `[progress]` lines — strip both
- All paths from `.env` must be `os.path.expanduser()` expanded before subprocess use
- The Voxtral binary manages its own VRAM lifecycle — do not attempt to pre-load it
- `tempfile.mktemp()` is used (not `mkstemp`) intentionally — CrispASR and Voxtral
  need a path to write to, not an open file descriptor; always clean up in `finally`
- Run `grep -r "pyaudio" backend/` after Fix 7 to confirm full removal
- Run `grep -r "whisper" backend/` after Fix 8 to confirm Whisper fully removed from STT
