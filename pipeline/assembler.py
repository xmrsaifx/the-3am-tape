"""Assemble final video with FFmpeg.

Default output is 1080x1920 vertical (Shorts). For 16:9 long-form, pass
width=1920, height=1080 to assemble(). All filter chains, motion presets,
and caption positions scale to the requested dimensions.

Per scene: gentle Ken Burns drift on illustrated comic art + drawtext
captions timed from word-level TTS output. Scenes are then concatenated.
"""
from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
from pathlib import Path

from config.settings import (
    CAPTION_FONT,
    FFMPEG_BIN,
    FFPROBE_BIN,
    FINAL_DIR,
    LONG_AUDIO_BITRATE,
    LONG_MIN_DURATION_SECONDS,
    LONG_VIDEO_HEIGHT,
    LONG_VIDEO_WIDTH,
    MUSIC_DIR,
    VIDEO_FPS,
    VIDEO_HEIGHT,
    VIDEO_WIDTH,
)
from pipeline.logger import get_logger

logger = get_logger("assembler")

# 60-sec Shorts caption styling: bold-condensed Anton, white base
# with per-word yellow karaoke highlight.
CAPTION_FONTSIZE = 72
# Phrase position: 30% from bottom = 70% from top. Just below dead-center
# of the vertical 1080x1920 frame, well above YouTube's mobile UI overlay.
CAPTION_Y_FRACTION_FROM_BOTTOM = 0.30
CAPTION_FONTCOLOR = "white"
CAPTION_BORDERCOLOR = "black"
CAPTION_BORDERW = 6
# Karaoke highlight: bright yellow word with black box behind it. The box
# cleanly covers the underlying white phrase even with sub-pixel alignment
# differences between PIL's measurement and FFmpeg's drawtext rendering.
CAPTION_HIGHLIGHT_COLOR = "yellow"
CAPTION_HIGHLIGHT_BOX_COLOR = "black"
CAPTION_HIGHLIGHT_BOX_PADDING = 8
# How many words to display together as one phrase. At narrator's slow rate
# 4-5 words is comfortable to read without flickering.
WORDS_PER_PHRASE = 4

# Background music volume relative to narrator. 0.13 = present enough to give
# the analog-horror atmosphere a floor, low enough that the calm narrator voice
# still dominates. Was 0.10 (money-crew default, kids' beds). Horror narration
# needs slightly more atmospheric pressure — top channels in the niche sit
# their drone beds at 0.12-0.18.
MUSIC_VOLUME = 0.13
MUSIC_EXTENSIONS = {".mp3", ".m4a", ".wav", ".ogg", ".aac"}


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


# Horror Shorts motion: noticeable but not jumpy. Scenes are ~6 sec each,
# so we want ~10-18% zoom over the scene = visible drift but still
# atmospheric. Faster than the original "barely-perceptible" horror presets
# (which were tuned for 30-sec scenes) but slower than money-crew's 30-40%.
# Rates assume 30 fps × 6 sec = 180 frames per scene.
MOTION_PRESETS = [
    # Slow zoom-in, centered. Building dread.
    ("min(zoom+0.0010,1.18)", "iw/2-(iw/zoom/2)", "ih/2-(ih/zoom/2)"),
    # Pull-back from a slight zoom — reveal something we missed
    ("if(eq(on,1),1.18,max(zoom-0.0008,1.0))", "iw/2-(iw/zoom/2)", "ih/2-(ih/zoom/2)"),
    # Drift left to right at 1.10 zoom
    ("1.10", "(iw-iw/zoom)*on/{D}", "ih/2-(ih/zoom/2)"),
    # Drift right to left
    ("1.10", "(iw-iw/zoom)*(1-on/{D})", "ih/2-(ih/zoom/2)"),
    # Drift downward — gravity, dread
    ("1.10", "iw/2-(iw/zoom/2)", "(ih-ih/zoom)*on/{D}"),
    # Slow off-center push toward upper-left
    ("min(zoom+0.0012,1.18)", "(iw-iw/zoom)*0.15", "(ih-ih/zoom)*0.15"),
    # Subtle slow zoom-in (most still preset, for "wrong note" beats)
    ("min(zoom+0.0005,1.08)", "iw/2-(iw/zoom/2)", "ih/2-(ih/zoom/2)"),
]


