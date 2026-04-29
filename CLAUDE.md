# CLAUDE.md — The 3AM Tape (YouTube horror narration channel)

## Project Overview

Fully automated YouTube channel for analog-horror / true-scary-story narration. Forked from `money-crew` (kids finance Shorts) — same engine, completely different niche.

- **Channel niche:** Horror narration / analog-horror / true scary stories
- **Style:** Analog-horror aesthetic (VHS grain, scan lines, 35mm film, low light, fog)
- **Audience:** Horror Shorts viewers, late-night doom-scrollers
- **Format:** **YouTube Shorts (vertical 9:16)** — 12 scenes, ~12-15 words narration each, target runtime 60-90 sec. (YouTube raised the Shorts duration cap to 180s in October 2024 — for analog horror narration, 60-90 sec is the sweet spot since the genre needs atmospheric build-up time that pure 60-sec cuts can't deliver.)
- **Captions:** Anton bold-condensed @ 90pt, white phrase + per-word yellow karaoke highlight (the proven viral-Shorts caption format)
- **Posting schedule (SPRINT MODE):** **3 uploads/day**, public-immediate, via 3 cron triggers in `.github/workflows/daily.yml`:
  - 02:00 UTC → US prime time (~21:00 ET, "horror story before bed" peak)
  - 16:00 UTC → EU early evening (~17:00 CET) / PK late evening (~21:00 PKT)
  - 22:00 UTC → US after-work (~17:00 ET) / UK prime time (~22:00 GMT)
  - Goal: 3M Shorts views in 90 days for early monetization (1,000 subs + 3M views threshold). 3/day gives the algorithm 3 daily shots on goal — lower per-video bar, faster signal accumulation.
- **Cost:** ~$0/video — same free pipeline as money-crew (Pollinations + edge-tts + FFmpeg)

---

## The Narrator

Single host. No rotation, no character pool. The narrator is intentionally unnamed — a calm adult male voice who recounts stories in first person, framed as "recovered tapes."

| Attribute | Value |
|---|---|
| Slug (in script JSON `character` field) | `narrator` |
| edge-tts voice | `en-US-ChristopherNeural` |
| Rate | `-15%` (slower than money-crew's `-8%` — horror needs space between phrases) |
| Tone | Calm, intimate, slightly weighted with dread |

Defined in [config/characters.py](config/characters.py) and [pipeline/voiceover.py](pipeline/voiceover.py).

---

## Tech Stack (identical to money-crew)

| Component | Tool |
|---|---|
| Image generation | **Pollinations.ai** (free Flux Schnell) |
| Image upscale | Pillow LANCZOS + UnsharpMask → 1080×1920 |
| Voiceover | **edge-tts** at `-15%` rate (slower than money-crew) |
| Captions | FFmpeg drawtext + bundled **Anton** font @ 90pt, **per-word yellow karaoke** highlight on top of base white phrase |
| Video assembly | FFmpeg full (libfreetype required) |
| Motion | FFmpeg zoompan — slow drift presets, barely perceptible vs money-crew's energetic Ken Burns |
| Upload | YouTube Data API v3 |
| Language | Python 3.11 in venv |
| Schedule | GitHub Actions cron |

---

## Project Structure

```
the-3am-tape/
├── CLAUDE.md
├── .env                       # API keys (gitignored)
├── .env.example
├── .gitignore
├── requirements.txt
├── make_video.py              # script JSON -> mp4 (entry point)
├── daily_pipeline.py          # daily orchestrator: queue → render → upload → archive
├── stats.py                   # daily channel stats snapshot
├── digest.py                  # weekly performance digest
├── auth.py                    # one-time YouTube OAuth bootstrap
│
├── config/
│   ├── settings.py            # paths, ffmpeg bin, video dims, env vars
│   ├── characters.py          # single Narrator definition
│   └── topics.py              # ~35 horror story topic seeds + 30-day cooldown
│
├── pipeline/
│   ├── logger.py
│   ├── image_generator.py     # Pollinations + analog-horror style anchors
│   ├── voiceover.py           # edge-tts narrator voice + slow rate
│   ├── assembler.py           # FFmpeg slow drift motion + subtle captions
│   ├── uploader.py            # YouTube upload via refresh token
│   ├── metadata.py            # Horror SEO (no #shorts, scary-stories tags)
│   ├── stats.py               # Channel stats fetcher
│   └── script_generator.py    # Claude API horror prompt
│
├── scripts/                   # Hand-written video scripts (JSON), FIFO queue
│   ├── README.md              # Schema doc + format guide
│   ├── tape-*.json            # Queued tapes
│   └── archive/               # Already-uploaded tapes
│
├── assets/
│   └── music/                 # Empty in v1 (deferred, same as money-crew)
│
├── outputs/                   # Gitignored except used_topics.json + stats/
│   ├── images/<video_id>/scene_NN.png
│   ├── voiceovers/<video_id>/scene_NN.mp3 + .captions.json
│   ├── final/<video_id>.mp4
│   ├── used_topics.json       # 30-day cooldown state
│   └── stats/<date>.json      # Daily snapshots for the weekly digest
│
└── .github/workflows/
    ├── daily.yml              # 17:00 UTC daily render+upload+commit
    └── weekly.yml             # Sunday 06:00 UTC stats digest as GitHub Issue
```

---

## Pipeline Flow

```
daily_pipeline.py (or workflow_dispatch)
  │
  ├── 1. Pick oldest scripts/*.json (FIFO). If empty + Claude key set, generate one.
  │
  ├── 2. make_video.py
  │      ├── image_generator.generate_for_video()
  │      │     • Pollinations.ai with analog-horror STYLE_SUFFIX
  │      │     • Sequential calls, retry up to 6 with backoff
  │      │     • Pillow upscale to 1080×1920 + sharpen
  │      ├── voiceover.generate_for_video(voice='en-US-ChristopherNeural', rate='-15%')
  │      │     • Per-scene mp3 + word-timed captions JSON
  │      └── assembler.assemble()
  │            • Per scene: slow drift zoompan + subtle drawtext captions
  │            • Concat into 1080×1920 H.264 + AAC
  │
  ├── 3. uploader.upload(privacy=private, publish_at=<random late-PKT>)
  ├── 4. Archive scripts/<id>.json -> scripts/archive/<id>.json
  ├── 5. Record topic in outputs/used_topics.json
  ├── 6. Backfill queue to depth 5 if Claude available
  └── 7. stats.py snapshot -> outputs/stats/<date>.json
```

All steps cache by file existence — re-runs only do new work.

---

## Script Format

Hand-written JSON in `scripts/`. Schema fully documented in [scripts/README.md](scripts/README.md).

**Shorts arc (12 scenes typical, ~12-15 words each, total 60-90 sec):**
- Scene 1: HOOK — drop the listener directly into unease (~10 words)
- Scenes 2–3: SETUP — concrete place, routine, who-where (~12 words each)
- Scenes 4–6: ESCALATION — one wrong detail, then another, then undeniable
- Scene 7: PEAK — the moment that flips the listener's stomach
- Scene 8–9: AFTERMATH or unresolved ending
- (Optional 10): TWIST that reframes everything

Total ~100-120 narration words. Read at -15% rate = ~58-65 seconds. Cuts well under the 60-sec Shorts cap with comfortable margin.

---

## Image Generation Rules

- Resolution target: 1080×1920 (vertical 9:16)
- Pollinations free tier returns ~576×1024 → upscale via `_upscale_to_target`
- Per-scene prompt = scene description + analog-horror STYLE_SUFFIX + NEGATIVE_HINT
- **The grain/film aesthetic is doing real work** — it sets the analog-horror tone AND masks AI artifacts (wonky hands, generic faces). Don't lose this anchor.
- **Never close-up faces** in image prompts — AI fails at faces in horror style. Prefer backs, silhouettes, hands, objects, locations.

---

## Voiceover Rules

- edge-tts at `rate="-15%"` (slower than money-crew)
- Single voice: `en-US-ChristopherNeural` (calm intimate adult male)
- `boundary="WordBoundary"` for word-level timing

---

## Captions

- Burnt in via FFmpeg `drawtext`
- Font: **Anton-Regular.ttf** bundled in `assets/fonts/` (Google Fonts, OFL license, ~170KB). Bold-condensed sans — the standard "viral Shorts caption" font that reads big and crisp at 90pt.
- **Two layers per phrase:**
  1. Base white phrase (with black border) — visible for the entire phrase
  2. Per-word **yellow karaoke highlight** with black box backing — visible only during the spoken interval of that word
- Word-level timing comes from edge-tts `WordBoundary` events. PIL `ImageFont.getlength` measures pixel widths so the yellow word lines up exactly with its position in the centered phrase.
- White text on black box hides any sub-pixel misalignment
- Position: 30% from bottom (just below dead-center of vertical 1080×1920)
- 4 words per phrase (so the eye reads ahead of the karaoke pointer)

---

## Assembler / FFmpeg Rules

- Always use the full ffmpeg build (libfreetype required for drawtext)
- **Motion is more visible than the original "barely perceptible" presets** — Shorts at 60 sec / 6 sec per scene need active drift. Zoom rates ~0.0008-0.0012/frame produce 14-22% zoom over a 6-sec scene = noticeable but not jumpy.
- 7 motion presets cycle per scene index
- Output: H.264 CRF 20, AAC 128k, yuv420p, 30fps, 1080×1920 vertical

---

## Coding Standards (same as money-crew)

- Python 3.11+, PEP 8, type hints, docstrings
- `pathlib.Path` for all paths
- `pipeline.logger.get_logger()` for logging — never `print()` in production
- `python-dotenv` for `.env`
- No hardcoded paths — env vars or `config/settings.py`

---

## Commands

```bash
# Setup (one-time)
brew install python@3.11 ffmpeg
python3.11 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
./venv/bin/python auth.py  # One-time YouTube OAuth for THIS channel

# Render one video locally (no upload)
./venv/bin/python make_video.py scripts/tape-night-shift-gas-station-001.json

# Render + upload private with publishAt
./venv/bin/python make_video.py scripts/tape-...json --upload --publish-at 2026-04-30T22:00:00+05:00

# Daily orchestrator (full pipeline)
./venv/bin/python daily_pipeline.py
```

---

## What Claude Code Should Always Do

1. **Single narrator** — never invent additional characters. The brand is "one calm voice telling stories"
2. **Never reintroduce illustration** — the channel is photoreal analog-horror. No comic book art, no cartoon
3. **Never propose music sources autonomously** — same lesson as money-crew. Music is deferred
4. **Always validate** final video is 1080×1920 9:16 before declaring success
5. **Always log** every step with timestamps via `pipeline.logger`
6. **Always upscale Pollinations output** via `_upscale_to_target`
7. **Never make horror visuals explicit** — implied dread, never gore/blood/jump scares. PG-13 by intention (helps monetization, avoids age-restriction)
8. **Always keep outputs** organized by `video_id`
9. **Never delete outputs on failure** — keep for debugging
10. **Keep videos under 180 sec** — YouTube Shorts cap (raised from 60s in Oct 2024). Target sweet spot is 60-90 sec for analog horror build-up. ~120-145 words narration is comfortable.
11. **Never push without confirmation** — same standing rule as money-crew
