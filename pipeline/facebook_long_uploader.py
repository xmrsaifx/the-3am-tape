"""Upload a long-form (8-12 min) video to a Facebook Page via Graph API /videos.

Distinct from pipeline/facebook_uploader.py which targets `/video_reels` for
sub-90-second Reels. Long-form needs the resumable chunked upload path because
typical 10-min 1080p videos run 250-400 MB — too big for a single multipart POST.

Graph API resumable upload (3 phases):
  1. POST /{page_id}/videos  upload_phase=start  file_size=<bytes>
       → upload_session_id, video_id, start_offset, end_offset
  2. POST /{page_id}/videos  upload_phase=transfer  upload_session_id=<>
       start_offset=<>  source=<chunk>
       → next start_offset, end_offset. Loop until start_offset == end_offset.
  3. POST /{page_id}/videos  upload_phase=finish  upload_session_id=<>
       title=<>  description=<>  published=true
       → success boolean, the video_id matches phase 1

SRT captions are uploaded separately via POST /{video_id}/captions because the
finish-phase params don't accept binary attachments cleanly across all FB API
versions. The captions endpoint requires the file to be named with the locale
suffix (e.g. `tape.en_US.srt`) — we shim with a tmp copy.

Required permissions:
  pages_manage_posts, pages_read_engagement, pages_show_list

Env vars (same as Reels uploader):
  FB_PAGE_ID, FB_PAGE_ACCESS_TOKEN

Usage:
    from pipeline import facebook_long_uploader
    url = facebook_long_uploader.upload(
        video_path=Path("outputs/final/longtape-grandmother-house-001.mp4"),
        title="...",
        description="...",
        srt_path=Path("outputs/captions/longtape-grandmother-house-001.srt"),
    )
"""
from __future__ import annotations

import shutil
import tempfile
from pathlib import Path
from typing import Optional

import requests

from config.settings import FB_PAGE_ACCESS_TOKEN, FB_PAGE_ID
from pipeline.logger import get_logger

logger = get_logger("facebook_long_uploader")

GRAPH_API_VERSION = "v19.0"
GRAPH_BASE = f"https://graph.facebook.com/{GRAPH_API_VERSION}"

# FB recommends 4 MB chunks for resumable upload. Each transfer call returns
# the next start_offset, so chunk size is just our request granularity.
CHUNK_SIZE_BYTES = 4 * 1024 * 1024

# Description cap. FB's hard cap is much higher but "see more" cuts in the
# feed around 8000 chars; keep room for full long-form descriptions.
DESCRIPTION_MAX = 8000


def _check_config() -> None:
    missing = [
        name for name, val in (
            ("FB_PAGE_ID", FB_PAGE_ID),
            ("FB_PAGE_ACCESS_TOKEN", FB_PAGE_ACCESS_TOKEN),
        )
        if not val
    ]
    if missing:
        raise RuntimeError(
            f"missing in .env: {', '.join(missing)} — "
            "set FB_PAGE_ID and FB_PAGE_ACCESS_TOKEN to enable Facebook long-form upload."
        )


def _start_upload(file_size: int) -> dict:
    """Phase 1. Returns {upload_session_id, video_id, start_offset, end_offset}."""
    resp = requests.post(
        f"{GRAPH_BASE}/{FB_PAGE_ID}/videos",
        data={
            "upload_phase": "start",
            "file_size": str(file_size),
            "access_token": FB_PAGE_ACCESS_TOKEN,
        },
        timeout=60,
    )
    resp.raise_for_status()
    return resp.json()


def _transfer_chunk(session_id: str, start_offset: int, chunk_bytes: bytes) -> dict:
    """Phase 2 single call. Returns next {start_offset, end_offset}."""
    resp = requests.post(
        f"{GRAPH_BASE}/{FB_PAGE_ID}/videos",
        data={
            "upload_phase": "transfer",
            "upload_session_id": session_id,
            "start_offset": str(start_offset),
            "access_token": FB_PAGE_ACCESS_TOKEN,
        },
        files={"video_file_chunk": ("chunk", chunk_bytes, "application/octet-stream")},
        timeout=300,
    )
    resp.raise_for_status()
    return resp.json()