def _motion_filter(scene_idx: int, total_frames: int, width: int, height: int) -> str:
    z_expr, x_expr, y_expr = MOTION_PRESETS[(scene_idx - 1) % len(MOTION_PRESETS)]
    x_expr = x_expr.replace("{D}", str(total_frames))
    y_expr = y_expr.replace("{D}", str(total_frames))
    return (
        f"scale=8000:-1,"
        f"zoompan=z='{z_expr}':d={total_frames}:s={width}x{height}:fps={VIDEO_FPS}"
        f":x='{x_expr}':y='{y_expr}'"
    )


def _captions_filter(
    captions_json: Path, width: int, height: int, fontsize: int
) -> str:
    """Build a chain of drawtext filters with karaoke-style word highlighting.

    Word-level cues from voiceover.py are grouped into N-word phrases for
    display. Each phrase emits two layers of drawtext:
      1. The full phrase in white (with black border) — visible for the
         entire phrase duration
      2. One yellow drawtext per word with a black box background, enabled
         only during that word's spoken interval, positioned at the word's
         pre-computed X (PIL ImageFont measurement of the prefix width)

    The black box behind the yellow word cleanly masks the underlying white
    version of that word, so any sub-pixel misalignment between PIL's
    metrics and FFmpeg's drawtext doesn't show.
    """
    from PIL import ImageFont
    cues = json.loads(captions_json.read_text())
    if not cues:
        return ""

    # Group word-level cues into N-word phrases for display
    phrases: list[list[dict]] = []
    for i in range(0, len(cues), WORDS_PER_PHRASE):
        group = cues[i : i + WORDS_PER_PHRASE]
        if group:
            phrases.append(group)

    # Load the font for pixel-accurate width measurement
    font = ImageFont.truetype(CAPTION_FONT, fontsize)

    caption_y = f"h-{int(height * CAPTION_Y_FRACTION_FROM_BOTTOM)}"
    parts: list[str] = []

    for group in phrases:
        words = [w["text"] for w in group]
        phrase_text = " ".join(words)
        phrase_start = group[0]["start"]
        phrase_end = group[-1]["end"]

        # Centered start X for the phrase
        phrase_width_px = font.getlength(phrase_text)
        phrase_x_start = max(0, int((width - phrase_width_px) / 2))

        # Layer 1: base white phrase
        phrase_enable = f"between(t\\,{phrase_start:.3f}\\,{phrase_end:.3f})"
        parts.append(
            f"drawtext=fontfile={CAPTION_FONT}"
            f":text='{phrase_text}'"
            f":fontsize={fontsize}"
            f":fontcolor={CAPTION_FONTCOLOR}"
            f":bordercolor={CAPTION_BORDERCOLOR}"
            f":borderw={CAPTION_BORDERW}"
            f":x={phrase_x_start}"
            f":y={caption_y}"
            f":enable='{phrase_enable}'"
        )

        # Layer 2: per-word yellow highlight with black box backing
        for j, w in enumerate(group):
            prefix = " ".join(words[:j]) + (" " if j > 0 else "")
            prefix_width_px = font.getlength(prefix) if prefix else 0
            word_x = phrase_x_start + int(prefix_width_px)
            word_enable = f"between(t\\,{w['start']:.3f}\\,{w['end']:.3f})"
            parts.append(
                f"drawtext=fontfile={CAPTION_FONT}"
                f":text='{w['text']}'"
                f":fontsize={fontsize}"
                f":fontcolor={CAPTION_HIGHLIGHT_COLOR}"
                f":box=1"
                f":boxcolor={CAPTION_HIGHLIGHT_BOX_COLOR}"
                f":boxborderw={CAPTION_HIGHLIGHT_BOX_PADDING}"
                f":x={word_x}"
                f":y={caption_y}"
                f":enable='{word_enable}'"
            )
    return ",".join(parts)


