"""Generate a LONG-FORM horror narration script JSON via the Claude API.

Fallback safety net for long_daily.yml: when the cron fires and scripts/long/
is empty AND ANTHROPIC_API_KEY is set, this module is invoked to fill the
queue with one auto-generated long-form script so the workflow can proceed.

Hand-written scripts always win FIFO. The auto-generator is only the
"the user didn't queue anything for today" fallback.

Format spec mirrors LONG_FORM.md §5 (sections schema). Calibrated to the
measured edge-tts rate (~2.2 wps at -25% on en-US-ChristopherNeural), so
the word budget targets the 8:00 mid-roll-ads threshold:
  - 10 sections × ~110 words/section ≈ 1,100 words ≈ 8:20 runtime

Reuses the same TOPIC_BANK and 30-day cooldown that Shorts uses, so a topic
running as a Short on Monday cannot also run as long-form on Wednesday
(cannibalizes both).

Usage:
    from pipeline import long_script_generator
    script = long_script_generator.generate(
        character="narrator",
        topic="I bought a house at auction and the basement door was nailed shut from inside",
    )
"""
from __future__ import annotations

import json
import re
from datetime import date

from config.settings import ANTHROPIC_API_KEY
from pipeline.logger import get_logger

logger = get_logger("long_script_generator")

CLAUDE_MODEL = "claude-sonnet-4-6"

