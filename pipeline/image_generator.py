"""Generate scene images via Pollinations.ai (free, key-less Flux backend).

Default output is 1080x1920 vertical (Shorts). For long-form 16:9 horizontal,
pass width=1920, height=1080 to generate_for_video().

Pollinations is a free public proxy in front of Flux Schnell. Same quality
profile as paid Replicate Flux Schnell, just queued and rate-limited.

RATE-LIMIT RESILIENCE (2026-04-30):
GitHub Actions runners share IP pools that get aggressively throttled at
peak US daytime hours, when our 02:00/16:00/22:00 UTC cron windows fire.
The pipeline now compensates with:
  - 7-second polite pacing between successful scene gens (don't be part of
    the problem)
  - 8 retry attempts with 30-180s backoff plus jitter
  - Alternate model fallback: tries `turbo` (a less-queued Pollinations
    model) on attempts 4-6, falls back to `flux` for 7-8
  - Browser-style User-Agent (python-requests/X.X gets flagged as a bot)
  - Random seed nudge on retry — same prompt URL might be cached on the
    server's 429 list, mutating the seed forces a fresh queue slot
"""
from __future__ import annotations

import os
import random
import time
import urllib.parse
from pathlib import Path
from typing import Iterable

import requests
from PIL import Image, ImageFilter

from config.settings import IMAGES_DIR, LONG_VIDEO_HEIGHT, LONG_VIDEO_WIDTH, VIDEO_HEIGHT, VIDEO_WIDTH
from pipeline.logger import get_logger

logger = get_logger("image_generator")

POLLINATIONS_BASE = "https://gen.pollinations.ai/image"

# Pacing: how long to wait between successful scene gens. 7s is enough to
# avoid burst-rate-limiting on Pollinations without making total render time
# unreasonable (12 scenes × 7s = 84s of pacing overhead).
POLITE_DELAY_BETWEEN_SCENES = 7

# Retry: more attempts than before, longer max wait.
MAX_ATTEMPTS_PER_SCENE = 8
# Backoff schedule per failed attempt (seconds). Total worst case across all
# 8 attempts ≈ 16 minutes for a single stuck scene. Plus jitter.
BACKOFF_SECONDS = [30, 60, 90, 120, 180, 180, 180, 180]
BACKOFF_JITTER_SECONDS = 15

# Pollinations supports several models. Flux is the default but most-queued.
# Turbo is faster + less-loaded, used as a fallback on attempts 4-6.
MODEL_PRIMARY = "flux"
MODEL_FALLBACK = "turbo"
ATTEMPTS_USING_FALLBACK_MODEL = (4, 5, 6)

# Realistic browser User-Agent. python-requests' default UA gets flagged by
# Pollinations' anti-abuse layer first when the queue is hot.
BROWSER_USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_5) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
)


def _http_headers() -> dict[str, str]:
    """Build request headers. POLLINATIONS_KEY (set via repo secret on CI, .env
    on local) is required as of mid-2026 — the anonymous tier started returning
    402 Payment Required on shared GitHub Actions IP pools. Register at
    enter.pollinations.ai to obtain a sk_... key; the free Seed tier covers our
    daily volume."""
    headers = {"User-Agent": BROWSER_USER_AGENT, "Accept": "image/png,image/*,*/*"}
    key = os.environ.get("POLLINATIONS_KEY", "").strip()
    if key:
        headers["Authorization"] = f"Bearer {key}"
    return headers