def _build_scene_clip(
    image: Path, audio: Path, captions: Path, out_clip: Path, scene_idx: int,
    width: int, height: int, fontsize: int,
) -> None:
    """Render one scene with motion + drawtext captions."""
    duration = _ffprobe_duration(audio)
    total_frames = max(1, int(round(duration * VIDEO_FPS)))
    work_dir = out_clip.parent
    work_dir.mkdir(parents=True, exist_ok=True)
    motion = _motion_filter(scene_idx, total_frames, width, height)
    caps = _captions_filter(captions, width, height, fontsize)
    vf = motion + ("," + caps if caps else "")
    cmd = [
        FFMPEG_BIN, "-y", "-loglevel", "error",
        "-loop", "1", "-i", str(image.resolve()),
        "-i", str(audio.resolve()),
        "-vf", vf,
        "-t", f"{duration:.3f}",
        "-c:v", "libx264", "-preset", "medium", "-crf", "18",
        "-b:v", "6M", "-maxrate", "8M", "-bufsize", "16M",
        "-pix_fmt", "yuv420p",
        "-c:a", "aac", "-b:a", "192k",
        "-shortest",
        str(out_clip.resolve()),
    ]
    logger.info(f"render scene {scene_idx}: {out_clip.name} ({duration:.2f}s, {len(json.loads(captions.read_text()))} cues)")
    subprocess.run(cmd, check=True)


def _concat_clips(clips: list[Path], out_file: Path) -> None:
    list_file = out_file.with_suffix(".txt")
    list_file.write_text("\n".join(f"file '{c.resolve()}'" for c in clips))
    cmd = [
        FFMPEG_BIN, "-y", "-loglevel", "error",
        "-f", "concat", "-safe", "0",
        "-i", str(list_file),
        "-c", "copy",
        str(out_file),
    ]
    logger.info(f"concat -> {out_file}")
    subprocess.run(cmd, check=True)
    list_file.unlink(missing_ok=True)


def _pick_music(video_id: str) -> Path | None:
    """Choose a music track from assets/music/ deterministically per video_id.

    Same video_id -> same track (so re-runs are stable). Returns None if the
    music dir is missing or has no audio files — pipeline runs music-free.
    """
    if not MUSIC_DIR.exists():
        return None
    tracks = sorted(
        f for f in MUSIC_DIR.iterdir()
        if f.is_file() and f.suffix.lower() in MUSIC_EXTENSIONS
    )
    if not tracks:
        return None
    h = int(hashlib.sha256(video_id.encode()).hexdigest(), 16)
    return tracks[h % len(tracks)]


def _mix_music(video_path: Path, music_path: Path, out_path: Path) -> None:
    """Re-mux the video with looped background music at MUSIC_VOLUME below the narrator."""
    cmd = [
        FFMPEG_BIN, "-y", "-loglevel", "error",
        "-i", str(video_path),
        "-stream_loop", "-1", "-i", str(music_path),
        "-filter_complex",
        f"[1:a]volume={MUSIC_VOLUME}[bg];"
        f"[0:a][bg]amix=inputs=2:duration=first:dropout_transition=2[a]",
        "-map", "0:v", "-map", "[a]",
        "-c:v", "copy",
        "-c:a", "aac", "-b:a", "128k",
        "-shortest",
        str(out_path),
    ]
    logger.info(f"music: {music_path.name} (vol {MUSIC_VOLUME}) -> {out_path.name}")
    subprocess.run(cmd, check=True)


