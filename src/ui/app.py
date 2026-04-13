"""Entrypoint for the Hedera technical blog generator UI."""

from __future__ import annotations

from ui.hedera_blog_app import build_app


if __name__ == "__main__":
    build_app().launch(server_name="0.0.0.0", server_port=None)
