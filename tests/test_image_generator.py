"""Tests for the image generator module.

These tests NEVER hit the real Gemini API - all HTTP calls are mocked.
This guarantees the test suite costs $0 and runs in milliseconds.

Critical guarantees under test:
    1. is_enabled() respects ENABLE_IMAGE_GEN env var.
    2. is_enabled() requires GEMINI_API_KEY.
    3. Cache hit: existing image is reused without API call (saves money).
    4. Cache miss: API is called once, image saved.
    5. API failure: returns gracefully without raising.
    6. ALWAYS sampleCount=1 in payload (cost control).
    7. force=True bypasses cache.
"""

from __future__ import annotations

import base64
import sys
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "src"))


# A tiny valid PNG (1x1 transparent pixel) for mock responses
TINY_PNG_B64 = (
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNkAAIAAAUAAen63NgAAAAASUVORK5CYII="
)


@pytest.fixture
def tmp_output(tmp_path):
    """Isolated output directory for each test."""
    return tmp_path / "posts"


@pytest.fixture
def enabled_env(monkeypatch):
    """Enable image generation with a fake key."""
    monkeypatch.setenv("ENABLE_IMAGE_GEN", "true")
    monkeypatch.setenv("GEMINI_API_KEY", "fake-test-key")


@pytest.fixture
def disabled_env(monkeypatch):
    """Image gen disabled."""
    monkeypatch.setenv("ENABLE_IMAGE_GEN", "false")
    monkeypatch.setenv("GEMINI_API_KEY", "fake-test-key")


def _mock_success_response():
    """Build a fake successful Gemini Imagen response."""
    resp = MagicMock()
    resp.status_code = 200
    resp.json.return_value = {
        "predictions": [{"bytesBase64Encoded": TINY_PNG_B64}],
    }
    return resp


def _mock_error_response(status=500, text="server error"):
    resp = MagicMock()
    resp.status_code = status
    resp.text = text
    return resp


# ─── is_enabled() ───────────────────────────────────────────────────

class TestIsEnabled:
    def test_enabled_with_key(self, enabled_env):
        from rag.image_generator import is_enabled
        assert is_enabled() is True

    def test_disabled_via_env(self, disabled_env):
        from rag.image_generator import is_enabled
        assert is_enabled() is False

    def test_disabled_when_no_key(self, monkeypatch):
        from rag.image_generator import is_enabled
        monkeypatch.setenv("ENABLE_IMAGE_GEN", "true")
        monkeypatch.delenv("GEMINI_API_KEY", raising=False)
        assert is_enabled() is False

    def test_default_disabled(self, monkeypatch):
        from rag.image_generator import is_enabled
        monkeypatch.delenv("ENABLE_IMAGE_GEN", raising=False)
        monkeypatch.setenv("GEMINI_API_KEY", "fake")
        assert is_enabled() is False

    def test_various_truthy_values(self, monkeypatch):
        from rag.image_generator import is_enabled
        monkeypatch.setenv("GEMINI_API_KEY", "fake")
        for truthy in ("true", "TRUE", "1", "yes", "Yes"):
            monkeypatch.setenv("ENABLE_IMAGE_GEN", truthy)
            assert is_enabled() is True, f"{truthy!r} should be truthy"

    def test_various_falsy_values(self, monkeypatch):
        from rag.image_generator import is_enabled
        monkeypatch.setenv("GEMINI_API_KEY", "fake")
        for falsy in ("false", "0", "no", ""):
            monkeypatch.setenv("ENABLE_IMAGE_GEN", falsy)
            assert is_enabled() is False, f"{falsy!r} should be falsy"


# ─── build_image_prompt() ───────────────────────────────────────────

