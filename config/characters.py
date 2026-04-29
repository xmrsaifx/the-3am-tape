"""The 3AM Tape narrator definition.

Single host, no rotation. Slow male voice, intimate-creepy tone — the
unnamed narrator framing every "tape" recovered from somewhere.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Narrator:
    name: str            # Display name in metadata; channel doesn't actually name them
    slug: str            # Used in script JSON's `character` field for compatibility with pipeline
    voice: str           # edge-tts voice id
    rate: str            # edge-tts rate (negative = slower)
    style_note: str      # Tone description used by script_generator
    voice_traits: str


THE_NARRATOR = Narrator(
    name="The Narrator",
    slug="narrator",
    # en-US-ChristopherNeural is a calm intimate male voice that works well at slower
    # rates without sounding sleepy. Alternatives we evaluated:
    #   en-GB-RyanNeural    — slightly warmer, more BBC-documentary feel
    #   en-US-TonyNeural    — deeper, but a bit too "advertising" sounding
    #   en-US-AndrewNeural  — too youthful for horror
    voice="en-US-ChristopherNeural",
    rate="-15%",  # slow but not sluggish; -20% starts to sound robotic
    style_note=(
        "Slow, deliberate, conversational. Like someone telling you a story they "
        "still don't fully believe themselves. Pauses on the unsettling parts."
    ),
    voice_traits="adult male, calm, intimate, dread-inflected",
)

ROSTER: tuple[Narrator, ...] = (THE_NARRATOR,)
BY_SLUG: dict[str, Narrator] = {n.slug: n for n in ROSTER}
