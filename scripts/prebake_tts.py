#!/usr/bin/env python3
"""
scripts/prebake_tts.py
----------------------
One-time script to pre-synthesise all static TTS phrases and save them to
models/tts_cache/{voice_id}/ so tts_cache.speak_cached() can serve them
instantly from RAM on the next server start.

Usage:
    # From the repo root:
    python scripts/prebake_tts.py

    # Re-synthesise everything even if files exist:
    python scripts/prebake_tts.py --force

    # Bake for a specific voice (default: casual_female):
    python scripts/prebake_tts.py --voice casual_male

    # Bake for ALL voices in the VOICES registry:
    python scripts/prebake_tts.py --all-voices

VRAM note: This script runs Voxtral synchronously and sequentially — one phrase
at a time. Do NOT run while the backend is doing live TTS.  Total time on an
RTX 4050 with EULER_STEPS=3: ~40 phrases × ~1.5s = ~60 seconds per voice.
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

# ── Add repo root to sys.path so local imports resolve ────────────────────────
REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from backend.agent.tts_cache import STATIC_PHRASES, prebake_static_phrases
from backend.agent.tts import VOICES, _DEFAULT_VOICE_ID


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Pre-synthesise Friday TTS phrase cache"
    )
    parser.add_argument(
        "--voice",
        default=_DEFAULT_VOICE_ID,
        help=f"Voxtral voice preset (default: {_DEFAULT_VOICE_ID})",
    )
    parser.add_argument(
        "--all-voices",
        action="store_true",
        help="Bake for every voice in the VOICES registry",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Re-synthesise even if WAV files already exist",
    )
    args = parser.parse_args()

    voices_to_bake: list[str] = (
        list(VOICES.values()) if args.all_voices else [args.voice]
    )

    print("=" * 64)
    print(f"Friday TTS Phrase Pre-baker")
    print(f"Phrases : {len(STATIC_PHRASES)}")
    print(f"Voice(s): {', '.join(voices_to_bake)}")
    print(f"Force   : {args.force}")
    print("=" * 64)

    for voice in voices_to_bake:
        print(f"\n── Baking voice: {voice!r} ──────────────────────────────")
        t0 = time.monotonic()
        prebake_static_phrases(
            phrases=STATIC_PHRASES,
            voice_id=voice,
            force=args.force,
        )
        elapsed = time.monotonic() - t0
        print(f"   Done in {elapsed:.1f}s")

    print("\n✅ All done. Start the backend — phrases will load into RAM automatically.")


if __name__ == "__main__":
    main()
