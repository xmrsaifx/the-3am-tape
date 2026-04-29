"""Top-level orchestrator: take a script JSON, produce a final mp4, optionally upload.

Usage:
    ./venv/bin/python make_video.py scripts/rico_coffee_trap.json
    ./venv/bin/python make_video.py scripts/rico_coffee_trap.json --upload
    ./venv/bin/python make_video.py scripts/rico_coffee_trap.json --upload --privacy=public
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from pipeline import assembler, image_generator, voiceover
from pipeline.logger import get_logger

logger = get_logger("orchestrator")


def main(
    script_path: Path,
    upload: bool,
    privacy: str,
    made_for_kids: bool,
    publish_at: str | None,
) -> Path:
    script = json.loads(script_path.read_text())
    video_id = script["video_id"]
    character = script["character"]
    scenes = script["scenes"]
    voice = script.get("voice") or voiceover.CHARACTER_VOICES[character]

    logger.info(f"=== Building {video_id} ({len(scenes)} scenes) ===")

    logger.info("Step 1: generating scene images")
    images = image_generator.generate_for_video(video_id, scenes)

    logger.info("Step 2: generating per-scene narration + captions")
    audio, caps = voiceover.generate_for_video(video_id, scenes, voice=voice)

    logger.info("Step 3: assembling final video (Ken Burns motion + captions)")
    final = assembler.assemble(video_id, images, audio, caps)

    logger.info(f"=== Done. Final video: {final} ===")

    if upload:
        from pipeline import metadata as meta_mod
        from pipeline import uploader
        meta = meta_mod.metadata_for(script)
        suffix = f" (publishAt={publish_at})" if publish_at else f" (privacy={privacy})"
        logger.info(f"Step 4: uploading to YouTube{suffix}")
        logger.info(f"  title: {meta['title']}")
        logger.info(f"  tags: {', '.join(meta['tags'])}")
        url = uploader.upload(
            video_path=final,
            title=meta["title"],
            description=meta["description"],
            tags=meta["tags"],
            privacy_status=privacy,
            made_for_kids=made_for_kids,
            publish_at=publish_at,
        )
        logger.info(f"=== Uploaded: {url} ===")
        print(f"\nYouTube URL: {url}")

    return final


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("script", type=Path)
    parser.add_argument(
        "--upload",
        action="store_true",
        help="After rendering, upload to YouTube (needs OAuth set up — see auth.py)",
    )
    parser.add_argument(
        "--privacy",
        choices=("private", "unlisted", "public"),
        default="unlisted",
        help="Upload privacy. Default 'unlisted' = link-only, safe for first runs.",
    )
    parser.add_argument(
        "--made-for-kids",
        action="store_true",
        help="Mark video as 'made for kids' (COPPA compliant — disables comments + personalized ads).",
    )
    parser.add_argument(
        "--publish-at",
        default=None,
        help="RFC-3339 timestamp for scheduled publishing, e.g. '2026-04-29T12:00:00+05:00'. "
             "Forces privacy=private at upload time; YouTube auto-flips to public at publishAt.",
    )
    args = parser.parse_args()
    main(
        args.script,
        upload=args.upload,
        privacy=args.privacy,
        made_for_kids=args.made_for_kids,
        publish_at=args.publish_at,
    )
