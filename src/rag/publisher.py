"""Auto-publish blog posts to GitHub Pages as styled HTML."""

from __future__ import annotations

import os
import re
import subprocess
from datetime import datetime
from pathlib import Path

import markdown

PROJECT_ROOT = Path(__file__).parent.parent.parent  # HederaContentCreatorHelper/
DOCS_DIR = PROJECT_ROOT / "docs"
POSTS_DIR = DOCS_DIR / "posts"
INDEX_PATH = DOCS_DIR / "index.html"

GITHUB_PAGES_BASE = "https://jmgomezl.github.io/HederaContentCreatorHelper"

HTML_TEMPLATE = """\
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{title}</title>
{meta_tags}
<style>
  @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&family=JetBrains+Mono:wght@400;500&display=swap');
  :root {{
    --hedera-purple: #8259EF; --hedera-purple-light: #A78BFA;
    --hedera-purple-bg: #F5F0FF; --hedera-dark: #1A1A2E;
    --text-primary: #1F2937; --text-secondary: #4B5563;
    --text-muted: #6B7280; --border: #E5E7EB;
    --bg-code: #F8F7FC; --bg-white: #FFFFFF;
    --accent-green: #10B981;
  }}
  * {{ margin: 0; padding: 0; box-sizing: border-box; }}
  body {{
    font-family: 'Inter', -apple-system, BlinkMacSystemFont, sans-serif;
    color: var(--text-primary); background: #F9FAFB;
    line-height: 1.7; -webkit-font-smoothing: antialiased;
  }}
  .article-container {{
    max-width: 780px; margin: 0 auto; padding: 60px 24px 80px;
    background: var(--bg-white); min-height: 100vh;
    box-shadow: 0 0 40px rgba(0,0,0,0.04);
  }}
  .article-header {{
    margin-bottom: 48px; padding-bottom: 32px;
    border-bottom: 3px solid var(--hedera-purple);
  }}
  .cover-image {{
    width: 100%; height: auto; border-radius: 12px;
    margin-bottom: 32px; box-shadow: 0 8px 32px rgba(130,89,239,0.2);
    display: block;
  }}
  .article-badge {{
    display: inline-block; background: var(--hedera-purple); color: white;
    font-size: 11px; font-weight: 600; letter-spacing: 1.2px;
    text-transform: uppercase; padding: 4px 12px; border-radius: 4px;
    margin-bottom: 20px;
  }}
  h1 {{
    font-size: 32px; font-weight: 700; line-height: 1.25;
    color: var(--hedera-dark); margin-bottom: 16px; letter-spacing: -0.5px;
  }}
  .subtitle {{
    font-size: 18px; font-style: italic; color: var(--text-secondary);
    line-height: 1.6; border-left: 3px solid var(--hedera-purple-light);
    padding-left: 16px;
  }}
  .meta {{ font-size: 13px; color: var(--text-muted); margin-top: 16px; }}
  h2 {{
    font-size: 24px; font-weight: 700; color: var(--hedera-dark);
    margin: 48px 0 16px; padding-bottom: 8px;
    border-bottom: 2px solid var(--hedera-purple-bg); letter-spacing: -0.3px;
  }}
  h3 {{
    font-size: 18px; font-weight: 600; color: var(--hedera-purple);
    margin: 32px 0 12px;
  }}
  p {{ margin-bottom: 16px; font-size: 16px; }}
  ul, ol {{ margin: 12px 0 20px 24px; }}
  li {{ margin-bottom: 8px; font-size: 15px; line-height: 1.65; }}
  li::marker {{ color: var(--hedera-purple); }}
  code {{
    font-family: 'JetBrains Mono', monospace; font-size: 13px;
    background: var(--hedera-purple-bg); color: var(--hedera-purple);
    padding: 2px 6px; border-radius: 4px; font-weight: 500;
  }}
  pre {{
    background: var(--hedera-dark); color: #E2E8F0; border-radius: 10px;
    padding: 24px; margin: 20px 0; overflow-x: auto;
    font-family: 'JetBrains Mono', monospace; font-size: 13px;
    line-height: 1.7; border: 1px solid #2D2D44;
  }}
  pre code {{
    background: none; color: inherit; padding: 0; font-size: 13px;
  }}
  a {{ color: var(--hedera-purple); text-decoration: none; }}
  a:hover {{ text-decoration: underline; }}
  .back-link {{
    display: inline-block; margin-bottom: 24px; font-size: 14px;
    color: var(--hedera-purple);
  }}
  .article-footer {{
    margin-top: 48px; padding-top: 24px; border-top: 1px solid var(--border);
    text-align: center; color: var(--text-muted); font-size: 13px;
  }}
  .tags {{
    margin-top: 32px; padding-top: 20px; border-top: 1px solid var(--border);
    display: flex; flex-wrap: wrap; gap: 8px;
  }}
  .tag {{
    display: inline-block; padding: 6px 14px; border-radius: 999px;
    background: var(--hedera-purple-bg); color: var(--hedera-purple);
    font-size: 13px; font-weight: 500; text-decoration: none;
  }}
  .medium-import {{
    margin-top: 24px; padding: 16px 20px;
    background: var(--bg-callout, #FAFAFE); border: 1px solid var(--border);
    border-radius: 8px; font-size: 13px; color: var(--text-secondary);
  }}
  .medium-import a {{ color: var(--hedera-purple); }}
  .medium-import code {{
    background: #F3F0FF; color: var(--hedera-purple); padding: 2px 6px;
    border-radius: 4px; font-size: 12px;
  }}
  @media (max-width: 640px) {{
    .article-container {{ padding: 32px 16px 48px; }}
    h1 {{ font-size: 26px; }}
    h2 {{ font-size: 20px; }}
    pre {{ padding: 16px; font-size: 12px; }}
  }}
</style>
</head>
<body>
<div class="article-container">
  <a href="../" class="back-link">&larr; All posts</a>
  {cover_image_html}
  <header class="article-header">
    <span class="article-badge">Hedera Technical Deep Dive</span>
    <h1>{title}</h1>
    {subtitle_html}
    <p class="meta">Published {date} &middot; Generated by HederaContentCreatorHelper</p>
  </header>
  {body}
  {tags_html}
  {medium_import_html}
  <div class="article-footer">
    <p>Generated by <a href="https://github.com/jmgomezl/HederaContentCreatorHelper">HederaContentCreatorHelper</a>
    &mdash; Multi-agent CrewAI pipeline</p>
  </div>
</div>
</body>
</html>
"""

