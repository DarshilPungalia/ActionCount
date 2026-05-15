# Friday TTS Integration — Reference Guide

> **Status: Active (re-enabled 2026-05-15).**
> Barge-in (`stop_speaking` on STT speech-start) was permanently removed so Voxtral synthesis
> and CrispASR transcription never overlap. VRAM budget: keep `VOXTRAL_EULER_STEPS=3` on RTX 4050.

---

## Architecture Overview

```
User voice transcript
        │
        ▼
  endpoint.py  ──▶  invoke_friday() (LangGraph)  ──▶  response_text
        │
        ├─ channel == "text"  ──▶  friday_text  WebSocket msg  (still works)
        │
        └─ channel == "voice" ──▶  tts_speak(response_text)
                                        │
                                        ▼
                               voxtral.exe subprocess
                               --gguf models/voxtral/voxtral-tts-q4.gguf
                               --voices-dir models/voxtral/voice_embedding
                               --voice casual_female
                               --euler-steps 3
                               --output /tmp/friday_tts_XYZ.wav
                                        │
                                        ▼
                               WAV bytes returned
                                        │
                          ┌─────────────┴─────────────┐
                          │                           │
                   speaking_indicator(True)    to_ws_envelope(wav_bytes)
                   WebSocket msg               WebSocket msg (base64 WAV)
                          │                           │
                   speaking_indicator(False)          │
                   WebSocket msg                      │
                                                      ▼
                                            Browser: new Audio(...).play()
```

---

## Files Involved

| File | Role |
|---|---|
| `backend/agent/tts.py` | Voxtral subprocess wrapper — `speak()`, `stop_speaking()`, `to_ws_envelope()`, `speaking_indicator()` |
| `backend/endpoint.py` | Two call sites: `_handle_friday_message()` + `_push_friday_tts()` |
| `frontend/index.html` | `FridayHUD.playAudio()` handles `tts_audio` WS msg; `setSpeakingIndicator()` handles `friday_speaking` |

---

## `backend/agent/tts.py` — Module Interface

```python
speak(text, voice_id=None) -> bytes | None
    # Synchronous — call via asyncio.to_thread()
    # voice_id = Voxtral preset name (e.g. "casual_female")
    # Silently falls back to _DEFAULT_VOICE_ID for unknown IDs (e.g. old ElevenLabs IDs)
    # Returns raw WAV bytes, or None on error / barge-in

stop_speaking() -> None
    # Called by STT barge-in to terminate the current Voxtral subprocess

to_ws_envelope(audio_bytes: bytes, _text: str = "") -> dict
    # Returns {"type": "tts_audio", "data": {"audio": "<base64>", "mime": "audio/wav"}}

speaking_indicator(active: bool) -> dict
    # Returns {"type": "friday_speaking", "data": {"active": True|False}}

list_voices() -> list[dict]           # [{name, voice_id}, ...]
VOICES: dict[str, str]                # "Casual Female" -> "casual_female"
_DEFAULT_VOICE_ID: str                # "casual_female"
```

### Key config (.env)
```env
VOXTRAL_BINARY=%USERPROFILE%\voxtral-rs\target\release\voxtral.exe
VOXTRAL_MODEL=models\voxtral\voxtral-tts-q4.gguf
VOXTRAL_VOICES_DIR=models\voxtral\voice_embedding
VOXTRAL_VOICE=casual_female
VOXTRAL_EULER_STEPS=3          # 3=real-time, 4=balanced, 8=quality
VOXTRAL_WARMUP=true            # set false to skip startup warmup synthesis
```

---

## `endpoint.py` Call Sites

### 1. Agent response — `_handle_friday_message()`

```python
# TTS audio — fires only on voice channel
if response_text and channel == "voice":
    await ws.send_json(speaking_indicator(True))
    user_voice_id = db.get_user_voice(username) or None
    mp3 = await asyncio.to_thread(tts_speak, response_text, user_voice_id)
    if mp3:
        await ws.send_json(to_ws_envelope(mp3, response_text))
    await ws.send_json(speaking_indicator(False))
    print(f"[FridayWS] Response cycle complete for {username!r}")
elif response_text:
    await ws.send_json({"type": "friday_text", "data": {"text": response_text}})
```

