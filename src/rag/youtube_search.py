"""Fetch recent Hedera livestreams from YouTube using scrapetube."""

from __future__ import annotations

import scrapetube

HEDERA_CHANNEL_ID = "UCIhE4NYpaX9E9SssFnwrjww"


def fetch_hedera_livestreams(limit: int = 10) -> tuple[list[dict], str | None]:
    """Fetch the latest livestreams from the Hedera YouTube channel.

    Returns:
        tuple: (list of video dicts with keys video_id/title/url, error message or None)
    """
    try:
        # Fetch extra to account for mobile/desktop duplicates
        videos = scrapetube.get_channel(
            channel_id=HEDERA_CHANNEL_ID,
            content_type="streams",
            limit=limit * 3,
        )
        results = []
        seen_titles: set[str] = set()
        for video in videos:
            video_id = video.get("videoId", "")
            title = (
                video.get("title", {}).get("runs", [{}])[0].get("text", "")
                if isinstance(video.get("title"), dict)
                else str(video.get("title", ""))
            )
            if not title:
                title = video_id

            # Deduplicate: skip mobile/vertical duplicates (same title with/without emoji)
            clean_title = title.encode("ascii", "ignore").decode().strip()
            if clean_title in seen_titles:
                continue
            seen_titles.add(clean_title)

            results.append({
                "video_id": video_id,
                "title": title,
                "url": f"https://www.youtube.com/watch?v={video_id}",
            })
            if len(results) >= limit:
                break
        if not results:
            return [], "No livestreams found for the Hedera channel."
        return results, None
    except Exception as exc:  # noqa: BLE001
        return [], f"Error fetching livestreams: {exc}"