INDEX_TEMPLATE = """\
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Hedera Content Blog</title>
<style>
  @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap');
  :root {{
    --hedera-purple: #8259EF; --hedera-dark: #1A1A2E;
    --text-primary: #1F2937; --text-secondary: #4B5563;
    --border: #E5E7EB; --bg-white: #FFFFFF;
  }}
  * {{ margin: 0; padding: 0; box-sizing: border-box; }}
  body {{
    font-family: 'Inter', sans-serif; color: var(--text-primary);
    background: #F9FAFB; line-height: 1.7;
  }}
  .container {{
    max-width: 780px; margin: 0 auto; padding: 60px 24px 80px;
    background: var(--bg-white); min-height: 100vh;
    box-shadow: 0 0 40px rgba(0,0,0,0.04);
  }}
  h1 {{
    font-size: 32px; font-weight: 700; color: var(--hedera-dark);
    margin-bottom: 8px;
  }}
  .tagline {{
    color: var(--text-secondary); font-size: 16px; margin-bottom: 40px;
    padding-bottom: 24px; border-bottom: 3px solid var(--hedera-purple);
  }}
  .post-card {{
    display: block; padding: 24px; margin-bottom: 16px;
    border: 1px solid var(--border); border-radius: 10px;
    text-decoration: none; color: inherit;
    transition: border-color 0.2s, box-shadow 0.2s;
  }}
  .post-card:hover {{
    border-color: var(--hedera-purple);
    box-shadow: 0 4px 12px rgba(130,89,239,0.1);
    text-decoration: none;
  }}
  .post-card h2 {{
    font-size: 20px; font-weight: 600; color: var(--hedera-dark);
    margin-bottom: 8px; line-height: 1.3;
  }}
  .post-card .date {{
    font-size: 13px; color: var(--text-secondary);
  }}
  .empty {{ color: var(--text-secondary); font-style: italic; margin-top: 24px; }}
</style>
</head>
<body>
<div class="container">
  <h1>Hedera Content Blog</h1>
  <p class="tagline">Technical blog posts generated from Hedera livestreams by AI agents</p>
  {posts_html}
</div>
</body>
</html>
"""


def _slugify(text: str) -> str:
    """Convert text to a URL-safe slug."""
    slug = text.lower().strip()
    slug = re.sub(r"[^\w\s-]", "", slug)
    slug = re.sub(r"[\s_]+", "-", slug)
    slug = re.sub(r"-+", "-", slug)
    return slug[:80].strip("-")


