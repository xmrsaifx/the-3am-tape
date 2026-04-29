"""Pull YouTube stats for our channel and save daily snapshots.

Each call to `record_snapshot()` writes outputs/stats/<date>.json with:
  {
    "date": "2026-04-29",
    "snapshot_at": "2026-04-29T10:00:00+05:00",
    "videos": [
      {
        "video_id": "GEDwiscMl7g",
        "title": "...",
        "published_at": "...",
        "privacy_status": "public",
        "duration_sec": 49,
        "views": 142,
        "likes": 12,
        "comments": 3,
        "views_per_day": 142.0
      },
      ...
    ]
  }

Comparing two snapshots gives day-over-day deltas without any extra plumbing.
Needs the OAuth token to include `youtube.readonly` scope — re-run auth.py if
you originally only granted `youtube.upload`.
"""
from __future__ import annotations

import json
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Iterable

from googleapiclient.discovery import build

from config.settings import STATS_DIR
from pipeline.logger import get_logger
from pipeline.uploader import _credentials

logger = get_logger("stats")


def _youtube_client():
    return build("youtube", "v3", credentials=_credentials(), cache_discovery=False)


def _parse_iso8601_duration(s: str) -> int:
    """YouTube returns durations as ISO-8601, e.g. PT1M5S. Return total seconds."""
    m = re.fullmatch(r"PT(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?", s)
    if not m:
        return 0
    h, mn, sec = (int(g) if g else 0 for g in m.groups())
    return h * 3600 + mn * 60 + sec


def fetch_my_uploads_playlist_id(yt) -> str:
    """Each channel has a special 'uploads' playlist that lists every video."""
    resp = yt.channels().list(part="contentDetails", mine=True).execute()
    items = resp.get("items", [])
    if not items:
        raise RuntimeError("No channel found for the authenticated account.")
    return items[0]["contentDetails"]["relatedPlaylists"]["uploads"]


def fetch_recent_video_ids(yt, max_results: int = 50) -> list[str]:
    playlist_id = fetch_my_uploads_playlist_id(yt)
    ids: list[str] = []
    page_token: str | None = None
    while len(ids) < max_results:
        resp = yt.playlistItems().list(
            part="contentDetails",
            playlistId=playlist_id,
            maxResults=min(50, max_results - len(ids)),
            pageToken=page_token,
        ).execute()
        for item in resp.get("items", []):
            ids.append(item["contentDetails"]["videoId"])
        page_token = resp.get("nextPageToken")
        if not page_token:
            break
    return ids


def fetch_stats(yt, video_ids: Iterable[str]) -> list[dict]:
    """Pull snippet+statistics+contentDetails+status in one batched call (50/page)."""
    out: list[dict] = []
    ids = list(video_ids)
    for i in range(0, len(ids), 50):
        batch = ids[i : i + 50]
        resp = yt.videos().list(
            part="snippet,statistics,contentDetails,status",
            id=",".join(batch),
        ).execute()
        for v in resp.get("items", []):
            snip = v.get("snippet", {})
            stats = v.get("statistics", {})
            content = v.get("contentDetails", {})
            status = v.get("status", {})
            published_at = snip.get("publishedAt")
            duration_sec = _parse_iso8601_duration(content.get("duration", "PT0S"))
            views = int(stats.get("viewCount", 0))
            likes = int(stats.get("likeCount", 0))
            comments = int(stats.get("commentCount", 0))
            # Days since publish (>=1 to avoid div-by-zero on day 0)
            try:
                pub_dt = datetime.fromisoformat(published_at.replace("Z", "+00:00"))
                days = max(1.0, (datetime.now(timezone.utc) - pub_dt).total_seconds() / 86400)
            except Exception:
                days = 1.0
            out.append({
                "video_id": v["id"],
                "title": snip.get("title", ""),
                "published_at": published_at,
                "privacy_status": status.get("privacyStatus", ""),
                "duration_sec": duration_sec,
                "views": views,
                "likes": likes,
                "comments": comments,
                "views_per_day": round(views / days, 2),
            })
    return out


