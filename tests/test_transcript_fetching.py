"""Tests for fetch_transcript with retry/backoff and cookies support.

All YouTube API calls are mocked - these tests run in milliseconds with zero
network access.

Guarantees under test:
    1. A transient IP-block error triggers retries with exponential backoff.
    2. After max_retries, the final error surfaces with a helpful hint.
    3. Non-IP errors (e.g. "No transcript") don't retry (save time/money).
    4. cookies_path argument loads cookies into the requests.Session.
    5. env var YOUTUBE_COOKIES_PATH is used as fallback.
    6. _is_ip_blocked_error correctly classifies various error strings.
    7. Happy path: a valid transcript returns on first try.
    8. time.sleep is mocked so retry tests complete instantly.
"""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "src"))


# ─── _is_ip_blocked_error ───────────────────────────────────────────

class TestIsIpBlockedError:
    def test_detects_request_blocked(self):
        from rag.hedera_blog import _is_ip_blocked_error
        assert _is_ip_blocked_error("RequestBlocked: YouTube is blocking you")
        assert _is_ip_blocked_error("IpBlocked: too many requests")
        assert _is_ip_blocked_error("YouTube is blocking requests from your IP")

    def test_detects_429(self):
        from rag.hedera_blog import _is_ip_blocked_error
        assert _is_ip_blocked_error("HTTP 429 Too Many Requests")

    def test_detects_too_many_requests(self):
        from rag.hedera_blog import _is_ip_blocked_error
        assert _is_ip_blocked_error("error: Too Many Requests")

    def test_non_ip_errors_not_matched(self):
        from rag.hedera_blog import _is_ip_blocked_error
        assert not _is_ip_blocked_error("No transcripts found")
        assert not _is_ip_blocked_error("Video does not exist")
        assert not _is_ip_blocked_error("Network timeout")


# ─── _build_transcript_session ──────────────────────────────────────

class TestBuildSession:
    def test_session_has_browser_user_agent(self):
        from rag.hedera_blog import _build_transcript_session
        session = _build_transcript_session(None)
        ua = session.headers.get("User-Agent", "")
        assert "Mozilla" in ua
        assert "Chrome" in ua

    def test_no_cookies_when_path_none(self):
        from rag.hedera_blog import _build_transcript_session
        session = _build_transcript_session(None)
        # Empty cookie jar
        assert len(session.cookies) == 0

    def test_nonexistent_cookies_path_does_not_fail(self, tmp_path):
        from rag.hedera_blog import _build_transcript_session
        # Should return a session even if file is missing (graceful)
        session = _build_transcript_session(str(tmp_path / "missing.txt"))
        assert session is not None
        assert len(session.cookies) == 0

    def test_loads_valid_netscape_cookies(self, tmp_path):
        """Load a minimal valid Netscape cookies.txt."""
        from rag.hedera_blog import _build_transcript_session
        cookies_file = tmp_path / "cookies.txt"
        # Minimal Netscape format: domain, flag, path, secure, expires, name, value
        cookies_file.write_text(
            "# Netscape HTTP Cookie File\n"
            ".youtube.com\tTRUE\t/\tFALSE\t9999999999\ttest_cookie\ttest_value\n"
        )
        session = _build_transcript_session(str(cookies_file))
        # The cookie should be loaded
        cookie_names = [c.name for c in session.cookies]
        assert "test_cookie" in cookie_names

    def test_corrupt_cookies_file_does_not_fail(self, tmp_path):
        from rag.hedera_blog import _build_transcript_session
        cookies_file = tmp_path / "cookies.txt"
        cookies_file.write_text("not a valid cookies file format")
        # Should not raise - just fall back to empty cookies
        session = _build_transcript_session(str(cookies_file))
        assert session is not None


# ─── fetch_transcript happy path ────────────────────────────────────

class TestFetchTranscriptHappyPath:
    def test_returns_transcript_on_success(self):
        from rag.hedera_blog import fetch_transcript

        mock_transcript_list = MagicMock()
        mock_transcript = MagicMock()
        mock_transcript.fetch.return_value = [{"text": "hello", "start": 0.0}]
        mock_transcript_list.find_manually_created_transcript.return_value = mock_transcript

        mock_api = MagicMock()
        mock_api.list.return_value = mock_transcript_list

        with patch("rag.hedera_blog.YouTubeTranscriptApi", return_value=mock_api):
            result, error = fetch_transcript("abc123XYZ_01")

        assert error is None
        assert result == [{"text": "hello", "start": 0.0}]

    def test_no_english_transcript_returns_error(self):
        from rag.hedera_blog import fetch_transcript

        mock_transcript_list = MagicMock()
        mock_transcript_list.find_manually_created_transcript.side_effect = Exception("no manual")
        mock_transcript_list.find_generated_transcript.side_effect = Exception("no generated")
        mock_transcript_list.find_transcript.side_effect = Exception("no fallback")

        mock_api = MagicMock()
        mock_api.list.return_value = mock_transcript_list

        with patch("rag.hedera_blog.YouTubeTranscriptApi", return_value=mock_api):
            result, error = fetch_transcript("abc123XYZ_01")

        assert result is None
        assert "No English transcript" in error


# ─── Retry and backoff ──────────────────────────────────────────────

