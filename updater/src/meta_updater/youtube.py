import json
import re
import shlex
import sys
from datetime import UTC, date, datetime
from time import sleep
from typing import Any
from urllib.error import HTTPError

from .shared.feeds import atom_entries, fetch

YT = "http://www.youtube.com/xml/schemas/2015"
HEADERS = {
    "User-Agent": (
        "ozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/148.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "en-US,en;q=0.8",
}


def _image(sources: list[dict[str, Any]], width: int) -> str:
    if not sources:
        return ""
    return min(sources, key=lambda item: abs(item.get("width", 0) - width)).get(
        "url", ""
    )


def channel_metadata(channel_id: str, timeout: float) -> dict[str, Any]:
    page_url = f"https://www.youtube.com/channel/{channel_id}"
    page = fetch(page_url, timeout, HEADERS).decode("utf-8", "replace")
    marker = '"channelMetadataRenderer":'
    start = page.find(marker)
    if start < 0:
        raise ValueError(f"missing channel metadata for {channel_id}")
    metadata, _ = json.JSONDecoder().raw_decode(page[start + len(marker):])
    initial_match = re.search(r"var ytInitialData = (\{.*?\});</script>", page)
    if not initial_match:
        raise ValueError(f"missing ytInitialData for {channel_id}")
    view = (
        json.loads(initial_match.group(1))
        .get("header", {})
        .get("pageHeaderRenderer", {})
        .get("content", {})
        .get("pageHeaderViewModel", {})
    )
    banners = (
        view.get("banner", {})
        .get("imageBannerViewModel", {})
        .get("image", {})
        .get("sources", [])
    )
    try:
        keywords = shlex.split(metadata.get("keywords", ""))
    except ValueError:
        keywords = metadata.get("keywords", "").split()
    url = metadata.get("vanityChannelUrl") or metadata.get(
        "channelUrl") or page_url
    return {
        "url": url,
        "description": metadata.get("description", "").strip(),
        "keywords": keywords,
        "avatar_url": _image(
            metadata.get("avatar", {}).get("thumbnails", []), 900
        ),
        "banner_url": _image(banners, 1060),
        "source_url": f"{url.rstrip('/')}/about",
    }


def channel_videos(channel_id: str, timeout: float) -> list[dict[str, Any]]:
    url = f"https://www.youtube.com/feeds/videos.xml?channel_id={channel_id}"

    document: bytes = b""
    retries = 3
    while retries > 0:
        retries -= 1
        try:
            document = fetch(url, timeout, HEADERS)
        except HTTPError as error:
            if error.code != 404:
                raise
            if retries == 0:
                print(f"warning: failed to fetch {url}: {error}", file=sys.stderr)
                return []
            sleep(0.5)
    entries = atom_entries(document, {"video_id": f"{{{YT}}}videoId"})
    result = []
    for entry in entries:
        if not entry["video_id"] or not entry["title"] or not entry["published"]:
            raise ValueError(f"incomplete RSS entry for {channel_id}")
        result.append(
            {
                "video_id": entry["video_id"],
                "title": entry["title"],
                "url": entry["url"] or f"https://youtu.be/{entry['video_id']}",
                "published": datetime.fromisoformat(
                    entry["published"].replace("Z", "+00:00")
                ).astimezone(UTC),
                "updated": datetime.fromisoformat(
                    entry["updated"].replace("Z", "+00:00")
                ).astimezone(UTC)
                if entry["updated"]
                else None,
                "description": entry["description"],
                "thumbnail_url": entry["thumbnail_url"],
                "tags": entry["tags"],
            }
        )
    return result


def normalize_video(item: Any) -> dict[str, Any]:
    data = item.model_dump() if hasattr(item, "model_dump") else dict(item)
    for name in ("published", "updated"):
        value = data.get(name)
        if isinstance(value, date) and not isinstance(value, datetime):
            data[name] = datetime.combine(value, datetime.min.time(), UTC)
    return data
