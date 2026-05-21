# Ambient horror beds

Drop royalty-free atmospheric drone/ambient files in this folder. The pipeline picks one deterministically per `video_id` (same id → same track on re-runs) and mixes it under the narrator at `MUSIC_VOLUME = 0.13` (~13% volume).

## What's in here now

Three procedurally-generated ambient beds (made with `ffmpeg lavfi` — 100% license-clear, no attribution needed):

- `drone_deep.mp3` — 55Hz + 82.5Hz sine drone + low-pass brown noise. Deep dread bed.
- `drone_uneasy.mp3` — 110Hz + 165Hz sine drone + tremolo + pink noise. Subtle warble. Used for uneasy/escalation tapes.
- `drone_wind.mp3` — brown + pink noise wash + 41Hz sub-sine. Wind-and-room-tone bed.

These are placeholders that work today. Replace with real sourced tracks when you want a more cinematic sound (see below).

## Supported formats

`.mp3` `.m4a` `.wav` `.ogg` `.aac`

## Where to source better tracks

For a horror narration channel, you want **slow ambient drones, room tones, low-frequency dread beds** — NOT music with melodies/rhythms (those compete with narration).

- **Pixabay Music** (https://pixabay.com/music/) — filter genre = "Ambient" + mood = "Dark". Free, no attribution.
- **YouTube Audio Library** (https://studio.youtube.com → Audio Library) — filter mood = "Dark" + genre = "Cinematic". Free, no attribution required for most.
- **Free Music Archive** (https://freemusicarchive.org/) — search "drone ambient" with CC0/CC-BY filter.
- **freesound.org** — search "drone", "ambient horror", "room tone". CC0 tracks only (filter by license).
- **Internet Archive** — public domain ambient/field recordings.

Avoid: jump-scare stingers, melodic horror scores (they fight the narrator), short loops under 60 sec.

## Recommendation

Add 5-8 different drone tracks once you've sourced real ones. The pipeline rotates them by `video_id` hash, so the channel doesn't sound monotonous across uploads.

## To disable music

Either remove all tracks from this folder, or rename the folder. The pipeline gracefully runs music-free if no tracks are found.

## How the procedural drones were generated

For reference / regenerating, the ffmpeg commands are in the git history of this directory. The recipe:

- One or two sine waves at low frequencies (40-165Hz) for the drone tone
- Brown or pink noise low-passed for room atmosphere
- Optional tremolo for subtle warble
- 4-5 sec fade-in and fade-out so the bed doesn't slam in/out