def _extract_title_and_subtitle(blog_md: str) -> tuple[str, str]:
    """Extract H1 title and italic subtitle from Markdown."""
    lines = blog_md.strip().splitlines()
    title = ""
    subtitle = ""
    for line in lines:
        stripped = line.strip()
        if stripped.startswith("# ") and not title:
            title = stripped[2:].strip()
        elif stripped.startswith("*") and stripped.endswith("*") and not subtitle and title:
            subtitle = stripped.strip("*").strip()
            break
        elif title and stripped:
            break
    return title, subtitle


def markdown_to_html(
    blog_md: str,
    title: str = "",
    subtitle: str = "",
    cover_image_filename: str = "",
    tags: list[str] | None = None,
    medium_md_filename: str = "",
    slug: str = "",
) -> str:
    """Convert Markdown blog to styled HTML page.

    Args:
        blog_md: The blog content in Markdown.
        title: Optional H1 title (auto-extracted from md if missing).
        subtitle: Optional italic subtitle.
        cover_image_filename: If provided, embed at top (relative to post HTML).
        tags: List of Medium tags (max 5) to render at the bottom of the article.
        medium_md_filename: If provided, link to it as the Medium-friendly version.
        slug: Used for absolute og:image URL.
    """
    if not title:
        title, subtitle = _extract_title_and_subtitle(blog_md)
    if not title:
        title = "Hedera Technical Blog"

    tags = tags or []

    body_html = markdown.markdown(
        blog_md,
        extensions=["fenced_code", "tables", "toc"],
    )

    subtitle_html = f'<p class="subtitle">{subtitle}</p>' if subtitle else ""

    cover_image_html = (
        f'<img class="cover-image" src="{cover_image_filename}" alt="{title}" />'
        if cover_image_filename
        else ""
    )

    # Open Graph + meta tags so Medium (and Twitter, LinkedIn) auto-pick the
    # cover image and description when the URL is shared/imported.
    description = subtitle or f"Hedera technical blog post about {title}"
    meta_lines = [
        f'<meta name="description" content="{_html_escape(description)}">',
        f'<meta property="og:title" content="{_html_escape(title)}">',
        f'<meta property="og:description" content="{_html_escape(description)}">',
        '<meta property="og:type" content="article">',
        f'<meta name="twitter:card" content="summary_large_image">',
    ]
    if cover_image_filename and slug:
        # Absolute URL is required for og:image to work in Medium import
        og_image_url = f"{GITHUB_PAGES_BASE}/posts/{cover_image_filename}"
        meta_lines.append(f'<meta property="og:image" content="{og_image_url}">')
        meta_lines.append(f'<meta name="twitter:image" content="{og_image_url}">')
    if tags:
        meta_lines.append(f'<meta name="keywords" content="{_html_escape(", ".join(tags))}">')
    meta_tags = "\n".join(meta_lines)

    # Render tags as pill chips at the bottom of the article
    tags_html = ""
    if tags:
        chips = "\n".join(f'    <span class="tag">{_html_escape(t)}</span>' for t in tags)
        tags_html = f'<div class="tags">\n{chips}\n  </div>'

    # Optional Medium import callout linking to the gist-embedded markdown
    medium_import_html = ""
    if medium_md_filename:
        medium_import_html = (
            '<div class="medium-import">\n'
            '    <strong>Publishing to Medium?</strong> '
            'For best results with code blocks, use the '
            f'<a href="{medium_md_filename}">Medium-friendly Markdown</a> '
            '(code blocks are pre-converted to embedded GitHub Gists). '
            'Paste it via <a href="https://medium.com/p/import">medium.com/p/import</a>.\n'
            '  </div>'
        )

    date = datetime.now().strftime("%B %d, %Y")

    return HTML_TEMPLATE.format(
        title=_html_escape(title),
        meta_tags=meta_tags,
        subtitle_html=subtitle_html,
        cover_image_html=cover_image_html,
        date=date,
        body=body_html,
        tags_html=tags_html,
        medium_import_html=medium_import_html,
    )


