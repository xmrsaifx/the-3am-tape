"""The 3AM Tape — daily horror video automation.

Logic:
  1. Pick the next queued script from scripts/*.json (FIFO by filename).
  2. If queue is empty AND ANTHROPIC_API_KEY is set, auto-generate one via
     pipeline/script_generator.py from a fresh topic in the bank.
  3. If queue is empty AND no Claude key → fail loudly.
  4. Render via make_video.py (image gen + voice + assemble).
  5. Upload to YouTube as PUBLIC IMMEDIATELY (sprint mode for monetization
     speed — see daily.yml, 3/day). Each cron fire is timed to a target
     audience peak so the upload-then-publish-now flow hits the algorithm
     at the right moment.
  6. Archive the used script to scripts/archive/.
  7. Record the topic so it cools down for 30 days.
  8. Top up the queue to TARGET_QUEUE_DEPTH if Claude is available.

Usage:
    ./venv/bin/python daily_pipeline.py                          # full auto, public-immediate
    ./venv/bin/python daily_pipeline.py --topic "..."            # force topic on next gen
    ./venv/bin/python daily_pipeline.py --dry-run                # pick a script, don't render or upload
    ./venv/bin/python daily_pipeline.py --no-upload              # render but skip upload
    ./venv/bin/python daily_pipeline.py --publish-at <ISO-8601>  # explicit scheduled publish (private + scheduled)

Single host ("narrator"). One video per fire. Cron fires 3x/day from daily.yml.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from config.settings import ANTHROPIC_API_KEY
from config.topics import TOPIC_BANK, pick_topic, record_topic
from pipeline.logger import get_logger

logger = get_logger("daily")

NARRATOR = "narrator"

QUEUE_DIR = Path("scripts")
ARCHIVE_DIR = QUEUE_DIR / "archive"
TARGET_QUEUE_DEPTH = 5


def _queued_scripts() -> list[Path]:
    QUEUE_DIR.mkdir(exist_ok=True)
    return sorted(p for p in QUEUE_DIR.glob("*.json") if p.is_file())


def _generate_and_save(topic: str) -> Path:
    """Call Claude to write a horror script for `topic`; save to scripts/."""
    from pipeline import script_generator
    script = script_generator.generate(character=NARRATOR, topic=topic)
    QUEUE_DIR.mkdir(exist_ok=True)
    path = QUEUE_DIR / f"{script['video_id']}.json"
    path.write_text(json.dumps(script, indent=2))
    logger.info(f"  generated: {path.name}")
    return path


def _topic_already_queued(topic: str, queued: list[Path]) -> bool:
    """True if this exact topic is already sitting in the queue."""
    for p in queued:
        try:
            data = json.loads(p.read_text())
        except Exception:
            continue
        if data.get("topic", "").startswith(topic):
            return True
    return False


def _backfill_queue() -> None:
    """If queue depth < TARGET_QUEUE_DEPTH, generate enough to fill it.
    No-op without ANTHROPIC_API_KEY (JSON-only mode)."""
    if not ANTHROPIC_API_KEY:
        logger.info("  backfill: ANTHROPIC_API_KEY not set, skipping (JSON-only mode)")
        return

    queued = _queued_scripts()
    needed = TARGET_QUEUE_DEPTH - len(queued)
    if needed <= 0:
        logger.info(f"  backfill: queue depth {len(queued)} >= target {TARGET_QUEUE_DEPTH}")
        return

    logger.info(f"  backfill: queue has {len(queued)}, generating {needed} more")
    for _ in range(needed):
        try:
            topic = pick_topic(NARRATOR)
        except RuntimeError:
            logger.warning("  backfill: ran out of fresh topics — extend TOPIC_BANK")
            break
        if _topic_already_queued(topic, _queued_scripts()):
            continue
        _generate_and_save(topic)


def _archive(script_path: Path) -> Path:
    ARCHIVE_DIR.mkdir(parents=True, exist_ok=True)
    target = ARCHIVE_DIR / script_path.name
    script_path.rename(target)
    logger.info(f"  archived: {target}")
    return target


def main(
    topic: str | None,
    dry_run: bool,
    no_upload: bool,
    publish_at: str | None,
) -> None:
    queue = _queued_scripts()
    if queue:
        script_path = queue[0]
        script = json.loads(script_path.read_text())
        logger.info(
            f"queue has {len(queue)}, using {script_path.name} "
            f"({len(script.get('scenes', []))} scenes)"
        )
    else:
        if not ANTHROPIC_API_KEY:
            raise SystemExit(
                "Queue is empty (scripts/*.json) and ANTHROPIC_API_KEY is not set. "
                "Drop a hand-written script in scripts/ or set the API key."
            )
        chosen_topic = topic or pick_topic(NARRATOR)
        logger.info(f"queue empty; generating script for topic: {chosen_topic!r}")
        script_path = _generate_and_save(chosen_topic)
        script = json.loads(script_path.read_text())

    chosen_topic = script.get("topic", "")

    if dry_run:
        logger.info("  --dry-run set; stopping after script selection")
        return

    # Sprint mode: publish PUBLIC IMMEDIATELY by default. Each daily.yml cron
    # fire is timed to a target audience peak (US 03:00 UTC, EU evening 16:00,
    # UK prime 22:00) so the upload-then-publish-now flow hits the algorithm
    # window without burning a private-then-scheduled buffer.
    # Override with --publish-at to use the old "private + scheduled" path.
    if publish_at:
        privacy = "private"
        logger.info(f"  publish: scheduled (publishAt={publish_at})")
    else:
        privacy = "public"
        logger.info(f"  publish: PUBLIC immediately (sprint mode)")

    from make_video import main as render_main
    render_main(
        script_path=script_path,
        upload=not no_upload,
        privacy=privacy,
        made_for_kids=False,
        publish_at=publish_at,
    )

    if not no_upload:
        _archive(script_path)
        record_topic(NARRATOR, chosen_topic)
        logger.info(f"  topic recorded: {chosen_topic}")
    else:
        logger.info("  --no-upload: leaving script in queue, not recording topic")

    _backfill_queue()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--topic", default=None,
                        help="Force a topic for the next Claude-generated script "
                             "(only used when queue is empty).")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--no-upload", action="store_true")
    parser.add_argument("--publish-at", default=None,
                        help="Override scheduled publish time (RFC-3339).")
    args = parser.parse_args()
    main(
        topic=args.topic,
        dry_run=args.dry_run,
        no_upload=args.no_upload,
        publish_at=args.publish_at,
    )
