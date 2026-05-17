"""Generate YouTube title/description/tags for The 3AM Tape episodes.

Each script JSON can override `title`, `description`, `tags` directly. If
absent, we generate them deterministically from the script's `topic` and
narration. No API call needed.

Long-form additions:
  - metadata_for_long(script, section_durations): builds the same shape but
    inserts a CHAPTERS block computed from real section runtimes (not the
    1:00 / 2:00 placeholders the script-writer typed before knowing actual
    audio length). Triggers YouTube's chapter UI when timestamps are in
    place — see LONG_FORM.md §10 for the requirements (first must be 0:00,
    ≥3 chapters, each ≥10 sec).
"""
from __future__ import annotations

import re
from typing import TypedDict


class VideoMetadata(TypedDict):
    title: str
    description: str
    tags: list[str]


CHANNEL_PITCH = (
    "The 3AM Tape — recovered recordings, true scary stories, and accounts no one\n"
    "kept on file. New tape every week.\n"
)

# SEO-leaning tags. These are the searches that actually pull viewers for
# horror narration: people looking for stories to listen to before sleep,
# while driving, or as background. We want to show up in those searches.
DEFAULT_TAGS = [
    "scary stories", "true scary stories", "horror stories",
    "creepypasta", "scary stories to tell in the dark",
    "horror narration", "scary stories narrated", "true horror stories",
    "paranormal stories", "true creepy stories", "creepy stories",
    "scary stories told", "the 3am tape", "3am stories",
    "analog horror", "found footage stories",
]

DEFAULT_HASHTAGS = (
    "#ScaryStories #TrueScaryStories #HorrorStories #Creepypasta "
    "#HorrorNarration #ParanormalStories #The3AMTape"
)


def _default_title(topic: str, narrations: list[str]) -> str:
    """SEO title: lead with the searchable hook phrase, no emoji.

    The personal-confession topic seed already works well as a title for
    horror narration channels. Just append a category tag for SEO weight.
    """
    hook = topic.strip()
    while hook and hook[-1] in ".,;:":
        hook = hook[:-1]
    suffix = " | True Scary Story"
    if hook.lower().endswith("story"):
        suffix = ""
    title = hook + suffix
    if len(title) > 100:
        title = title[:97] + "..."
    return title


def _default_description(topic: str, narrations: list[str]) -> str:
    """Hook line, brief teaser, channel pitch, hashtags."""
    hook = narrations[0].strip() if narrations else ""
    teaser = " ".join(narrations[1:3]).strip() if len(narrations) > 2 else ""
    if len(teaser) > 350:
        teaser = teaser[:347] + "..."
    lines = [topic.strip(), "", hook, ""]
    if teaser:
        lines.extend([teaser, ""])
    lines.extend([
        "If this gave you that feeling — subscribe. New tape every week.",
        "",
        CHANNEL_PITCH,
        "",
        DEFAULT_HASHTAGS,
    ])
    return "\n".join(lines)


def _default_tags() -> list[str]:
    return DEFAULT_TAGS[:]


def metadata_for(script: dict) -> VideoMetadata:
    """Pull or generate title/description/tags from a parsed script JSON.

    Supports both Shorts ('scenes') and long-form ('sections') schemas — for
    narration-defaulting only. Long-form callers should use metadata_for_long
    to also get a runtime-accurate CHAPTERS block."""
    topic = script.get("topic", "")
    units = script.get("scenes") or script.get("sections") or []
    narrations = [s.get("narration", "") for s in units]
    title = script.get("title") or _default_title(topic, narrations)
    description = script.get("description") or _default_description(topic, narrations)
    tags = script.get("tags") or _default_tags()
    return {"title": title[:100], "description": description[:5000], "tags": tags[:30]}


# ---------------------------------------------------------------------------
# Long-form metadata
# ---------------------------------------------------------------------------

# Detect a chapter block in the script's hand-written description so we can
# replace it with runtime-accurate timestamps. Matches consecutive lines that
# start with a MM:SS or H:MM:SS prefix.
_CHAPTER_BLOCK_RE = re.compile(
    r"(?:^[ \t]*\d{1,2}:\d{2}(?::\d{2})?[ \t]+.+\n?)+",
    re.MULTILINE,
)


def _format_chapter_timestamp(seconds: float) -> str:
    """YouTube chapter timestamp: M:SS for under 1 hour, H:MM:SS otherwise.
    First chapter MUST be exactly '0:00' (not '00:00') to trigger the UI."""
    total = max(0, int(round(seconds)))
    h, rem = divmod(total, 3600)
    m, s = divmod(rem, 60)
    if h:
        return f"{h}:{m:02d}:{s:02d}"
    return f"{m}:{s:02d}"


def _build_chapter_block(sections: list[dict], section_durations: list[float]) -> str:
    """One line per section: `MM:SS Beat Chapter Title`. First is always 0:00."""
    if len(sections) != len(section_durations):
        raise ValueError(
            f"chapters: {len(sections)} sections vs {len(section_durations)} durations"
        )
    lines: list[str] = []
    cumulative = 0.0
    for i, sec in enumerate(sections):
        ts = _format_chapter_timestamp(0 if i == 0 else cumulative)
        title = sec.get("beat_chapter_title") or sec.get("beat") or f"Section {sec.get('id', i+1)}"
        lines.append(f"{ts} {title}")
        cumulative += section_durations[i]
    return "\n".join(lines)


def _splice_chapter_block(description: str, new_block: str) -> str:
    """Replace an existing chapter block in the description (if present), else
    insert before the first hashtag-or-end-of-text. Preserves blank lines
    around the block for readability."""
    match = _CHAPTER_BLOCK_RE.search(description)
    if match:
        return description[: match.start()] + new_block + "\n" + description[match.end():]
    # Find first hashtag line to insert before
    lines = description.split("\n")
    insert_idx = len(lines)
    for i, line in enumerate(lines):
        if line.strip().startswith("#"):
            insert_idx = i
            break
    spliced = lines[:insert_idx] + ["", new_block, ""] + lines[insert_idx:]
    return "\n".join(spliced)


def metadata_for_long(
    script: dict, section_durations: list[float]
) -> VideoMetadata:
    """Long-form metadata: same shape as metadata_for, but the description's
    CHAPTERS block is regenerated from actual per-section runtimes. The
    hand-written script can contain placeholder chapters (1:00, 2:00, …) or
    none — either way the pipeline replaces with accurate timestamps before
    upload, so the YouTube chapter UI lines up with the audio."""
    base = metadata_for(script)
    sections = script.get("sections") or []
    if not sections:
        return base
    chapter_block = _build_chapter_block(sections, section_durations)
    description = _splice_chapter_block(base["description"], chapter_block)
    return {
        "title": base["title"],
        "description": description[:5000],
        "tags": base["tags"],
    }