def _html_escape(text: str) -> str:
    """Minimal HTML escape for attribute values."""
    return (
        text.replace("&", "&amp;")
        .replace('"', "&quot;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
    )


def _build_index() -> None:
    """Rebuild the index.html listing all published posts."""
    POSTS_DIR.mkdir(parents=True, exist_ok=True)

    posts = []
    for html_file in sorted(POSTS_DIR.glob("*.html"), reverse=True):
        # Extract title from the HTML file
        content = html_file.read_text(encoding="utf-8")
        title_match = re.search(r"<h1>(.*?)</h1>", content)
        title = title_match.group(1) if title_match else html_file.stem.replace("-", " ").title()

        date_match = re.search(r"Published (\w+ \d+, \d+)", content)
        date = date_match.group(1) if date_match else ""

        posts.append({
            "title": title,
            "date": date,
            "url": f"posts/{html_file.name}",
        })

    if posts:
        posts_html = "\n".join(
            f'  <a href="{p["url"]}" class="post-card">\n'
            f'    <h2>{p["title"]}</h2>\n'
            f'    <span class="date">{p["date"]}</span>\n'
            f'  </a>'
            for p in posts
        )
    else:
        posts_html = '<p class="empty">No posts published yet.</p>'

    INDEX_PATH.write_text(
        INDEX_TEMPLATE.format(posts_html=posts_html),
        encoding="utf-8",
    )


def publish_to_github_pages(
    blog_md: str,
    title: str = "",
    subtitle: str = "",
    focus: str = "",
    tags: list[str] | None = None,
) -> tuple[str, str]:
    """Publish a blog post to GitHub Pages.

    Args:
        blog_md: Blog content in Markdown.
        title: Optional title (auto-extracted if empty).
        subtitle: Optional italic subtitle.
        focus: Optional focus areas (used for image generation hint).
        tags: Optional Medium tags (max 5) to render as pills.

    Returns:
        tuple: (live_url, error_or_empty)
    """
    if not title:
        title, subtitle = _extract_title_and_subtitle(blog_md)

    slug = _slugify(title) if title else f"post-{datetime.now().strftime('%Y%m%d-%H%M%S')}"
    POSTS_DIR.mkdir(parents=True, exist_ok=True)

    # 1. Cover image (optional - silently skips if disabled or fails)
    cover_image_filename = ""
    try:
        from rag.image_generator import generate_image
        cover_image_filename, img_error = generate_image(
            title=title,
            slug=slug,
            output_dir=POSTS_DIR,
            focus=focus,
        )
        if img_error and not cover_image_filename:
            import logging
            logging.getLogger(__name__).info("Image gen skipped: %s", img_error)
    except Exception as exc:
        import logging
        logging.getLogger(__name__).warning("Image gen exception: %s", exc)
        cover_image_filename = ""

    # 2. Medium-friendly markdown with Gist-embedded code blocks
    # Skipped automatically if the blog has no code blocks.
    medium_md_filename = ""
    try:
        from rag.gist_embedder import convert_to_medium_markdown
        medium_md, gist_meta = convert_to_medium_markdown(blog_md, blog_title=title)
        if not gist_meta["skipped"] and gist_meta["gist_count"] > 0:
            medium_md_filename = f"{slug}-medium.md"
            (POSTS_DIR / medium_md_filename).write_text(medium_md, encoding="utf-8")
            import logging
            logging.getLogger(__name__).info(
                "Created %d Gist embeds for Medium import: %s",
                gist_meta["gist_count"],
                medium_md_filename,
            )
    except Exception as exc:
        import logging
        logging.getLogger(__name__).warning("Gist embedder exception: %s", exc)

    # 3. Generate HTML (with cover image, tags, and Medium import callout)
    html = markdown_to_html(
        blog_md,
        title=title,
        subtitle=subtitle,
        cover_image_filename=cover_image_filename,
        tags=tags,
        medium_md_filename=medium_md_filename,
        slug=slug,
    )

    # 4. Write post file
    post_path = POSTS_DIR / f"{slug}.html"
    post_path.write_text(html, encoding="utf-8")

    # 5. Rebuild index
    _build_index()

    # Git commit and push
    try:
        subprocess.run(
            ["git", "add", "docs/"],
            cwd=str(PROJECT_ROOT),
            check=True,
            capture_output=True,
        )
        subprocess.run(
            ["git", "commit", "-m", f"Publish: {title}"],
            cwd=str(PROJECT_ROOT),
            check=True,
            capture_output=True,
        )
        subprocess.run(
            ["git", "push"],
            cwd=str(PROJECT_ROOT),
            check=True,
            capture_output=True,
            timeout=30,
        )
    except subprocess.CalledProcessError as exc:
        return "", f"Git error: {exc.stderr.decode()[:200] if exc.stderr else str(exc)}"
    except subprocess.TimeoutExpired:
        return "", "Git push timed out. Check your network connection."

    live_url = f"{GITHUB_PAGES_BASE}/posts/{slug}.html"
    return live_url, ""
