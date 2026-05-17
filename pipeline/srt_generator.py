"""Build a SubRip (.srt) caption track from per-section edge-tts word boundaries.

Long-form videos don't burn captions into the video (see LONG_FORM.md §2);
instead a separate SRT is uploaded as a YouTube caption track and as Facebook's
`captions_file` parameter. YouTube's algorithm actively favors videos with a
real CC track (accessibility signal tied to recommendation reach).

Word-level cues from voiceover.py are timed per-section (starting at 0 each).
This module shifts each section's cues by the cumulative audio duration of
prior sections, then groups words into 6-word display cues for natural reading
pace at long-form speed.
"""
from __future__ import annotations

import json
import subprocess
from pathlib import Path

from config.settings import CAPTIONS_DIR, FFPROBE_BIN
from pipeline.logger import get_logger

logger = get_logger("srt_generator")

# Words per SRT cue. 6 is the readability sweet spot for narrated content at
# 1.5-1.8 wps — each cue holds ~3-4 sec, long enough to read without rushing
# and short enough to keep the highlight moving.
WORDS_PER_CUE = 6

# Minimum cue duration. Edge-tts can emit very short words (<150ms) which
# create unreadable single-frame cues if grouped at chunk boundaries. We
# extend the cue end to satisfy this floor so the captions don't strobe.
MIN_CUE_DURATION_SECONDS = 1.2


def _ffprobe_duration(audio: Path) -> float:
    out = subprocess.check_output(
        [
            FFPROBE_BIN, "-v", "error",
            "-show_entries", "format=duration",
            "-of", "default=noprint_wrappers=1:nokey=1",
            str(audio),
        ]
    )
    return float(out.strip())


def _format_timestamp(seconds: float) -> str:
    """SRT timestamp: HH:MM:SS,mmm"""
    if seconds < 0:
        seconds = 0
    total_ms = int(round(seconds * 1000))
    hours, rem = divmod(total_ms, 3600 * 1000)
    minutes, rem = divmod(rem, 60 * 1000)
    secs, millis = divmod(rem, 1000)
    return f"{hours:02d}:{minutes:02d}:{secs:02d},{millis:03d}"


def _chunk_words(words: list[dict]) -> list[dict]:
    """Group word cues into N-word display cues. Each output cue has
    {start, end, text} where text is space-joined word_raws and timings are
    first.start -> max(last.end, first.start + MIN_CUE_DURATION)."""
    cues: list[dict] = []
    for i in range(0, len(words), WORDS_PER_CUE):
        group = words[i : i + WORDS_PER_CUE]
        if not group:
            continue
        text = " ".join(w.get("text_raw") or w["text"] for w in group).strip()
        start = group[0]["start"]
        end = group[-1]["end"]
        if end - start < MIN_CUE_DURATION_SECONDS:
            end = start + MIN_CUE_DURATION_SECONDS
        cues.append({"start": start, "end": end, "text": text})

    # Guarantee no overlap with the next cue (rounding/min-duration can cause)
    for j in range(len(cues) - 1):
        if cues[j]["end"] > cues[j + 1]["start"]:
            cues[j]["end"] = max(cues[j]["start"] + 0.4, cues[j + 1]["start"] - 0.05)
    return cues


def build_srt_from_sections(
    video_id: str,
    section_audio: list[Path],
    section_captions: list[Path],
) -> Path:
    """Build outputs/captions/<video_id>.srt from parallel per-section audio +
    captions lists (both sorted by section_id). Returns the SRT path.

    Cumulative offset for section N = sum of ffprobe durations of sections
    1..N-1, so section boundaries line up exactly with the audio concat that
    assembler._concat_audio produces.
    """
    if len(section_audio) != len(section_captions):
        raise ValueError(
            f"srt: length mismatch — {len(section_audio)} audio vs "
            f"{len(section_captions)} caption files"
        )

    CAPTIONS_DIR.mkdir(parents=True, exist_ok=True)
    out_path = CAPTIONS_DIR / f"{video_id}.srt"

    all_words: list[dict] = []
    cumulative_offset = 0.0
    for audio_path, cap_path in zip(section_audio, section_captions):
        if not cap_path.exists():
            raise FileNotFoundError(f"missing captions: {cap_path}")
        if not audio_path.exists():
            raise FileNotFoundError(f"missing audio: {audio_path}")
        section_words = json.loads(cap_path.read_text())
        for w in section_words:
            all_words.append({
                "start": w["start"] + cumulative_offset,
                "end": w["end"] + cumulative_offset,
                "text": w.get("text", ""),
                "text_raw": w.get("text_raw") or w.get("text", ""),
            })
        cumulative_offset += _ffprobe_duration(audio_path)
        logger.info(
            f"srt: section {cap_path.stem} appended ({len(section_words)} words), "
            f"new offset {cumulative_offset:.2f}s"
        )

    cues = _chunk_words(all_words)
    logger.info(f"srt: {len(all_words)} words -> {len(cues)} display cues")

    lines: list[str] = []
    for i, cue in enumerate(cues, start=1):
        lines.append(str(i))
        lines.append(f"{_format_timestamp(cue['start'])} --> {_format_timestamp(cue['end'])}")
        lines.append(cue["text"])
        lines.append("")  # blank line separator

    out_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    logger.info(f"srt written: {out_path} ({len(cues)} cues, {cumulative_offset:.1f}s total)")
    return out_path
