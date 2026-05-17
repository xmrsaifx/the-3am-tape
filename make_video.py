"""Top-level orchestrator: take a script JSON, produce a final mp4, optionally upload.

Routes on `script["format"]`:
  - "short" (default): existing Shorts pipeline (vertical 9:16, karaoke captions,
    per-scene MP3 + image, optional FB/IG Reels cross-post).
  - "long": long-form pipeline (horizontal 16:9, no burned captions, per-section
    MP3 with N images each, SRT track, custom thumbnail, FB long-video cross-post).
    See LONG_FORM.md for spec. Long-form supports matrix-style execution via:
        --section N        render one section's images + voice (matrix shard worker)
        --assemble-only    skip per-section rendering, just assemble + upload
                           from already-rendered (e.g. artifact-restored) files.

Usage (Shorts):
    ./venv/bin/python make_video.py scripts/tape-foo.json
    ./venv/bin/python make_video.py scripts/tape-foo.json --upload --privacy=public

Usage (long-form, single-machine end-to-end):
    ./venv/bin/python make_video.py scripts/long/longtape-grandmother-house-001.json --upload

Usage (long-form, matrix worker — one section only):
    ./venv/bin/python make_video.py scripts/long/longtape-grandmother-house-001.json --section 3

Usage (long-form, matrix assemble step):
    ./venv/bin/python make_video.py scripts/long/longtape-grandmother-house-001.json \\
        --assemble-only --upload --privacy=public
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from pipeline import assembler, image_generator, voiceover
from pipeline.logger import get_logger

logger = get_logger("orchestrator")


def _run_short(script: dict, args: argparse.Namespace) -> Path | None:
    """Existing Shorts pipeline. Returns the final video path (or None for
    matrix-style flags that aren't valid here)."""
    if args.section is not None or args.assemble_only:
        raise SystemExit(
            "--section / --assemble-only are long-form only "
            "(format: 'short' doesn't shard)"
        )
    video_id = script["video_id"]
    character = script["character"]
    scenes = script["scenes"]
    voice = script.get("voice") or voiceover.CHARACTER_VOICES[character]

    logger.info(f"=== Building {video_id} (short, {len(scenes)} scenes) ===")

    logger.info("Step 1: generating scene images")
    images = image_generator.generate_for_video(video_id, scenes)

    logger.info("Step 2: generating per-scene narration + captions")
    audio, caps = voiceover.generate_for_video(video_id, scenes, voice=voice)

    logger.info("Step 3: assembling final video (Ken Burns motion + captions)")
    final = assembler.assemble(video_id, images, audio, caps)

    logger.info(f"=== Done. Final video: {final} ===")

    if args.upload:
        from pipeline import metadata as meta_mod
        from pipeline import uploader
        meta = meta_mod.metadata_for(script)
        suffix = f" (publishAt={args.publish_at})" if args.publish_at else f" (privacy={args.privacy})"
        logger.info(f"Step 4: uploading to YouTube{suffix}")
        url = uploader.upload(
            video_path=final, title=meta["title"], description=meta["description"],
            tags=meta["tags"], privacy_status=args.privacy,
            made_for_kids=args.made_for_kids, publish_at=args.publish_at,
        )
        logger.info(f"=== Uploaded: {url} ===")
        print(f"\nYouTube URL: {url}")

    if args.fb_upload:
        from pipeline import facebook_uploader
        from pipeline import metadata as meta_mod
        meta = meta_mod.metadata_for(script)
        logger.info("Step 5: uploading to Facebook Reels")
        try:
            fb_url = facebook_uploader.upload(
                video_path=final, title=meta["title"], description=meta["description"],
            )
            logger.info(f"=== Facebook Reel: {fb_url} ===")
            print(f"Facebook Reel: {fb_url}")
        except Exception as e:
            logger.error(f"Facebook upload failed (non-fatal): {e}")

    if args.ig_upload:
        from pipeline import instagram_uploader
        from pipeline import metadata as meta_mod
        meta = meta_mod.metadata_for(script)
        logger.info("Step 6: uploading to Instagram Reels")
        try:
            ig_url = instagram_uploader.upload(
                video_path=final, title=meta["title"], description=meta["description"],
            )
            logger.info(f"=== Instagram Reel: {ig_url} ===")
            print(f"Instagram: {ig_url}")
        except Exception as e:
            logger.error(f"Instagram upload failed (non-fatal): {e}")

    return final


def _run_long(script: dict, args: argparse.Namespace) -> Path | None:
    """Long-form pipeline. Supports three execution shapes:
      1. Single-machine end-to-end (no special flags): render all sections,
         assemble, optionally upload.
      2. Matrix shard worker (--section N): render only section N's images +
         voice. Exit without assembling. Files land in canonical paths so the
         assemble step can pick them back up after artifact restore.
      3. Matrix assemble step (--assemble-only): expect all per-section files
         already on disk (e.g. just downloaded as artifacts). Assemble + SRT
         + thumbnail + upload.
    """
    video_id = script["video_id"]
    character = script["character"]
    sections = script["sections"]
    voice = script.get("voice") or voiceover.CHARACTER_VOICES[character]

    if args.section is not None and args.assemble_only:
        raise SystemExit("--section and --assemble-only are mutually exclusive")

    # ---- Per-section matrix worker ----
    if args.section is not None:
        sec_id = args.section
        if not any(s["id"] == sec_id for s in sections):
            raise SystemExit(f"section {sec_id} not in script (ids: {[s['id'] for s in sections]})")
        logger.info(f"=== Matrix shard: {video_id} section {sec_id} ===")
        logger.info("Step 1: images for this section")
        image_generator.generate_for_long_video(
            video_id, sections, section_filter=sec_id,
        )
        logger.info("Step 2: voice + captions for this section")
        voiceover.generate_for_long_video(
            video_id, sections, voice=voice, section_filter=sec_id,
        )
        logger.info(f"=== Shard {sec_id} complete ===")
        return None

    # ---- Render all sections (skipped if --assemble-only and files cached) ----
    if not args.assemble_only:
        logger.info(f"=== Building {video_id} (long, {len(sections)} sections) ===")
        logger.info("Step 1: generating section images (N per section)")
        image_generator.generate_for_long_video(video_id, sections)
        logger.info("Step 2: generating per-section narration + captions")
        voiceover.generate_for_long_video(video_id, sections, voice=voice)
    else:
        logger.info(f"=== Assemble-only: {video_id} (expecting cached per-section files) ===")

    # Collect canonical paths from the cached files (no re-render — both calls
    # are no-ops if files exist on disk).
    section_images = image_generator.generate_for_long_video(video_id, sections)
    section_audio, section_captions = voiceover.generate_for_long_video(
        video_id, sections, voice=voice,
    )

    # Build the sections_data list assembler expects
    sections_sorted = sorted(sections, key=lambda s: s["id"])
    sections_data = []
    for i, sec in enumerate(sections_sorted):
        sections_data.append({
            "section_id": sec["id"],
            "audio": section_audio[i],
            "images": section_images[sec["id"]],
        })

    logger.info("Step 3: assembling long-form video (slow drift, no burned captions)")
    final = assembler.assemble_long(video_id, sections_data)
    logger.info(f"=== Final video: {final} ===")

    # SRT (always — cheap and improves YT reach even without uploading)
    srt_path = None
    if not args.no_srt:
        from pipeline import srt_generator
        logger.info("Step 4: generating SRT caption track")
        srt_path = srt_generator.build_srt_from_sections(
            video_id, section_audio, section_captions,
        )

    # Thumbnail
    thumb_path = None
    if not args.no_thumbnail:
        from pipeline import thumbnail_generator
        logger.info("Step 5: generating custom thumbnail")
        thumb_path = thumbnail_generator.generate_thumbnail(script)

    if not args.upload:
        logger.info(f"=== Done (no upload). Video: {final} ===")
        return final

    # ---- Upload chain ----
    from pipeline import metadata as meta_mod
    from pipeline import uploader

    section_durations = [assembler._ffprobe_duration(a) for a in section_audio]
    meta = meta_mod.metadata_for_long(script, section_durations)

    suffix = f" (publishAt={args.publish_at})" if args.publish_at else f" (privacy={args.privacy})"
    logger.info(f"Step 6: uploading to YouTube{suffix}")
    yt_url = uploader.upload(
        video_path=final, title=meta["title"], description=meta["description"],
        tags=meta["tags"],
        category_id=str(script.get("category_id") or "24"),  # 24 = Entertainment
        privacy_status=args.privacy, made_for_kids=args.made_for_kids,
        publish_at=args.publish_at,
    )
    yt_video_id = yt_url.rsplit("=", 1)[-1]
    logger.info(f"=== YouTube: {yt_url} ===")
    print(f"\nYouTube URL: {yt_url}")

    # Thumbnail (after upload — YouTube needs the video id)
    if thumb_path is not None:
        try:
            uploader.set_thumbnail(yt_video_id, thumb_path)
        except Exception as e:
            logger.error(f"thumbnail set failed (non-fatal): {e}")

    # SRT to YouTube
    if srt_path is not None:
        try:
            uploader.upload_caption(yt_video_id, srt_path)
        except Exception as e:
            logger.error(f"YT caption upload failed (non-fatal): {e}")

    # Facebook long-form cross-post
    if not args.no_fb:
        from pipeline import facebook_long_uploader
        try:
            fb_url = facebook_long_uploader.upload(
                video_path=final, title=meta["title"], description=meta["description"],
                srt_path=srt_path,
            )
            logger.info(f"=== Facebook: {fb_url} ===")
            print(f"Facebook URL: {fb_url}")
        except Exception as e:
            logger.error(f"Facebook long upload failed (non-fatal): {e}")

    return final


def main(args: argparse.Namespace) -> Path | None:
    script = json.loads(args.script.read_text())
    fmt = script.get("format", "short")
    if fmt == "long":
        return _run_long(script, args)
    return _run_short(script, args)


def render(
    script_path: Path,
    upload: bool = False,
    privacy: str = "unlisted",
    made_for_kids: bool = False,
    publish_at: str | None = None,
    fb_upload: bool = False,
    ig_upload: bool = False,
    section: int | None = None,
    assemble_only: bool = False,
    no_srt: bool = False,
    no_thumbnail: bool = False,
    no_fb: bool = False,
) -> Path | None:
    """Programmatic entry-point used by daily_pipeline.py. Wraps `main` so
    callers don't have to construct an argparse.Namespace by hand."""
    args = argparse.Namespace(
        script=Path(script_path),
        upload=upload, privacy=privacy, made_for_kids=made_for_kids,
        publish_at=publish_at, fb_upload=fb_upload, ig_upload=ig_upload,
        section=section, assemble_only=assemble_only,
        no_srt=no_srt, no_thumbnail=no_thumbnail, no_fb=no_fb,
    )
    return main(args)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("script", type=Path)
    parser.add_argument(
        "--upload", action="store_true",
        help="After rendering, upload to YouTube (needs OAuth set up — see auth.py)",
    )
    parser.add_argument(
        "--privacy", choices=("private", "unlisted", "public"), default="unlisted",
        help="Upload privacy. Default 'unlisted' = link-only, safe for first runs.",
    )
    parser.add_argument(
        "--made-for-kids", action="store_true",
        help="Mark video as 'made for kids' (COPPA — disables comments + personalized ads).",
    )
    parser.add_argument(
        "--publish-at", default=None,
        help="RFC-3339 timestamp for scheduled publishing. "
             "Forces privacy=private at upload; YouTube auto-flips at publishAt.",
    )
    parser.add_argument(
        "--fb-upload", action="store_true",
        help="(Shorts) Also upload to Facebook as a Reel.",
    )
    parser.add_argument(
        "--ig-upload", action="store_true",
        help="(Shorts) Also upload to Instagram as a Reel.",
    )
    # ---- Long-form matrix flags ----
    parser.add_argument(
        "--section", type=int, default=None,
        help="(Long-form) Render only this section's images + voice and exit. "
             "Used by matrix shard workers in long_daily.yml.",
    )
    parser.add_argument(
        "--assemble-only", action="store_true",
        help="(Long-form) Skip per-section rendering. Expects all section files "
             "already on disk (e.g. just restored from artifacts).",
    )
    parser.add_argument(
        "--no-srt", action="store_true",
        help="(Long-form) Skip SRT generation.",
    )
    parser.add_argument(
        "--no-thumbnail", action="store_true",
        help="(Long-form) Skip custom thumbnail generation.",
    )
    parser.add_argument(
        "--no-fb", action="store_true",
        help="(Long-form) Skip Facebook cross-post when --upload is set.",
    )
    main(parser.parse_args())
