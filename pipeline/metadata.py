"""Generate YouTube title/description/tags for The 3AM Tape episodes.

Each script JSON can override `title`, `description`, `tags` directly. If
absent, we generate them deterministically from the script's `topic` and
narration. No API call needed.
"""
from __future__ import annotations

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
    """Pull or generate title/description/tags from a parsed script JSON."""
    topic = script.get("topic", "")
    narrations = [s.get("narration", "") for s in script.get("scenes", [])]
    title = script.get("title") or _default_title(topic, narrations)
    description = script.get("description") or _default_description(topic, narrations)
    tags = script.get("tags") or _default_tags()
    return {"title": title[:100], "description": description[:5000], "tags": tags[:30]}
