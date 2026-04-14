#!/usr/bin/env python3
"""Weekly automated Hedera livestream publisher.

Runs every Sunday at 8 PM Colombia time (via launchd):
1. Fetches the latest 10 Hedera livestreams
2. Checks processed.json to find unprocessed videos
3. For each new livestream: extracts transcript, runs ContentBlogCrew, publishes to GitHub Pages
4. Sends a Telegram notification (when configured)
5. Updates processed.json

Usage:
    python scripts/weekly_publisher.py                 # Normal run
    python scripts/weekly_publisher.py --dry-run       # No actual publishing
    python scripts/weekly_publisher.py --limit 1       # Only process 1 new video
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys
from datetime import datetime
from pathlib import Path

# Ensure src is on the path
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from dotenv import load_dotenv

load_dotenv(PROJECT_ROOT / ".env")

from rag.hedera_blog import extract_video_id, fetch_transcript, format_transcript
from rag.publisher import publish_to_github_pages
from rag.youtube_search import fetch_hedera_livestreams
from crew.crew import ContentBlogCrew

PROCESSED_PATH = PROJECT_ROOT / "scripts" / "processed.json"
LOG_PATH = PROJECT_ROOT / "logs" / "weekly_publisher.log"


def setup_logging() -> logging.Logger:
    LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
        handlers=[
            logging.FileHandler(LOG_PATH),
            logging.StreamHandler(sys.stdout),
        ],
    )
    return logging.getLogger("weekly_publisher")


def load_processed() -> dict:
    """Load the set of already-processed video IDs."""
    if PROCESSED_PATH.exists():
        try:
            return json.loads(PROCESSED_PATH.read_text())
        except Exception:
            return {"processed": [], "last_run": None}
    return {"processed": [], "last_run": None}


def save_processed(data: dict) -> None:
    """Persist the processed video IDs."""
    PROCESSED_PATH.parent.mkdir(parents=True, exist_ok=True)
    PROCESSED_PATH.write_text(json.dumps(data, indent=2))


def send_telegram_notification(message: str, logger: logging.Logger) -> None:
    """Send a message to Telegram. Placeholder until configured.

    To enable: set TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID in .env
    """
    token = os.getenv("TELEGRAM_BOT_TOKEN")
    chat_id = os.getenv("TELEGRAM_CHAT_ID")

    if not token or not chat_id:
        logger.info("[Telegram PLACEHOLDER] %s", message)
        return

    try:
        import requests

        resp = requests.post(
            f"https://api.telegram.org/bot{token}/sendMessage",
            json={
                "chat_id": chat_id,
                "text": message,
                "parse_mode": "Markdown",
                "disable_web_page_preview": False,
            },
            timeout=10,
        )
        if resp.status_code == 200:
            logger.info("Telegram notification sent")
        else:
            logger.warning("Telegram notification failed: %s", resp.text[:200])
    except Exception as exc:
        logger.warning("Telegram error: %s", exc)


def process_livestream(
    livestream: dict,
    logger: logging.Logger,
    dry_run: bool = False,
) -> tuple[bool, str]:
    """Process a single livestream: transcript -> crew -> publish.

    Returns:
        tuple: (success, url_or_error_message)
    """
    video_id = livestream["video_id"]
    title = livestream["title"]
    url = livestream["url"]

    logger.info("Processing: %s (%s)", title, video_id)

    # Extract transcript
    transcript, error = fetch_transcript(video_id)
    if error:
        return False, f"Transcript error: {error}"

    transcript_text = format_transcript(transcript, include_timestamps=False)
    if not transcript_text:
        return False, "Empty transcript"

    logger.info("Transcript: %d chars", len(transcript_text))

    if dry_run:
        return True, "[DRY RUN] would have published"

    # Run the multi-agent crew
    try:
        crew = ContentBlogCrew(include_docs=True, include_compliance=True)
        result = crew.run(
            transcript_text=transcript_text,
            audience="Web3 developers and Hedera builders",
            focus="Hedera ecosystem, HTS, HCS, smart contracts, tooling",
            reference_links="",
            titles_count=5,
            output_format="Markdown",
        )
    except Exception as exc:
        return False, f"Crew error: {exc}"

    blog = result.get("blog", "")
    if not blog:
        return False, "Crew produced empty blog"

    logger.info("Blog generated: %d chars", len(blog))

    # Publish to GitHub Pages
    try:
        live_url, pub_error = publish_to_github_pages(blog)
        if pub_error:
            return False, f"Publish error: {pub_error}"
        return True, live_url
    except Exception as exc:
        return False, f"Publish exception: {exc}"


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true", help="No actual publishing")
    parser.add_argument("--limit", type=int, default=3, help="Max new videos to process")
    args = parser.parse_args()

    logger = setup_logging()
    logger.info("=" * 60)
    logger.info("Weekly publisher starting | dry_run=%s limit=%d", args.dry_run, args.limit)

    if not os.getenv("OPENAI_API_KEY"):
        logger.error("OPENAI_API_KEY not set")
        send_telegram_notification("Weekly publisher FAILED: OPENAI_API_KEY missing", logger)
        sys.exit(1)

    # Default to gpt-5-mini to control costs
    os.environ.setdefault("OPENAI_MODEL", "gpt-5-mini")

    # 1. Fetch latest livestreams
    logger.info("Fetching latest Hedera livestreams...")
    livestreams, error = fetch_hedera_livestreams(limit=10)
    if error:
        logger.error("Fetch error: %s", error)
        send_telegram_notification(f"Weekly publisher FAILED: {error}", logger)
        sys.exit(1)
    logger.info("Fetched %d livestreams", len(livestreams))

    # 2. Load processed history
    data = load_processed()
    processed_ids = set(data.get("processed", []))
    logger.info("Already processed: %d videos", len(processed_ids))

    # 3. Find new livestreams
    new_livestreams = [ls for ls in livestreams if ls["video_id"] not in processed_ids]
    logger.info("New livestreams to process: %d", len(new_livestreams))

    if not new_livestreams:
        logger.info("No new livestreams this week")
        data["last_run"] = datetime.now().isoformat()
        data["last_status"] = "no new livestreams"
        save_processed(data)
        send_telegram_notification("Weekly check: no new Hedera livestreams", logger)
        return

    # 4. Process up to --limit new livestreams
    processed_this_run = []
    for livestream in new_livestreams[: args.limit]:
        success, result_msg = process_livestream(livestream, logger, dry_run=args.dry_run)
        if success:
            logger.info("PUBLISHED: %s -> %s", livestream["title"], result_msg)
            processed_this_run.append({
                "video_id": livestream["video_id"],
                "title": livestream["title"],
                "url": result_msg,
                "published_at": datetime.now().isoformat(),
            })
            # Save IMMEDIATELY after each success to prevent duplicates
            # if the script is interrupted mid-loop.
            if not args.dry_run:
                processed_ids.add(livestream["video_id"])
                data["processed"] = list(processed_ids)
                data["last_run"] = datetime.now().isoformat()
                data["last_run_results"] = processed_this_run
                save_processed(data)
        else:
            logger.error("FAILED: %s -> %s", livestream["title"], result_msg)

    # 5. Final save (in case no successes, still record last_run)
    if not args.dry_run and not processed_this_run:
        data["last_run"] = datetime.now().isoformat()
        data["last_status"] = "all candidates failed"
        save_processed(data)

    # 6. Notify
    if processed_this_run:
        msg_lines = ["*Weekly Hedera Blog Published*\n"]
        for item in processed_this_run:
            msg_lines.append(f"- [{item['title']}]({item['url']})")
        send_telegram_notification("\n".join(msg_lines), logger)
    else:
        send_telegram_notification("Weekly run: processing failed for all candidates", logger)

    logger.info("Weekly publisher done. Processed %d videos.", len(processed_this_run))


if __name__ == "__main__":
    main()