### 2. Posture corrections & motivation — `_push_friday_tts()`

Called from the `/ws/stream` frame-loop whenever `session.tts_queue` has items:

```python
# In the /ws/stream loop — drain queue and push to all voice-channel Friday WS connections:
while not session.tts_queue.empty():
    _kind, _text = session.tts_queue.get_nowait()
    for _uname, _fws in list(_friday_ws_connections.items()):
        if _get_user_channel(_uname) == "voice":
            asyncio.create_task(_push_friday_tts(_fws, _uname, _text))

# The helper function:
async def _push_friday_tts(ws, username, text):
    user_voice_id = db.get_user_voice(username) or None
    await ws.send_json(speaking_indicator(True))
    mp3 = await asyncio.to_thread(tts_speak, text, user_voice_id)
    if mp3:
        await ws.send_json(to_ws_envelope(mp3, text))
    await ws.send_json(speaking_indicator(False))
```

The posture correction phrases are enqueued by `InferenceWorker` in `session_manager.py`
via `session.tts_queue.put(("posture", correction_text))`.

### 3. Voice preference REST API

```
GET  /api/voices        -> {voices: [{name, voice_id}], default: "casual_female"}
POST /api/user/voice    body: {voice_id: "casual_female"}  -> {status, voice_id, voice_name}
```

User preference stored in MongoDB via `db.get_user_voice(username)` / `db.set_user_voice(username, voice_id)`.

---

## WebSocket Protocol (Friday WS)

Messages sent from backend -> frontend during a TTS response:

```jsonc
// 1. Speaking started
{"type": "friday_speaking", "data": {"active": true}}

// 2. Audio payload (base64 WAV, ~400 KB per short response)
{"type": "tts_audio", "data": {"audio": "<base64>", "mime": "audio/wav"}}

// 3. Speaking ended
{"type": "friday_speaking", "data": {"active": false}}
```

Frontend handler in `index.html`:
```js
// Currently handles old format (friday_audio). Update to tts_audio when re-enabling:
else if (msg.type === 'tts_audio') {
    try { new Audio('data:' + msg.data.mime + ';base64,' + msg.data.audio).play().catch(()=>{}); }
    catch(_) {}
}
if (msg.type === 'friday_speaking') FridayHUD.setSpeakingIndicator(msg.data.active);
```

---

## Barge-in Flow

```
User speaks while Friday is responding
        |
        v
  Silero VAD fires (confidence > threshold)
        |
        v
  FridaySTT._on_speech_start()
        |
        +-- calls stop_speaking()
                |
                v
        FridayTTS.stop_speaking()
                |
                +-- self._stop_event.set()
                +-- proc.terminate()  (kills voxtral.exe subprocess immediately)
```

---

## How to Re-Enable TTS

1. **Restore imports** in `endpoint.py`:
```python
from backend.agent.tts import (
    speak as tts_speak,
    to_ws_envelope,
    speaking_indicator,
    list_voices,
    VOICES as TTS_VOICES,
    _DEFAULT_VOICE_ID as TTS_DEFAULT_VOICE,
)
```

2. **Restore `_handle_friday_message`** TTS block (see Section 1 above).

3. **Restore `_push_friday_tts`** function (see Section 2 above).

4. **Restore `session.tts_queue` drain loop** in `/ws/stream` (see Section 2 above).

5. **Restore voice API endpoints** (`/api/voices`, `/api/user/voice`) — see Section 3.

6. **Update frontend** `index.html` to handle `tts_audio` type (see WebSocket Protocol section).

7. **VRAM budget**: RTX 4050 Laptop (6 GB). Keep `VOXTRAL_EULER_STEPS=3`.
   Peak simultaneous (Voxtral + CrispASR at barge-in): ~5.1 GB / 6.1 GB.

---

## Why It Was Removed

| Reason | Detail |
|---|---|
| GPU OOM | Barge-in overlap (Voxtral ~2.4 GB + CrispASR ~1.3 GB + pose model ~1.1 GB) exceeded 6 GB VRAM |
| Workaround tried | `--use_tts=false` CLI flag, conditional import gate — still crashed due to unconditional module import |
| Final decision | Removed entirely; re-enable when VRAM upgraded or lighter Voxtral quantisation available |
