"""Upload a finished video to a Facebook Page as a Reel via Graph API.

Auth model: a long-lived Page Access Token stored in .env / GitHub Secrets.
Standard user tokens expire in 60 days; generate a System User token in
Meta Business Suite → System Users to get a non-expiring token.

Graph API 3-step Reels upload:
  1. POST /{page_id}/video_reels  upload_phase=start  → video_id + upload_url
  2. POST {upload_url}  (raw binary, Authorization: OAuth header)  → {"success": true}
  3. POST /{page_id}/video_reels  upload_phase=finish  → {"success": true}

Required app permissions: pages_manage_posts, pages_read_engagement,
pages_show_list, public_profile.

Usage:
    from pipeline import facebook_uploader
    url = facebook_uploader.upload(
        video_path=Path("outputs/final/tape-xyz.mp4"),
        title="We Found a Baby Monitor We Didn't Install | True Scary Story",
        description="...",
    )
"""
from __future__ import annotations

from pathlib import Path

import requests

from config.settings import FB_PAGE_ACCESS_TOKEN, FB_PAGE_ID
from pipeline.logger import get_logger

logger = get_logger("facebook_uploader")

GRAPH_API_VERSION = "v19.0"
GRAPH_BASE = f"https://graph.facebook.com/{GRAPH_API_VERSION}"

# Facebook Reels: max 90-second description shown in the feed.
# Truncate at 2200 chars — FB's practical cap before "see more" cuts.
DESCRIPTION_MAX = 2200


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
            "set FB_PAGE_ID and FB_PAGE_ACCESS_TOKEN to enable Facebook Reels upload."
        )


def _start_upload() -> tuple[str, str]:
    """Phase 1: initialize the Reels upload session.

    Returns (video_id, upload_url).
    """
    resp = requests.post(
        f"{GRAPH_BASE}/{FB_PAGE_ID}/video_reels",
        data={"upload_phase": "start", "access_token": FB_PAGE_ACCESS_TOKEN},
        timeout=30,
    )
    resp.raise_for_status()
    data = resp.json()
    return data["video_id"], data["upload_url"]


def _transfer_video(upload_url: str, video_path: Path) -> None:
    """Phase 2: stream the video binary to the upload URL."""
    file_size = video_path.stat().st_size
    with video_path.open("rb") as fh:
        resp = requests.post(
            upload_url,
            headers={
                "Authorization": f"OAuth {FB_PAGE_ACCESS_TOKEN}",
                "offset": "0",
                "file_size": str(file_size),
            },
            data=fh,
            timeout=300,
        )
    resp.raise_for_status()
    result = resp.json()
    if not result.get("success"):
        raise RuntimeError(f"FB video transfer failed: {result}")


def _finish_upload(video_id: str, title: str, description: str) -> None:
    """Phase 3: publish the Reel."""
    resp = requests.post(
        f"{GRAPH_BASE}/{FB_PAGE_ID}/video_reels",
        data={
            "upload_phase": "finish",
            "video_id": video_id,
            "video_state": "PUBLISHED",
            "title": title[:255],
            "description": description[:DESCRIPTION_MAX],
            "access_token": FB_PAGE_ACCESS_TOKEN,
        },
        timeout=60,
    )
    resp.raise_for_status()
    result = resp.json()
    if not result.get("success"):
        raise RuntimeError(f"FB publish failed: {result}")


def upload(video_path: Path, title: str, description: str) -> str:
    """Upload `video_path` as a Facebook Reel; return the page Reels URL.

    Non-fatal caller pattern: wrap in try/except so a FB failure doesn't
    block YouTube archival in daily_pipeline.py.
    """
    _check_config()
    if not video_path.exists():
        raise FileNotFoundError(video_path)

    file_size = video_path.stat().st_size
    logger.info(f"fb upload start: {video_path.name} ({file_size:,} bytes)")

    video_id, upload_url = _start_upload()
    logger.info(f"  fb session: video_id={video_id}")

    _transfer_video(upload_url, video_path)
    logger.info(f"  fb transfer: complete")

    _finish_upload(video_id, title, description)

    url = f"https://www.facebook.com/reel/{video_id}/"
    logger.info(f"fb upload OK: {url}")
    return url