# The 3AM Tape aesthetic: analog-horror / found-footage / cinematic photoreal.
# Grain + low-light + dread atmosphere. The film-grain look is doing real
# work — it sets the analog-horror tone AND masks AI artifacts (wonky hands,
# generic faces) that would jump out in clean illustration. Per-scene
# image_prompt still provides composition (vertical 9:16 vs horizontal 16:9).
STYLE_SUFFIX = (
    ", cinematic horror photograph, found-footage analog horror aesthetic, "
    "VHS noise grain texture, soft scan lines, muted desaturated color grading, "
    "deep shadows, dim ambient lighting, fog and haze, atmospheric dread, "
    "vintage 35mm film, slight chromatic aberration, vignette, "
    "still life composition, no monsters visible, unsettling without being explicit"
)
NEGATIVE_HINT = (
    " (avoid: cartoon, anime, illustration, 3D render, bright cheerful, "
    "neon, vibrant saturated, glowing red eyes, dripping blood, generic ghost, "
    "monster face, demon, gore, deformed faces, wonky hands, extra fingers, "
    "watermark, text overlay, AI artifacts, modern smartphone, jumpscare)"
)


def _build_url(prompt: str, seed: int, width: int, height: int, model: str = MODEL_PRIMARY) -> str:
    full_prompt = prompt + STYLE_SUFFIX + NEGATIVE_HINT
    encoded = urllib.parse.quote(full_prompt, safe="")
    params = {
        "width": str(width),
        "height": str(height),
        "seed": str(seed),
        "model": model,
        "nologo": "true",
        "enhance": "true",
        "private": "true",
    }
    qs = "&".join(f"{k}={v}" for k, v in params.items())
    return f"{POLLINATIONS_BASE}/{encoded}?{qs}"


def _upscale_to_target(path: Path, width: int, height: int) -> None:
    """Pollinations silently downscales to its free-tier cap (~576px on the
    short side) even when we ask for full HD. Upscale in place with Pillow
    LANCZOS + UnsharpMask so the cached PNG matches target resolution and
    stays sharp."""
    with Image.open(path) as im:
        im = im.convert("RGB")
        if im.size == (width, height):
            return
        im = im.resize((width, height), Image.Resampling.LANCZOS)
        # Compensate for upscale softness — moderate sharpen, not aggressive
        im = im.filter(ImageFilter.UnsharpMask(radius=1.4, percent=110, threshold=3))
        im.save(path, format="PNG", optimize=True)


def generate_scene_image(
    prompt: str, seed: int, dest: Path, width: int, height: int,
    model: str = MODEL_PRIMARY,
) -> Path:
    """Hit Pollinations, save the PNG, then upscale to target resolution."""
    url = _build_url(prompt, seed, width, height, model=model)
    logger.info(f"pollinations: model={model} seed={seed} prompt={prompt[:80]}...")
    dest.parent.mkdir(parents=True, exist_ok=True)
    with requests.get(url, stream=True, timeout=180, headers=_http_headers()) as r:
        r.raise_for_status()
        with dest.open("wb") as f:
            for chunk in r.iter_content(chunk_size=8192):
                f.write(chunk)
    _upscale_to_target(dest, width, height)
    return dest


def _generate_one_with_retry(
    prompt: str, dest: Path, base_seed: int, width: int, height: int, label: str,
) -> None:
    """Render one image to `dest` with the standard Pollinations retry/backoff
    schedule. `label` is used purely for logging ("scene 3" or "section 02 image 04")."""
    attempts = 0
    while True:
        attempts += 1
        model = (
            MODEL_FALLBACK if attempts in ATTEMPTS_USING_FALLBACK_MODEL
            else MODEL_PRIMARY
        )
        seed_for_attempt = base_seed + (attempts - 1) * 1000
        try:
            generate_scene_image(
                prompt, seed=seed_for_attempt, dest=dest,
                width=width, height=height, model=model,
            )
            if dest.stat().st_size < 5_000:
                raise RuntimeError(f"image too small: {dest.stat().st_size} bytes")
            logger.info(f"{label}: saved ({dest.stat().st_size:,} bytes)")
            return
        except Exception as e:
            logger.warning(
                f"{label} attempt {attempts}/{MAX_ATTEMPTS_PER_SCENE} failed: {e}"
            )
            dest.unlink(missing_ok=True)
            if attempts >= MAX_ATTEMPTS_PER_SCENE:
                raise
            base = BACKOFF_SECONDS[min(attempts - 1, len(BACKOFF_SECONDS) - 1)]
            jitter = random.uniform(-BACKOFF_JITTER_SECONDS, BACKOFF_JITTER_SECONDS)
            wait = max(5, base + jitter)
            logger.info(f"  backoff: sleep {wait:.0f}s before retry")
            time.sleep(wait)


