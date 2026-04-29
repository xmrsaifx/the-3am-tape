"""The 3AM Tape — horror story topic seeds with 30-day cooldown.

Topics are SEEDS, not full premises. Each one is a hook the script writer
(or you) can build a 5-7 minute story around. Mostly evergreen horror tropes
filtered for "could be told as a recovered tape recording."

Schema parity with money-crew/config/topics.py: TOPIC_BANK[<slug>] is a list,
even though we only have one slug ('narrator') here. Keeps daily_pipeline.py's
existing pick_topic / record_topic logic working without changes.
"""
from __future__ import annotations

import json
from datetime import date, timedelta
from pathlib import Path

from config.settings import OUTPUT_DIR

# Single host on this channel — keep schema parity with the existing pipeline.
TOPIC_BANK: dict[str, list[str]] = {
    "narrator": [
        # — Workplace / night-shift —
        "I worked the graveyard shift at a 24-hour gas station in the middle of nowhere",
        "I was a security guard at an empty hospital that was scheduled for demolition",
        "My night shift at the call center kept getting calls from a number that didn't exist",
        "I was the only employee on the night shift at a small motel off Route 6",
        "I worked at a remote weather station and something started leaving footprints in the snow",

        # — Houses / homes —
        "We moved into a house that was suspiciously cheap and now I know why",
        "There is a door in my basement that wasn't there last week",
        "My grandmother's house has a room that everyone in the family pretends doesn't exist",
        "I bought an old house at auction and the previous owner had nailed every window shut",
        "The new house came with a baby monitor in the attic that we did not install",

        # — Found media (analog-horror native) —
        "I bought a box of unmarked VHS tapes at an estate sale for two dollars",
        "I found my grandfather's old camcorder and the last recording is from after his death",
        "The Polaroid camera I inherited only takes pictures of one specific room",
        "I found a cassette tape labeled DO NOT PLAY in my late uncle's attic",
        "There is a recording on my answering machine from someone I have never met",

        # — Travel / road / forest —
        "I took a wrong turn on a back road and ended up in the same town twice",
        "My GPS keeps telling me to take an exit that does not exist",
        "I went hiking alone and found a campsite that had been waiting for me",
        "My truck broke down on a highway with no other cars for three hours, then one came",
        "I drove through a town that was not on any map I owned",

        # — Relationships / family unsettled —
        "My brother went missing for six hours when we were kids and came back wrong",
        "I have a twin I did not know about until last summer",
        "My new neighbor knows things about me he should not know",
        "The man my mother is dating is wearing my father's wedding ring",
        "I have a daughter who is not in any of the family photos but she is here",

        # — Childhood memories revisited —
        "There was an empty house at the end of my street that the adults all whispered about",
        "I remembered a babysitter we had when I was seven that no one else in my family remembers",
        "My imaginary friend from when I was four has started visiting my own daughter",

        # — Online / modern tech —
        "I bought a used phone online and someone is still receiving messages on it",
        "My smart doorbell keeps recording someone standing in our hallway",
        "There is a video on my drone's SD card that I never recorded",
        "My elderly neighbor's voice assistant kept asking her questions she did not understand",

        # — Industry / outdoor —
        "I deliver food at night and I have learned which addresses to never go to twice",
        "I was a nurse at a hospice and one room kept its last patient too long",
        "I drive long-haul trucks and there is a stretch of highway between Tulsa and Amarillo",
    ],
}

USED_TOPICS_FILE = OUTPUT_DIR / "used_topics.json"
COOLDOWN_DAYS = 30


def _load_history() -> list[dict]:
    if not USED_TOPICS_FILE.exists():
        return []
    return json.loads(USED_TOPICS_FILE.read_text())


def _save_history(history: list[dict]) -> None:
    USED_TOPICS_FILE.parent.mkdir(parents=True, exist_ok=True)
    USED_TOPICS_FILE.write_text(json.dumps(history, indent=2))


def pick_topic(character_slug: str, today: date | None = None) -> str:
    """Return the next un-cooled-down topic for the given narrator slug.

    Raises if every topic has been used within COOLDOWN_DAYS — caller should
    extend the topic bank when this happens.
    """
    today = today or date.today()
    cutoff = today - timedelta(days=COOLDOWN_DAYS)
    history = _load_history()
    recently_used = {
        entry["topic"]
        for entry in history
        if date.fromisoformat(entry["date"]) >= cutoff
        and entry["character"] == character_slug
    }
    for topic in TOPIC_BANK[character_slug]:
        if topic not in recently_used:
            return topic
    raise RuntimeError(
        f"All topics for {character_slug} used within {COOLDOWN_DAYS} days — extend topic bank"
    )


def record_topic(character_slug: str, topic: str, today: date | None = None) -> None:
    today = today or date.today()
    history = _load_history()
    history.append(
        {"date": today.isoformat(), "character": character_slug, "topic": topic}
    )
    _save_history(history)
