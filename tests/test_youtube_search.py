"""Tests for the YouTube livestream fetcher with dedup."""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import patch

import pytest

PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "src"))


def _mock_video(video_id: str, title: str) -> dict:
    """Build a fake scrapetube video record."""
    return {
        "videoId": video_id,
        "title": {"runs": [{"text": title}]},
    }


class TestLivestreamDedup:
    def test_dedupes_mobile_and_desktop_versions(self):
        """Hedera uploads each livestream twice - with and without emoji.
        Our fetcher must dedupe by cleaned title."""
        from rag.youtube_search import fetch_hedera_livestreams

        fake_videos = [
            _mock_video("vid1", "Fork-testing Hedera Smart Contracts 📱"),
            _mock_video("vid2", "Fork-testing Hedera Smart Contracts"),
            _mock_video("vid3", "Building real-world utility 📱"),
            _mock_video("vid4", "Building real-world utility"),
            _mock_video("vid5", "Deploying Smart Contracts"),
        ]

        with patch("scrapetube.get_channel", return_value=iter(fake_videos)):
            results, error = fetch_hedera_livestreams(limit=10)

        assert error is None
        assert len(results) == 3  # Duplicates removed
        titles = [r["title"] for r in results]
        # The mobile version (📱) wins because it comes first
        assert any("Fork-testing" in t for t in titles)
        assert any("real-world utility" in t for t in titles)
        assert any("Deploying" in t for t in titles)

    def test_respects_limit(self):
        from rag.youtube_search import fetch_hedera_livestreams
        fake_videos = [_mock_video(f"vid{i}", f"Unique Title {i}") for i in range(20)]

        with patch("scrapetube.get_channel", return_value=iter(fake_videos)):
            results, error = fetch_hedera_livestreams(limit=5)

        assert error is None
        assert len(results) == 5

    def test_empty_result_returns_error(self):
        from rag.youtube_search import fetch_hedera_livestreams
        with patch("scrapetube.get_channel", return_value=iter([])):
            results, error = fetch_hedera_livestreams(limit=10)
        assert results == []
        assert "No livestreams" in error

    def test_scrapetube_error_returns_error(self):
        from rag.youtube_search import fetch_hedera_livestreams
        with patch("scrapetube.get_channel", side_effect=Exception("network error")):
            results, error = fetch_hedera_livestreams(limit=10)
        assert results == []
        assert "network error" in error

    def test_returns_urls(self):
        from rag.youtube_search import fetch_hedera_livestreams
        fake_videos = [_mock_video("abc123XYZ_11", "Title")]
        with patch("scrapetube.get_channel", return_value=iter(fake_videos)):
            results, _ = fetch_hedera_livestreams(limit=1)
        assert results[0]["url"] == "https://www.youtube.com/watch?v=abc123XYZ_11"
