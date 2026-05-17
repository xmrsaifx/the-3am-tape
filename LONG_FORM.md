# LONG_FORM.md — The 3AM Tape (long-form companion channel)

Long-form (8–12 min) horror narration sibling format. Same brand voice as Shorts ([CLAUDE.md](CLAUDE.md)), but reframed for **lean-back YouTube watch time + Facebook video reach**. Targets a **separate YouTube channel and a Facebook Page** (different OAuth credentials than the Shorts channel).

This is a companion to the Shorts pipeline, not a replacement. The Shorts queue keeps running 4/day. Long-form runs on its own cadence and queue.

---

## 1. Why long-form

| Goal | Shorts (existing) | Long-form (new) |
|---|---|---|
| Monetization gate | 1,000 subs + 3M Shorts views in 90d | 1,000 subs + **4,000 watch-hours** in 365d |
| What the algorithm rewards | Loops, swipes, completion % | **Watch time**, session length, CTR |
| Cost per video | ~$0 | ~$0 (same free pipeline) |
| User effort | 1 short JSON, 100–150 words | 1 long JSON, 750–1,150 words (user writes full prose) |

Long-form unlocks the standard YPP monetization path, mid-roll ads (5×–10× RPM vs Shorts), and Facebook Reels/Video monetization on Pages with 60k watch-min/60d.

---

## 2. Format spec

