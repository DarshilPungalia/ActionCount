# Friday STT — Implementation Plan
> Target file: `backend/agent/friday_stt.py`  
> Pass this document to Claude Code to apply all fixes in order.

---

## Context

`FridaySTT` is a real-time speech-to-text daemon using PyAudio + Silero VAD + `openai/whisper-large-v3` (HuggingFace Transformers pipeline). The system produces correct transcriptions only ~1 in 5 utterances. Root-cause analysis identified 5 bugs and 1 diagnostic gap. Fix them in the order listed below.

---

## Fix 1 — VAD Pre-Buffer (Critical)

**Problem:**  
During the `MIN_SPEECH_CHUNKS` confirmation window, incoming speech chunks are appended to `speech_buffer` only after `is_speaking` is set to `True`. The first `MIN_SPEECH_CHUNKS` worth of audio (~160 ms, often containing the first word) is lost before transcription.

**Changes to `_recognition_loop`:**

1. Add a `_pre_buffer: list[np.ndarray] = []` local variable alongside `speech_buffer`.

2. Replace the existing `if confidence > 0.5` block with the following logic:

```python
if confidence > SPEECH_THRESHOLD:
    if not is_speaking:
        speech_chunk_count += 1
        _pre_buffer.append(chunk)
        if speech_chunk_count >= MIN_SPEECH_CHUNKS:
            is_speaking   = True
            silence_count = 0
            speech_buffer.extend(_pre_buffer)  # flush pre-speech audio in
            _pre_buffer = []
            print(f"{_TAG} 🎙  Speech STARTED (VAD confidence={confidence:.2f})")
            self._fire_speech_start()
    else:
        speech_buffer.append(chunk)
    silence_count = 0
```

3. In the `else` (silence) branch, keep a rolling window of the pre-buffer so it never grows unbounded:

```python
else:
    if not is_speaking:
        speech_chunk_count = max(0, speech_chunk_count - 1)
        # Keep only the last MIN_SPEECH_CHUNKS chunks as a rolling pre-buffer
        _pre_buffer = _pre_buffer[-(MIN_SPEECH_CHUNKS):]
        continue
    # ... existing silence / finalization logic unchanged
```

**Expected outcome:** First word of every utterance is captured and sent to Whisper.

---

## Fix 2 — Dual-Threshold VAD Hysteresis (Critical)

**Problem:**  
A single threshold of `0.5` is used for both speech onset and speech offset. Speech at borderline confidence (0.35–0.50) — common with accents, quiet voices, or slight mic distance — is classified as silence and terminates the utterance early or prevents it from starting.

**Changes:**

1. Add two new module-level constants below the existing `MIN_SPEECH_CHUNKS` line:

```python
SPEECH_THRESHOLD  = 0.5    # confidence required to enter speech state
SILENCE_THRESHOLD = 0.35   # confidence below which silence is confirmed (hysteresis)
```

2. Replace every bare `confidence > 0.5` comparison with `confidence > SPEECH_THRESHOLD`.

3. Add a hysteresis band in the silence branch. When confidence is between `SILENCE_THRESHOLD` and `SPEECH_THRESHOLD` and the system is currently speaking, treat the chunk as continued speech rather than silence:

```python
else:
    # Hysteresis band: ambiguous confidence while speaking → keep buffering
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

**Expected outcome:** Soft-spoken or accented speech no longer triggers premature end-of-utterance.

---

## Fix 3 — Hallucination Filter (High Priority)

**Problem:**  
Whisper frequently hallucinates on short or noisy clips, emitting phrases like `"Thank you."`, `"you"`, `"..."`, or `"Subtitles by..."`. These are passed directly to the downstream agent, causing spurious tool calls.

**Changes:**

1. Add a module-level constant set after the imports:

```python
_HALLUCINATIONS: frozenset[str] = frozenset({
    "you", "thank you", "thanks", "bye", "goodbye", "ok", "okay",
    ".", "..", "...", "uh", "um", "hmm", "hm",
    "the", "a", "and", "subtitles by", "transcribed by",
    "www.", ".com", "amara.org", "like and subscribe",
})
```

2. Add a new private method to `FridaySTT`:

```python
def _is_hallucination(self, text: str) -> bool:
    """Return True if the transcript looks like a Whisper hallucination."""
    t = text.lower().strip().strip(".,!?\"'")
    if len(t) < 3:
        return True
    if t in _HALLUCINATIONS:
        return True
    if any(h in t for h in ("subtitle", "transcrib", "www.", ".com", "amara")):
        return True
    return False
