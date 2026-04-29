# Writing Shorts scripts by hand for The 3AM Tape

This folder is the **video queue**. Every JSON file is a 60-second horror Short waiting to be rendered. The daily workflow ([`.github/workflows/daily.yml`](../.github/workflows/daily.yml)) picks the oldest script (FIFO by filename), renders + uploads it, then moves it to [`scripts/archive/`](archive/).

Drop a new script here whenever you want to queue a tape. With `ANTHROPIC_API_KEY` set, the workflow auto-tops the queue back up to 5 after each run; without it, the queue only ever has what you put in.

## Quick start (copy-paste template)

Save as `scripts/tape-<short-slug>-001.json`:

```json
{
  "video_id": "tape-night-shift-bell-001",
  "character": "narrator",
  "topic": "I worked the graveyard shift at a 24-hour gas station in the middle of nowhere",
  "title": "I Worked the Night Shift at a Gas Station Off Highway 49 | True Scary Story",
  "scenes": [
    {
      "id": 1,
      "narration": "I worked the graveyard shift at a Shell station off Highway 49.",
      "image_prompt": "interior of an empty 1990s gas station at three in the morning, fluorescent ceiling lights, foggy parking lot beyond the windows, vertical 9:16 framing"
    },
    {
      "id": 2,
      "narration": "Most nights, nothing happened. Last Tuesday wasn't most nights.",
      "image_prompt": "..."
    }
  ]
}
```

That's it. Drop the file in `scripts/`, commit (don't push without confirmation), the next daily run will pick it up.

## Format target: 60-sec YouTube Shorts

| Constraint | Value |
|---|---|
| **Total runtime** | ≤ 60 seconds (Shorts hard cap) |
| **Scenes** | 8–10 |
| **Per-scene narration** | ~12–15 words (~6 seconds at narrator's `-15%` rate) |
| **Total narration words** | ~100–120 |
| **Aspect ratio** | 9:16 vertical (1080×1920) |

## Schema reference

### Required top-level fields

| Field | Type | Notes |
|---|---|---|
| `video_id` | string | Slug. Format: `tape-<topic-slug>-NNN`. Used as the filename for outputs and the YouTube key. Must be unique across queue + archive. |
| `character` | string | Always `"narrator"`. |
| `topic` | string | The topic seed (matches `config/topics.py`). Recorded in `outputs/used_topics.json` for 30-day cooldown. |
| `scenes` | array | 8–10 scenes. Each scene = ~12-15 words. |

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
| `narration` | First-person past-tense. ~12-15 words. |
| `image_prompt` | A still photograph composition. End with `vertical 9:16 framing`. |

## Narration rules

- **First-person past tense throughout.** "I worked", "I noticed". Never address the viewer directly.
- **No quote marks anywhere.** Pipeline strips them. Render dialogue as reported speech.
- **Spell out numbers.** TTS at slow rate mangles digits. "two thousand and four" not "2004".
- **Allowed punctuation:** letters, digits, spaces, periods, commas, `!`, `?`. Anything else is stripped from captions.
- **~12-15 words per scene** at narrator's `-15%` rate ≈ 6 seconds.
- **Scene 1 is the hook.** Drop the listener directly into unease. No "let me tell you" preambles.
- **Last scene has the punch.** Either an unresolved beat that lingers, or a twist that reframes everything.

## The Shorts arc (8-10 scenes, ~60 sec)

| Scene | Beat | Example (~12 words) |
|---|---|---|
| 1 | **Hook** | "I worked the graveyard shift at a Shell station off Highway 49." |
| 2 | **Setup place** | "I was alone from ten at night until six in the morning." |
| 3 | **Setup routine** | "Most nights, nothing happened. Last Tuesday at three AM was different." |
| 4 | **First wrong note** | "The bell on the front door rang. Nobody had come in." |
| 5 | **Escalation** | "I rewound the camera. The bell rang on the recording too. The door was closed." |
| 6 | **Escalation** | "I went outside. The parking lot was empty. The wind had stopped." |
| 7 | **Peak** | "I came back inside. I locked the door. Then I heard footsteps in the back aisle." |
| 8 | **Aftermath** | "I do not remember leaving. The Shell station closed three weeks later." |
| 9 | **Lingering ending** | "The building still stands. The lights are still on." |

## Image-prompt rules

The pipeline already adds the analog-horror style suffix automatically (VHS grain, scan lines, 35mm film, vignette, dim lighting, fog). You focus on **composition and subject**:

- **Always describe a still photograph.** Locations, objects, hands, silhouettes from behind, distant figures.
- **Never close-up faces** — AI image gen fails on faces in horror style.
- **Use specific real-world objects.** Rotary phone. Laminate countertop. Wood-paneled basement. Cassette tape. Yellow gas-station lighting.
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
1. The full phrase in white (Anton-Regular @ 90pt) for ~4 words at a time
2. **Per-word yellow karaoke highlight** (with black box) on top, lit only during the spoken word

This is the engagement-optimized "viral Shorts caption" format. You don't write captions — you write narration, and the pipeline does the rest.

## Testing a script before queuing

```bash
./venv/bin/python make_video.py scripts/my_tape.json
# Watch outputs/final/<video_id>.mp4 — should be ~60 sec
```