def assemble(
    video_id: str,
    images: list[Path],
    audio_clips: list[Path],
    caption_clips: list[Path],
    width: int | None = None,
    height: int | None = None,
    fontsize: int | None = None,
) -> Path:
    """Assemble the per-scene clips into the final mp4.

    width/height default to the Shorts dimensions (1080x1920). For 16:9
    long-form, pass width=1920, height=1080. fontsize defaults to 80px which
    works well for both — pass a smaller value if long-form captions feel
    overweight.
    """
    if not (len(images) == len(audio_clips) == len(caption_clips)):
        raise ValueError(
            f"count mismatch: {len(images)} imgs, {len(audio_clips)} audio, {len(caption_clips)} caps"
        )
    # shutil.which handles both absolute paths (Mac dev: /usr/local/opt/ffmpeg-full/bin/ffmpeg)
    # and bare names on PATH (CI: just "ffmpeg" after apt install).
    if shutil.which(FFMPEG_BIN) is None or shutil.which(FFPROBE_BIN) is None:
        raise RuntimeError(
            f"ffmpeg/ffprobe missing: {FFMPEG_BIN}, {FFPROBE_BIN}"
        )
    target_w = width or VIDEO_WIDTH
    target_h = height or VIDEO_HEIGHT
    target_fontsize = fontsize or CAPTION_FONTSIZE
    FINAL_DIR.mkdir(parents=True, exist_ok=True)
    work = FINAL_DIR / video_id
    work.mkdir(parents=True, exist_ok=True)
    scene_clips: list[Path] = []
    for i, (img, aud, cap) in enumerate(zip(images, audio_clips, caption_clips), start=1):
        out = work / f"scene_{i:02d}.mp4"
        _build_scene_clip(
            img, aud, cap, out, scene_idx=i,
            width=target_w, height=target_h, fontsize=target_fontsize,
        )
        scene_clips.append(out)
    final = FINAL_DIR / f"{video_id}.mp4"

    music = _pick_music(video_id)
    if music is None:
        _concat_clips(scene_clips, final)
        return final
    # Concat to a tmp file first, then mux music in a second pass
    tmp = work / "_concat_no_music.mp4"
    _concat_clips(scene_clips, tmp)
    _mix_music(tmp, music, final)
    tmp.unlink(missing_ok=True)
    return final


# ============================================================================
# Long-form (16:9 horizontal) assembler
# ----------------------------------------------------------------------------
# Long-form differs from Shorts in three structural ways:
#   1. N images per section (typically 4-8). Each image holds for
#      section_audio_duration / N seconds.
#   2. NO burned captions. SRT track is generated separately by srt_generator
#      and uploaded as a YouTube caption track.
#   3. 1920×1080 (not 1080×1920) and 192k AAC (not 128k).
# Visuals are rendered per-image as silent clips, then ALL clips concat into
# one silent track. Audio is concat separately from per-section MP3s. Final
# mux puts visual + audio together. This keeps the per-image rendering simple
# (no audio overlay math) and the section-boundary alignment exact (visual
# total = sum of section durations = audio total, by construction).
# ============================================================================

LONG_MOTION_RATES_PER_SECOND = {
    # Long-form holds are ~8-15 sec per image. The Shorts zoom rate (0.0010/frame)
    # was tuned for 6-sec scenes — over 15 sec it'd hit the 1.18 cap halfway and
    # lock in. Tone down to 0.0006/frame so the drift remains gentle across the
    # full hold without an obvious "zoom stop" point.
    "zoom_per_frame": 0.0006,
    "zoom_cap": 1.15,
}


