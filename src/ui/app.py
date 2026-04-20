"""Entrypoint for the Hedera technical blog generator UI."""

from __future__ import annotations

# Load .env FIRST, before any other imports. This ensures OPENAI_API_KEY,
# GEMINI_API_KEY, YOUTUBE_COOKIES_PATH, etc. are available to all modules.
from pathlib import Path

try:
    from dotenv import load_dotenv
    # Look for .env at the project root (2 levels up from this file)
    _env_path = Path(__file__).parent.parent.parent / ".env"
    if _env_path.exists():
        load_dotenv(_env_path)
except ImportError:
    pass

from ui.hedera_blog_app import build_app


if __name__ == "__main__":
    build_app().launch(server_name="0.0.0.0", server_port=None)
