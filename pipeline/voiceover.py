"""Generate per-scene narration mp3 + word-level caption JSON via edge-tts.

Each scene gets:
  outputs/voiceovers/<video_id>/scene_NN.mp3
  outputs/voiceovers/<video_id>/scene_NN.captions.json
    -> [{"start": 0.0, "end": 0.4, "text": "I"},
        {"start": 0.4, "end": 0.7, "text": "WORKED"}, ...]

Captions are emitted ONE WORD PER ENTRY. The assembler groups them into
N-word phrases for display and renders both the base phrase and the
karaoke-style per-word yellow highlight.
"""
from __future__ import annotations

import asyncio
import json
import re
import time
from pathlib import Path
from typing import Iterable

import edge_tts

from config.settings import VOICEOVERS_DIR
from pipeline.logger import get_logger

logger = get_logger("voiceover")

CHARACTER_VOICES = {
    # en-US-ChristopherNeural at -25% rate + -10Hz pitch = the V3 horror tuning
    # validated on 2026-04-29. Christopher's calm-deep baseline + slow rate +
    # downshifted pitch produces creepypasta-narrator dread without sounding
    # robotic. Alternatives evaluated:
    #   en-GB-RyanNeural     — UK BBC documentary feel (V5 — close runner-up)
    #   en-US-RogerNeural    — older alternate voice (V4)
    #   en-US-EricNeural     — older male
    #   en-US-SteffanNeural  — newer voice, calm
    # NOTE: en-US-DavisNeural was removed from edge-tts in 2026 — do not re-add.
    "narrator": "en-US-ChristopherNeural",
}

# Horror tuning: slower rate + lower pitch. Deepens the voice toward the
# Mr. Nightmare / Dr. Creepen register without sounding warbly.
# Rate was -25% until 2026-05-22 — viewer feedback (Facebook comment) flagged
# the pacing as too slow. Bumped to -15%, which still sits below normal
# speech (preserves dread between phrases) while feeling natural to listen
# to. -10% and faster start sounding chipper for horror narration.
NARRATION_RATE = "-15%"
NARRATION_PITCH = "-10Hz"


_DRAWTEXT_SAFE = re.compile(r"[^A-Z0-9 \!\?]")


def _sanitize_caption(text: str) -> str:
    """Strip everything but uppercase letters, digits, spaces, ! and ? for safe drawtext."""
    return _DRAWTEXT_SAFE.sub("", text.upper()).strip()


def _build_word_cues(boundaries: list[dict]) -> list[dict]:
    """One cue per word. Assembler groups words into display phrases at render time
    and uses each word's start/end for the karaoke yellow highlight.

    `text` is the sanitized uppercase form used for FFmpeg drawtext (Shorts
    karaoke). `text_raw` preserves the original mixed-case word from edge-tts
    so the long-form SRT generator can emit proper-case closed captions."""
    cues: list[dict] = []
    for b in boundaries:
        text = _sanitize_caption(b["text"])
        if not text:
            continue
        start_s = b["offset"] / 10_000_000
        end_s = (b["offset"] + b["duration"]) / 10_000_000
        cues.append({
            "start": round(start_s, 3),
            "end": round(end_s, 3),
            "text": text,
            "text_raw": b["text"],
        })
    return cues


async def _generate_async(
    text: str, voice: str, mp3_dest: Path, captions_dest: Path
) -> None:
    mp3_dest.parent.mkdir(parents=True, exist_ok=True)
    communicate = edge_tts.Communicate(
        text, voice=voice, rate=NARRATION_RATE, pitch=NARRATION_PITCH,
        boundary="WordBoundary",
    )
    boundaries: list[dict] = []
    with mp3_dest.open("wb") as f:
        async for chunk in communicate.stream():
            t = chunk.get("type")
            if t == "audio":
                f.write(chunk["data"])
            elif t == "WordBoundary":
                boundaries.append({
                    "offset": chunk["offset"],
                    "duration": chunk["duration"],
                    "text": chunk["text"],
                })
    cues = _build_word_cues(boundaries)
    captions_dest.write_text(json.dumps(cues, indent=2))


def generate_clip(text: str, voice: str, mp3_dest: Path, captions_dest: Path) -> None:
    asyncio.run(_generate_async(text, voice, mp3_dest, captions_dest))


def _resolve_scene_voice(scene: dict, default_voice: str) -> str:
    """Per-scene voice override: scene["voice"] can be a CHARACTER_VOICES key
    or a raw edge-tts voice id."""
    override = scene.get("voice")
    if not override:
        return default_voice
    return CHARACTER_VOICES.get(override, override)


def _generate_items(
    video_id: str,
    items: Iterable[dict],
    voice: str,
    prefix: str,
    filter_id: int | None = None,
) -> tuple[list[Path], list[Path]]:
    """Generate per-item mp3 + captions. `prefix` is 'scene' (Shorts) or 'section'
    (long-form). If `filter_id` is set, only that one item is rendered — used
    by the long-form matrix shards so one job touches one section's audio."""
    out_dir = VOICEOVERS_DIR / video_id
    out_dir.mkdir(parents=True, exist_ok=True)
    mp3s: list[Path] = []
    caps: list[Path] = []
    for item in items:
        idx = item["id"]
        if filter_id is not None and idx != filter_id:
            continue
        item_voice = _resolve_scene_voice(item, voice)
        mp3 = out_dir / f"{prefix}_{idx:02d}.mp3"
        cap = out_dir / f"{prefix}_{idx:02d}.captions.json"
        if mp3.exists() and cap.exists() and mp3.stat().st_size > 0:
            logger.info(f"{prefix} {idx} voice: cached")
            mp3s.append(mp3)
            caps.append(cap)
            continue
        attempts = 0
        while True:
            attempts += 1
            try:
                logger.info(
                    f"edge-tts: voice={item_voice} {prefix}={idx} "
                    f"text={item['narration'][:80]!r}"
                )
                generate_clip(item["narration"], item_voice, mp3, cap)
                if mp3.stat().st_size < 1_000:
                    raise RuntimeError(f"audio too small: {mp3.stat().st_size}")
                logger.info(
                    f"{prefix} {idx} voice + captions saved ({mp3.stat().st_size:,} bytes)"
                )
                mp3s.append(mp3)
                caps.append(cap)
                break
            except Exception as e:
                logger.warning(f"{prefix} {idx} attempt {attempts} failed: {e}")
                mp3.unlink(missing_ok=True)
                cap.unlink(missing_ok=True)
                if attempts >= 3:
                    raise
                time.sleep(3)
    return mp3s, caps


def generate_for_video(
    video_id: str, scenes: Iterable[dict], voice: str
) -> tuple[list[Path], list[Path]]:
    """Shorts: return (mp3_paths, captions_json_paths) parallel to scenes order."""
    return _generate_items(video_id, scenes, voice, prefix="scene")


def generate_for_long_video(
    video_id: str,
    sections: Iterable[dict],
    voice: str,
    section_filter: int | None = None,
) -> tuple[list[Path], list[Path]]:
    """Long-form: one mp3 + captions per section (named section_NN). Pass
    `section_filter=N` from the matrix shard worker to render only section N;
    pass None from the assemble job to collect all (cached) section files in
    the canonical order required for SRT generation."""
    return _generate_items(video_id, sections, voice, prefix="section", filter_id=section_filter)
