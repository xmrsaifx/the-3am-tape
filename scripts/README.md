# Writing Shorts scripts by hand for The 3AM Tape

This folder is the **video queue**. Every JSON file is a 60–90 second horror Short waiting to be rendered. The daily workflow ([`.github/workflows/daily.yml`](../.github/workflows/daily.yml)) picks the oldest script (FIFO by filename), renders + uploads it **public immediately**, then moves it to [`scripts/archive/`](archive/).

Channel runs in **4/day sprint mode** (cron fires at 02:00, 09:00, 16:00, 22:00 UTC) targeting Shorts monetization. Queue depth matters — at 4/day a 28-script queue gives you ~7 days of runway.

Drop a new script here whenever you want to queue one. With `ANTHROPIC_API_KEY` set as a GitHub Secret, the workflow auto-backfills via Claude when queue depth < 5. Without it, the queue only ever has what you put in.

## Quick start (copy-paste template)

Save as `scripts/tape-<short-slug>-001.json` (filename must be unique across queue + archive):

```json
{
  "video_id": "tape-attic-photo-001",
  "character": "narrator",
  "topic": "I found a Polaroid in my grandmother's attic with my own face in it",
  "title": "I Found a Polaroid in My Grandmother's Attic with My Own Face in It | True Scary Story",
  "scenes": [
    {
      "id": 1,
      "narration": "I found a Polaroid in my grandmother's attic. The photo was forty years old. It was a picture of me.",
      "image_prompt": "close shot of a single yellowed Polaroid photograph held in a hand against a dim attic background, the image showing an adult face in faded color, dust visible on the photo's white border, dim ambient attic light from a small window, vertical 9:16 framing"
    },
    {
      "id": 2,
      "narration": "I was thirty two. The photo was dated nineteen eighty four.",
      "image_prompt": "..."
    }
  ]
}
```

That's it. Drop the file in `scripts/`, commit, push (with confirmation). Next cron run picks it up.

## Format target: YouTube Shorts (vertical 9:16)

