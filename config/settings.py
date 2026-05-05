"""Central config for The 3AM Tape pipeline. All paths and constants live here."""
from __future__ import annotations

import os
from pathlib import Path
from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parent.parent
load_dotenv(PROJECT_ROOT / ".env")

ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")
REPLICATE_API_TOKEN = os.getenv("REPLICATE_API_TOKEN", "")

# YouTube Data API v3 — see uploader.py for the OAuth flow.
YOUTUBE_CLIENT_ID = os.getenv("YOUTUBE_CLIENT_ID", "")
YOUTUBE_CLIENT_SECRET = os.getenv("YOUTUBE_CLIENT_SECRET", "")
YOUTUBE_REFRESH_TOKEN = os.getenv("YOUTUBE_REFRESH_TOKEN", "")

# Instagram Graph API — for Reels upload via pipeline/instagram_uploader.py.
# IG account must be Business/Creator and linked to the Facebook page.
# Reuses FB_PAGE_ACCESS_TOKEN — no separate IG token needed.
IG_USER_ID = os.getenv("IG_USER_ID", "")


# Facebook Graph API — for Reels upload via pipeline/facebook_uploader.py.
# Generate a non-expiring System User token in Meta Business Suite to avoid
# the 60-day expiry on standard user tokens.
FB_PAGE_ID = os.getenv("FB_PAGE_ID", "")
FB_PAGE_ACCESS_TOKEN = os.getenv("FB_PAGE_ACCESS_TOKEN", "")

OUTPUT_DIR = Path(os.getenv("OUTPUT_DIR", PROJECT_ROOT / "outputs")).resolve()
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")

ASSETS_DIR = PROJECT_ROOT / "assets"
MUSIC_DIR = ASSETS_DIR / "music"
FONTS_DIR = ASSETS_DIR / "fonts"

SCRIPTS_DIR = OUTPUT_DIR / "scripts"
IMAGES_DIR = OUTPUT_DIR / "images"
VOICEOVERS_DIR = OUTPUT_DIR / "voiceovers"
FINAL_DIR = OUTPUT_DIR / "final"
STATS_DIR = OUTPUT_DIR / "stats"

LOGS_DIR = PROJECT_ROOT / "logs"

CLAUDE_MODEL = "claude-sonnet-4-6"

VIDEO_WIDTH = 1080
VIDEO_HEIGHT = 1920
VIDEO_FPS = 30
# Format: YouTube Shorts (vertical 9:16). YouTube raised the Shorts duration cap
# from 60s to 180s in October 2024. We target 60-90 seconds — long enough for
# proper analog-horror dread build-up, short enough to keep retention strong.
# 12 scenes × ~6-7 sec each is the sweet spot. ~12-15 words narration per scene.
SCENES_PER_VIDEO = 12
SCENE_DURATION_SECONDS = 7
SHORT_TARGET_DURATION_SECONDS = 90   # our target sweet spot
SHORT_MAX_DURATION_SECONDS = 180     # hard cap before YouTube classifies as regular video

# Need a full ffmpeg with libfreetype for drawtext/captions.
FFMPEG_BIN = os.getenv("FFMPEG_BIN", "/usr/local/opt/ffmpeg-full/bin/ffmpeg")
FFPROBE_BIN = os.getenv("FFPROBE_BIN", "/usr/local/opt/ffmpeg-full/bin/ffprobe")

# Caption font path. Default is the bundled Anton (Google Fonts, OFL license).
# Anton is bold-condensed sans — the standard "viral Shorts caption" font that
# reads big and crisp at 90pt. Overridable via env if you want to swap.
CAPTION_FONT = os.getenv(
    "CAPTION_FONT",
    str(FONTS_DIR / "Anton-Regular.ttf"),
)
