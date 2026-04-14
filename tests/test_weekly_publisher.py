"""Unit and scenario tests for the weekly publisher.

These tests do NOT hit OpenAI, YouTube, or GitHub. They mock all external
I/O so the CI can verify the dedup logic and error paths in <2 seconds.

Critical guarantees under test:
    1. Already-processed videos are NEVER reprocessed.
    2. A new livestream fires exactly one blog generation.
    3. If no new livestreams, zero LLM calls and zero commits.
    4. --limit caps the number of videos processed per run.
    5. Successful publishes are persisted IMMEDIATELY (crash safety).
    6. --dry-run never modifies processed.json.
    7. A failing publish does NOT mark the video as processed (will retry next week).
    8. A corrupted processed.json is recovered gracefully.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "src"))
sys.path.insert(0, str(PROJECT_ROOT / "scripts"))

# Prevent actual .env loading / env var leakage during tests
os.environ["OPENAI_API_KEY"] = "test-key"


@pytest.fixture
def tmp_processed(tmp_path, monkeypatch):
    """Fixture: isolate processed.json to a tmp path for each test."""
    processed_file = tmp_path / "processed.json"
    log_dir = tmp_path / "logs"
    log_dir.mkdir()

    # Patch the module-level paths before import
    import scripts.weekly_publisher as wp
    monkeypatch.setattr(wp, "PROCESSED_PATH", processed_file)
    monkeypatch.setattr(wp, "LOG_PATH", log_dir / "test.log")
    return processed_file


@pytest.fixture
def mock_livestreams():
    """Three sample livestreams."""
    return [
        {"video_id": "abc123", "title": "Video A", "url": "https://youtube.com/watch?v=abc123"},
        {"video_id": "def456", "title": "Video B", "url": "https://youtube.com/watch?v=def456"},
        {"video_id": "ghi789", "title": "Video C", "url": "https://youtube.com/watch?v=ghi789"},
    ]


# ─── load_processed / save_processed ────────────────────────────────

class TestProcessedIO:
    def test_load_empty_file(self, tmp_processed):
        from scripts.weekly_publisher import load_processed
        result = load_processed()
        assert result == {"processed": [], "last_run": None}

    def test_load_valid_file(self, tmp_processed):
        tmp_processed.parent.mkdir(parents=True, exist_ok=True)
        tmp_processed.write_text(json.dumps({
            "processed": ["vid1", "vid2"],
            "last_run": "2026-04-14T00:00:00",
        }))
        from scripts.weekly_publisher import load_processed
        result = load_processed()
        assert set(result["processed"]) == {"vid1", "vid2"}

    def test_load_corrupt_file_recovers(self, tmp_processed):
        tmp_processed.parent.mkdir(parents=True, exist_ok=True)
        tmp_processed.write_text("not valid json {[")
        from scripts.weekly_publisher import load_processed
        result = load_processed()
        assert result == {"processed": [], "last_run": None}

    def test_save_and_reload(self, tmp_processed):
        from scripts.weekly_publisher import save_processed, load_processed
        save_processed({"processed": ["vid1"], "last_run": "2026-04-14"})
        result = load_processed()
        assert result["processed"] == ["vid1"]


# ─── Core dedup behavior ────────────────────────────────────────────

class TestDedupScenarios:
    """These are the most important tests - they verify videos never repeat."""

    def _run(self, mock_livestreams, processed_ids=None, limit=3, dry_run=False):
        """Helper: run main() with mocked IO, return the final state."""
        from scripts import weekly_publisher as wp

        fetched_ids = []  # Track which videos the crew was asked to process

        def mock_process_livestream(livestream, logger, dry_run=False):
            fetched_ids.append(livestream["video_id"])
            return True, f"https://example.com/post-{livestream['video_id']}.html"

        # Pre-populate processed.json if needed
        if processed_ids:
            wp.save_processed({"processed": list(processed_ids), "last_run": None})

        with patch.object(wp, "fetch_hedera_livestreams", return_value=(mock_livestreams, None)), \
             patch.object(wp, "process_livestream", side_effect=mock_process_livestream), \
             patch.object(wp, "send_telegram_notification"), \
             patch.object(sys, "argv", ["weekly_publisher.py", "--limit", str(limit)] +
                          (["--dry-run"] if dry_run else [])):
            wp.main()

        final_state = wp.load_processed()
        return fetched_ids, final_state

    def test_no_new_livestreams_does_nothing(self, tmp_processed, mock_livestreams):
        """If all videos are already processed, nothing is fetched or published."""
        all_ids = [ls["video_id"] for ls in mock_livestreams]
        fetched, state = self._run(mock_livestreams, processed_ids=all_ids)
        assert fetched == []  # No videos were processed
        assert set(state["processed"]) == set(all_ids)  # State unchanged

    def test_one_new_livestream_publishes_once(self, tmp_processed, mock_livestreams):
        """Only the unprocessed video is handled."""
        fetched, state = self._run(
            mock_livestreams,
            processed_ids=["abc123", "def456"],  # C is new
        )
        assert fetched == ["ghi789"]
        assert set(state["processed"]) == {"abc123", "def456", "ghi789"}

    def test_all_new_with_limit(self, tmp_processed, mock_livestreams):
        """With 3 new videos and limit=2, only 2 are processed."""
        fetched, state = self._run(mock_livestreams, limit=2)
        assert len(fetched) == 2
        assert fetched == ["abc123", "def456"]  # First two in order
        # Only 2 should be in processed list
        assert set(state["processed"]) == {"abc123", "def456"}

    def test_subsequent_run_picks_up_remaining(self, tmp_processed, mock_livestreams):
        """After processing 2 with limit, next run picks up the third."""
        self._run(mock_livestreams, limit=2)  # First run: processes abc, def
        fetched, state = self._run(mock_livestreams, limit=2)  # Second run
        assert fetched == ["ghi789"]  # Only C remains
        assert set(state["processed"]) == {"abc123", "def456", "ghi789"}

    def test_no_videos_repeat_across_runs(self, tmp_processed, mock_livestreams):
        """Run the publisher 3 times - no video should ever be processed twice."""
        all_fetched = []
        for _ in range(3):
            fetched, _ = self._run(mock_livestreams)
            all_fetched.extend(fetched)
        # Across all runs, each video id appears exactly once
        assert len(all_fetched) == len(set(all_fetched)) == 3

    def test_dry_run_does_not_mutate_state(self, tmp_processed, mock_livestreams):
        """--dry-run never persists processed videos."""
        fetched, state = self._run(mock_livestreams, dry_run=True)
        assert fetched == ["abc123", "def456", "ghi789"]  # All were "processed" in-memory
        assert state["processed"] == []  # But nothing persisted

    def test_failure_does_not_mark_as_processed(self, tmp_processed, mock_livestreams):
        """If process_livestream returns False, the video stays unprocessed."""
        from scripts import weekly_publisher as wp

        def flaky_process(livestream, logger, dry_run=False):
            if livestream["video_id"] == "def456":
                return False, "Simulated transcript error"
            return True, f"https://example.com/{livestream['video_id']}.html"

        with patch.object(wp, "fetch_hedera_livestreams", return_value=(mock_livestreams, None)), \
             patch.object(wp, "process_livestream", side_effect=flaky_process), \
             patch.object(wp, "send_telegram_notification"), \
             patch.object(sys, "argv", ["weekly_publisher.py", "--limit", "3"]):
            wp.main()

        state = wp.load_processed()
        # abc and ghi succeeded, def failed and is NOT marked
        assert set(state["processed"]) == {"abc123", "ghi789"}

    def test_failed_videos_retry_next_week(self, tmp_processed, mock_livestreams):
        """A failure on week 1 should cause the failed video to be retried on week 2."""
        from scripts import weekly_publisher as wp

        call_count = {"count": 0}

        def fails_once(livestream, logger, dry_run=False):
            if livestream["video_id"] == "def456":
                call_count["count"] += 1
                if call_count["count"] == 1:
                    return False, "Week 1 failure"
                return True, "https://example.com/def456.html"
            return True, f"https://example.com/{livestream['video_id']}.html"

        with patch.object(wp, "fetch_hedera_livestreams", return_value=(mock_livestreams, None)), \
             patch.object(wp, "process_livestream", side_effect=fails_once), \
             patch.object(wp, "send_telegram_notification"), \
             patch.object(sys, "argv", ["weekly_publisher.py", "--limit", "3"]):
            # Week 1
            wp.main()
            state = wp.load_processed()
            assert "def456" not in state["processed"]  # Not yet

            # Week 2 - should retry def456
            wp.main()
            state = wp.load_processed()
            assert "def456" in state["processed"]  # Now processed

    def test_limit_one_processes_only_one(self, tmp_processed, mock_livestreams):
        """--limit 1 should process exactly one video even if many are new."""
        fetched, state = self._run(mock_livestreams, limit=1)
        assert len(fetched) == 1
        assert len(state["processed"]) == 1

    def test_multiple_new_livestreams_all_published_uniquely(self, tmp_processed):
        """Core guarantee: if the week brings multiple new livestreams, ALL are
        published and NONE are duplicated."""
        # 5 fresh livestreams this week
        week_videos = [
            {"video_id": f"week1-vid{i}", "title": f"Livestream {i}", "url": f"https://yt/{i}"}
            for i in range(5)
        ]

        fetched, state = self._run(week_videos, limit=10)

        # All 5 were processed
        assert len(fetched) == 5
        # Each video_id appears exactly once in fetched list
        assert len(fetched) == len(set(fetched))
        # All 5 are in the persisted state
        assert set(state["processed"]) == {f"week1-vid{i}" for i in range(5)}

    def test_mixed_new_and_already_processed(self, tmp_processed):
        """Mix: 2 already-processed + 3 new. Only the 3 new should be published."""
        all_videos = [
            {"video_id": "old-1", "title": "Old 1", "url": "https://yt/old-1"},
            {"video_id": "new-1", "title": "New 1", "url": "https://yt/new-1"},
            {"video_id": "old-2", "title": "Old 2", "url": "https://yt/old-2"},
            {"video_id": "new-2", "title": "New 2", "url": "https://yt/new-2"},
            {"video_id": "new-3", "title": "New 3", "url": "https://yt/new-3"},
        ]
        fetched, state = self._run(
            all_videos,
            processed_ids=["old-1", "old-2"],
            limit=10,
        )
        assert set(fetched) == {"new-1", "new-2", "new-3"}
        assert "old-1" not in fetched
        assert "old-2" not in fetched
        # Final state has all 5 (old + new)
        assert set(state["processed"]) == {"old-1", "old-2", "new-1", "new-2", "new-3"}

    def test_crash_mid_loop_preserves_earlier_successes(self, tmp_processed):
        """If processing crashes on video 3, videos 1 and 2 must still be saved."""
        from scripts import weekly_publisher as wp

        videos = [
            {"video_id": "a", "title": "A", "url": "https://yt/a"},
            {"video_id": "b", "title": "B", "url": "https://yt/b"},
            {"video_id": "c", "title": "C", "url": "https://yt/c"},
            {"video_id": "d", "title": "D", "url": "https://yt/d"},
        ]

        call_count = {"n": 0}

        def crash_on_third(livestream, logger, dry_run=False):
            call_count["n"] += 1
            if call_count["n"] == 3:
                raise RuntimeError("simulated crash on video C")
            return True, f"https://example.com/{livestream['video_id']}.html"

        with patch.object(wp, "fetch_hedera_livestreams", return_value=(videos, None)), \
             patch.object(wp, "process_livestream", side_effect=crash_on_third), \
             patch.object(wp, "send_telegram_notification"), \
             patch.object(sys, "argv", ["weekly_publisher.py", "--limit", "10"]):
            with pytest.raises(RuntimeError):
                wp.main()

        # After crash, processed.json should still have A and B (saved after each success)
        state = wp.load_processed()
        assert "a" in state["processed"]
        assert "b" in state["processed"]
        # C was never saved (crashed mid-process)
        assert "c" not in state["processed"]
        assert "d" not in state["processed"]

    def test_rerun_after_crash_picks_up_where_it_left_off(self, tmp_processed):
        """After a crash saving 2 of 4, next run processes the remaining 2."""
        from scripts import weekly_publisher as wp

        videos = [
            {"video_id": "a", "title": "A", "url": "https://yt/a"},
            {"video_id": "b", "title": "B", "url": "https://yt/b"},
            {"video_id": "c", "title": "C", "url": "https://yt/c"},
            {"video_id": "d", "title": "D", "url": "https://yt/d"},
        ]

        # Simulate a previous crash that saved a and b
        wp.save_processed({"processed": ["a", "b"], "last_run": None})

        fetched_now = []
        def track(livestream, logger, dry_run=False):
            fetched_now.append(livestream["video_id"])
            return True, f"https://example.com/{livestream['video_id']}.html"

        with patch.object(wp, "fetch_hedera_livestreams", return_value=(videos, None)), \
             patch.object(wp, "process_livestream", side_effect=track), \
             patch.object(wp, "send_telegram_notification"), \
             patch.object(sys, "argv", ["weekly_publisher.py", "--limit", "10"]):
            wp.main()

        # Only c and d are processed (a, b already done)
        assert set(fetched_now) == {"c", "d"}
        # Final state has all 4
        state = wp.load_processed()
        assert set(state["processed"]) == {"a", "b", "c", "d"}


# ─── process_livestream unit tests ──────────────────────────────────

class TestProcessLivestream:
    def test_transcript_error_returns_failure(self, tmp_processed):
        from scripts import weekly_publisher as wp

        livestream = {"video_id": "abc", "title": "Test", "url": "https://youtube.com/abc"}
        logger = MagicMock()

        with patch.object(wp, "fetch_transcript", return_value=(None, "IP blocked")):
            success, msg = wp.process_livestream(livestream, logger)
        assert success is False
        assert "Transcript error" in msg

    def test_empty_transcript_returns_failure(self, tmp_processed):
        from scripts import weekly_publisher as wp

        livestream = {"video_id": "abc", "title": "Test", "url": "https://youtube.com/abc"}
        logger = MagicMock()

        with patch.object(wp, "fetch_transcript", return_value=([], None)), \
             patch.object(wp, "format_transcript", return_value=""):
            success, msg = wp.process_livestream(livestream, logger)
        assert success is False
        assert "Empty transcript" in msg

    def test_dry_run_skips_crew(self, tmp_processed):
        from scripts import weekly_publisher as wp

        livestream = {"video_id": "abc", "title": "Test", "url": "https://youtube.com/abc"}
        logger = MagicMock()

        with patch.object(wp, "fetch_transcript", return_value=([{"text": "hi"}], None)), \
             patch.object(wp, "format_transcript", return_value="hi there"), \
             patch.object(wp, "ContentBlogCrew") as mock_crew:
            success, msg = wp.process_livestream(livestream, logger, dry_run=True)
        assert success is True
        assert "DRY RUN" in msg
        mock_crew.assert_not_called()  # No crew instantiation in dry-run

    def test_crew_error_returns_failure(self, tmp_processed):
        from scripts import weekly_publisher as wp

        livestream = {"video_id": "abc", "title": "Test", "url": "https://youtube.com/abc"}
        logger = MagicMock()

        with patch.object(wp, "fetch_transcript", return_value=([{"text": "hi"}], None)), \
             patch.object(wp, "format_transcript", return_value="full transcript text"), \
             patch.object(wp, "ContentBlogCrew") as mock_crew:
            mock_crew.return_value.run.side_effect = RuntimeError("crew exploded")
            success, msg = wp.process_livestream(livestream, logger)
        assert success is False
        assert "Crew error" in msg

    def test_empty_blog_returns_failure(self, tmp_processed):
        from scripts import weekly_publisher as wp

        livestream = {"video_id": "abc", "title": "Test", "url": "https://youtube.com/abc"}
        logger = MagicMock()

        with patch.object(wp, "fetch_transcript", return_value=([{"text": "hi"}], None)), \
             patch.object(wp, "format_transcript", return_value="full transcript"), \
             patch.object(wp, "ContentBlogCrew") as mock_crew:
            mock_crew.return_value.run.return_value = {"blog": "", "titles": "", "status": ""}
            success, msg = wp.process_livestream(livestream, logger)
        assert success is False
        assert "empty blog" in msg.lower()

    def test_publish_error_returns_failure(self, tmp_processed):
        from scripts import weekly_publisher as wp

        livestream = {"video_id": "abc", "title": "Test", "url": "https://youtube.com/abc"}
        logger = MagicMock()

        with patch.object(wp, "fetch_transcript", return_value=([{"text": "hi"}], None)), \
             patch.object(wp, "format_transcript", return_value="full transcript"), \
             patch.object(wp, "ContentBlogCrew") as mock_crew, \
             patch.object(wp, "publish_to_github_pages", return_value=("", "git push rejected")):
            mock_crew.return_value.run.return_value = {"blog": "# Title", "titles": "", "status": ""}
            success, msg = wp.process_livestream(livestream, logger)
        assert success is False
        assert "Publish error" in msg

    def test_happy_path_returns_url(self, tmp_processed):
        from scripts import weekly_publisher as wp

        livestream = {"video_id": "abc", "title": "Test", "url": "https://youtube.com/abc"}
        logger = MagicMock()

        with patch.object(wp, "fetch_transcript", return_value=([{"text": "hi"}], None)), \
             patch.object(wp, "format_transcript", return_value="full transcript"), \
             patch.object(wp, "ContentBlogCrew") as mock_crew, \
             patch.object(wp, "publish_to_github_pages",
                          return_value=("https://example.com/post.html", "")):
            mock_crew.return_value.run.return_value = {
                "blog": "# Real blog content",
                "titles": "Title 1",
                "status": "ok",
            }
            success, msg = wp.process_livestream(livestream, logger)
        assert success is True
        assert msg.startswith("https://example.com/")


# ─── Telegram placeholder ───────────────────────────────────────────

class TestTelegramNotification:
    def test_no_credentials_logs_only(self, tmp_processed, monkeypatch):
        from scripts import weekly_publisher as wp
        monkeypatch.delenv("TELEGRAM_BOT_TOKEN", raising=False)
        monkeypatch.delenv("TELEGRAM_CHAT_ID", raising=False)

        logger = MagicMock()
        wp.send_telegram_notification("hello", logger)
        # Should log but not make HTTP call
        logger.info.assert_called_once()
        assert "PLACEHOLDER" in str(logger.info.call_args)

    def test_with_credentials_sends_http(self, tmp_processed, monkeypatch):
        from scripts import weekly_publisher as wp
        monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "fake-token")
        monkeypatch.setenv("TELEGRAM_CHAT_ID", "12345")

        logger = MagicMock()
        with patch("requests.post") as mock_post:
            mock_post.return_value.status_code = 200
            wp.send_telegram_notification("hello", logger)
        mock_post.assert_called_once()
        args, kwargs = mock_post.call_args
        assert "api.telegram.org" in args[0]
        assert kwargs["json"]["chat_id"] == "12345"
        assert kwargs["json"]["text"] == "hello"


# ─── Full main() flow ───────────────────────────────────────────────

class TestMainFlow:
    def test_main_missing_api_key_exits(self, tmp_processed, monkeypatch):
        from scripts import weekly_publisher as wp
        monkeypatch.delenv("OPENAI_API_KEY", raising=False)
        with patch.object(sys, "argv", ["weekly_publisher.py"]), \
             pytest.raises(SystemExit) as exc:
            wp.main()
        assert exc.value.code == 1

    def test_main_fetch_error_exits(self, tmp_processed):
        from scripts import weekly_publisher as wp
        with patch.object(wp, "fetch_hedera_livestreams", return_value=([], "Network down")), \
             patch.object(wp, "send_telegram_notification"), \
             patch.object(sys, "argv", ["weekly_publisher.py"]), \
             pytest.raises(SystemExit):
            wp.main()

    def test_main_sends_empty_notification_when_no_new(self, tmp_processed, mock_livestreams):
        from scripts import weekly_publisher as wp
        # Pre-populate all IDs as already processed
        wp.save_processed({
            "processed": [ls["video_id"] for ls in mock_livestreams],
            "last_run": None,
        })

        with patch.object(wp, "fetch_hedera_livestreams", return_value=(mock_livestreams, None)), \
             patch.object(wp, "send_telegram_notification") as mock_notify, \
             patch.object(wp, "process_livestream") as mock_process, \
             patch.object(sys, "argv", ["weekly_publisher.py"]):
            wp.main()
        mock_process.assert_not_called()  # No processing happened
        mock_notify.assert_called_once()  # But notification was sent
        assert "no new" in str(mock_notify.call_args).lower()
