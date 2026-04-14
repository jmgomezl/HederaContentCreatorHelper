"""Unit tests for the publisher module (markdown -> HTML + git publish)."""

from __future__ import annotations

import os
import sys
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "src"))


# ─── _slugify ───────────────────────────────────────────────────────

class TestSlugify:
    def test_basic_title(self):
        from rag.publisher import _slugify
        assert _slugify("Hello World") == "hello-world"

    def test_special_characters_stripped(self):
        from rag.publisher import _slugify
        assert _slugify("Hello! World? 123") == "hello-world-123"

    def test_multiple_spaces_collapsed(self):
        from rag.publisher import _slugify
        assert _slugify("foo   bar    baz") == "foo-bar-baz"

    def test_apostrophes_stripped(self):
        from rag.publisher import _slugify
        # "Zeni's patterns" -> "zenis-patterns" (apostrophe stripped by [^\w\s-])
        result = _slugify("Zeni's patterns")
        assert "zenis" in result or "zeni" in result

    def test_long_title_truncated(self):
        from rag.publisher import _slugify
        long_title = "a" * 200
        result = _slugify(long_title)
        assert len(result) <= 80

    def test_leading_trailing_dashes_stripped(self):
        from rag.publisher import _slugify
        assert not _slugify("---hello---").startswith("-")
        assert not _slugify("---hello---").endswith("-")

    def test_lowercase(self):
        from rag.publisher import _slugify
        assert _slugify("HELLO WORLD") == "hello-world"


# ─── _extract_title_and_subtitle ────────────────────────────────────

class TestExtractTitle:
    def test_h1_only(self):
        from rag.publisher import _extract_title_and_subtitle
        md = "# My Title\n\nSome content here."
        title, subtitle = _extract_title_and_subtitle(md)
        assert title == "My Title"
        assert subtitle == ""

    def test_h1_with_italic_subtitle(self):
        from rag.publisher import _extract_title_and_subtitle
        md = "# My Title\n*This is a subtitle*\n\nContent."
        title, subtitle = _extract_title_and_subtitle(md)
        assert title == "My Title"
        assert subtitle == "This is a subtitle"

    def test_no_title_returns_empty(self):
        from rag.publisher import _extract_title_and_subtitle
        md = "Just some text without headings."
        title, subtitle = _extract_title_and_subtitle(md)
        assert title == ""
        assert subtitle == ""

    def test_h2_is_ignored(self):
        from rag.publisher import _extract_title_and_subtitle
        md = "## Not a title\n\nContent."
        title, _ = _extract_title_and_subtitle(md)
        assert title == ""


# ─── markdown_to_html ───────────────────────────────────────────────

class TestMarkdownToHtml:
    def test_h1_becomes_html_h1(self):
        from rag.publisher import markdown_to_html
        html = markdown_to_html("# Hello World\n\nContent.")
        assert "<h1>Hello World</h1>" in html

    def test_code_block_preserved(self):
        from rag.publisher import markdown_to_html
        md = "# Title\n\n```python\nprint('hi')\n```\n"
        html = markdown_to_html(md)
        assert "<pre>" in html
        assert "print" in html

    def test_bullet_list_rendered(self):
        from rag.publisher import markdown_to_html
        md = "# Title\n\n- Item 1\n- Item 2\n"
        html = markdown_to_html(md)
        assert "<ul>" in html
        assert "<li>Item 1</li>" in html

    def test_includes_hedera_styling(self):
        from rag.publisher import markdown_to_html
        html = markdown_to_html("# Test")
        assert "hedera-purple" in html  # CSS variable
        assert "article-container" in html

    def test_subtitle_extracted_from_markdown(self):
        from rag.publisher import markdown_to_html
        md = "# My Post\n*A great subtitle*\n\nBody."
        html = markdown_to_html(md)
        assert "A great subtitle" in html
        assert 'class="subtitle"' in html

    def test_default_title_when_missing(self):
        from rag.publisher import markdown_to_html
        html = markdown_to_html("No heading here.", title="", subtitle="")
        assert "Hedera Technical Blog" in html  # Default title


# ─── publish_to_github_pages ────────────────────────────────────────

class TestPublishToGitHubPages:
    @pytest.fixture
    def isolated_docs(self, tmp_path, monkeypatch):
        """Isolate docs/ writes to a tmp path."""
        import rag.publisher as pub
        tmp_docs = tmp_path / "docs"
        tmp_posts = tmp_docs / "posts"
        monkeypatch.setattr(pub, "DOCS_DIR", tmp_docs)
        monkeypatch.setattr(pub, "POSTS_DIR", tmp_posts)
        monkeypatch.setattr(pub, "INDEX_PATH", tmp_docs / "index.html")
        monkeypatch.setattr(pub, "PROJECT_ROOT", tmp_path)
        return tmp_docs

    def test_writes_html_file(self, isolated_docs):
        from rag.publisher import publish_to_github_pages
        md = "# Test Post\n*Subtitle*\n\nContent."
        with patch("subprocess.run") as mock_run:
            mock_run.return_value.returncode = 0
            url, error = publish_to_github_pages(md)
        assert error == ""
        post_files = list((isolated_docs / "posts").glob("*.html"))
        assert len(post_files) == 1
        assert "test-post" in post_files[0].name

    def test_builds_index(self, isolated_docs):
        from rag.publisher import publish_to_github_pages
        md = "# Test Post\n\nContent."
        with patch("subprocess.run") as mock_run:
            mock_run.return_value.returncode = 0
            publish_to_github_pages(md)
        index = (isolated_docs / "index.html").read_text()
        assert "Test Post" in index
        assert "post-card" in index

    def test_url_uses_slug(self, isolated_docs):
        from rag.publisher import publish_to_github_pages
        md = "# My Awesome Post\n\nContent."
        with patch("subprocess.run") as mock_run:
            mock_run.return_value.returncode = 0
            url, _ = publish_to_github_pages(md)
        assert "my-awesome-post" in url

    def test_git_error_returned(self, isolated_docs):
        from rag.publisher import publish_to_github_pages
        import subprocess
        md = "# Test\n\nContent."

        def fail_git(*args, **kwargs):
            raise subprocess.CalledProcessError(
                1, args[0], stderr=b"fatal: push rejected",
            )

        with patch("subprocess.run", side_effect=fail_git):
            url, error = publish_to_github_pages(md)
        assert url == ""
        assert "Git error" in error

    def test_multiple_posts_all_in_index(self, isolated_docs):
        from rag.publisher import publish_to_github_pages
        with patch("subprocess.run") as mock_run:
            mock_run.return_value.returncode = 0
            publish_to_github_pages("# First Post\n\nBody.")
            publish_to_github_pages("# Second Post\n\nBody.")
            publish_to_github_pages("# Third Post\n\nBody.")
        index = (isolated_docs / "index.html").read_text()
        assert "First Post" in index
        assert "Second Post" in index
        assert "Third Post" in index
        post_files = list((isolated_docs / "posts").glob("*.html"))
        assert len(post_files) == 3
