"""Unit tests to verify configuration, temperature, and model settings.

These tests do NOT call OpenAI — they verify the pipeline won't crash
before spending any tokens.
"""

import os
import sys

import pytest

# Ensure src is on the path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from rag.hedera_blog import (
    BlogConfig,
    extract_video_id,
    _length_guidance,
    _max_section_sentences,
    _verbosity_guidance,
    _length_multiplier,
    build_blog_prompt,
    build_review_prompt,
    build_publisher_prompt,
    build_refine_prompt,
    build_linguistic_prompt,
    build_title_prompt,
    build_notes_prompt,
)


# ─── BlogConfig defaults ────────────────────────────────────────────

class TestBlogConfigDefaults:
    def test_default_model_is_gpt5_mini(self):
        config = BlogConfig()
        assert config.model_name == "gpt-5-mini"

    def test_default_temperature_is_1(self):
        """gpt-5-mini only supports temperature=1.0"""
        config = BlogConfig()
        assert config.temperature == 1.0

    def test_default_max_chunks(self):
        config = BlogConfig()
        assert config.max_chunks == 12

    def test_default_max_iterations(self):
        config = BlogConfig()
        assert config.max_iterations == 2

    def test_custom_config_overrides(self):
        config = BlogConfig(model_name="gpt-4.1", temperature=0.2, max_chunks=5)
        assert config.model_name == "gpt-4.1"
        assert config.temperature == 0.2
        assert config.max_chunks == 5


# ─── Temperature safety ─────────────────────────────────────────────

class TestTemperatureSafety:
    """Ensure no hardcoded temperature values that would break gpt-5-mini."""

    def test_no_hardcoded_temperature_in_source(self):
        """Scan hedera_blog.py for hardcoded temperature values other than config.temperature."""
        import re
        blog_path = os.path.join(
            os.path.dirname(__file__), "..", "src", "rag", "hedera_blog.py"
        )
        with open(blog_path) as f:
            source = f.read()

        # Find all ChatOpenAI instantiations with temperature=
        matches = re.findall(r"temperature\s*=\s*([^,\n\)]+)", source)
        for match in matches:
            match = match.strip()
            # Allow: config.temperature, temperature (parameter), 1.0
            # Reject: hardcoded floats like 0.2, 0.3, min(...)
            if match in ("config.temperature", "temperature", "1.0"):
                continue
            if "min(" in match or "max(" in match:
                pytest.fail(
                    f"Found hardcoded temperature expression: temperature={match}. "
                    f"gpt-5-mini only supports temperature=1.0. "
                    f"Use config.temperature instead."
                )
            try:
                val = float(match)
                if val != 1.0:
                    pytest.fail(
                        f"Found hardcoded temperature={val}. "
                        f"gpt-5-mini only supports 1.0. Use config.temperature."
                    )
            except ValueError:
                pass  # It's a variable reference, that's fine


# ─── Video ID extraction ────────────────────────────────────────────

class TestExtractVideoId:
    def test_raw_id(self):
        assert extract_video_id("dQw4w9WgXcQ") == "dQw4w9WgXcQ"

    def test_watch_url(self):
        assert extract_video_id("https://www.youtube.com/watch?v=dQw4w9WgXcQ") == "dQw4w9WgXcQ"

    def test_live_url(self):
        assert extract_video_id("https://www.youtube.com/live/dQw4w9WgXcQ") == "dQw4w9WgXcQ"

    def test_short_url(self):
        assert extract_video_id("https://youtu.be/dQw4w9WgXcQ") == "dQw4w9WgXcQ"

    def test_invalid_url(self):
        assert extract_video_id("not-a-url") is None

    def test_empty(self):
        assert extract_video_id("") is None


# ─── Prompt templates build without errors ───────────────────────────

