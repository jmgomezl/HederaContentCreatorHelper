import os

import pytest

from rag.hedera_blog import create_medium_blog_from_youtube

try:
    from dotenv import load_dotenv

    load_dotenv()
except Exception:
    pass


@pytest.mark.slow
@pytest.mark.skipif(
    os.getenv("OPENAI_API_KEY") is None or os.getenv("RUN_LIVE_TESTS") != "1",
    reason="Requires OPENAI_API_KEY and RUN_LIVE_TESTS=1",
)
def test_publishable_blog_generation():
    blog, status = create_medium_blog_from_youtube(
        video_url="https://www.youtube.com/watch?v=rBWYdQI_ovc",
        audience="Web3 developers and Hedera builders",
        length="Medium",
        focus="Hedera native services, tooling, ecosystem updates",
        reference_links="",
        strict_mode=True,
        verbosity="Standard",
        length_multiplier=1,
        auto_iterate=True,
    )

    assert "Error" not in status
    assert blog.startswith("# ")
    assert "## TL;DR" in blog
    assert "## Key takeaways" in blog
    assert "Additional details" not in blog
