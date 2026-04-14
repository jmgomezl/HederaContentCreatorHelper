"""Tests for ContentBlogCrew._parse_publisher_output (tags + titles parsing).

These tests verify the parser correctly handles the publisher's output format:
    {blog markdown}
    ---TITLES---
    {title 1}
    {title 2}
    ---TAGS---
    {tag 1}
    {tag 2}

They are pure unit tests with no API calls.
"""

from __future__ import annotations

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "src"))


class TestParsePublisherOutput:
    def test_full_output_with_blog_titles_tags(self):
        from crew.crew import ContentBlogCrew
        output = """# My Blog Title

This is the blog content.

## Section

More content here.

---TITLES---
Title One
Title Two
Title Three

---TAGS---
hedera
hts
smart-contracts
web3
defi
"""
        blog, titles, tags = ContentBlogCrew._parse_publisher_output(output)
        assert blog.startswith("# My Blog Title")
        assert "More content here" in blog
        assert "Title One" in titles
        assert "Title Three" in titles
        assert tags == ["hedera", "hts", "smart-contracts", "web3", "defi"]

    def test_no_separators_returns_blog_only(self):
        from crew.crew import ContentBlogCrew
        output = "# Just Blog\n\nNo separators here."
        blog, titles, tags = ContentBlogCrew._parse_publisher_output(output)
        assert blog == "# Just Blog\n\nNo separators here."
        assert titles == ""
        assert tags == []

    def test_titles_but_no_tags(self):
        from crew.crew import ContentBlogCrew
        output = "# Blog\n\nContent.\n\n---TITLES---\nTitle 1\nTitle 2"
        blog, titles, tags = ContentBlogCrew._parse_publisher_output(output)
        assert blog == "# Blog\n\nContent."
        assert "Title 1" in titles
        assert tags == []

    def test_tags_capped_at_five(self):
        """Even if the LLM outputs more than 5 tags, we only keep 5."""
        from crew.crew import ContentBlogCrew
        output = """# Blog

Content.

---TITLES---
T1

---TAGS---
tag1
tag2
tag3
tag4
tag5
tag6
tag7
"""
        _, _, tags = ContentBlogCrew._parse_publisher_output(output)
        assert len(tags) == 5
        assert tags == ["tag1", "tag2", "tag3", "tag4", "tag5"]

    def test_tags_normalized_lowercase_with_dashes(self):
        from crew.crew import ContentBlogCrew
        output = """# Blog

Content.

---TITLES---
T1

---TAGS---
Hedera
Smart Contracts
WEB3 DEVELOPMENT
HTS
"""
        _, _, tags = ContentBlogCrew._parse_publisher_output(output)
        assert tags == ["hedera", "smart-contracts", "web3-development", "hts"]

    def test_tags_strip_bullet_markers(self):
        """Some LLMs output tags with leading dashes - strip them."""
        from crew.crew import ContentBlogCrew
        output = """# Blog

Content.

---TITLES---
T1

---TAGS---
- hedera
- hts
- web3
"""
        _, _, tags = ContentBlogCrew._parse_publisher_output(output)
        assert tags == ["hedera", "hts", "web3"]

    def test_empty_lines_in_tags_section_ignored(self):
        from crew.crew import ContentBlogCrew
        output = """# Blog

Content.

---TITLES---
T1

---TAGS---
hedera

hts


web3
"""
        _, _, tags = ContentBlogCrew._parse_publisher_output(output)
        assert tags == ["hedera", "hts", "web3"]

    def test_blog_content_preserved_exactly(self):
        """Multi-paragraph blog content should be preserved verbatim."""
        from crew.crew import ContentBlogCrew
        blog_content = (
            "# Title\n\n*Subtitle*\n\n## Intro\n\n"
            "First paragraph.\n\nSecond paragraph.\n\n"
            "## Section\n\n```python\ncode here\n```\n\nMore."
        )
        output = blog_content + "\n\n---TITLES---\nT1\n\n---TAGS---\ntag1\ntag2"
        blog, _, _ = ContentBlogCrew._parse_publisher_output(output)
        assert blog == blog_content

    def test_separator_with_extra_whitespace(self):
        from crew.crew import ContentBlogCrew
        output = "# Blog\n\n---TITLES---  \nT1\n\n---TAGS---\nhedera"
        blog, titles, tags = ContentBlogCrew._parse_publisher_output(output)
        assert blog == "# Blog"
        assert "T1" in titles
        assert tags == ["hedera"]
