"""Tests for the gist_embedder module.

All `gh gist create` subprocess calls are mocked - tests run in milliseconds
and never touch the real GitHub API.

Critical guarantees:
    1. extract_code_blocks finds all fenced code blocks with language hints.
    2. No code blocks -> no API calls (skipped flag set).
    3. Each code block triggers exactly one `gh gist create` call.
    4. Failed gist creation leaves the original code block in place (graceful).
    5. Multiple successful gists all replace their respective blocks.
    6. Filenames use sensible extensions per language.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "src"))


# ─── extract_code_blocks ────────────────────────────────────────────

class TestExtractCodeBlocks:
    def test_no_code_blocks(self):
        from rag.gist_embedder import extract_code_blocks
        md = "# Title\n\nJust prose, no code at all.\n\n## Section\n\nMore prose."
        assert extract_code_blocks(md) == []

    def test_single_python_block(self):
        from rag.gist_embedder import extract_code_blocks
        md = "Some text.\n\n```python\nprint('hi')\n```\n\nMore text."
        blocks = extract_code_blocks(md)
        assert len(blocks) == 1
        assert blocks[0].language == "python"
        assert "print('hi')" in blocks[0].code

    def test_multiple_blocks_different_languages(self):
        from rag.gist_embedder import extract_code_blocks
        md = (
            "First:\n\n```python\nx = 1\n```\n\n"
            "Second:\n\n```javascript\nconst y = 2;\n```\n\n"
            "Third:\n\n```solidity\ncontract Foo {}\n```\n"
        )
        blocks = extract_code_blocks(md)
        assert len(blocks) == 3
        languages = [b.language for b in blocks]
        assert languages == ["python", "javascript", "solidity"]

    def test_no_language_hint_defaults_to_text(self):
        from rag.gist_embedder import extract_code_blocks
        md = "```\nplain code\n```"
        blocks = extract_code_blocks(md)
        assert len(blocks) == 1
        assert blocks[0].language == "text"

    def test_preserves_full_match_for_replacement(self):
        from rag.gist_embedder import extract_code_blocks
        md = "Pre\n\n```python\nprint('hi')\n```\n\nPost"
        blocks = extract_code_blocks(md)
        assert blocks[0].full_match.startswith("```python")
        assert blocks[0].full_match.endswith("```")

    def test_multiline_code(self):
        from rag.gist_embedder import extract_code_blocks
        md = "```python\ndef foo():\n    return 42\n\nfoo()\n```"
        blocks = extract_code_blocks(md)
        assert len(blocks) == 1
        assert "def foo()" in blocks[0].code
        assert "return 42" in blocks[0].code


# ─── _filename_for ──────────────────────────────────────────────────

class TestFilenameFor:
    def test_python_extension(self):
        from rag.gist_embedder import _filename_for
        assert _filename_for("python", 1) == "snippet-01.py"

    def test_solidity_extension(self):
        from rag.gist_embedder import _filename_for
        assert _filename_for("solidity", 2) == "snippet-02.sol"

    def test_unknown_language_falls_back_to_txt(self):
        from rag.gist_embedder import _filename_for
        assert _filename_for("klingon", 1) == "snippet-01.txt"

    def test_index_padding(self):
        from rag.gist_embedder import _filename_for
        assert _filename_for("python", 9) == "snippet-09.py"
        assert _filename_for("python", 10) == "snippet-10.py"


# ─── create_gist (subprocess mocked) ────────────────────────────────

def _mock_subprocess_success(url="https://gist.github.com/jmgomezl/abc123"):
    """Build a fake successful subprocess.run result."""
    result = MagicMock()
    result.returncode = 0
    result.stdout = url + "\n"
    result.stderr = ""
    return result


def _mock_subprocess_failure(stderr="permission denied"):
    result = MagicMock()
    result.returncode = 1
    result.stdout = ""
    result.stderr = stderr
    return result


class TestCreateGist:
    def test_successful_gist(self):
        from rag.gist_embedder import create_gist
        with patch("subprocess.run", return_value=_mock_subprocess_success()) as mock_run:
            url, error = create_gist("print('hi')", "python", "test snippet")
        assert error == ""
        assert url == "https://gist.github.com/jmgomezl/abc123"
        # Verify the gh CLI was called with the right args
        cmd = mock_run.call_args[0][0]
        assert "gh" in cmd
        assert "gist" in cmd
        assert "create" in cmd
        assert "--public" in cmd

    def test_empty_code_returns_error_no_call(self):
        from rag.gist_embedder import create_gist
        with patch("subprocess.run") as mock_run:
            url, error = create_gist("", "python", "test")
        assert url == ""
        assert "Empty" in error
        mock_run.assert_not_called()

    def test_gh_failure_returns_error(self):
        from rag.gist_embedder import create_gist
        with patch("subprocess.run",
                   return_value=_mock_subprocess_failure("auth required")):
            url, error = create_gist("code", "python", "test")
        assert url == ""
        assert "auth required" in error

    def test_gh_not_installed(self):
        from rag.gist_embedder import create_gist
        with patch("subprocess.run", side_effect=FileNotFoundError("gh not found")):
            url, error = create_gist("code", "python", "test")
        assert url == ""
        assert "gh CLI not installed" in error

    def test_timeout_returns_error(self):
        from rag.gist_embedder import create_gist
        with patch("subprocess.run",
                   side_effect=subprocess.TimeoutExpired(cmd="gh", timeout=30)):
            url, error = create_gist("code", "python", "test")
        assert url == ""
        assert "timed out" in error

    def test_unexpected_output_returns_error(self):
        from rag.gist_embedder import create_gist
        bad_result = MagicMock()
        bad_result.returncode = 0
        bad_result.stdout = "not a gist URL"
        bad_result.stderr = ""
        with patch("subprocess.run", return_value=bad_result):
            url, error = create_gist("code", "python", "test")
        assert url == ""
        assert "Unexpected" in error

    def test_uses_correct_filename(self):
        from rag.gist_embedder import create_gist
        with patch("subprocess.run", return_value=_mock_subprocess_success()) as mock_run:
            create_gist("contract Foo {}", "solidity", "test", index=3)
        cmd = mock_run.call_args[0][0]
        # The filename arg should be present
        assert "--filename" in cmd
        idx = cmd.index("--filename")
        assert cmd[idx + 1] == "snippet-03.sol"


# ─── convert_to_medium_markdown ─────────────────────────────────────

class TestConvertToMediumMarkdown:
    def test_no_code_blocks_skipped(self):
        from rag.gist_embedder import convert_to_medium_markdown
        md = "# Title\n\nJust text, no code."
        with patch("subprocess.run") as mock_run:
            converted, meta = convert_to_medium_markdown(md, "Test")
        assert converted == md  # Unchanged
        assert meta["skipped"] is True
        assert meta["gist_count"] == 0
        mock_run.assert_not_called()  # No API calls

    def test_single_block_replaced_with_gist_url(self):
        from rag.gist_embedder import convert_to_medium_markdown
        md = "Pre\n\n```python\nprint('hi')\n```\n\nPost"
        with patch("subprocess.run", return_value=_mock_subprocess_success()):
            converted, meta = convert_to_medium_markdown(md, "Test")
        assert meta["skipped"] is False
        assert meta["gist_count"] == 1
        assert "https://gist.github.com/" in converted
        assert "```python" not in converted  # Code block gone
        assert "Pre" in converted
        assert "Post" in converted

    def test_multiple_blocks_each_get_gist(self):
        from rag.gist_embedder import convert_to_medium_markdown

        urls = [
            "https://gist.github.com/jmgomezl/aaa",
            "https://gist.github.com/jmgomezl/bbb",
            "https://gist.github.com/jmgomezl/ccc",
        ]
        call_count = {"n": 0}

        def fake_run(*args, **kwargs):
            r = MagicMock()
            r.returncode = 0
            r.stdout = urls[call_count["n"]] + "\n"
            r.stderr = ""
            call_count["n"] += 1
            return r

        md = (
            "```python\nx=1\n```\n\n"
            "```javascript\ny=2\n```\n\n"
            "```solidity\nz=3\n```\n"
        )
        with patch("subprocess.run", side_effect=fake_run):
            converted, meta = convert_to_medium_markdown(md, "Test")

        assert meta["gist_count"] == 3
        for url in urls:
            assert url in converted
        # All three code blocks should be removed
        assert "```python" not in converted
        assert "```javascript" not in converted
        assert "```solidity" not in converted

    def test_failed_gist_leaves_original_block(self):
        """If gh fails, the original code block stays - blog still publishes."""
        from rag.gist_embedder import convert_to_medium_markdown
        md = "```python\nfoo\n```"
        with patch("subprocess.run", return_value=_mock_subprocess_failure()):
            converted, meta = convert_to_medium_markdown(md, "Test")
        assert meta["gist_count"] == 0
        assert len(meta["errors"]) == 1
        # Original block should still be there
        assert "```python" in converted

    def test_partial_failure_replaces_only_successes(self):
        """If some gists succeed and others fail, only the successes are replaced."""
        from rag.gist_embedder import convert_to_medium_markdown

        results = [
            _mock_subprocess_success("https://gist.github.com/jmgomezl/ok"),
            _mock_subprocess_failure("rate limited"),
        ]
        call_count = {"n": 0}

        def fake_run(*args, **kwargs):
            r = results[call_count["n"]]
            call_count["n"] += 1
            return r

        md = "```python\nfirst\n```\n\n```javascript\nsecond\n```"
        with patch("subprocess.run", side_effect=fake_run):
            converted, meta = convert_to_medium_markdown(md, "Test")

        assert meta["gist_count"] == 1
        assert len(meta["errors"]) == 1
        # First block replaced, second left intact
        assert "https://gist.github.com/jmgomezl/ok" in converted
        assert "```javascript" in converted

    def test_one_api_call_per_code_block(self):
        """Cost contract: never call gh more times than there are code blocks."""
        from rag.gist_embedder import convert_to_medium_markdown
        md = "```python\na\n```\n\n```python\nb\n```\n\n```python\nc\n```"
        with patch("subprocess.run", return_value=_mock_subprocess_success()) as mock_run:
            convert_to_medium_markdown(md, "Test")
        assert mock_run.call_count == 3


# ─── Publisher integration ─────────────────────────────────────────

class TestPublisherIntegration:
    @pytest.fixture
    def isolated(self, tmp_path, monkeypatch):
        import rag.publisher as pub
        tmp_docs = tmp_path / "docs"
        tmp_posts = tmp_docs / "posts"
        monkeypatch.setattr(pub, "DOCS_DIR", tmp_docs)
        monkeypatch.setattr(pub, "POSTS_DIR", tmp_posts)
        monkeypatch.setattr(pub, "INDEX_PATH", tmp_docs / "index.html")
        monkeypatch.setattr(pub, "PROJECT_ROOT", tmp_path)
        monkeypatch.setenv("ENABLE_IMAGE_GEN", "false")
        return tmp_posts

    def test_no_code_blocks_no_medium_md_file(self, isolated):
        """If the blog has no code blocks, no -medium.md file is created."""
        from rag.publisher import publish_to_github_pages
        md = "# Title\n\nProse only."
        with patch("subprocess.run") as mock_git:
            mock_git.return_value.returncode = 0
            url, error = publish_to_github_pages(md, tags=["hedera", "web3"])
        assert error == ""
        assert not (isolated / "title-medium.md").exists()
        # Only git commands should have been called (no gh)
        gh_calls = [c for c in mock_git.call_args_list if "gh" in str(c.args[0])]
        assert len(gh_calls) == 0

    def test_with_code_blocks_creates_medium_md(self, isolated):
        """If the blog has code blocks, a -medium.md file is created with gist URLs."""
        from rag.publisher import publish_to_github_pages
        md = (
            "# Hedera Test Post\n\n"
            "Some intro.\n\n"
            "```python\nprint('hi')\n```\n\n"
            "More text."
        )

        def fake_run(*args, **kwargs):
            cmd = args[0] if args else kwargs.get("args", [])
            if "gh" in cmd:
                r = MagicMock()
                r.returncode = 0
                r.stdout = "https://gist.github.com/jmgomezl/test123\n"
                r.stderr = ""
                return r
            # git commands
            r = MagicMock()
            r.returncode = 0
            return r

        with patch("subprocess.run", side_effect=fake_run):
            url, error = publish_to_github_pages(md, tags=["hedera", "python"])

        assert error == ""
        # Medium markdown file should exist
        medium_files = list(isolated.glob("*-medium.md"))
        assert len(medium_files) == 1
        content = medium_files[0].read_text()
        assert "https://gist.github.com/jmgomezl/test123" in content

    def test_html_includes_tags_pills(self, isolated):
        from rag.publisher import publish_to_github_pages
        with patch("subprocess.run") as mock_git:
            mock_git.return_value.returncode = 0
            publish_to_github_pages(
                "# Title\n\nContent.",
                tags=["hedera", "hts", "web3"],
            )
        html = list(isolated.glob("*.html"))[0].read_text()
        assert 'class="tags"' in html
        assert 'class="tag"' in html
        assert ">hedera<" in html
        assert ">hts<" in html
        assert ">web3<" in html
        # Also in keywords meta tag
        assert "hedera, hts, web3" in html