class TestRetryBackoff:
    def test_ip_block_triggers_retries(self):
        """Three transient IP-block errors -> 3 retries -> final error with hint."""
        from rag.hedera_blog import fetch_transcript

        mock_api = MagicMock()
        mock_api.list.side_effect = Exception("RequestBlocked: YouTube is blocking requests from your IP")

        with patch("rag.hedera_blog.YouTubeTranscriptApi", return_value=mock_api), \
             patch("time.sleep") as mock_sleep:
            result, error = fetch_transcript("abc123XYZ_01", max_retries=3)

        assert result is None
        assert "YouTube IP-blocked" in error
        assert "cookies.txt" in error  # Helpful hint in message
        # Called list() 4 times total (initial + 3 retries)
        assert mock_api.list.call_count == 4
        # Slept 3 times between retries
        assert mock_sleep.call_count == 3

    def test_backoff_durations_are_exponential(self):
        """Wait durations should be 4s, 16s, 64s (4 * 4^attempt)."""
        from rag.hedera_blog import fetch_transcript

        mock_api = MagicMock()
        mock_api.list.side_effect = Exception("IpBlocked")

        with patch("rag.hedera_blog.YouTubeTranscriptApi", return_value=mock_api), \
             patch("time.sleep") as mock_sleep:
            fetch_transcript("abc123XYZ_01", max_retries=3)

        # First arg of each sleep call
        sleep_durations = [call.args[0] for call in mock_sleep.call_args_list]
        assert sleep_durations == [4, 16, 64]

    def test_non_ip_error_does_not_retry(self):
        """A non-IP error (e.g. video not found) should NOT trigger retries."""
        from rag.hedera_blog import fetch_transcript

        mock_api = MagicMock()
        mock_api.list.side_effect = Exception("Video unavailable")

        with patch("rag.hedera_blog.YouTubeTranscriptApi", return_value=mock_api), \
             patch("time.sleep") as mock_sleep:
            result, error = fetch_transcript("abc123XYZ_01", max_retries=3)

        assert result is None
        assert "Unable to access" in error
        # Only called once - no retries
        assert mock_api.list.call_count == 1
        mock_sleep.assert_not_called()

    def test_retry_succeeds_on_second_attempt(self):
        """If the first call fails with IP block but second succeeds, return the transcript."""
        from rag.hedera_blog import fetch_transcript

        mock_transcript = MagicMock()
        mock_transcript.fetch.return_value = [{"text": "ok", "start": 0}]
        mock_list = MagicMock()
        mock_list.find_manually_created_transcript.return_value = mock_transcript

        mock_api = MagicMock()
        # First call: IP block, second call: success
        mock_api.list.side_effect = [
            Exception("IpBlocked"),
            mock_list,
        ]

        with patch("rag.hedera_blog.YouTubeTranscriptApi", return_value=mock_api), \
             patch("time.sleep"):
            result, error = fetch_transcript("abc123XYZ_01", max_retries=3)

        assert error is None
        assert result == [{"text": "ok", "start": 0}]
        assert mock_api.list.call_count == 2


# ─── Cookies integration ────────────────────────────────────────────

class TestCookiesIntegration:
    def test_explicit_cookies_path_is_used(self, tmp_path):
        """Passing cookies_path explicitly should load cookies into the session."""
        from rag.hedera_blog import fetch_transcript

        cookies_file = tmp_path / "cookies.txt"
        cookies_file.write_text(
            "# Netscape HTTP Cookie File\n"
            ".youtube.com\tTRUE\t/\tFALSE\t9999999999\tSID\tfake-session\n"
        )

        captured_session = {}

        def capture_api(http_client=None, **kwargs):
            captured_session["session"] = http_client
            mock_api = MagicMock()
            mock_list = MagicMock()
            mock_t = MagicMock()
            mock_t.fetch.return_value = [{"text": "ok", "start": 0}]
            mock_list.find_manually_created_transcript.return_value = mock_t
            mock_api.list.return_value = mock_list
            return mock_api

        with patch("rag.hedera_blog.YouTubeTranscriptApi", side_effect=capture_api):
            fetch_transcript("abc123XYZ_01", cookies_path=str(cookies_file))

        session = captured_session["session"]
        assert session is not None
        cookie_names = [c.name for c in session.cookies]
        assert "SID" in cookie_names

    def test_env_var_cookies_path_fallback(self, tmp_path, monkeypatch):
        """If cookies_path not passed, use YOUTUBE_COOKIES_PATH env var."""
        from rag.hedera_blog import fetch_transcript

        cookies_file = tmp_path / "env_cookies.txt"
        cookies_file.write_text(
            "# Netscape HTTP Cookie File\n"
            ".youtube.com\tTRUE\t/\tFALSE\t9999999999\tENV_SID\tfrom-env\n"
        )
        monkeypatch.setenv("YOUTUBE_COOKIES_PATH", str(cookies_file))

        captured_session = {}

        def capture_api(http_client=None, **kwargs):
            captured_session["session"] = http_client
            mock_api = MagicMock()
            mock_list = MagicMock()
            mock_t = MagicMock()
            mock_t.fetch.return_value = [{"text": "ok", "start": 0}]
            mock_list.find_manually_created_transcript.return_value = mock_t
            mock_api.list.return_value = mock_list
            return mock_api

        with patch("rag.hedera_blog.YouTubeTranscriptApi", side_effect=capture_api):
            # Don't pass cookies_path - should pick up env var
            fetch_transcript("abc123XYZ_01")

        session = captured_session["session"]
        cookie_names = [c.name for c in session.cookies]
        assert "ENV_SID" in cookie_names

    def test_no_cookies_still_works(self):
        """fetch_transcript works without any cookies configured (anonymous)."""
        from rag.hedera_blog import fetch_transcript

        mock_api = MagicMock()
        mock_list = MagicMock()
        mock_t = MagicMock()
        mock_t.fetch.return_value = [{"text": "anon ok"}]
        mock_list.find_manually_created_transcript.return_value = mock_t
        mock_api.list.return_value = mock_list

        with patch("rag.hedera_blog.YouTubeTranscriptApi", return_value=mock_api):
            result, error = fetch_transcript("abc123XYZ_01")

        assert error is None
        assert result == [{"text": "anon ok"}]