class TestBuildImagePrompt:
    def test_default_prompt_has_branding(self):
        from rag.image_generator import build_image_prompt
        prompt = build_image_prompt("Some title")
        assert "minimalist" in prompt.lower()
        assert "purple" in prompt.lower()
        assert "no text" in prompt.lower()  # Critical: no text in the image

    def test_smart_contract_topic(self):
        from rag.image_generator import build_image_prompt
        prompt = build_image_prompt("Hedera Smart Contracts on EVM")
        assert "code editor" in prompt.lower() or "contract" in prompt.lower()

    def test_token_topic(self):
        from rag.image_generator import build_image_prompt
        prompt = build_image_prompt("Building with HTS Tokens")
        assert "hexagonal" in prompt.lower() or "token" in prompt.lower()

    def test_consensus_topic(self):
        from rag.image_generator import build_image_prompt
        prompt = build_image_prompt("Hashgraph Consensus Deep Dive")
        assert "node" in prompt.lower() or "graph" in prompt.lower()

    def test_unknown_topic_uses_default(self):
        from rag.image_generator import build_image_prompt
        prompt = build_image_prompt("Random unrelated topic")
        assert "hedera" in prompt.lower()  # Falls through to ecosystem default

    def test_prompt_always_forbids_text(self):
        """SAFETY CONTRACT: every prompt must aggressively forbid text in the image.

        Image generators (especially the fast variant) produce garbled or
        misspelled text. The blog title is rendered in HTML separately, so the
        cover image must be purely visual. This test enforces aggressive
        no-text constraints for ALL topic variations.
        """
        from rag.image_generator import build_image_prompt
        topics = [
            "Hedera Smart Contracts on EVM",
            "Building HTS Tokens",
            "Hashgraph Consensus Internals",
            "Hardware Wallet Security",
            "DeFi Lending Pools",
            "AI Agents on Hedera",
            "Some Random Topic With No Keywords",
            "",  # Empty title edge case
        ]
        # The hardened prompt must include all of these constraint phrases
        required_negatives = [
            "no text", "no words", "no letters", "no numbers",
            "no logos", "no captions", "no labels", "no typography",
        ]
        for title in topics:
            prompt = build_image_prompt(title)
            lower = prompt.lower()
            for needed in required_negatives:
                assert needed in lower, (
                    f"Missing constraint {needed!r} for title {title!r}"
                )

    def test_prompt_does_not_mention_text_inducing_terms(self):
        """The prompt must NEVER include words that bias the model toward text.

        Words like 'code editor', 'screen', 'monitor', 'dashboard', 'document'
        strongly suggest text-containing imagery to the model, even if we
        say 'no text' afterwards. We must avoid those completely.
        """
        from rag.image_generator import build_image_prompt
        # Topics that USED to mention text-inducing terms in old prompts
        topics = [
            "Smart Contracts",
            "DeFi Dashboard Stats",
            "EVM Code Patterns",
        ]
        # Forbidden in the POSITIVE part of the prompt (we DO mention them
        # in the negative section "no code editors" etc — that's expected)
        for title in topics:
            prompt = build_image_prompt(title)
            # Split prompt into positive (start) and negative (after the
            # "no text" enforcement section) and check only the positive part
            negative_marker = "PURELY ABSTRACT VISUAL ONLY"
            assert negative_marker in prompt
            positive = prompt.split(negative_marker)[0].lower()
            # These terms should NOT appear in the visual description
            forbidden_in_positive = [
                "code editor", "screen", "monitor", "dashboard",
                "document", "page",
            ]
            for term in forbidden_in_positive:
                assert term not in positive, (
                    f"Positive prompt for {title!r} contains text-inducing "
                    f"term {term!r} - this biases the model toward text"
                )


# ─── generate_image() ───────────────────────────────────────────────

