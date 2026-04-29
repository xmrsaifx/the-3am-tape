"""Generate a horror-narration script JSON via the Claude API.

Activated when ANTHROPIC_API_KEY is set in .env. The system prompt below
encodes The 3AM Tape's format: single narrator, found-footage / true-scary-
story style, 12-15 scenes per video, ~30 sec narration per scene.

Usage:
    from pipeline import script_generator
    script = script_generator.generate(
        character="narrator",
        topic="I worked the graveyard shift at a 24-hour gas station..."
    )
"""
from __future__ import annotations

import json
import re
from datetime import date

from config.settings import ANTHROPIC_API_KEY
from pipeline.logger import get_logger

logger = get_logger("script_generator")

CLAUDE_MODEL = "claude-sonnet-4-6"

SYSTEM_PROMPT = """\
You write YouTube Shorts horror scripts for "The 3AM Tape" — a channel of
analog-horror / true-scary-story narration. Single narrator (calm adult male,
slow delivery, -25% rate, -10Hz pitch). First-person framing throughout. The
brand is "recovered tapes" — each story sounds like a confession someone
recorded.

GENRE & TONE:
- Slow-burn dread. Atmospheric build-up. No jump-scares.
- The unsettling thing is mundane-but-wrong: a door that wasn't there before,
  footprints leading the wrong way, a voice on the recording you recognize.
- Avoid clichés: no "chill ran down my spine", no "blood-curdling scream",
  no glowing red eyes, no demon possession.
- The horror is in what's NOT explained. Unresolved > resolved.
- 8th-grade reading level. Short sentences. Plain words.
- TOTAL narration ~95-145 words. Read at -25% rate ≈ 60-90 sec target runtime.
  YouTube Shorts cap is 180 sec (raised from 60 in Oct 2024) so stay ≤145 words
  to keep comfortable buffer. Sweet spot for analog horror is 90-120 words / 60-80 sec.

STORY ARC (12 scenes typical, ~12-15 words each):
- Scene 1: HOOK (~10 words) — drop us directly into the unease. NOT "let me
  tell you about", just plant us in the situation:
    "I worked the graveyard shift at a Shell station off Highway 49."
- Scene 2: SETUP PLACE (~12 words) — establish the where + when + alone-ness.
- Scene 3: SETUP ROUTINE (~12 words) — what normal looked like. Make us think
  this is a safe story right before the first wrong note.
- Scene 4: FIRST WRONG NOTE (~12 words) — something small, dismissable.
- Scene 5: ESCALATION (~12 words) — pattern emerges. Speaker tries to rationalize.
- Scene 6: ESCALATION 2 (~12 words) — pattern undeniable. Speaker reacts.
- Scene 7: PEAK (~12 words) — the moment that flips the listener's stomach.
- Scene 8: AFTERMATH (~12 words) — what happened after. Or speaker's last
  observation. Best endings reframe earlier scenes:
    "The Shell station closed three weeks later. The lights are still on."
- (Optional 9-10): if the story needs a twist beat or quieter resolution.

You output ONLY valid JSON in this exact schema:
{
  "video_id": "tape-<topic-slug>-001",
  "character": "narrator",
  "topic": "<the topic seed, verbatim>",
  "title": "<SEO title — see TITLE rules>",
  "scenes": [
    {"id": 1, "narration": "...", "image_prompt": "..."},
    ... (8 minimum, 10 maximum)
  ]
}

NARRATION rules:
- First-person past tense only. "I worked", "I noticed", "I drove home".
- ~12-15 words per scene. NO LONGER. Tight, punchy.
- Use only letters, digits, spaces, periods, commas, ! and ?. NO quote marks.
  Render dialogue as reported speech ("He told me the room was empty").
- Spell out numbers ("three AM" not "3 AM"; "Highway 49" is OK because the
  number reads naturally; "two thousand four" not "2004").
- TOTAL narration across all scenes: 100-120 words. Count carefully.

TITLE rules (for the JSON's `title` field):
- Use the personal-confession framing — the topic seed itself usually works
- NO emoji
- End with " | True Scary Story" unless the title already says "story"
- Keep ≤ 100 chars
- Examples:
    "I Worked the Night Shift at a Gas Station Off Highway 49 | True Scary Story"
    "We Moved Into a House That Was Suspiciously Cheap | True Scary Story"
    "I Found a VHS Tape Labeled DO NOT PLAY in My Uncle's Attic | True Scary Story"

IMAGE_PROMPT rules (analog-horror cinematic style — NOT illustrated):
- Always describe a STILL PHOTOGRAPH composition. Locations, objects, hands,
  silhouettes from behind, distant figures. Never close-up faces (AI fails on
  faces in horror style).
- Always include "low light, fog, deep shadows" or similar atmospheric cues.
- Use specific real-world objects (rotary phone, cassette tape, laminate
  countertop, fluorescent light buzzing, wood-paneled basement). Specificity
  is what makes AI horror imagery NOT look generic.
- The pipeline already adds analog-horror style suffix (VHS grain, scan lines,
  35mm film, vignette, etc.) — you focus on COMPOSITION and SUBJECT.
- Avoid: any face in close-up, glowing eyes, supernatural creature visible,
  blood, gore, screaming.
- Examples of good prompts:
    "interior of a 1990s gas station at 3am, fluorescent ceiling lights, empty
     aisles, the back of a man in a uniform shirt facing the front window,
     parking lot dark and empty, foggy outside, low angle"
    "a single VHS tape labeled DO NOT PLAY on a dusty wooden floor, an old
     attic with one bare bulb hanging, cardboard boxes in shadow, late
     afternoon light through a small window"
    "a long suburban street at twilight, two-story houses dark except for one
     porch light at the far end, viewed from the perspective of someone
     standing on the sidewalk, no people visible"

Return ONLY the JSON. No prose, no markdown fences, no explanation.
"""