def record_snapshot() -> Path:
    """Pull current stats for all our channel videos and save today's snapshot."""
    yt = _youtube_client()
    ids = fetch_recent_video_ids(yt, max_results=200)
    logger.info(f"fetching stats for {len(ids)} videos")
    rows = fetch_stats(yt, ids)
    today = datetime.now().date().isoformat()
    STATS_DIR.mkdir(parents=True, exist_ok=True)
    path = STATS_DIR / f"{today}.json"
    payload = {
        "date": today,
        "snapshot_at": datetime.now(timezone.utc).isoformat(),
        "videos": sorted(rows, key=lambda r: r["views"], reverse=True),
    }
    path.write_text(json.dumps(payload, indent=2))
    logger.info(f"snapshot saved: {path}")
    return path


def previous_snapshot(today: Path) -> dict | None:
    """Return yesterday's (or last available) snapshot for diffing."""
    snaps = sorted(STATS_DIR.glob("*.json"))
    snaps = [p for p in snaps if p != today]
    if not snaps:
        return None
    return json.loads(snaps[-1].read_text())


def render_summary(today_path: Path) -> str:
    """Pretty-print today's stats with day-over-day deltas."""
    today = json.loads(today_path.read_text())
    prev = previous_snapshot(today_path)
    prev_views = {v["video_id"]: v for v in (prev["videos"] if prev else [])}

    lines = [
        f"Stats snapshot for {today['date']}",
        f"Compared to: {prev['date'] if prev else '<no prior snapshot>'}",
        "",
        f"{'TITLE':<60} {'V':>7} {'+24h':>6} {'/day':>7} {'L':>4} {'C':>3} {'STATUS':>10}",
        "-" * 100,
    ]
    for v in today["videos"]:
        title = v["title"][:60]
        prior = prev_views.get(v["video_id"], {})
        delta = v["views"] - prior.get("views", v["views"]) if prev else 0
        delta_str = f"+{delta}" if delta else "—"
        lines.append(
            f"{title:<60} {v['views']:>7} {delta_str:>6} {v['views_per_day']:>7.1f} "
            f"{v['likes']:>4} {v['comments']:>3} {v['privacy_status']:>10}"
        )
    return "\n".join(lines)


def _snapshot_n_days_ago(today_path: Path, days: int) -> dict | None:
    """Return the snapshot closest to `days` days before today_path, or None."""
    snaps = sorted(STATS_DIR.glob("*.json"))
    snaps = [p for p in snaps if p != today_path]
    if not snaps:
        return None
    today_date = datetime.fromisoformat(today_path.stem).date()
    target_date = today_date - timedelta(days=days)
    # Pick the snapshot whose date is closest to target_date (but not after today)
    best = None
    best_distance = 999
    for p in snaps:
        try:
            d = datetime.fromisoformat(p.stem).date()
        except ValueError:
            continue
        if d > today_date:
            continue
        distance = abs((d - target_date).days)
        if distance < best_distance:
            best_distance = distance
            best = p
    if best is None:
        return None
    return json.loads(best.read_text())


def _detect_character(title: str) -> str:
    """Best-effort: pull the mascot name from a video title we generated."""
    t = title.lower()
    for c in ("rico", "penny", "max", "nana"):
        if c in t:
            return c
    return "unknown"


