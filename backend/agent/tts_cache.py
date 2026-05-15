"""
tts_cache.py
------------
Two-tier phrase cache for Friday TTS.

Tier 1 — Static phrase cache  (RAM-resident, pre-baked via scripts/prebake_tts.py)
    • Loaded at module import from  models/tts_cache/{voice_id}/
    • A manifest.json maps normalised text → WAV filename
    • Zero synthesis latency — pure memory lookup + bytes copy
    • Covers: all posture corrections, all motivation variants

Tier 2 — Per-user greeting cache  (disk-persistent, synthesised on first connection)
    • Stored in  models/tts_cache/greetings/{voice_id}/{username}_{kind}.wav
    • First connection for a new user: calls tts.speak() once, saves WAV
    • All subsequent logins: returns cached bytes instantly (~0 ms)

Tier 3 — Dynamic fallback  (full Voxtral synthesis)
    • speak_cached() falls through to tts.speak() on a cache miss
    • All LLM-generated responses always hit Tier 3

Public API (drop-in replacements for tts.speak):
    speak_cached(text, voice_id=None)  -> bytes | None
    get_greeting_audio(username, name, is_new, voice_id=None)  -> bytes | None

Run  python scripts/prebake_tts.py  once to pre-generate all static WAV files.
"""

from __future__ import annotations

import json
import os
import re
import unicodedata
from pathlib import Path
from typing import Optional

from backend.agent.tts import speak, _DEFAULT_VOICE_ID, VOICES

# ── Directory layout ──────────────────────────────────────────────────────────
# Resolve relative to the repo root (two levels up from this file)
_REPO_ROOT  = Path(__file__).resolve().parent.parent.parent
CACHE_ROOT  = _REPO_ROOT / "models" / "tts_cache"

_TAG = "[TTSCache]"

# ── All static phrases that will be pre-baked ─────────────────────────────────
# Add any new counter posture string here — prebake_tts.py reads this list.
STATIC_PHRASES: list[str] = [

    # ── Squat ─────────────────────────────────────────────────────────────────
    "Keep knees aligned with toes",
    "Keep chest upright",
    "Distribute weight evenly",
    "Go deeper into squat",

    # ── Pushup ────────────────────────────────────────────────────────────────
    "Keep body in straight line, engage core",
    "Lower hips to align body",
    "Keep head neutral with spine",
    "Keep elbows closer to body (~45°)",
    "Lower chest closer to ground",
    "Control movement, avoid bouncing",
    "Push evenly with both arms",

    # ── Bicep Curl ────────────────────────────────────────────────────────────
    "Keep torso stable, avoid swinging",
    "Tuck elbows inward",
    "Keep elbows fixed close to torso",
    "Fully extend arms at bottom",
    "Maintain symmetry between arms",
    "Slow down, use controlled movement",

    # ── Lateral Raise ─────────────────────────────────────────────────────────
    "Keep torso upright",
    "Stop at shoulder height",
    "Maintain slight elbow bend",
    "Raise both arms evenly",

    # ── Overhead Press ────────────────────────────────────────────────────────
    "Engage core, keep spine neutral",
    "Keep elbows slightly forward",
    "Fully extend arms overhead",
    "Lock both arms evenly",

    # ── Pull-up ───────────────────────────────────────────────────────────────
    "Avoid swinging, control body",
    "Pull evenly with both arms",
    "Complete full range of motion",

    # ── Sit-up ────────────────────────────────────────────────────────────────
    "Move in a controlled manner",
    "Avoid pulling neck, use core",
    "Complete full sit-up",

    # ── Crunch ────────────────────────────────────────────────────────────────
    "Keep lower back pressed down",
    "Keep neck neutral, avoid pulling head",
    "Lift upper body fully",
    "Lift slowly using abs",

    # ── Motivation phrases — all n=1 and n=2 variants ─────────────────────────
    "1 more rep! You've got this!",
    "2 more reps! You've got this!",
    "Keep pushing — you're almost there!",
    "Don't stop now, you can do it!",
    "Come on! 1 more rep!",
    "Come on! 2 more reps!",
    "Dig deep, keep going!",
    "Push through it — almost done!",
]