class TestGenerateImage:
    def test_disabled_returns_empty_no_api_call(self, disabled_env, tmp_output):
        from rag.image_generator import generate_image
        with patch("requests.post") as mock_post:
            filename, error = generate_image("Test", "test-slug", tmp_output)
        assert filename == ""
        assert "disabled" in error.lower()
        mock_post.assert_not_called()  # No API call when disabled (cost saved)

    def test_no_key_returns_empty_no_api_call(self, monkeypatch, tmp_output):
        from rag.image_generator import generate_image
        monkeypatch.setenv("ENABLE_IMAGE_GEN", "true")
        monkeypatch.delenv("GEMINI_API_KEY", raising=False)
        with patch("requests.post") as mock_post:
            filename, error = generate_image("Test", "test-slug", tmp_output)
        assert filename == ""
        mock_post.assert_not_called()

    def test_successful_generation_saves_image(self, enabled_env, tmp_output):
        from rag.image_generator import generate_image
        with patch("requests.post", return_value=_mock_success_response()) as mock_post:
            filename, error = generate_image("Test Post", "test-post", tmp_output)
        assert filename == "image-test-post.png"
        assert error == ""
        assert (tmp_output / filename).exists()
        # Verify ONE API call was made (cost control)
        assert mock_post.call_count == 1

    def test_payload_always_sample_count_one(self, enabled_env, tmp_output):
        """Cost control: must NEVER request more than 1 sample per call."""
        from rag.image_generator import generate_image
        with patch("requests.post", return_value=_mock_success_response()) as mock_post:
            generate_image("Test", "test", tmp_output)
        _, kwargs = mock_post.call_args
        assert kwargs["json"]["parameters"]["sampleCount"] == 1

    def test_uses_bounded_cost_model(self, enabled_env, tmp_output):
        """Cost contract: must use a bounded-cost Imagen model.

        We use imagen-4.0-generate-001 (standard) NOT imagen-4.0-ultra-generate-001
        because:
        - "fast" produces garbled text (we tried it, user reported text mistakes)
        - "standard" follows negative prompts reliably and renders any text correctly
        - "ultra" is 1.5x more expensive than standard for marginal quality gains
        """
        from rag.image_generator import generate_image, IMAGEN_MODEL
        # Must be an Imagen 4 model
        assert "imagen-4" in IMAGEN_MODEL.lower()
        # Forbid the most expensive variant
        assert "ultra" not in IMAGEN_MODEL.lower(), \
            "Cost contract: never use Imagen Ultra (1.5x cost vs standard)"
        with patch("requests.post", return_value=_mock_success_response()) as mock_post:
            generate_image("Test", "test", tmp_output)
        url = mock_post.call_args[0][0]
        assert IMAGEN_MODEL in url

    def test_cache_hit_skips_api_call(self, enabled_env, tmp_output):
        """If the image already exists, NEVER call the API (saves money)."""
        from rag.image_generator import generate_image
        # Pre-create the cached image
        tmp_output.mkdir(parents=True, exist_ok=True)
        cached = tmp_output / "image-cached-slug.png"
        cached.write_bytes(b"fake image")

        with patch("requests.post") as mock_post:
            filename, error = generate_image("Test", "cached-slug", tmp_output)
        assert filename == "image-cached-slug.png"
        assert error == ""
        mock_post.assert_not_called()  # Critical: no API call on cache hit

    def test_force_bypasses_cache(self, enabled_env, tmp_output):
        """force=True regenerates even if cached."""
        from rag.image_generator import generate_image
        tmp_output.mkdir(parents=True, exist_ok=True)
        cached = tmp_output / "image-force-test.png"
        cached.write_bytes(b"old image")

        with patch("requests.post", return_value=_mock_success_response()) as mock_post:
            filename, error = generate_image("Test", "force-test", tmp_output, force=True)
        assert mock_post.call_count == 1  # API was called

    def test_api_error_returns_gracefully(self, enabled_env, tmp_output):
        """API errors should not raise - return empty filename + error message."""
        from rag.image_generator import generate_image
        with patch("requests.post", return_value=_mock_error_response(500, "server down")):
            filename, error = generate_image("Test", "test", tmp_output)
        assert filename == ""
        assert "API error 500" in error

    def test_network_error_returns_gracefully(self, enabled_env, tmp_output):
        """Network errors should not raise."""
        from rag.image_generator import generate_image
        import requests as req
        with patch("requests.post", side_effect=req.RequestException("connection refused")):
            filename, error = generate_image("Test", "test", tmp_output)
        assert filename == ""
        assert "Request error" in error

    def test_empty_predictions_returns_error(self, enabled_env, tmp_output):
        from rag.image_generator import generate_image
        resp = MagicMock()
        resp.status_code = 200
        resp.json.return_value = {"predictions": []}
        with patch("requests.post", return_value=resp):
            filename, error = generate_image("Test", "test", tmp_output)
        assert filename == ""
        assert "No predictions" in error

    def test_filename_uses_slug(self, enabled_env, tmp_output):
        from rag.image_generator import generate_image
        with patch("requests.post", return_value=_mock_success_response()):
            filename, _ = generate_image("My Title", "my-cool-slug", tmp_output)
        assert filename == "image-my-cool-slug.png"


