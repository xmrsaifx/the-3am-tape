"""Generate a 1280×720 YouTube thumbnail for a long-form tape.

Per LONG_FORM.md §10, thumbnail CTR is the single biggest lever on long-form
views — YouTube's auto-picked frames are a dropped ball. This module picks a
key scene image, resizes/darkens it for legibility, and overlays a short
teaser phrase in Anton (the same brand font used for Shorts karaoke).

Picking source image and overlay text:
- Source image: `script["thumbnail_source"]` like {"section": 1, "image": 1},
  defaults to section 1 image 1.
- Overlay text: `script["thumbnail_text"]`, else first ~4 words of the title
  (stripped of the " | True Scary Story" suffix), forced to uppercase.
"""
from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw, ImageEnhance, ImageFilter, ImageFont

from config.settings import (
    CAPTION_FONT,
    IMAGES_DIR,
    THUMBNAIL_HEIGHT,
    THUMBNAIL_WIDTH,
    THUMBNAILS_DIR,
)
from pipeline.logger import get_logger

logger = get_logger("thumbnail_generator")

# Overlay text: max chars per line, max lines. Anton is condensed so it fits
# more chars per inch than a normal sans, but we still cap at 18 chars/line
# so the text reads on a phone-grid thumbnail.
MAX_CHARS_PER_LINE = 18
MAX_LINES = 2
# Anton displays well at thumbnail scale around 1/6th of the height.
FONT_SIZE = 130
STROKE_WIDTH = 6


def _resolve_source_image(script: dict, video_id: str) -> Path:
    """Pick which rendered PNG to use as the thumbnail backdrop."""
    src_spec = script.get("thumbnail_source") or {"section": 1, "image": 1}
    sec_id = src_spec.get("section", 1)
    img_idx = src_spec.get("image", 1)
    path = IMAGES_DIR / video_id / f"section_{sec_id:02d}_image_{img_idx:02d}.png"
    if not path.exists():
        raise FileNotFoundError(
            f"thumbnail source image missing: {path} — render the section first"
        )
    return path


def _derive_overlay_text(script: dict) -> str:
    """Use explicit `thumbnail_text` if provided, else trim down the title."""
    if script.get("thumbnail_text"):
        return script["thumbnail_text"].strip().upper()
    title = script.get("title", "") or script.get("topic", "") or "THE 3AM TAPE"
    # Drop the YouTube SEO suffix like " | True Scary Story"
    head = title.split("|")[0].strip()
    # Take the first 5 words — short, punchy, fits two lines
    words = head.split()
    return " ".join(words[:5]).upper()


def _wrap_to_lines(text: str, max_chars: int, max_lines: int) -> list[str]:
    """Greedy word-wrap into at most `max_lines` lines of at most `max_chars`
    each. If the text won't fit, drop trailing words until it does."""
    words = text.split()
    lines: list[str] = []
    current = ""
    for word in words:
        candidate = (current + " " + word).strip()
        if len(candidate) <= max_chars:
            current = candidate
        else:
            if current:
                lines.append(current)
            current = word
            if len(lines) >= max_lines:
                break
    if current and len(lines) < max_lines:
        lines.append(current)
    return lines[:max_lines]


def _apply_letterbox_gradient(im: Image.Image) -> Image.Image:
    """Darken the lower 60% of the image so white text reads against any
    underlying brightness. Returns a copy."""
    overlay = Image.new("RGBA", im.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)
    h = im.size[1]
    grad_start = int(h * 0.30)
    grad_end = h
    for y in range(grad_start, grad_end):
        # 0 at top of gradient, ~190 alpha at bottom — preserves some image visibility
        alpha = int(((y - grad_start) / max(1, grad_end - grad_start)) * 190)
        draw.line([(0, y), (im.size[0], y)], fill=(0, 0, 0, alpha))
    out = im.convert("RGBA")
    out.alpha_composite(overlay)
    return out.convert("RGB")


def generate_thumbnail(script: dict) -> Path:
    """Build outputs/thumbnails/<video_id>.png. Returns the path."""
    video_id = script["video_id"]
    src_path = _resolve_source_image(script, video_id)
    overlay_text = _derive_overlay_text(script)
    lines = _wrap_to_lines(overlay_text, MAX_CHARS_PER_LINE, MAX_LINES)
    logger.info(f"thumb source: {src_path.name}, text lines: {lines}")

    THUMBNAILS_DIR.mkdir(parents=True, exist_ok=True)
    out_path = THUMBNAILS_DIR / f"{video_id}.png"

    with Image.open(src_path) as raw:
        im = raw.convert("RGB").resize(
            (THUMBNAIL_WIDTH, THUMBNAIL_HEIGHT), Image.Resampling.LANCZOS
        )
    # Slight sharpen + saturation bump so the thumb pops in the grid
    im = im.filter(ImageFilter.UnsharpMask(radius=1.2, percent=120, threshold=2))
    im = ImageEnhance.Color(im).enhance(1.10)
    im = _apply_letterbox_gradient(im)

    font = ImageFont.truetype(CAPTION_FONT, FONT_SIZE)
    draw = ImageDraw.Draw(im)

    # Stack lines vertically, anchored to lower-third center
    line_heights = []
    for line in lines:
        bbox = draw.textbbox((0, 0), line, font=font, stroke_width=STROKE_WIDTH)
        line_heights.append(bbox[3] - bbox[1])
    total_h = sum(line_heights) + (len(lines) - 1) * 12  # 12px line gap
    block_top = int(THUMBNAIL_HEIGHT * 0.62) - total_h // 2

    y = block_top
    for line, lh in zip(lines, line_heights):
        bbox = draw.textbbox((0, 0), line, font=font, stroke_width=STROKE_WIDTH)
        w = bbox[2] - bbox[0]
        x = (THUMBNAIL_WIDTH - w) // 2 - bbox[0]
        draw.text(
            (x, y - bbox[1]),
            line,
            font=font,
            fill=(255, 255, 255),
            stroke_width=STROKE_WIDTH,
            stroke_fill=(0, 0, 0),
        )
        y += lh + 12

    im.save(out_path, format="PNG", optimize=True)
    logger.info(f"thumb saved: {out_path} ({out_path.stat().st_size:,} bytes)")
    return out_path