class TestPromptTemplatesBuild:
    """Verify all prompt templates can be built and have expected variables."""

    def test_notes_prompt(self):
        p = build_notes_prompt(strict_mode=False)
        assert "chunk" in p.input_variables

    def test_notes_prompt_strict(self):
        p = build_notes_prompt(strict_mode=True)
        assert "chunk" in p.input_variables

    def test_blog_prompt(self):
        p = build_blog_prompt(strict_mode=False)
        assert "notes" in p.input_variables
        assert "audience" in p.input_variables

    def test_review_prompt(self):
        p = build_review_prompt(strict_mode=False)
        assert "notes" in p.input_variables
        assert "draft" in p.input_variables

    def test_publisher_prompt(self):
        p = build_publisher_prompt(strict_mode=False)
        assert "notes" in p.input_variables
        assert "review" in p.input_variables

    def test_refine_prompt(self):
        p = build_refine_prompt(strict_mode=False)
        assert "issues" in p.input_variables
        assert "draft" in p.input_variables

    def test_linguistic_prompt(self):
        p = build_linguistic_prompt(strict_mode=False)
        assert "notes" in p.input_variables
        assert "draft" in p.input_variables

    def test_title_prompt(self):
        p = build_title_prompt()
        assert "blog" in p.input_variables
        assert "count" in p.input_variables


# ─── Helper functions ────────────────────────────────────────────────

class TestHelpers:
    def test_length_guidance_medium(self):
        result = _length_guidance("Medium")
        assert "1200" in result
        assert "2000" in result

    def test_max_section_sentences_not_too_small(self):
        """Sections must allow enough sentences for substantive content."""
        result = _max_section_sentences("medium", "Standard")
        assert result >= 6, f"Max sentences {result} is too small for publishable content"

    def test_max_section_sentences_detailed(self):
        result = _max_section_sentences("medium", "Detailed")
        assert result >= 10

    def test_verbosity_guidance(self):
        assert _verbosity_guidance("Detailed") == "Detailed"
        assert _verbosity_guidance("Concise") == "Concise"
        assert _verbosity_guidance(None) == "Standard"

    def test_length_multiplier_bounds(self):
        assert _length_multiplier(0) == 1
        assert _length_multiplier(5) == 3
        assert _length_multiplier(None) == 1


# ─── Compliance module ───────────────────────────────────────────────

class TestComplianceModule:
    def test_compliance_rules_exist(self):
        from rag.compliance import HEDERA_COMPLIANCE_RULES
        assert "Hedera" in HEDERA_COMPLIANCE_RULES
        assert "HBAR" in HEDERA_COMPLIANCE_RULES
        assert "hashgraph" in HEDERA_COMPLIANCE_RULES

    def test_compliance_gpt_url(self):
        from rag.compliance import COMPLIANCE_GPT_URL
        assert "chatgpt.com" in COMPLIANCE_GPT_URL

    def test_compliance_check_prompt_builds(self):
        from rag.compliance import build_compliance_check_prompt
        p = build_compliance_check_prompt()
        assert "blog" in p.input_variables
        assert "notes" in p.input_variables

    def test_compliance_fix_prompt_builds(self):
        from rag.compliance import build_compliance_fix_prompt
        p = build_compliance_fix_prompt()
        assert "violations" in p.input_variables
        assert "draft" in p.input_variables


# ─── Hedera docs module ─────────────────────────────────────────────

class TestHederaDocsModule:
    def test_sources_defined(self):
        from rag.hedera_docs import HEDERA_SOURCES
        assert "docs" in HEDERA_SOURCES
        assert "blog" in HEDERA_SOURCES
        assert "learning" in HEDERA_SOURCES

    def test_cache_reset(self):
        from rag.hedera_docs import reset_cache, _cache
        reset_cache()
        assert _cache.retriever is None
        assert _cache.doc_count == 0


# ─── YouTube search module ──────────────────────────────────────────

class TestYouTubeSearch:
    def test_channel_id_defined(self):
        from rag.youtube_search import HEDERA_CHANNEL_ID
        assert len(HEDERA_CHANNEL_ID) > 10


# ─── UI module ───────────────────────────────────────────────────────

class TestUI:
    def test_app_builds(self):
        from ui.hedera_blog_app import build_app
        app = build_app()
        assert len(app.blocks) > 30

    def test_no_length_dropdown_in_ui(self):
        """Blog length should not be a user choice — always standard."""
        import inspect
        from ui.hedera_blog_app import build_app
        source = inspect.getsource(build_app)
        assert "Blog length" not in source