def _finish_upload(
    session_id: str, title: str, description: str, published: bool
) -> dict:
    """Phase 3. Returns {success: bool}."""
    resp = requests.post(
        f"{GRAPH_BASE}/{FB_PAGE_ID}/videos",
        data={
            "upload_phase": "finish",
            "upload_session_id": session_id,
            "title": title[:255],
            "description": description[:DESCRIPTION_MAX],
            "published": "true" if published else "false",
            "access_token": FB_PAGE_ACCESS_TOKEN,
        },
        timeout=120,
    )
    resp.raise_for_status()
    result = resp.json()
    if not result.get("success"):
        raise RuntimeError(f"FB finish failed: {result}")
    return result


def _upload_captions(video_id: str, srt_path: Path, locale: str = "en_US") -> None:
    """POST /{video_id}/captions with a locale-named SRT copy."""
    if not srt_path.exists():
        logger.warning(f"srt missing, skipping caption upload: {srt_path}")
        return
    # FB requires the captions filename to encode the locale: foo.en_US.srt
    with tempfile.TemporaryDirectory() as tmp:
        named = Path(tmp) / f"{srt_path.stem}.{locale}.srt"
        shutil.copy2(srt_path, named)
        with named.open("rb") as fh:
            resp = requests.post(
                f"{GRAPH_BASE}/{video_id}/captions",
                data={
                    "default_locale": locale,
                    "access_token": FB_PAGE_ACCESS_TOKEN,
                },
                files={"captions_file": (named.name, fh, "application/octet-stream")},
                timeout=120,
            )
    if resp.status_code >= 400:
        # Non-fatal: log the FB error body so caller can decide.
        logger.error(f"caption upload http {resp.status_code}: {resp.text[:500]}")
        resp.raise_for_status()
    logger.info(f"fb captions OK: {srt_path.name} ({locale})")


def upload(
    video_path: Path,
    title: str,
    description: str,
    srt_path: Optional[Path] = None,
    published: bool = True,
) -> str:
    """Upload a long-form video and (optionally) attach an SRT caption track.

    Returns the public Facebook permalink for the video. Caller pattern is
    try/except so a FB failure doesn't block YouTube success — see
    daily_pipeline.py / make_video.py.
    """
    _check_config()
    if not video_path.exists():
        raise FileNotFoundError(video_path)
    if video_path.stat().st_size < 5 * 1024 * 1024:
        raise RuntimeError(
            f"Refusing to upload {video_path.name} "
            f"({video_path.stat().st_size} bytes < 5 MB) — likely something broke upstream."
        )

    file_size = video_path.stat().st_size
    logger.info(f"fb long upload start: {video_path.name} ({file_size:,} bytes)")

    start = _start_upload(file_size)
    session_id = start["upload_session_id"]
    video_id = start["video_id"]
    start_offset = int(start["start_offset"])
    end_offset = int(start["end_offset"])
    logger.info(f"  fb session: id={session_id} video_id={video_id}")

    with video_path.open("rb") as fh:
        while start_offset < end_offset:
            length = min(CHUNK_SIZE_BYTES, end_offset - start_offset)
            fh.seek(start_offset)
            chunk = fh.read(length)
            result = _transfer_chunk(session_id, start_offset, chunk)
            new_start = int(result["start_offset"])
            new_end = int(result["end_offset"])
            pct = (new_start / file_size) * 100 if file_size else 100
            logger.info(
                f"  transfer: {start_offset:,} -> {new_start:,} of {end_offset:,} "
                f"({pct:.1f}%)"
            )
            start_offset, end_offset = new_start, new_end

    _finish_upload(session_id, title, description, published)
    logger.info(f"  fb finish OK: video_id={video_id}")

    if srt_path is not None:
        try:
            _upload_captions(video_id, srt_path)
        except Exception as e:
            # Captions are an additive — don't fail the whole upload.
            logger.error(f"fb caption upload failed (non-fatal): {e}")

    url = f"https://www.facebook.com/{FB_PAGE_ID}/videos/{video_id}"
    logger.info(f"fb long upload OK: {url}")
    return url