```

3. In `_transcribe`, add the check immediately after stripping the text:

```python
text = (result.get("text") or "").strip()
if not text:
    print(f"{_TAG} Empty transcript (silence / noise).")
    return
if self._is_hallucination(text):
    print(f"{_TAG} 🚫 Hallucination filtered: \"{text}\"")
    return
```

**Expected outcome:** Garbage transcripts never reach the agent callback.

---

## Fix 4 — Reduce Silence Finalization Delay (Medium Priority)

**Problem:**  
`SILENCE_CHUNKS = 25` means the system waits ~800 ms of silence before finalizing an utterance. This makes the assistant feel unresponsive.

**Change:**  
Update the constant:

```python
SILENCE_CHUNKS = 15   # ~480 ms — was 25 (~800 ms)
```

No other code changes required.

**Expected outcome:** Utterances are finalized ~320 ms faster, improving perceived responsiveness.

---

## Fix 5 — Remove `import torch` From the Hot Loop (Medium Priority)

**Problem:**  
`import torch` is called inside the `while not self._stop_event.is_set()` loop, executing a module lookup on every 32 ms audio chunk (~31×/second). While Python caches imports, the repeated attribute lookup adds unnecessary overhead.

**Change:**  
Move `import torch` to the top of the `_recognition_loop` method, alongside the existing `import numpy` and `import pyaudio` statements:

```python
def _recognition_loop(self) -> None:
    import numpy as np
    import pyaudio
    import torch          # ← move here, outside the loop
    ...
```

Remove the `import torch` line from inside the `while` loop body.

**Expected outcome:** Reduced per-chunk overhead; cleaner hot path.

---

## Fix 6 — Add Device Diagnostic at Startup (Low Priority / Diagnostic)

**Problem:**  
PyAudio silently opens the OS default input device. If that device's native sample rate is not 16 kHz, audio going into Silero VAD and Whisper is mis-sampled, causing severe accuracy degradation with no error message.

**Change:**  
At the top of `_recognition_loop`, before opening the PyAudio stream, add:

```python
pa = pyaudio.PyAudio()
info = pa.get_default_input_device_info()
print(f"{_TAG} Default input device : {info['name']}")
print(f"{_TAG} Native sample rate   : {info['defaultSampleRate']} Hz")
print(f"{_TAG} Max input channels   : {info['maxInputChannels']}")
if int(info['defaultSampleRate']) != SAMPLE_RATE:
    print(f"{_TAG} ⚠️  WARNING: Native rate {info['defaultSampleRate']} Hz != {SAMPLE_RATE} Hz. "
          f"PyAudio will attempt resampling — accuracy may be degraded.")
```

**Expected outcome:** Any sample-rate mismatch is immediately visible in logs at startup.

---

## Summary of All Changes

| # | Location | Type | Impact |
|---|---|---|---|
| 1 | `_recognition_loop` | Pre-buffer VAD confirmation chunks | 🔴 Critical — first word recovery |
| 2 | `_recognition_loop` + module constants | Dual-threshold hysteresis | 🔴 Critical — soft speech detection |
| 3 | `_transcribe` + new `_is_hallucination` | Hallucination filter | 🟠 High — protects agent from garbage |
| 4 | Module constant `SILENCE_CHUNKS` | Reduce 800ms → 480ms | 🟡 Medium — responsiveness |
| 5 | `_recognition_loop` | Move `import torch` out of loop | 🟡 Medium — hot path cleanup |
| 6 | `_recognition_loop` startup | Device diagnostic logging | 🟢 Low — observability |

---

## Acceptance Criteria

After applying all fixes, the following should hold:

- [ ] Speaking a single short word (e.g. "yes", "stop") is transcribed correctly on the first attempt
- [ ] Startup logs show the correct input device name and confirm 16 kHz sample rate
- [ ] Hallucinated phrases (`"Thank you."`, `"..."`, single words) are printed as filtered and never reach the callback
- [ ] Time from finishing speaking to transcription starting is visibly under 500 ms
- [ ] No `import torch` statement appears inside the `while` loop body

---

## Notes for Claude Code

- Do not change the public API (`start`, `stop`, `instance`) — callers depend on these signatures.
- Do not change the WebSocket / barge-in logic in `_fire_speech_start`.
- Preserve all existing `print` log lines; only add new ones, do not remove.
- All new constants should be added at the module level near the existing `SILENCE_CHUNKS` / `MIN_SPEECH_CHUNKS` block.
- Run `python -c "from backend.agent.friday_stt import FridaySTT"` as a smoke test after changes to confirm no import errors.