# ─── Integration with publisher ─────────────────────────────────────

class TestPublisherIntegration:
    """Verify publisher.py correctly uses image generator without breaking."""

    def test_publisher_works_without_image(self, monkeypatch, tmp_path):
        """If image gen is disabled, publisher still produces valid HTML."""
        monkeypatch.setenv("ENABLE_IMAGE_GEN", "false")
        import rag.publisher as pub
        tmp_docs = tmp_path / "docs"
        tmp_posts = tmp_docs / "posts"
        monkeypatch.setattr(pub, "DOCS_DIR", tmp_docs)
        monkeypatch.setattr(pub, "POSTS_DIR", tmp_posts)
        monkeypatch.setattr(pub, "INDEX_PATH", tmp_docs / "index.html")
        monkeypatch.setattr(pub, "PROJECT_ROOT", tmp_path)

        with patch("subprocess.run") as mock_git:
            mock_git.return_value.returncode = 0
            url, error = pub.publish_to_github_pages("# Test\n\nContent.")

        assert error == ""
        post_files = list(tmp_posts.glob("*.html"))
        assert len(post_files) == 1
        # No image files should exist
        image_files = list(tmp_posts.glob("image-*.png"))
        assert len(image_files) == 0

    def test_publisher_includes_image_when_enabled(self, monkeypatch, tmp_path):
        """When enabled, image should be generated and embedded in HTML."""
        monkeypatch.setenv("ENABLE_IMAGE_GEN", "true")
        monkeypatch.setenv("GEMINI_API_KEY", "fake")
        import rag.publisher as pub
        tmp_docs = tmp_path / "docs"
        tmp_posts = tmp_docs / "posts"
        monkeypatch.setattr(pub, "DOCS_DIR", tmp_docs)
        monkeypatch.setattr(pub, "POSTS_DIR", tmp_posts)
        monkeypatch.setattr(pub, "INDEX_PATH", tmp_docs / "index.html")
        monkeypatch.setattr(pub, "PROJECT_ROOT", tmp_path)

        with patch("subprocess.run") as mock_git, \
             patch("requests.post", return_value=_mock_success_response()):
            mock_git.return_value.returncode = 0
            url, error = pub.publish_to_github_pages("# My Post\n\nContent.")

        assert error == ""
        # Image file should exist
        image_files = list(tmp_posts.glob("image-*.png"))
        assert len(image_files) == 1
        # HTML should embed the image
        html_files = list(tmp_posts.glob("*.html"))
        html = html_files[0].read_text()
        assert 'class="cover-image"' in html
        assert "image-my-post.png" in html

    def test_publisher_continues_when_image_gen_fails(self, monkeypatch, tmp_path):
        """If image gen fails (API error), the blog should still publish."""
        monkeypatch.setenv("ENABLE_IMAGE_GEN", "true")
        monkeypatch.setenv("GEMINI_API_KEY", "fake")
        import rag.publisher as pub
        tmp_docs = tmp_path / "docs"
        tmp_posts = tmp_docs / "posts"
        monkeypatch.setattr(pub, "DOCS_DIR", tmp_docs)
        monkeypatch.setattr(pub, "POSTS_DIR", tmp_posts)
        monkeypatch.setattr(pub, "INDEX_PATH", tmp_docs / "index.html")
        monkeypatch.setattr(pub, "PROJECT_ROOT", tmp_path)

        with patch("subprocess.run") as mock_git, \
             patch("requests.post", return_value=_mock_error_response(500, "down")):
            mock_git.return_value.returncode = 0
            url, error = pub.publish_to_github_pages("# Title\n\nContent.")

        # Publish should still succeed, just without an image
        assert error == ""
        html = list(tmp_posts.glob("*.html"))[0].read_text()
        assert "<h1>Title</h1>" in html
        assert 'class="cover-image"' not in html
