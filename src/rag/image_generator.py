"""Generate cover images for blog posts using Gemini Imagen.

Cost control:
- ONE image per blog (never more)
- Cached by slug: re-publishing the same slug uses the existing image
- Hard kill-switch via ENABLE_IMAGE_GEN env var
- Uses imagen-4.0-fast-generate-001 (the cheapest Imagen model)
- Returns gracefully if API key missing or call fails (no image, no exception)
"""

from __future__ import annotations

import base64
import logging
import os
from pathlib import Path

import requests

logger = logging.getLogger(__name__)

# Cheapest Imagen model — see https://ai.google.dev/gemini-api/docs/pricing
IMAGEN_MODEL = "imagen-4.0-fast-generate-001"
IMAGEN_ENDPOINT = (
    f"https://generativelanguage.googleapis.com/v1beta/models/{IMAGEN_MODEL}:predict"
)
REQUEST_TIMEOUT = 90  # seconds


def is_enabled() -> bool:
    """Image generation is opt-in via ENABLE_IMAGE_GEN env var."""
    enabled = os.getenv("ENABLE_IMAGE_GEN", "false").lower() in ("true", "1", "yes")
    has_key = bool(os.getenv("GEMINI_API_KEY"))
    return enabled and has_key


def build_image_prompt(title: str, focus: str = "") -> str:
    """Build a concise image-gen prompt from blog metadata.

    IMPORTANT: This prompt is engineered to FORBID all text in the generated image.
    Text generators (including Imagen) often produce garbled, misspelled, or
    nonsensical text. The safest approach is to instruct the model to never
    include any text, words, letters, numbers, or logos. The blog title is
    rendered in HTML separately, so the cover image only needs to be visual.
    """
    # Strong negative-text constraints repeated for emphasis - Imagen respects
    # repetition more than single mentions.
    no_text_clause = (
        "ABSOLUTELY NO TEXT in the image. No words, no letters, no numbers, "
        "no captions, no labels, no logos, no signage, no watermarks, no symbols "
        "that resemble characters. The image must be purely visual and abstract. "
    )

    base = (
        "Modern minimalist tech blog cover image, abstract geometric shapes, "
        "deep purple and dark blue gradient background, subtle blockchain network "
        "patterns, professional editorial style, cinematic lighting. "
        + no_text_clause
    )

    # Add a topic-specific visual hint
    topic = title.lower()
    if "smart contract" in topic or "evm" in topic or "solidity" in topic:
        base += "Stylized abstract code blocks and contract diagrams floating in space (no readable text). "
    elif "token" in topic or "hts" in topic:
        base += "Glowing hexagonal token shapes connected by light streams (no text or numbers on the tokens). "
    elif "consensus" in topic or "hcs" in topic or "hashgraph" in topic:
        base += "Interconnected nodes forming a directed acyclic graph network. "
    elif "wallet" in topic or "identity" in topic or "device" in topic:
        base += "Secure hardware chip with circuit traces and microelectronic patterns. "
    elif "defi" in topic or "lending" in topic or "stablecoin" in topic:
        base += "Financial dashboard with abstract liquidity flows and curved data streams. "
    else:
        base += "Hedera ecosystem visualization with flowing data streams and geometric particles. "

    return base


def generate_image(
    title: str,
    slug: str,
    output_dir: Path,
    focus: str = "",
    force: bool = False,
) -> tuple[str, str]:
    """Generate a cover image for a blog post and save it to disk.

    Args:
        title: Blog title (used in the image prompt).
        slug: URL slug (used as the filename and cache key).
        output_dir: Directory where the image PNG will be saved.
        focus: Optional focus areas to bias the prompt.
        force: If True, regenerate even if a cached image exists.

    Returns:
        tuple: (relative_image_path, error_message_or_empty)
            - On success: ("image-{slug}.png", "")
            - On failure or disabled: ("", reason)
    """
    if not is_enabled():
        return "", "Image generation disabled (ENABLE_IMAGE_GEN=false or no GEMINI_API_KEY)"

    output_dir.mkdir(parents=True, exist_ok=True)
    image_filename = f"image-{slug}.png"
    image_path = output_dir / image_filename

    # Cache hit: don't re-generate (saves money)
    if image_path.exists() and not force:
        logger.info("Image cache hit: %s", image_filename)
        return image_filename, ""

    api_key = os.getenv("GEMINI_API_KEY")
    prompt = build_image_prompt(title, focus)

    payload = {
        "instances": [{"prompt": prompt}],
        "parameters": {
            "sampleCount": 1,  # ALWAYS 1 to control cost
            "aspectRatio": "16:9",  # Wide cover for blog header
        },
    }

    try:
        resp = requests.post(
            f"{IMAGEN_ENDPOINT}?key={api_key}",
            json=payload,
            timeout=REQUEST_TIMEOUT,
        )
    except requests.RequestException as exc:
        logger.warning("Image gen request failed: %s", exc)
        return "", f"Request error: {exc}"

    if resp.status_code != 200:
        logger.warning("Image gen API returned %d: %s", resp.status_code, resp.text[:200])
        return "", f"API error {resp.status_code}: {resp.text[:200]}"

    try:
        predictions = resp.json().get("predictions", [])
        if not predictions:
            return "", "No predictions returned"
        b64 = predictions[0].get("bytesBase64Encoded", "")
        if not b64:
            return "", "Empty image data"
        image_path.write_bytes(base64.b64decode(b64))
        logger.info("Image saved: %s (%d bytes)", image_filename, image_path.stat().st_size)
        return image_filename, ""
    except Exception as exc:
        logger.warning("Failed to decode/save image: %s", exc)
        return "", f"Decode error: {exc}"