def weekly_digest(today_path: Path | None = None, lookback_days: int = 7) -> str:
    """Build a markdown channel-performance digest comparing today vs ~7 days ago.

    Output is suitable for posting as a GitHub Issue body. Sections:
      - Headline: total channel views/likes this week, vs prior
      - Top performers (5)
      - Underperformers (3) — videos worth analyzing or pulling
      - By mascot — which character drove the most views this week
      - Full table — every video with weekly view delta
    """
    if today_path is None:
        snaps = sorted(STATS_DIR.glob("*.json"))
        if not snaps:
            return "_No stats snapshots yet — digest will populate after the first daily run._"
        today_path = snaps[-1]
    today = json.loads(today_path.read_text())
    prior = _snapshot_n_days_ago(today_path, lookback_days)
    today_videos = today["videos"]
    prior_views = {v["video_id"]: v["views"] for v in (prior["videos"] if prior else [])}
    prior_likes = {v["video_id"]: v["likes"] for v in (prior["videos"] if prior else [])}

    # Per-video deltas
    rows = []
    for v in today_videos:
        prev_v = prior_views.get(v["video_id"], v["views"] if not prior else 0)
        prev_l = prior_likes.get(v["video_id"], v["likes"] if not prior else 0)
        rows.append({
            "video_id": v["video_id"],
            "title": v["title"],
            "character": _detect_character(v["title"]),
            "views": v["views"],
            "delta_views": v["views"] - prev_v,
            "likes": v["likes"],
            "delta_likes": v["likes"] - prev_l,
            "comments": v["comments"],
            "views_per_day": v["views_per_day"],
            "duration_sec": v["duration_sec"],
            "published_at": v["published_at"],
        })

    total_views_now = sum(r["views"] for r in rows)
    total_views_prior = sum(prior_views.values()) if prior else 0
    weekly_view_gain = total_views_now - total_views_prior
    total_likes_now = sum(r["likes"] for r in rows)
    total_comments = sum(r["comments"] for r in rows)

    # Top + bottom performers, ranked by view gain over the week
    sorted_by_gain = sorted(rows, key=lambda r: r["delta_views"], reverse=True)
    top = sorted_by_gain[:5]
    public_rows = [r for r in rows if r["delta_views"] is not None]
    bottom_pool = [r for r in public_rows if r["delta_views"] < 50][:3]

    # Per-mascot aggregates (this week's view gain)
    mascot_gain: dict[str, int] = {}
    mascot_count: dict[str, int] = {}
    for r in rows:
        mascot_gain[r["character"]] = mascot_gain.get(r["character"], 0) + r["delta_views"]
        mascot_count[r["character"]] = mascot_count.get(r["character"], 0) + 1
    mascot_ranking = sorted(mascot_gain.items(), key=lambda kv: kv[1], reverse=True)

    prior_label = prior["date"] if prior else f"<no snapshot ~{lookback_days}d ago>"
    lines: list[str] = []
    lines.append(f"# Channel digest — {today['date']}")
    lines.append("")
    lines.append(f"_Comparing **{today['date']}** vs **{prior_label}** ({lookback_days}-day lookback)._")
    lines.append("")
    lines.append("## Headline")
    lines.append("")
    lines.append(f"- **Total views:** {total_views_now:,} (+{weekly_view_gain:,} this week)")
    lines.append(f"- **Total likes:** {total_likes_now:,}")
    lines.append(f"- **Total comments:** {total_comments:,}")
    lines.append(f"- **Videos on channel:** {len(rows)}")
    lines.append("")

    lines.append("## Top performers (this week's view gain)")
    lines.append("")
    if not top or all(r["delta_views"] == 0 for r in top):
        lines.append("_No view gains this week — too early or stats not yet propagated._")
    else:
        lines.append("| Title | Mascot | +Views (7d) | Likes | Views/day |")
        lines.append("|---|---|---:|---:|---:|")
        for r in top:
            lines.append(
                f"| {r['title'][:60]} | {r['character']} | +{r['delta_views']:,} | "
                f"{r['likes']:,} | {r['views_per_day']:.1f} |"
            )
    lines.append("")

    lines.append("## Underperformers (worth reviewing the hook + thumbnail)")
    lines.append("")
    if not bottom_pool:
        lines.append("_No clear underperformers — every video gained ≥50 views this week._")
    else:
        lines.append("| Title | Mascot | +Views (7d) | Total views | Published |")
        lines.append("|---|---|---:|---:|---|")
        for r in bottom_pool:
            pub = (r["published_at"] or "")[:10]
            lines.append(
                f"| {r['title'][:60]} | {r['character']} | +{r['delta_views']:,} | "
                f"{r['views']:,} | {pub} |"
            )
    lines.append("")

    lines.append("## By mascot (this week's view gain)")
    lines.append("")
    lines.append("| Mascot | Videos | +Views (7d) |")
    lines.append("|---|---:|---:|")
    for char, gain in mascot_ranking:
        lines.append(f"| {char} | {mascot_count.get(char, 0)} | +{gain:,} |")
    lines.append("")

    lines.append("## Full table")
    lines.append("")
    lines.append("| Title | Mascot | Views | +7d | Likes | Comments |")
    lines.append("|---|---|---:|---:|---:|---:|")
    for r in sorted(rows, key=lambda r: r["views"], reverse=True):
        lines.append(
            f"| {r['title'][:60]} | {r['character']} | {r['views']:,} | "
            f"+{r['delta_views']:,} | {r['likes']:,} | {r['comments']:,} |"
        )
    lines.append("")
    lines.append("---")
    lines.append("_Auto-generated by `.github/workflows/weekly.yml`._")
    return "\n".join(lines)
