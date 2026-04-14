"""Convert markdown code blocks to GitHub Gist embeds for Medium import.

Why: Medium's URL-import tool flattens multi-line code blocks into single lines,
breaking syntax highlighting and readability. The official workaround is to
embed code as GitHub Gists — Medium auto-renders Gist URLs as proper code blocks
when imported.

Approach:
1. Extract all fenced code blocks from a Markdown document
2. For each, create a public Gist via `gh gist create` (uses existing CLI auth)
3. Replace the code block in the Markdown with the Gist URL on its own line
4. Save the result as `{slug}-medium.md` next to the regular HTML

The result: when you paste this Markdown into Medium's import tool, all code
blocks render as embedded Gists with proper formatting.

Cost: Gists are FREE on GitHub. We deliberately do NOT cache (Gists are cheap)
but we do skip the entire flow if there are no code blocks (no API calls).
"""

from __future__ import annotations

import logging
import os
import re
import subprocess
import tempfile
from dataclasses import dataclass

logger = logging.getLogger(__name__)

# Map language hints to file extensions for nicer Gist filenames
LANGUAGE_EXTENSIONS = {
    "python": "py",
    "py": "py",
    "javascript": "js",
    "js": "js",
    "typescript": "ts",
    "ts": "ts",
    "go": "go",
    "golang": "go",
    "rust": "rs",
    "rs": "rs",
    "solidity": "sol",
    "sol": "sol",
    "java": "java",
    "kotlin": "kt",
    "swift": "swift",
    "ruby": "rb",
    "php": "php",
    "bash": "sh",
    "shell": "sh",
    "sh": "sh",
    "zsh": "sh",
    "json": "json",
    "yaml": "yml",
    "yml": "yml",
    "xml": "xml",
    "html": "html",
    "css": "css",
    "scss": "scss",
    "sql": "sql",
    "c": "c",
    "cpp": "cpp",
    "c++": "cpp",
    "csharp": "cs",
    "cs": "cs",
    "markdown": "md",
    "md": "md",
    "text": "txt",
    "plaintext": "txt",
}

# Match fenced code blocks with optional language hint
# ```python
# code here
# ```
CODE_BLOCK_RE = re.compile(
    r"```([a-zA-Z0-9_+\-]*)\n(.*?)```",
    re.DOTALL,
)


@dataclass
class CodeBlock:
    """A fenced code block extracted from Markdown."""
    language: str
    code: str
    full_match: str  # The original markdown (including fences)


def extract_code_blocks(markdown: str) -> list[CodeBlock]:
    """Find every fenced code block in a Markdown document.

    Returns:
        List of CodeBlock instances in document order.
    """
    blocks = []
    for m in CODE_BLOCK_RE.finditer(markdown):
        language = (m.group(1) or "text").strip().lower()
        code = m.group(2)
        blocks.append(CodeBlock(
            language=language,
            code=code,
            full_match=m.group(0),
        ))
    return blocks


def _filename_for(language: str, index: int) -> str:
    """Build a sensible filename for a Gist snippet."""
    ext = LANGUAGE_EXTENSIONS.get(language.lower(), "txt")
    return f"snippet-{index:02d}.{ext}"


def create_gist(
    code: str,
    language: str,
    description: str,
    index: int = 1,
) -> tuple[str, str]:
    """Create a public GitHub Gist via the gh CLI.

    Args:
        code: The code content.
        language: Language hint (used for file extension).
        description: Gist description (visible on github.com/gists).
        index: Used to build the filename when there are multiple gists per blog.

    Returns:
        tuple: (gist_url, error_message_or_empty)
            On success: ("https://gist.github.com/user/abc123", "")
            On failure: ("", "reason")
    """
    if not code.strip():
        return "", "Empty code block"

    filename = _filename_for(language, index)

    # Write code to a temp file with the right extension so gh names it properly
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            suffix=f"_{filename}",
            delete=False,
            encoding="utf-8",
        ) as f:
            f.write(code)
            temp_path = f.name
    except Exception as exc:
        return "", f"Temp file error: {exc}"

    try:
        result = subprocess.run(
            [
                "gh", "gist", "create",
                "--public",
                "--desc", description[:200],  # gh has a description length limit
                "--filename", filename,
                temp_path,
            ],
            capture_output=True,
            text=True,
            timeout=30,
        )
        if result.returncode != 0:
            err = (result.stderr or result.stdout or "unknown error").strip()
            return "", f"gh gist create failed: {err[:200]}"

        gist_url = result.stdout.strip()
        if not gist_url.startswith("https://gist.github.com/"):
            return "", f"Unexpected gh output: {gist_url[:100]}"
        return gist_url, ""
    except subprocess.TimeoutExpired:
        return "", "gh gist create timed out"
    except FileNotFoundError:
        return "", "gh CLI not installed"
    except Exception as exc:
        return "", f"Gist creation error: {exc}"
    finally:
        try:
            os.unlink(temp_path)
        except Exception:
            pass


def convert_to_medium_markdown(
    markdown: str,
    blog_title: str = "Hedera blog snippet",
) -> tuple[str, dict]:
    """Convert a Markdown document so its code blocks become Gist embeds.

    Each fenced code block is replaced with the Gist URL on its own line.
    When this Markdown is imported into Medium, it auto-embeds the Gist as
    a properly formatted code block.

    Args:
        markdown: The original blog Markdown.
        blog_title: Used as the Gist description prefix.

    Returns:
        tuple: (converted_markdown, metadata)
            metadata dict contains:
                - "gist_count": int, number of Gists created
                - "gist_urls": list[str], all Gist URLs created
                - "errors": list[str], any errors encountered
                - "skipped": bool, True if no code blocks were found
    """
    blocks = extract_code_blocks(markdown)

    if not blocks:
        # No code blocks - nothing to do, no API calls
        return markdown, {
            "gist_count": 0,
            "gist_urls": [],
            "errors": [],
            "skipped": True,
        }

    converted = markdown
    gist_urls: list[str] = []
    errors: list[str] = []

    for i, block in enumerate(blocks, start=1):
        description = f"{blog_title} - snippet {i} ({block.language})"
        gist_url, err = create_gist(
            code=block.code,
            language=block.language,
            description=description,
            index=i,
        )
        if gist_url:
            gist_urls.append(gist_url)
            # Replace ONLY the first occurrence (in case identical blocks repeat)
            # The Gist URL on its own line triggers Medium's embed behavior.
            replacement = f"\n\n{gist_url}\n\n"
            converted = converted.replace(block.full_match, replacement, 1)
            logger.info("Created gist %d/%d: %s", i, len(blocks), gist_url)
        else:
            errors.append(f"Block {i}: {err}")
            logger.warning("Failed to create gist %d: %s", i, err)
            # Leave the original code block in place

    return converted, {
        "gist_count": len(gist_urls),
        "gist_urls": gist_urls,
        "errors": errors,
        "skipped": False,
    }
