"""Upload a finished video to YouTube via the Data API v3.

Auth model: a one-time OAuth dance (run `auth.py`) yields a refresh token
that we store in `.env`. Every upload uses that refresh token to mint a
short-lived access token — no browser interaction needed at runtime.

Usage:
    from pipeline import uploader
    url = uploader.upload(
        video_path=Path("outputs/final/rico-mike-vs-tom-comic-001.mp4"),
        title="Be a Tom, Not a Mike! ☕ Money Crew",
        description="...",
        tags=["money", "finance", "kids"],
    )
"""
from __future__ import annotations

from pathlib import Path
from typing import Optional

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from googleapiclient.http import MediaFileUpload

from config.settings import (
    YOUTUBE_CLIENT_ID,
    YOUTUBE_CLIENT_SECRET,
    YOUTUBE_REFRESH_TOKEN,
)
from pipeline.logger import get_logger

logger = get_logger("uploader")

# Must mirror auth.py's SCOPES exactly. If we list a narrower set here, the
# refresh-token exchange asks Google for a downscoped access token and reads
# (stats) + privacy updates fail with 403 even though the grant covers them.
YT_SCOPES = [
    "https://www.googleapis.com/auth/youtube.upload",
    "https://www.googleapis.com/auth/youtube.readonly",
    "https://www.googleapis.com/auth/youtube.force-ssl",
]
YT_TOKEN_URI = "https://oauth2.googleapis.com/token"
YT_CATEGORY_EDUCATION = "27"


def _credentials() -> Credentials:
    """Build a Credentials object from env-stored refresh token."""
    missing = [
        name for name, val in (
            ("YOUTUBE_CLIENT_ID", YOUTUBE_CLIENT_ID),
            ("YOUTUBE_CLIENT_SECRET", YOUTUBE_CLIENT_SECRET),
            ("YOUTUBE_REFRESH_TOKEN", YOUTUBE_REFRESH_TOKEN),
        )
        if not val
    ]
    if missing:
        raise RuntimeError(
            f"missing in .env: {', '.join(missing)} — run auth.py to get the refresh token"
        )
    creds = Credentials(
        token=None,
        refresh_token=YOUTUBE_REFRESH_TOKEN,
        client_id=YOUTUBE_CLIENT_ID,
        client_secret=YOUTUBE_CLIENT_SECRET,
        token_uri=YT_TOKEN_URI,
        scopes=YT_SCOPES,
    )
    creds.refresh(Request())
    return creds


def upload(
    video_path: Path,
    title: str,
    description: str,
    tags: list[str],
    category_id: str = YT_CATEGORY_EDUCATION,
    privacy_status: str = "public",
    made_for_kids: bool = False,
    publish_at: Optional[str] = None,
) -> str:
    """Upload `video_path` to the authenticated channel; return the video URL.

    privacy_status: 'public' | 'unlisted' | 'private'
    made_for_kids: True disables comments + personalized ads (COPPA).
    publish_at: RFC-3339 timestamp (e.g. "2026-04-29T12:00:00+05:00"). If set,
                video is uploaded as 'private' and auto-flips public at that
                time. Forces privacy_status='private' regardless of input.
    """
    if not video_path.exists():
        raise FileNotFoundError(video_path)
    if video_path.stat().st_size < 5 * 1024 * 1024:
        # Fail-loud guard from CLAUDE.md: never upload if the file is suspiciously small.
        raise RuntimeError(
            f"Refusing to upload {video_path.name} ({video_path.stat().st_size} bytes < 5 MB) "
            "— likely something went wrong upstream."
        )

    creds = _credentials()
    youtube = build("youtube", "v3", credentials=creds, cache_discovery=False)

    status: dict = {
        "selfDeclaredMadeForKids": made_for_kids,
    }
    if publish_at:
        # YouTube requires privacyStatus=private when publishAt is set.
        status["privacyStatus"] = "private"
        status["publishAt"] = publish_at
    else:
        status["privacyStatus"] = privacy_status

    body = {
        "snippet": {
            "title": title[:100],  # YouTube hard cap
            "description": description[:5000],
            "tags": tags[:30],
            "categoryId": category_id,
            "defaultLanguage": "en",
            "defaultAudioLanguage": "en",
        },
        "status": status,
    }

    media = MediaFileUpload(
        str(video_path), chunksize=8 * 1024 * 1024, resumable=True, mimetype="video/mp4"
    )
    logger.info(f"upload start: {video_path.name} ({video_path.stat().st_size:,} bytes)")
    request = youtube.videos().insert(
        part="snippet,status", body=body, media_body=media
    )
    response: Optional[dict] = None
    while response is None:
        try:
            status, response = request.next_chunk()
            if status:
                logger.info(f"  uploading {int(status.progress() * 100)}%")
        except HttpError as e:
            logger.error(f"upload http error: {e}")
            raise

    video_id = response["id"]
    url = f"https://www.youtube.com/watch?v={video_id}"
    when = f" (publishes at {publish_at})" if publish_at else f" ({privacy_status})"
    logger.info(f"upload OK: {url}{when}")
    return url


def update_privacy(youtube_video_id: str, privacy_status: str) -> None:
    """Flip an existing video's privacy (e.g. unlisted -> public). No re-upload."""
    creds = _credentials()
    youtube = build("youtube", "v3", credentials=creds, cache_discovery=False)
    youtube.videos().update(
        part="status",
        body={"id": youtube_video_id, "status": {"privacyStatus": privacy_status}},
    ).execute()
    logger.info(f"privacy update: {youtube_video_id} -> {privacy_status}")


def upload_caption(
    youtube_video_id: str,
    srt_path: Path,
    language: str = "en",
    name: str = "English",
) -> str:
    """Attach an SRT caption track to an existing video via captions.insert.

    Long-form videos rely on this for accessibility (YouTube boosts videos
    with a real CC track in recommendations). Returns the caption resource id.
    Requires the `youtube.force-ssl` scope which is already in YT_SCOPES.
    """
    if not srt_path.exists():
        raise FileNotFoundError(srt_path)
    creds = _credentials()
    youtube = build("youtube", "v3", credentials=creds, cache_discovery=False)

    body = {
        "snippet": {
            "videoId": youtube_video_id,
            "language": language,
            "name": name,
            "isDraft": False,
        }
    }
    media = MediaFileUpload(
        str(srt_path), mimetype="application/octet-stream", resumable=False
    )
    logger.info(f"caption upload start: {srt_path.name} -> video {youtube_video_id}")
    response = youtube.captions().insert(
        part="snippet", body=body, media_body=media
    ).execute()
    caption_id = response["id"]
    logger.info(f"caption upload OK: id={caption_id}")
    return caption_id


def set_thumbnail(youtube_video_id: str, thumbnail_path: Path) -> None:
    """Set a custom thumbnail on an existing video via thumbnails.set.

    YouTube requires the channel to be verified to use custom thumbnails.
    File must be ≤ 2 MB; we generate at PNG ~150-400 KB so we're well under.
    """
    if not thumbnail_path.exists():
        raise FileNotFoundError(thumbnail_path)
    creds = _credentials()
    youtube = build("youtube", "v3", credentials=creds, cache_discovery=False)
    media = MediaFileUpload(str(thumbnail_path), mimetype="image/png", resumable=False)
    logger.info(f"thumb upload start: {thumbnail_path.name} -> video {youtube_video_id}")
    youtube.thumbnails().set(videoId=youtube_video_id, media_body=media).execute()
    logger.info(f"thumb upload OK")
