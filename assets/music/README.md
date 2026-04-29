# Background music tracks

Drop royalty-free, kid-friendly background music files in this folder. The pipeline picks one deterministically per `video_id` (same id → same track on re-runs) and mixes it under the narrator at `MUSIC_VOLUME = 0.10` (~10% volume).

## Supported formats

`.mp3` `.m4a` `.wav` `.ogg` `.aac`

## Where to source

- **YouTube Audio Library** (https://studio.youtube.com → Audio Library) — best source. Filter by:
  - Mood: Happy / Bright / Inspirational
  - Genre: Children's / Cinematic / Pop
  - Attribution: "no attribution required" (most are)
  - Duration: 60+ sec works (we loop the track if shorter than the video)
- **Pixabay Music** — free, no attribution
- **Free Music Archive** — Creative Commons, check license per track

## Recommendation

Add 3–5 different tracks. The pipeline rotates them by `video_id` hash, so different videos get different beds and the channel doesn't sound monotonous.

## To disable music

Either remove all tracks from this folder, or rename the folder. The pipeline gracefully runs music-free if no tracks are found.