# ═══════════════════════════════════════════════════════════════════════════════
# Helpers
# ═══════════════════════════════════════════════════════════════════════════════

def _normalise(text: str) -> str:
    """
    Canonical lookup key: NFKC-normalised, lowercased, whitespace-collapsed,
    all non-alphanumeric characters stripped.
    Allows the cache to survive minor punctuation differences.
    """
    s = unicodedata.normalize("NFKC", text).lower().strip()
    s = re.sub(r"[^a-z0-9 ]+", "", s)
    return re.sub(r"\s+", " ", s).strip()


def _safe_filename(text: str) -> str:
    """Convert phrase to a safe filename stem (max 60 chars)."""
    s = re.sub(r"[^a-z0-9]+", "_", _normalise(text))
    return s[:60].strip("_")


# ═══════════════════════════════════════════════════════════════════════════════
# Tier 1 — Lazy phrase cache  (manifest in RAM, WAV bytes read from disk on demand)
# ═══════════════════════════════════════════════════════════════════════════════

# {voice_id: {normalised_text: absolute_Path_to_wav}}
# Only the manifest index (plain strings) lives in RAM — WAV bytes are never
# pre-loaded; each phrase does one SSD read (~1–5 ms) when first spoken.
_manifest_index: dict[str, dict[str, Path]] = {}


def _load_manifest(voice_id: str) -> None:
    """Read manifest.json for *voice_id* and build the path index."""
    cache_dir = CACHE_ROOT / voice_id
    manifest  = cache_dir / "manifest.json"
    if not manifest.exists():
        _manifest_index[voice_id] = {}   # mark as attempted so we don't retry
        return

    with open(manifest, encoding="utf-8") as fh:
        mapping: dict[str, str] = json.load(fh)  # normalised_text → filename

    index = {
        norm_text: cache_dir / filename
        for norm_text, filename in mapping.items()
    }
    _manifest_index[voice_id] = index
    print(f"{_TAG} Manifest loaded: {len(index)} phrases indexed for voice '{voice_id}'")


def _ensure_manifest(voice_id: str) -> None:
    if voice_id not in _manifest_index:
        _load_manifest(voice_id)


# ── Load default voice manifest at module import (tiny — just strings) ─────────
_load_manifest(_DEFAULT_VOICE_ID)


def speak_cached(text: str, voice_id: Optional[str] = None) -> bytes | None:
    """
    Serve TTS audio from the pre-baked phrase cache.

    Lookup flow:
      1. Find the phrase in the in-RAM manifest index  (~0 µs)
      2. Read its WAV file from disk on demand          (~1–5 ms SSD)
      3. On cache miss: fall back to full Voxtral synthesis

    No WAV bytes are kept in RAM between calls — only the
    manifest (a dict of strings → file paths) lives in memory.

    voice_id: Voxtral preset name; falls back to _DEFAULT_VOICE_ID if unset/invalid.
    """
    from backend.agent.tts import _VALID_PRESETS  # avoid circular at top level
    voice = voice_id if (voice_id and voice_id in _VALID_PRESETS) else _DEFAULT_VOICE_ID

    _ensure_manifest(voice)
    key      = _normalise(text)
    wav_path = _manifest_index.get(voice, {}).get(key)

    if wav_path and wav_path.exists():
        print(f"{_TAG} ⚡ Cache HIT [{voice}]: {text[:50]!r}")
        return wav_path.read_bytes()   # ~1–5 ms disk read

    print(f"{_TAG} Cache MISS — falling through to Voxtral: {text[:50]!r}")
    return speak(text, voice)


# ═══════════════════════════════════════════════════════════════════════════════
# Tier 2 — Per-user greeting cache
# ═══════════════════════════════════════════════════════════════════════════════