| Constraint | Value |
|---|---|
| **Total runtime** | 60–90 seconds (sweet spot). Hard cap is 180 seconds (YouTube raised in Oct 2024). |
| **Scenes** | **12 (typical)** — can range 10–15 |
| **Per-scene narration** | ~10–15 words (~5–8 seconds at narrator's slow rate) |
| **Total narration words** | **95–150** |
| **Aspect ratio** | 9:16 vertical (1080×1920) |
| **Voice** | en-US-ChristopherNeural at **-25% rate, -10Hz pitch** (deep horror narration tuning) |
| **Words-per-second** | ~1.57 wps at the V3 voice tuning. So 100 words ≈ 64 sec. |

> **Why 60-90 sec is the sweet spot:** analog horror narration needs space to build dread. Pure 60-sec Shorts cut the atmosphere short. Channels in this niche (Be. Busta, ThatChapter) routinely run 90-120 sec because the genre demands it. Stay ≤180 sec to keep the Shorts classification.

## Schema reference

### Required top-level fields

| Field | Type | Notes |
|---|---|---|
| `video_id` | string | Slug. Format: `tape-<topic-slug>-NNN`. Used as the filename for outputs and the YouTube key. Must be unique across queue + archive. |
| `character` | string | Always `"narrator"`. |
| `topic` | string | The topic seed (matches `config/topics.py`). Recorded in `outputs/used_topics.json` for 30-day cooldown. |
| `scenes` | array | 10–15 scenes (12 is the sweet spot). |

### Optional top-level fields

| Field | Default if omitted |
|---|---|
| `title` | Auto-generated from `topic` + ` \| True Scary Story` suffix |
| `description` | Auto-generated |
| `tags` | Auto-generated horror SEO tag set |

### Per-scene fields

| Field | Notes |
|---|---|
| `id` | 1-indexed sequential |
| `narration` | First-person past-tense. ~10-15 words. |
| `image_prompt` | A still photograph composition. End with `vertical 9:16 framing`. |

## Narration rules

- **First-person past tense throughout.** "I worked", "I noticed". Never address the viewer directly.
- **No quote marks anywhere.** Pipeline strips them. Render dialogue as reported speech.
- **Spell out numbers.** TTS at slow rate mangles digits. "two thousand and four" not "2004"; "three AM" not "3 AM".
- **Allowed punctuation:** letters, digits, spaces, periods, commas, `!`, `?`. Anything else is stripped from captions.
- **~10-15 words per scene** at narrator's `-25%` rate ≈ 5-8 seconds. Mix impact beats (3-6 words) with standard scenes (10-15 words) for cinematic rhythm.
- **Last scene has the punch** — unresolved beat or twist that reframes earlier scenes.

## Scene 1 hook is everything (the most important rule)

YouTube Shorts retention is determined in **the first 1.5 seconds**. Setup-style intros ("I worked at a gas station for two years...") get scrolled past. **Front-load the impossible thing immediately**.

### Hook archetypes that work

| Archetype | Pattern | Example |
|---|---|---|
| **Impossible-thing-now** | "There is X that should not exist." | *"There is a door in my basement. Last week it was a wall."* |
| **Paradox / contradiction** | "X does not exist. But Y." | *"Exit one forty seven does not exist. My GPS tells me to take it every morning."* |
| **Dead-and-alive** | "X is dead. But X is also doing Y." | *"My grandfather has been dead fifteen years. His camcorder has footage dated after he died."* |
| **Eerie statistic** | "N happened over T. Implications:" | *"Eleven families lived in our house in forty years. None of them stayed past two."* |
| **Specific-knowledge violation** | "X knew Y. They could not have known Y." | *"My new neighbor knew my dead father's anniversary. I had never told anyone on this street."* |
| **Promise + tension** | "There are addresses I will never X. One of them is..." | *"There are addresses I will never deliver to twice. Fourteen Voss Lane is one of them."* |

**Bad scene 1** (setup): *"I worked the graveyard shift at a Shell station off Highway 49 for two years."*  
**Good scene 1** (hook): *"There was an elevator in Mercy General that should not exist. I found it."*

The setup happens in scenes 2–3, AFTER the listener is hooked.

## The 12-scene arc

| Scene | Beat | Words | Notes |
|---|---|---|---|
| 1 | **Hook** | 10–15 | Impossible thing front-loaded. See archetypes above. |
| 2 | **Setup place** | 7–10 | Where, when, alone? |
| 3 | **Setup routine** | 4–6 (impact) | What "normal" looked like. |
| 4 | **First wrong note** | 8–12 | Inciting moment. Specific. |
| 5 | **Reaction beat** | 3–5 (impact) | Speaker's first response. |
| 6 | **What you saw / didn't see** | 6–9 | Confirm the wrongness. |
| 7 | **Investigative action** | 3–5 (impact) | Speaker tries to verify. |
| 8 | **Confirmation of wrongness** | 4–6 (impact) | The pattern is real. |
| 9 | **Escalation** | 8–11 | New action, deeper trouble. |
| 10 | **Peak** | 10–13 | The stomach-flip moment. No monster shown. |
| 11 | **Aftermath sentence 1** | 7–9 | What happened after. |
| 12 | **Aftermath sentence 2 / lingering image** | 7–9 | The line that won't leave them. |

Mix of standard scenes (10–13 words) and impact beats (3–6 words) creates rhythm. Don't make every scene the same length.

## Image-prompt rules

The pipeline already adds the analog-horror style suffix automatically (VHS grain, scan lines, 35mm film, vignette, dim lighting, fog). You focus on **composition and subject**:

- **Always describe a still photograph.** Locations, objects, hands, silhouettes from behind, distant figures.
- **Never close-up faces** — AI image gen fails on faces in horror style. Backs of heads, silhouettes, hands, objects, locations only.
- **Use specific real-world objects.** Rotary phone. Laminate countertop. Wood-paneled basement. Cassette tape. Yellow gas-station lighting. The specificity is what makes AI horror NOT look generic.
- **Atmospheric cues every prompt:** "low light", "fog", "deep shadows", "fluorescent buzz", "twilight".
- **End with `vertical 9:16 framing`** so Pollinations frames the subject correctly for Shorts.
- **Avoid:** monster face, glowing eyes, blood, gore, screaming. Implied dread > explicit horror.

### Examples of good image prompts

- `"interior of a 1990s gas station at three in the morning, fluorescent ceiling lights buzzing, empty aisles of snacks, the back of a man in a uniform shirt facing the front window, parking lot dark and empty, foggy outside, low angle composition, vertical 9:16 framing"`
- `"a single VHS tape labeled DO NOT PLAY on a dusty wooden floor, an old attic with one bare bulb hanging, cardboard boxes stacked in shadow, late afternoon light through a small window, vertical 9:16 framing"`
- `"a long suburban street at twilight, two-story houses dark except for one porch light at the far end, viewed from the perspective of someone standing on the sidewalk, no people visible, slight fog, vertical 9:16 framing"`
- `"a rotary phone receiver lifted off its hook lying on a kitchen counter, laminate floral wallpaper visible behind, the phone cord dangling off the edge, single overhead pendant lamp, late night dim lighting, vertical 9:16 framing"`

## Captions you don't have to write

Captions are auto-generated from the narration via edge-tts word-level timing. The pipeline renders:
1. The full phrase in white (**Anton-Regular @ 72pt**) for ~4 words at a time
2. **Per-word yellow karaoke highlight** (with black box) on top, lit only during the spoken word

This is the engagement-optimized "viral Shorts caption" format. You don't write captions — you write narration, and the pipeline does the rest.

## Testing a script before queuing

```bash
./venv/bin/python make_video.py scripts/my_tape.json
# Watch outputs/final/<video_id>.mp4 — should be 60–90 sec
```

If you want to upload as a private preview before the next cron picks it up:

```bash
./venv/bin/python make_video.py scripts/my_tape.json --upload --privacy=private
```

## Common mistakes to avoid

- **Setup-style scene 1.** Always front-load the impossible thing. See hook archetypes above.
- **Word count over 150.** Pushes into the 100+ sec range; viewers drop off before the payoff.
- **Word count under 80.** Story doesn't have time to build dread; feels rushed.
- **Numbers as digits.** Use words: "three AM" not "3 AM".
- **Quote marks in narration.** Use reported speech: `He told me the room was empty` not `He said, "The room was empty."`
- **Close-up faces in image prompts.** AI image gen will produce uncanny results. Backs / silhouettes / objects only.
- **Generic "horror" image prompts.** "Scary hallway" produces generic AI horror. Specific objects ("brass doorknob, fingerprints visible, dim hallway light") produce atmospheric specificity that masks AI artifacts.