SYSTEM_PROMPT = """\
You write LONG-FORM (8-10 minute) YouTube horror narration scripts for "The
3AM Tape" — an analog-horror / true-scary-story channel. Single narrator
(calm adult male, slow delivery, edge-tts en-US-ChristopherNeural at -25%
rate, -10Hz pitch). First-person past tense throughout. The brand is
"recovered tapes" — each story sounds like a quiet confession someone is
recording into a cassette years after the fact.

CRITICAL FORMAT CONSTRAINTS:
- Aspect ratio: HORIZONTAL 16:9 (1920×1080). Every image_prompt must end with
  "horizontal 16:9 framing".
- Total runtime target: 8-10 minutes. Calibrated edge-tts rate at -25% is
  ~2.2 words per second. So total narration MUST be 1,050-1,300 words.
  10 sections × ~110 words is the sweet spot. Sections under 90 words feel
  thin; over 130 feel padded.
- 10 sections by default. Each section is one story BEAT (hook / setup /
  escalation / peak / aftermath), continuous prose, no scene-cuts within.

GENRE & TONE (same as Shorts brand — do NOT drift):
- Slow-burn dread. Atmospheric build-up. NO jump-scares. NO gore.
- The horror is mundane-but-wrong: a door that wasn't there, footprints
  leading the wrong direction, neighbors who call you the wrong name.
- The unsettling thing is what's NOT explained. Unresolved > resolved.
- AVOID CLICHÉS: no "chill ran down my spine", no "blood-curdling scream",
  no glowing red eyes, no demon possession, no jump-cut to a face.
- 8th-grade reading level. Short sentences. Plain words. Specific real-world
  objects (Polaroid, casserole dish, masking tape, fluorescent buzz).
- PG-13 by intention. Implied dread, never explicit.

VIRAL PREMISE TEMPLATE (from real channel stats — top 10 by views/day all
follow this; bottom 10 break it):
- Setting: an ordinary daily-life place 90% of viewers occupy — their house,
  car, phone gallery, family photos, doorbell, GPS, grocery store.
- Hook (section 1): name the impossible detail without naming the cause.
  GOOD: "Exit 147 doesn't exist but my GPS tells me to take it every morning."
  BAD: "My twin lives in our parents' attic." (gives the answer; no curiosity left)
- Physical, photographable anomaly: a tape, a door, a window, a photo, a car.
- AVOID: night-shift-at-X, remote weather stations, dead-parent reveals,
  abstract software anomalies. These flop.

STORY ARC (10 sections):
  1. Hook         — Front-load the impossible thing. Sensory detail. ~95-110 words.
  2. Setup place  — Where, when, why the narrator is there. Build the ordinary.
  3. Setup routine — What "normal" looked like for the first day/week.
  4. First wrong note — Small, specific, deniable.
  5. Reaction + dismissal — Narrator rationalizes it. (Lets the audience dismiss
     too, so the next beat hits harder.)
  6. Pattern recognition — Second incident. Not coincidence anymore.
  7. Investigation — Narrator tries to verify / disprove. Finds, looks up, asks.
  8. Escalation — The wrong thing intensifies or changes shape.
  9. Peak — Stomach-flip moment. STILL no monster shown — dread is implication.
 10. Aftermath / lingering image — What happened after. End on a line that
     won't leave them.

OUTPUT SCHEMA (return ONLY this JSON, no markdown fences, no prose):
{
  "video_id": "longtape-<topic-slug>-001",
  "format": "long",
  "character": "narrator",
  "topic": "<the topic seed, verbatim>",
  "title": "<60-70 char SEO title>",
  "thumbnail_text": "<3-5 word punchy hook for the 1280x720 thumbnail overlay, ALL CAPS>",
  "description_intro": "<the first paragraph of the YouTube description — the hook recap, ~50 words>",
  "description": "<full 3-paragraph description: (1) hook recap, (2) setting/atmosphere, (3) tease without spoiling. End with hashtag line. Do NOT include chapter timestamps — the pipeline injects those.>",
  "tags": [8-12 YouTube tags relevant to the topic],
  "category_id": "24",
  "sections": [
    {
      "id": 1,
      "beat": "hook",
      "beat_chapter_title": "<2-4 word title shown in YouTube chapter UI>",
      "narration": "<continuous prose, ~95-115 words, first-person past tense>",
      "word_count": <integer count of words in narration>,
      "image_prompts": [
        "<atmospheric prompt 1, ending in 'horizontal 16:9 framing'>",
        "<atmospheric prompt 2, ending in 'horizontal 16:9 framing'>",
        "<atmospheric prompt 3, ending in 'horizontal 16:9 framing'>",
        "<atmospheric prompt 4, ending in 'horizontal 16:9 framing'>",
        "<atmospheric prompt 5, ending in 'horizontal 16:9 framing'>"
      ]
    },
    ... (10 total sections, ids 1-10)
  ]
}

NARRATION rules:
- First-person past tense ONLY. "I worked", "I noticed", "I drove home".
- NO quote marks. Render dialogue as reported speech ("She told me she
  hadn't seen anyone").
- Spell out numbers in narration ("three AM" not "3 AM", "two thousand four"
  not "2004"). EXCEPTION: "Highway 49" / "Route 6" / numeric addresses where
  the number reads naturally.
- Each section: 90-130 words. Sweet spot 105-115.
- Total across all 10 sections: 1,050-1,300 words. COUNT CAREFULLY before
  emitting. Output the integer word_count field for each section.

TITLE rules:
- 60-70 chars. Lead with the searchable hook phrase.
- End with " | True Scary Story" (or " | Analog Horror" if the topic is
  found-media). Skip the suffix if title already ends with "Story".
- Examples:
    "I Inherited My Grandmother's House and the Neighbors Think I'm Her | True Scary Story"
    "Exit 147 Doesn't Exist But My GPS Tells Me to Take It Every Morning | True Scary Story"

THUMBNAIL_TEXT rules:
- 3-5 words, ALL CAPS. The punchy hook line for the 1280x720 thumbnail.
- Should make a viewer hover over the thumb. Examples:
    "THEY THINK I'M HER"
    "EXIT 147 DOESN'T EXIST"
    "MY HOUSE WASN'T MINE"

DESCRIPTION rules:
- 3 paragraphs (~50 words each):
    Para 1: Hook recap. Plant the reader in the situation, name the
      impossible detail.
    Para 2: Setting + atmosphere. Where, when, the ordinary frame.
    Para 3: Tease the payoff without spoiling. "Watch until the end" type lines.
- Final line: hashtag block (#scarystories #truescarystories #horrornarration
  #analoghorror #scarystoriestotellinthedark #truehorrorstories #creepypasta).
- DO NOT include chapter timestamps. The pipeline injects them from real
  per-section runtimes.

BEAT_CHAPTER_TITLE rules:
- 2-4 words. Shown in YouTube's chapter UI.
- Examples (from a known-good script):
    "The House" / "Moving In" / "The First Week" / "The Food on the Porch"
    / "Her Name" / "What the Neighbor Said" / "The Photograph"
    / "The Third Floor Window" / "The Last Night" / "What I Found in the Morning"

IMAGE_PROMPT rules (5 per section, analog-horror cinematic style — NOT illustrated):
- Each prompt describes a STILL PHOTOGRAPH composition. Locations, objects,
  hands, silhouettes from behind, distant figures. NEVER close-up faces (AI
  fails on faces in horror style — keep faces obscured, distant, back-turned).
- Vary the angle across the 5 images: wide → medium → object detail → empty
  interior → atmospheric exterior. This avoids same-frame fatigue when each
  image holds for 8-12 sec.
- Always include "low light" / "soft grey" / "overcast" or similar
  atmospheric cues. Specific real-world objects (rotary phone, casserole
  dish, glass mason jar, screen door, porch railing).
- Pipeline adds STYLE_SUFFIX (VHS grain, scan lines, 35mm film, vignette).
  You focus on COMPOSITION + SUBJECT.
- AVOID: any face in close-up, glowing eyes, supernatural creature visible,
  blood, gore, screaming, modern smartphones, neon, vibrant saturated colors.
- Every prompt MUST end with "horizontal 16:9 framing".
- Example of a good prompt:
    "wide exterior shot of a two-storey wooden house at the end of a quiet
     residential street in early spring, bare trees, overcast sky, single
     porch light on, horizontal 16:9 framing"

TAGS:
- 8-12 strings, comma-separated values. Mix of generic ("scary stories",
  "true scary stories", "horror narration", "analog horror") and topic-
  specific ("inherited house horror", "found footage cassette").

Return ONLY the JSON object. No markdown fences. No prose. No explanation.
"""