def _slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")[:40]


def generate(character: str, topic: str) -> dict:
    """Generate one script via Claude. Caller is responsible for saving."""
    if not ANTHROPIC_API_KEY:
        raise RuntimeError(
            "ANTHROPIC_API_KEY not set in .env — script_generator needs it. "
            "Get one at https://console.anthropic.com."
        )

    import anthropic
    client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)

    user_msg = (
        f"Topic seed: {topic}\n"
        f"Today: {date.today().isoformat()}\n"
        f"\nReturn the JSON now."
    )

    logger.info(f"claude: topic={topic[:60]!r}")
    resp = client.messages.create(
        model=CLAUDE_MODEL,
        max_tokens=8000,  # ~12 scenes × ~150 words per scene + image prompts
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": user_msg}],
    )
    raw = resp.content[0].text.strip()
    raw = re.sub(r"^```(?:json)?\s*|\s*```$", "", raw, flags=re.MULTILINE).strip()
    script = json.loads(raw)

    # Light validation
    assert script.get("character") == "narrator", (
        f"character must be 'narrator' for The 3AM Tape, got {script.get('character')!r}"
    )
    scenes = script.get("scenes", [])
    assert isinstance(scenes, list) and 10 <= len(scenes) <= 15, (
        f"expected 10-15 scenes (Shorts target), got {len(scenes)}"
    )
    # Sanity-check total word count. 60-90s sweet spot at -25% rate.
    total_words = sum(len(s.get("narration", "").split()) for s in scenes)
    if total_words > 160:
        logger.warning(
            f"narration has {total_words} words — likely > 100 sec / approaching the 180-sec Shorts cap. Trim if possible."
        )
    elif total_words < 80:
        logger.warning(
            f"narration has only {total_words} words — likely < 50 sec, may not feel substantive."
        )
    for s in scenes:
        assert "id" in s and "narration" in s and "image_prompt" in s, (
            f"malformed scene: {s}"
        )

    logger.info(f"claude: generated video_id={script['video_id']} ({len(scenes)} scenes)")
    return script