| Constraint | Value |
|---|---|
| **Total runtime** | **8–12 min** (480–720 sec). 10 min is the sweet spot — unlocks mid-roll ads (8+ min required) without over-stretching one story. |
| **Aspect ratio** | **16:9 horizontal — 1920×1080** |
| **Voice** | `en-US-ChristopherNeural` at **-25% rate, -10Hz pitch** (same V3 tuning as Shorts — keeps brand voice identical across formats) |
| **Words-per-second** | **~2.2 wps measured** at `-25%` rate on `en-US-ChristopherNeural` (2026-05-18 calibration). **~1,060 words = 8 min, ~1,320 words = 10 min, ~1,580 words = 12 min.** The earlier 1.57 wps estimate was too low — scripts targeting 940 words actually render at ~7:15, below the 8:00 mid-roll-ads threshold. |
| **Image cadence** | **Dense — ~60–90 images per video, 6–10 sec each** with slow drift motion |
| **Captions** | **No burned captions.** Generate SRT from edge-tts word timings, upload as separate CC track to YouTube + Facebook |
| **Music** | Deferred (same as Shorts). Add later if a free license source is identified |
| **Output** | H.264 CRF 20, AAC 192k (bump from Shorts' 128k for lean-back listening), yuv420p, 30fps, 1920×1080 |

### Why no burned captions

Long-form is watched on TV / desktop / car (autoplay). Burned karaoke text is a phone-content signal that hurts perceived production value on a 55" screen. YouTube's algorithm actively favors videos with a proper CC track (accessibility metric tied to recommendation reach). The same SRT uploads cleanly to Facebook as a caption file. The Shorts karaoke look stays a Shorts-only brand signal.

### Why dense image cadence

60–90 images × 6–10 sec means the eye never sees the same frame for >10 sec. Combined with slow drift zoompan, this keeps long-form visually alive without leaning on stock B-roll or talking-head padding. Cost: ~60–90 sequential Pollinations calls (3–8 min generation time) and ~120–270 MB of intermediate PNGs per video — acceptable for a 1/day cadence.

---

## 3. Posting cadence (proposed)

Start at **1/day**, single slot:

| Slot | Why |
|---|---|
| **23:00 UTC** | US prime-time bedtime (~18:00 ET / ~19:00 ET), highest "watch a 10-min horror story before sleep" intent |

Reasoning for 1/day vs Shorts' 4/day:
- Long-form requires ~750–1,150 words of hand-written prose per script. Burnout-prone at higher cadence.
- One quality 10-min video out-performs three rushed ones on watch-time metrics.
- Algorithm session-bonus rewards consistency over volume on long-form (unlike Shorts).

Scale to 2/day only after 30 days of consistent 1/day with avg view duration ≥ 4 min.

---

## 4. Pipeline integration

Extend the existing pipeline ([CLAUDE.md §Pipeline Flow](CLAUDE.md)) rather than forking. A `format` field on the script JSON switches behavior:

```json
{ "format": "short" }   // default if omitted — current Shorts pipeline
{ "format": "long" }    // new long-form pipeline
```

### Modules to extend

| Module | Change for `format: "long"` |
|---|---|
| [config/settings.py](config/settings.py) | Add `LONG_VIDEO_WIDTH=1920`, `LONG_VIDEO_HEIGHT=1080`, `LONG_AUDIO_BITRATE="192k"` |
| [pipeline/image_generator.py](pipeline/image_generator.py) | Switch upscale target to 1920×1080; strip "vertical 9:16 framing" from prompts, replace with "horizontal 16:9 framing"; keep same analog-horror STYLE_SUFFIX |
| [pipeline/voiceover.py](pipeline/voiceover.py) | Same voice / rate / pitch. Generate per-section MP3 (not per-scene) since sections are longer prose blocks. Still emit `WordBoundary` JSON for SRT generation |
| [pipeline/assembler.py](pipeline/assembler.py) | Skip `drawtext` filter entirely. Compute per-image hold duration from section duration ÷ image count. Apply slow drift zoompan (same 7 presets, cycled) |
| **NEW** `pipeline/srt_generator.py` | Convert edge-tts WordBoundary timings into a standard `.srt` caption file |
| [pipeline/uploader.py](pipeline/uploader.py) | Accept `--channel` flag selecting OAuth refresh token (`YT_REFRESH_TOKEN_LONG` env var). Upload SRT via `captions.insert`. Set `categoryId=22` (People) or `24` (Entertainment) for long-form. No `#shorts` tag. |
| [pipeline/metadata.py](pipeline/metadata.py) | Long-form SEO is different: longer titles (60–70 chars), 3–5 paragraph descriptions, timestamp chapters in description |
| **NEW** `pipeline/facebook_uploader.py` | Graph API video upload to a Page. See §8. |
| [daily_pipeline.py](daily_pipeline.py) | Detect `format` field; route to long-form path when present. Pick from `scripts/long/` queue. Archive to `scripts/long/archive/` |

### Filesystem additions

```
the-3am-tape/
├── scripts/
│   ├── tape-*.json              # existing Shorts queue
│   ├── archive/                 # existing
│   └── long/                    # NEW — long-form queue (FIFO)
│       ├── README.md            # long-form script guide
│       ├── longtape-*.json
│       └── archive/
├── outputs/
│   ├── final/
│   │   ├── tape-*.mp4           # existing Shorts
│   │   └── longtape-*.mp4       # NEW
│   ├── captions/                # NEW — generated SRT files
│   │   └── longtape-*.srt
│   └── used_topics.json         # shared cooldown across formats
└── .github/workflows/
    ├── daily.yml                # existing Shorts (4×/day)
    └── long_daily.yml           # NEW — 1/day at 23:00 UTC
```

---

## 5. Script schema (long-form)

Hand-written JSON in `scripts/long/`. User writes the full prose; pipeline auto-times images against section duration.

```json
{
  "video_id": "longtape-cabin-mirror-001",
  "format": "long",
  "character": "narrator",
  "topic": "I rented a cabin and the only mirror inside showed a room I had never seen",
  "title": "I Rented a Cabin and the Mirror Showed a Room I Had Never Seen | True Scary Story",
  "description_intro": "A two-week cabin rental in the Adirondacks. Everything was ordinary except for one detail in the bathroom mirror that I cannot explain to this day. This is what happened over those fourteen nights.",
  "sections": [
    {
      "id": 1,
      "beat": "hook",
      "narration": "The cabin was a two week rental in upstate New York. I had been there four days before I noticed the mirror was wrong. The room reflected back was not the bathroom I was standing in. It was a child's bedroom. Pale blue walls. A small bed against the far wall. And a window where my window was a solid tiled wall.",
      "image_prompts": [
        "exterior of a small wooden cabin in dense pine forest at dusk, single porch light glowing, no people, low fog at the tree line, horizontal 16:9 framing",
        "interior view of a rustic cabin bathroom, vintage mirror above a porcelain sink, dim wall sconce light, wood-paneled walls, horizontal 16:9 framing",
        "close shot of an antique bathroom mirror reflecting a softly-lit child's bedroom that does not match the bathroom around it, pale blue wallpaper visible in the reflection, no figures, horizontal 16:9 framing",
        "wide shot of a small empty child's bedroom with pale blue walls, a single child-sized bed against the far wall, late evening light through a single window, no people, horizontal 16:9 framing"
      ]
    },
    {
      "id": 2,
      "beat": "setup",
      "narration": "I had taken the cabin to finish a book...",
      "image_prompts": ["...", "..."]
    }
  ]
}
```

### Field reference

| Field | Required | Notes |
|---|---|---|
| `video_id` | yes | `longtape-<slug>-NNN`. Must be unique across queue + archive. |
| `format` | yes | Always `"long"`. Triggers the long-form code path. |
| `character` | yes | Always `"narrator"`. |
| `topic` | yes | Recorded in shared `outputs/used_topics.json` (30-day cooldown shared with Shorts so the same story doesn't run in both formats). |
| `title` | recommended | 60–70 chars. Append `\| True Scary Story` or `\| Analog Horror`. |
| `description_intro` | recommended | First paragraph of the YouTube description (hook). Pipeline appends chapter timestamps + tags. |
| `sections` | yes | **8–14 sections** typical. Each section is one story beat (hook, setup, escalation, peak, aftermath). |
| `sections[].id` | yes | 1-indexed. |
| `sections[].beat` | optional | `hook \| setup \| escalation \| peak \| aftermath`. Used for description chapter labels. |
| `sections[].narration` | yes | **60–100 words per section.** Continuous prose. Same narration rules as Shorts (first-person past, no quote marks, spell out numbers). |
| `sections[].image_prompts` | yes | **4–8 prompts per section.** Pipeline divides section audio duration evenly across these. End each with `horizontal 16:9 framing`. Same composition rules as Shorts (no close-up faces, specific real-world objects, atmospheric cues). |

### Word budget guide

Calibrated against measured `-25%` rate on `en-US-ChristopherNeural` (~2.2 wps).

| Target runtime | Total narration words | Sections × words each |
|---|---|---|
| 8 min (mid-roll ads minimum) | ~1,060 | 10 × 106, or 12 × 88 |
| 10 min (sweet spot) | ~1,320 | 12 × 110, or 14 × 95 |
| 12 min | ~1,580 | 14 × 113, or 16 × 99 |

**Hitting the 8:00 mid-roll-ads threshold is the single most important budget constraint.** A 971-word script renders to ~7:15 — under the mid-roll gate, so it ships as a regular video without the 5×–10× RPM bump. The assembler logs a warning but does not fail when this happens; the user can decide whether to extend the script or accept the lower monetization tier.

### Story arc (long-form 10-section default)

| Section | Beat | Purpose |
|---|---|---|
| 1 | Hook | Front-load the impossible thing. Same archetypes as Shorts (see [scripts/README.md](scripts/README.md) §Hook archetypes), but expand to a full paragraph with sensory detail. |
| 2 | Setup — place | Where, when, why the narrator was there. Build the ordinary. |
| 3 | Setup — routine | What "normal" looked like for the first day/week. |
| 4 | First wrong note | Specific, small, deniable. |
| 5 | Reaction + dismissal | Narrator rationalizes it. (Critical — gives the audience permission to dismiss it too, then it hits harder when they can't.) |
| 6 | Pattern recognition | Second incident. Now it's not coincidence. |
| 7 | Investigation | Narrator actively tries to verify / disprove. Found objects, asked people, checked records. |
| 8 | Escalation | The wrong thing intensifies or changes nature. |
| 9 | Peak | The stomach-flip moment. Still no monster shown — the dread is in implication. |
| 10 | Aftermath / lingering image | What happened after. End on the line that won't leave them. |

This is a **scaled-up 12-scene Shorts arc**, not a different structure. The same hook → escalation → peak → aftermath shape works at both lengths; long-form just gives each beat room to breathe with sensory detail and the listener's emotional reaction.

---

## 6. Image generation rules (long-form delta vs Shorts)

Same analog-horror STYLE_SUFFIX. Same NEGATIVE_HINT. Same "never close-up faces." The only changes:

- **End every prompt with `horizontal 16:9 framing`** (not `vertical 9:16`).
- **Upscale target is 1920×1080** (not 1080×1920).
- **More environmental variety per section** — since each section gets 4–8 images held 6–10 sec each, vary the angle (wide → medium → object detail → empty interior) within a section to avoid same-frame-too-long fatigue.
- **Recurring spatial anchors are good.** Repeating the same exterior cabin shot every 2–3 sections creates a sense of place. Don't make every image novel — anchors build location memory.

---

## 7. Captions / SRT

Pipeline generates a `.srt` from edge-tts WordBoundary events. Algorithm:

1. Concatenate all sections' WordBoundary streams with cumulative offset.
2. Chunk into caption blocks of **6–8 words** (~3–4 sec per cue).
3. Break on natural punctuation (period, comma) when possible.
4. Write to `outputs/captions/<video_id>.srt`.

Upload flow:
- **YouTube:** `youtube.captions.insert` after video upload, language `en`, name `English`.
- **Facebook:** Upload as `captions_file` parameter on the Graph API `/videos` POST (Facebook requires the SRT filename to follow `filename.<locale>_<LOCALE>.srt` pattern, e.g. `longtape-cabin-mirror-001.en_US.srt`).

---

## 8. Facebook upload (new module)

`pipeline/facebook_uploader.py` — uploads to a Facebook **Page** via the Graph API.

### Requirements
- A Facebook Page (not a personal profile) — videos to personal profiles can't be uploaded via API.
- Page access token with `pages_manage_posts`, `pages_read_engagement`, `pages_show_list` scopes.
- App in either Development mode (for the Page admins) or App Review approved.

### Env vars
```
FB_PAGE_ID=<numeric page id>
FB_PAGE_ACCESS_TOKEN=<long-lived page token>
```

### Upload flow (resumable for videos > 100 MB)
1. `POST /{page-id}/videos` with `upload_phase=start` → get `upload_session_id`.
2. Chunked `upload_phase=transfer` calls.
3. `upload_phase=finish` with `title`, `description`, `captions_file` (SRT).
4. Set `published=true` for immediate post, or `scheduled_publish_time` for queued posts (must be 10 min – 6 months in future).

### Posting cadence on Facebook
Same long-form video, posted **within 1 hour of YouTube upload**. Facebook's algorithm penalizes content it detects as re-shared from elsewhere, so:
- Upload natively (don't link to YouTube).
- Use a slightly different title (the YouTube SEO title is too keyword-stuffed for FB's editorial-feel ranking).
- First comment from the Page should be a one-line teaser, not the YouTube link.

---

## 9. Multi-channel / multi-account credentials

The Shorts channel has its own OAuth. The long-form channel needs a separate one.

```
# Shorts channel (existing)
YT_CLIENT_ID=...
YT_CLIENT_SECRET=...
YT_REFRESH_TOKEN=...

# Long-form channel (NEW)
YT_LONG_CLIENT_ID=...
YT_LONG_CLIENT_SECRET=...
YT_LONG_REFRESH_TOKEN=...

# Facebook Page for long-form (NEW)
FB_PAGE_ID=...
FB_PAGE_ACCESS_TOKEN=...
```

[auth.py](auth.py) needs a `--channel=long` flag that writes the long-form OAuth into `YT_LONG_REFRESH_TOKEN`. [pipeline/uploader.py](pipeline/uploader.py) reads the appropriate token set based on the script's `format` field.

---

## 10. Metadata / SEO (long-form)

| Element | Long-form pattern |
|---|---|
| **Title** | 60–70 chars. Mystery hook + genre tag. Example: `I Rented a Cabin and the Mirror Showed a Room I Had Never Seen \| True Scary Story` |
| **Description** | 3–5 paragraphs. (1) Hook recap. (2) Setting/atmosphere paragraph. (3) Why-you-should-watch tease without spoiling. (4) Chapter timestamps. (5) Channel CTA + 5–8 relevant hashtags at bottom. |
| **Chapters** | Auto-generated from `sections[].beat` + cumulative timing. `0:00 The Cabin` / `1:32 The First Night` / etc. **Triggers YouTube chapter UI if formatted correctly** — first timestamp must be `0:00`, minimum 3 chapters, each ≥10 sec. |
| **Tags** | `scary stories, true scary stories, horror narration, analog horror, [topic noun], creepypasta, scary stories to tell in the dark, true horror stories reddit` |
| **Category** | `Entertainment` (24) for narration. Not `People & Blogs`. |
| **Thumbnail** | Generate a custom 1280×720 thumbnail from a key scene image + 2–4 word overlay text. (NEW pipeline step — Shorts doesn't need this since YouTube auto-picks Shorts thumbs.) **Critical for long-form CTR.** |
| **End screen** | Last 20 sec of video should hold on a static dark frame so YouTube's end-screen elements (subscribe + next video) place cleanly. |

---

## 11. What Claude Code should always do (long-form additions)

In addition to the 11 rules in [CLAUDE.md §What Claude Code Should Always Do](CLAUDE.md):

12. **Never burn captions onto long-form video** — SRT only. The Shorts karaoke look is Shorts-only brand.
13. **Long-form must hit 8:00 minimum runtime** to qualify for mid-roll ads. Validate before declaring success — reject if final video is < 480 sec.
14. **Always generate a custom thumbnail** for long-form. Thumbnail CTR is the single biggest lever on long-form views; auto-picked frames are a dropped ball.
15. **Same narrator voice across formats.** Don't switch to a "longer-form" voice — brand consistency across Shorts and long-form is what trains the audience to recognize the channel.
16. **Share the 30-day topic cooldown** across Shorts and long-form via `outputs/used_topics.json`. A topic running in Shorts on Monday shouldn't run in long-form on Wednesday — cannibalizes both.
17. **Long-form aspect = 1920×1080.** Validate before declaring success.

---

## 12. Open items the user needs to decide before building

These are blocking; the doc is otherwise complete:

- [ ] **Long-form YouTube channel name + handle** (separate channel from Shorts? Or a "Long Stories" playlist on the same channel? Recommendation: separate channel, so the Shorts feed isn't polluted by 10-min thumbnails and vice versa.)
- [ ] **Facebook Page name** + whether it's the same brand or a Page-specific variant
- [ ] **Run OAuth bootstrap** for the new long-form YouTube channel: `./venv/bin/python auth.py --channel=long`
- [ ] **Create Facebook App + Page access token** (one-time setup, ~30 min)
- [ ] **Confirm 1/day cadence at 23:00 UTC** as the starting slot, or pick a different one
- [ ] **First long-form script** — user delivers ~750–1,150 words of prose in the schema in §5; pipeline build can validate against it

Once these are answered, the build is: extend the 4 existing pipeline modules + add 2 new ones (SRT, FB uploader) + write the long_daily workflow. Estimated 1–2 days of focused work for a working end-to-end render+upload on both platforms.