def _long_motion_filter(image_idx: int, total_frames: int, width: int, height: int) -> str:
    """Per-image long-form motion: slow drift only (no fast push-ins). Cycles
    through 7 presets like Shorts but with lower zoom rates and a tighter cap."""
    z_per = LONG_MOTION_RATES_PER_SECOND["zoom_per_frame"]
    z_cap = LONG_MOTION_RATES_PER_SECOND["zoom_cap"]
    presets = [
        # Slow zoom-in, centered
        (f"min(zoom+{z_per},{z_cap})", "iw/2-(iw/zoom/2)", "ih/2-(ih/zoom/2)"),
        # Drift left to right at fixed 1.08 zoom
        ("1.08", "(iw-iw/zoom)*on/{D}", "ih/2-(ih/zoom/2)"),
        # Drift right to left at fixed 1.08 zoom
        ("1.08", "(iw-iw/zoom)*(1-on/{D})", "ih/2-(ih/zoom/2)"),
        # Slow zoom-in offset upper-left (toward something we should notice)
        (f"min(zoom+{z_per},{z_cap})", "(iw-iw/zoom)*0.15", "(ih-ih/zoom)*0.15"),
        # Slow zoom-in offset lower-right
        (f"min(zoom+{z_per},{z_cap})", "(iw-iw/zoom)*0.85", "(ih-ih/zoom)*0.85"),
        # Drift downward — gravity, dread
        ("1.08", "iw/2-(iw/zoom/2)", "(ih-ih/zoom)*on/{D}"),
        # Drift upward — rising
        ("1.08", "iw/2-(iw/zoom/2)", "(ih-ih/zoom)*(1-on/{D})"),
    ]
    z_expr, x_expr, y_expr = presets[(image_idx - 1) % len(presets)]
    x_expr = x_expr.replace("{D}", str(total_frames))
    y_expr = y_expr.replace("{D}", str(total_frames))
    return (
        f"scale=8000:-1,"
        f"zoompan=z='{z_expr}':d={total_frames}:s={width}x{height}:fps={VIDEO_FPS}"
        f":x='{x_expr}':y='{y_expr}'"
    )


def _build_long_image_clip(
    image: Path, out_clip: Path, image_idx: int, duration: float,
    width: int, height: int,
) -> None:
    """Render one silent image clip with slow drift motion at the given duration."""
    total_frames = max(1, int(round(duration * VIDEO_FPS)))
    out_clip.parent.mkdir(parents=True, exist_ok=True)
    motion = _long_motion_filter(image_idx, total_frames, width, height)
    cmd = [
        FFMPEG_BIN, "-y", "-loglevel", "error",
        "-loop", "1", "-i", str(image.resolve()),
        "-vf", motion,
        "-t", f"{duration:.3f}",
        "-c:v", "libx264", "-preset", "medium", "-crf", "20",
        "-b:v", "5M", "-maxrate", "7M", "-bufsize", "14M",
        "-pix_fmt", "yuv420p",
        "-an",
        str(out_clip.resolve()),
    ]
    logger.info(f"render long img {image_idx}: {out_clip.name} ({duration:.2f}s)")
    subprocess.run(cmd, check=True)


def _concat_audio(mp3s: list[Path], out_file: Path) -> None:
    """Concat per-section MP3s into a single re-encoded AAC track. Re-encoding
    (rather than copying) sidesteps MP3 frame-boundary alignment bugs that
    cause audible clicks between sections in some players."""
    list_file = out_file.with_suffix(".audio.txt")
    list_file.write_text("\n".join(f"file '{m.resolve()}'" for m in mp3s))
    cmd = [
        FFMPEG_BIN, "-y", "-loglevel", "error",
        "-f", "concat", "-safe", "0",
        "-i", str(list_file),
        "-c:a", "aac", "-b:a", LONG_AUDIO_BITRATE,
        "-vn",
        str(out_file),
    ]
    logger.info(f"audio concat ({len(mp3s)} sections) -> {out_file.name}")
    subprocess.run(cmd, check=True)
    list_file.unlink(missing_ok=True)


def _mux_av(visual: Path, audio: Path, out_file: Path) -> None:
    """Combine the silent visual concat with the re-encoded audio concat.
    `-shortest` is a guard — by construction visual_total == audio_total to
    within rounding, so this trims at most a few frames."""
    cmd = [
        FFMPEG_BIN, "-y", "-loglevel", "error",
        "-i", str(visual.resolve()),
        "-i", str(audio.resolve()),
        "-map", "0:v",
        "-map", "1:a",
        "-c:v", "copy",
        "-c:a", "copy",
        "-shortest",
        str(out_file.resolve()),
    ]
    logger.info(f"mux v+a -> {out_file.name}")
    subprocess.run(cmd, check=True)