def get_greeting_audio(
    username: str,
    name: str,
    is_new: bool,
    voice_id: Optional[str] = None,
) -> bytes | None:
    """
    Return WAV bytes for the personalised greeting.

    • First call for this user+kind: synthesises via Voxtral, caches to disk.
    • All subsequent calls: returns cached bytes from disk (~0 ms disk read).

    The greeting text must exactly match what endpoint.py sends as `friday_text`
    so the UI and audio stay in sync.
    """
    from backend.agent.tts import _VALID_PRESETS
    voice = voice_id if (voice_id and voice_id in _VALID_PRESETS) else _DEFAULT_VOICE_ID

    kind    = "new" if is_new else "returning"
    greet_dir = CACHE_ROOT / "greetings" / voice
    greet_dir.mkdir(parents=True, exist_ok=True)

    # Safe username — strip path-unsafe chars
    safe_user = re.sub(r"[^a-zA-Z0-9_-]", "_", username)[:40]
    wav_path  = greet_dir / f"{safe_user}_{kind}.wav"

    if wav_path.exists():
        print(f"{_TAG} ⚡ Greeting cache HIT for '{username}' [{kind}]")
        return wav_path.read_bytes()

    # Build greeting text (must match endpoint.py exactly)
    if is_new:
        text = f"Hello {name}, I've created your profile. Let's get started."
    else:
        text = f"Hello {name}, welcome back. What are you up to?"

    print(f"{_TAG} Synthesising greeting for '{username}' [{kind}] — will cache after …")
    wav = speak(text, voice)
    if wav:
        try:
            wav_path.write_bytes(wav)
            print(f"{_TAG} Greeting cached → {wav_path.name}")
        except OSError as exc:
            print(f"{_TAG} Warning: could not write greeting cache: {exc}")
    return wav


# ═══════════════════════════════════════════════════════════════════════════════
# Utility: write static cache to disk  (called by scripts/prebake_tts.py)
# ═══════════════════════════════════════════════════════════════════════════════

def prebake_static_phrases(
    phrases: list[str] | None = None,
    voice_id: str | None = None,
    force: bool = False,
) -> None:
    """
    Synthesise every phrase in *phrases* (defaults to STATIC_PHRASES) and
    write WAV files + manifest.json to  models/tts_cache/{voice_id}/.

    Skips phrases whose WAV already exists on disk (pass force=True to re-bake).
    Intended to be called from  scripts/prebake_tts.py  — not at runtime.
    """
    voice   = voice_id or _DEFAULT_VOICE_ID
    phrases = phrases  or STATIC_PHRASES
    out_dir = CACHE_ROOT / voice
    out_dir.mkdir(parents=True, exist_ok=True)

    manifest_path = out_dir / "manifest.json"
    manifest: dict[str, str] = {}
    if manifest_path.exists():
        with open(manifest_path, encoding="utf-8") as fh:
            manifest = json.load(fh)

    done = skipped = errors = 0
    for phrase in phrases:
        norm = _normalise(phrase)
        fname = _safe_filename(phrase) + ".wav"
        wav_path = out_dir / fname

        if not force and norm in manifest and wav_path.exists():
            print(f"  [SKIP] {phrase!r}")
            skipped += 1
            continue

        print(f"  [BAKE] {phrase!r} …", end=" ", flush=True)
        wav = speak(phrase, voice)
        if wav:
            wav_path.write_bytes(wav)
            manifest[norm] = fname
            print(f"OK ({len(wav):,} bytes)")
            done += 1
        else:
            print("FAILED")
            errors += 1

    with open(manifest_path, "w", encoding="utf-8") as fh:
        json.dump(manifest, fh, indent=2, ensure_ascii=False)

    print(f"\n{_TAG} Prebake complete: {done} baked, {skipped} skipped, {errors} errors")
    print(f"{_TAG} Manifest written → {manifest_path}")
