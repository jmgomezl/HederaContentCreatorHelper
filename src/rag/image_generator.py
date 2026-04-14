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

# Imagen model selection notes (https://ai.google.dev/gemini-api/docs/pricing):
#   - imagen-4.0-fast-generate-001    ~$0.02 — cheapest but ignores "no text"
#                                              prompts and produces garbled letters
#   - imagen-4.0-generate-001          ~$0.04 — standard quality, follows negative
#                                              prompts reliably (RECOMMENDED)
#   - imagen-4.0-ultra-generate-001    ~$0.06 — best quality, 1.5x cost
#
# We use STANDARD (not fast) because the fast model produces garbled text in
# generated images. At 1 blog/week the difference is ~$1/year.
IMAGEN_MODEL = "imagen-4.0-generate-001"
IMAGEN_ENDPOINT = (
    f"https://generativelanguage.googleapis.com/v1beta/models/{IMAGEN_MODEL}:predict"
)
REQUEST_TIMEOUT = 120  # seconds (standard model is slightly slower than fast)


def is_enabled() -> bool:
    """Image generation is opt-in via ENABLE_IMAGE_GEN env var."""
    enabled = os.getenv("ENABLE_IMAGE_GEN", "false").lower() in ("true", "1", "yes")
    has_key = bool(os.getenv("GEMINI_API_KEY"))
    return enabled and has_key


def build_image_prompt(title: str, focus: str = "") -> str:
    """Build a concise image-gen prompt from blog metadata.

    IMPORTANT: This prompt is engineered to FORBID all text in the generated image.
    Text generators (including Imagen) often produce garbled, misspelled, or
    nonsensical text. The blog title is rendered separately in HTML, so the
    cover image only needs to be visual.

    The prompt strategy:
    1. Lead with the visual style description (positive instruction)
    2. NEVER mention "code", "screen", "monitor", "ui", "dashboard", "interface"
       in the visual hints — these strongly bias the model toward text-like content
    3. Use abstract terms: "geometric", "particles", "flows", "patterns"
    4. End with strong, repeated no-text constraints (negative instruction)
    """
    base = (
        "Abstract minimalist editorial illustration, futuristic technology theme, "
        "deep purple and dark navy gradient background, glowing geometric particles, "
        "flowing energy streams, soft volumetric lighting, cinematic depth of field, "
        "professional magazine cover style, ultra-clean composition. "
    )

    # Add a topic-specific visual hint - using ONLY abstract/visual descriptors,
    # never mentioning code, text, labels, screens, or anything letter-like.
    topic = title.lower()
    if "smart contract" in topic or "evm" in topic or "solidity" in topic:
        base += "Interconnected geometric nodes forming an abstract network mesh, glowing connections. "
    elif "token" in topic or "hts" in topic:
        base += "Translucent hexagonal crystal shapes floating in space with light beams between them. "
    elif "consensus" in topic or "hcs" in topic or "hashgraph" in topic:
        base += "Layered abstract topology of bright dots and curved light trails, organic network shapes. "
    elif "wallet" in topic or "identity" in topic or "device" in topic:
        base += "Abstract microchip silhouette with glowing circuit-like geometric tracings. "
    elif "defi" in topic or "lending" in topic or "stablecoin" in topic:
        base += "Curving abstract liquidity ribbons and floating geometric tokens in deep space. "
    elif "ai" in topic or "agent" in topic:
        base += "Abstract neural network of glowing nodes and pulses, organic data flows. "
    else:
        base += "Abstract Hedera ecosystem visualization with flowing energy and floating geometric particles. "

    # Strong, repeated negative constraints at the END (image models weight
    # tail instructions more heavily). Multiple phrasings of the same idea.
    base += (
        "PURELY ABSTRACT VISUAL ONLY. "
        "Strictly no text. No words. No letters. No numbers. No captions. "
        "No labels. No logos. No watermarks. No signs. No typography. "
        "No characters. No symbols that resemble writing. No book pages. "
        "No documents. No screens displaying text. No code editors. "
        "No user interface elements. No buttons with labels. "
        "The image must be 100 percent textless and purely visual."
    )

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