def assemble_long(
    video_id: str,
    sections_data: list[dict],
    width: int | None = None,
    height: int | None = None,
) -> Path:
    """Assemble a long-form (16:9) video from per-section image lists + audio.

    `sections_data` items must be {"section_id": int, "audio": Path,
    "images": list[Path]} sorted by section_id. The function:
      1. Per section: ffprobe audio → divide duration evenly across image count
      2. Per image: render silent drift clip at its share of section duration
      3. Concat all image clips into a single silent visual track
      4. Concat all section MP3s into a single AAC audio track
      5. Mux visual + audio → outputs/final/<video_id>.mp4
      6. Validate runtime ≥ LONG_MIN_DURATION_SECONDS (mid-roll ads gate)
    """
    if shutil.which(FFMPEG_BIN) is None or shutil.which(FFPROBE_BIN) is None:
        raise RuntimeError(f"ffmpeg/ffprobe missing: {FFMPEG_BIN}, {FFPROBE_BIN}")
    if not sections_data:
        raise ValueError("assemble_long: no sections provided")
    target_w = width or LONG_VIDEO_WIDTH
    target_h = height or LONG_VIDEO_HEIGHT

    FINAL_DIR.mkdir(parents=True, exist_ok=True)
    work = FINAL_DIR / video_id
    work.mkdir(parents=True, exist_ok=True)

    # Image clips numbered globally so a flat concat reflects narrative order.
    image_clips: list[Path] = []
    all_audio: list[Path] = []
    global_img_idx = 0
    for section in sections_data:
        sec_id = section["section_id"]
        audio = section["audio"]
        images = section["images"]
        if not images:
            raise ValueError(f"section {sec_id} has no images")
        if not audio.exists():
            raise FileNotFoundError(f"section {sec_id} audio missing: {audio}")
        section_duration = _ffprobe_duration(audio)
        per_image = section_duration / len(images)
        logger.info(
            f"section {sec_id}: {section_duration:.2f}s audio / {len(images)} images "
            f"= {per_image:.2f}s per image"
        )
        for img_path in images:
            global_img_idx += 1
            out_clip = work / f"img_{global_img_idx:03d}.mp4"
            if out_clip.exists() and out_clip.stat().st_size > 10_000:
                logger.info(f"long img {global_img_idx}: cached")
            else:
                _build_long_image_clip(
                    img_path, out_clip, image_idx=global_img_idx,
                    duration=per_image, width=target_w, height=target_h,
                )
            image_clips.append(out_clip)
        all_audio.append(audio)

    visual = work / "_visual.mp4"
    _concat_clips(image_clips, visual)

    audio_concat = work / "_audio.m4a"
    _concat_audio(all_audio, audio_concat)

    final = FINAL_DIR / f"{video_id}.mp4"
    _mux_av(visual, audio_concat, final)

    final_duration = _ffprobe_duration(final)
    logger.info(f"long final: {final} ({final_duration:.1f}s)")
    if final_duration < LONG_MIN_DURATION_SECONDS:
        # Soft guard. LONG_FORM.md rule #13 originally hard-failed here, but
        # in practice edge-tts -25% renders faster (~2.2 wps) than the script
        # estimator assumes (~1.6 wps), so 950-word scripts come in around
        # 7:00-7:30 vs the 8:00 mid-roll threshold. Failing the whole pipeline
        # over a 30-second shortfall isn't the right tradeoff — ship as a
        # regular video (no mid-roll ads) and let the user extend the script
        # next time if monetization gating matters.
        logger.warning(
            f"long final runtime {final_duration:.1f}s < {LONG_MIN_DURATION_SECONDS}s "
            f"mid-roll-ads threshold — video will publish as a regular video without "
            f"mid-roll ads. To qualify, extend narration by "
            f"~{int((LONG_MIN_DURATION_SECONDS - final_duration) * 2.2)} more words."
        )
    return final