def generate_for_video(
    video_id: str,
    scenes: Iterable[dict],
    seed: int = 42,
    width: int | None = None,
    height: int | None = None,
) -> list[Path]:
    """Shorts: one image per scene; return ordered list of saved paths."""
    target_w = width or VIDEO_WIDTH
    target_h = height or VIDEO_HEIGHT
    out_dir = IMAGES_DIR / video_id
    out_dir.mkdir(parents=True, exist_ok=True)
    paths: list[Path] = []
    api_call_count = 0
    for scene in scenes:
        idx = scene["id"]
        dest = out_dir / f"scene_{idx:02d}.png"

        if dest.exists() and dest.stat().st_size > 0:
            logger.info(f"scene {idx}: cached at {dest}")
            paths.append(dest)
            continue

        if api_call_count > 0:
            logger.info(f"  pacing: sleep {POLITE_DELAY_BETWEEN_SCENES}s before scene {idx}")
            time.sleep(POLITE_DELAY_BETWEEN_SCENES)

        _generate_one_with_retry(
            scene["image_prompt"], dest, base_seed=seed + idx,
            width=target_w, height=target_h, label=f"scene {idx}",
        )
        paths.append(dest)
        api_call_count += 1
    return paths


def generate_for_long_video(
    video_id: str,
    sections: Iterable[dict],
    seed: int = 42,
    width: int | None = None,
    height: int | None = None,
    section_filter: int | None = None,
) -> dict[int, list[Path]]:
    """Long-form: N images per section, named section_NN_image_NN.png.

    Returns {section_id: [path1, path2, ...]} sorted by section_id. When
    `section_filter` is set, only that one section is rendered — used by matrix
    shards so one job handles one section's 4-8 images. When None, iterates
    all sections (cached entries are returned without re-rendering, which is
    how the assemble job recollects everything from downloaded artifacts).
    """
    target_w = width or LONG_VIDEO_WIDTH
    target_h = height or LONG_VIDEO_HEIGHT
    out_dir = IMAGES_DIR / video_id
    out_dir.mkdir(parents=True, exist_ok=True)
    result: dict[int, list[Path]] = {}
    api_call_count = 0
    for section in sections:
        sec_id = section["id"]
        if section_filter is not None and sec_id != section_filter:
            continue
        prompts = section.get("image_prompts") or []
        if not prompts:
            raise ValueError(f"section {sec_id} has no image_prompts")
        section_paths: list[Path] = []
        for img_idx, prompt in enumerate(prompts, start=1):
            dest = out_dir / f"section_{sec_id:02d}_image_{img_idx:02d}.png"
            if dest.exists() and dest.stat().st_size > 0:
                logger.info(f"section {sec_id} image {img_idx}: cached at {dest}")
                section_paths.append(dest)
                continue
            if api_call_count > 0:
                logger.info(
                    f"  pacing: sleep {POLITE_DELAY_BETWEEN_SCENES}s "
                    f"before section {sec_id} image {img_idx}"
                )
                time.sleep(POLITE_DELAY_BETWEEN_SCENES)
            # Unique base seed across (section, image) so reruns are deterministic
            # and different prompts don't collide on identical seeds.
            base_seed = seed + sec_id * 100 + img_idx
            _generate_one_with_retry(
                prompt, dest, base_seed=base_seed,
                width=target_w, height=target_h,
                label=f"section {sec_id} image {img_idx}",
            )
            section_paths.append(dest)
            api_call_count += 1
        result[sec_id] = section_paths
    return dict(sorted(result.items()))