def _slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")[:40]


def generate(character: str, topic: str) -> dict:
    """Generate one long-form script via Claude. Caller is responsible for
    saving to scripts/long/<video_id>.json. Validates schema + word budget
    before returning so a malformed completion doesn't get queued silently."""
    if not ANTHROPIC_API_KEY:
        raise RuntimeError(
            "ANTHROPIC_API_KEY not set — long_script_generator needs it. "
            "Get one at https://console.anthropic.com."
        )

    import anthropic
    client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)

    user_msg = (
        f"Topic seed: {topic}\n"
        f"Today: {date.today().isoformat()}\n"
        f"\nWrite the long-form script as JSON only. 10 sections, "
        f"1,050-1,300 words total. Return the JSON now."
    )

    logger.info(f"claude long: topic={topic[:80]!r}")
    resp = client.messages.create(
        model=CLAUDE_MODEL,
        max_tokens=16000,
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": user_msg}],
    )
    raw = resp.content[0].text.strip()
    raw = re.sub(r"^```(?:json)?\s*|\s*```$", "", raw, flags=re.MULTILINE).strip()
    script = json.loads(raw)

    # Hard validation. A bad script is worse than no script — better to fail
    # the generation and let the workflow report it than to publish garbage.
    assert script.get("format") == "long", (
        f"format must be 'long', got {script.get('format')!r}"
    )
    assert script.get("character") == "narrator", (
        f"character must be 'narrator', got {script.get('character')!r}"
    )
    sections = script.get("sections", [])
    assert isinstance(sections, list) and len(sections) == 10, (
        f"expected exactly 10 sections, got {len(sections)}"
    )
    total_words = 0
    for s in sections:
        for key in ("id", "narration", "image_prompts", "beat_chapter_title"):
            assert key in s, f"section missing {key!r}: {s.get('id')}"
        assert isinstance(s["image_prompts"], list) and 4 <= len(s["image_prompts"]) <= 8, (
            f"section {s['id']}: expected 4-8 image_prompts, got {len(s['image_prompts'])}"
        )
        # Every prompt must end with the aspect-ratio anchor
        for ip in s["image_prompts"]:
            assert "16:9" in ip, (
                f"section {s['id']} image_prompt missing '16:9 framing': {ip[:80]}..."
            )
        total_words += len(s["narration"].split())

    # Word budget gate. Below 1,000 → won't hit 8:00 mid-roll ads.
    if total_words < 1000:
        logger.warning(
            f"narration has only {total_words} words — likely < 7:30 runtime, "
            "may not qualify for mid-roll ads. Regenerate or extend if it matters."
        )
    elif total_words > 1500:
        logger.warning(
            f"narration has {total_words} words — likely > 11:00 runtime. "
            "Long-form attention curve drops past 12 min; consider trimming."
        )

    # Ensure video_id naming convention
    if not script.get("video_id", "").startswith("longtape-"):
        script["video_id"] = f"longtape-{_slug(topic)}-001"

    logger.info(
        f"claude long: generated video_id={script['video_id']} "
        f"({len(sections)} sections, {total_words} words)"
    )
    return script
