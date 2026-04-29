"""One-time YouTube OAuth bootstrap.

Run once after creating an OAuth Client ID in Google Cloud Console:

    1. Go to https://console.cloud.google.com → create/select project "money-crew"
    2. APIs & Services → Library → search "YouTube Data API v3" → Enable
    3. APIs & Services → OAuth consent screen → External, just yourself as test user
    4. APIs & Services → Credentials → Create OAuth Client ID → "Desktop app"
    5. Download the credentials JSON. Place it at credentials.json in this folder.
    6. Run:  ./venv/bin/python auth.py
    7. A browser opens; sign in with the Google account that owns your YouTube channel.
    8. Approve the requested scope (youtube.upload).
    9. Script prints YOUTUBE_CLIENT_ID, YOUTUBE_CLIENT_SECRET, YOUTUBE_REFRESH_TOKEN —
       paste those into .env. Then delete credentials.json.

The refresh token never expires (until you revoke), so this is a one-time setup.
"""
from __future__ import annotations

import json
from pathlib import Path

from google_auth_oauthlib.flow import InstalledAppFlow

SCOPES = [
    "https://www.googleapis.com/auth/youtube.upload",
    "https://www.googleapis.com/auth/youtube.readonly",   # needed for stats fetching
    "https://www.googleapis.com/auth/youtube.force-ssl",  # needed to update videos (flip privacy, edit metadata)
]
CLIENT_SECRETS_FILE = Path(__file__).parent / "credentials.json"


def main() -> None:
    if not CLIENT_SECRETS_FILE.exists():
        raise SystemExit(
            f"Missing {CLIENT_SECRETS_FILE}. Download the OAuth Client ID JSON from "
            "Google Cloud Console (APIs & Services → Credentials), rename it to "
            "credentials.json, and put it next to this script."
        )

    flow = InstalledAppFlow.from_client_secrets_file(str(CLIENT_SECRETS_FILE), SCOPES)
    creds = flow.run_local_server(port=0, open_browser=True)

    secrets = json.loads(CLIENT_SECRETS_FILE.read_text())
    section = secrets.get("installed") or secrets.get("web") or {}
    client_id = section.get("client_id", "")
    client_secret = section.get("client_secret", "")

    print("\n=== Paste these into your .env (then delete credentials.json) ===")
    print(f"YOUTUBE_CLIENT_ID={client_id}")
    print(f"YOUTUBE_CLIENT_SECRET={client_secret}")
    print(f"YOUTUBE_REFRESH_TOKEN={creds.refresh_token}")


if __name__ == "__main__":
    main()
