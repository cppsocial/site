import base64
import hashlib
import html
import re
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime
from typing import Any

import markdown

from .feeds import feed_entries, fetch
from .images import attributes as html_attributes
from .images import meta_values, page_avatar
from .provenance import track_provenance

HEADERS = {
    "User-Agent": "cpp.social feed updater (+https://cpp.social/contributing/)",
    "Accept-Language": "en-US,en;q=0.8",
}


def post_id(source_id: str, url: str) -> str:
    """Return a compact, stable ID without repeating the post URL."""
    identity = f"{source_id}\0{url}".encode()
    digest = hashlib.sha256(identity).digest()[:12]
    return base64.urlsafe_b64encode(digest).decode("ascii").rstrip("=")


def render_description(value: str) -> str:
    """Render feed text for compact browser storage without a redundant paragraph."""
    rendered = markdown.markdown(value)
    if rendered.startswith("<p>") and rendered.endswith("</p>"):
        inner = rendered[3:-4]
        if "<p>" not in inner and "</p>" not in inner:
            return inner
    return rendered


def _datetime(value: str) -> datetime | None:
    if not value:
        return None
    try:
        result = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        result = parsedate_to_datetime(value)
    if result.tzinfo is None:
        result = result.replace(tzinfo=UTC)
    return result.astimezone(UTC)


def _text(value: str, limit: int = 280) -> str:
    value = re.sub(r"<[^>]+>", " ", value)
    value = " ".join(html.unescape(value).split())
    return value if len(value) <= limit else value[: limit - 1].rstrip() + "…"


def posts(source: dict[str, Any], timeout: float) -> list[dict[str, Any]]:
    result = []
    for entry in feed_entries(fetch(source["rss_url"], timeout, HEADERS)):
        published = _datetime(entry["published"] or entry["updated"])
        if not entry["title"] or not entry["url"] or published is None:
            continue
        result.append(
            {
                "post_id": post_id(source["id"], entry["url"]),
                "source_id": source["id"],
                "source_title": source["title"],
                "title": _text(entry["title"], 180),
                "url": entry["url"],
                "published": published,
                "updated": _datetime(entry["updated"]),
                "description": _text(entry["description"]),
                "tags": entry["tags"],
            }
        )
    if not result:
        raise ValueError(f"feed returned no usable posts for {source['id']}")
    return result


def _header_description(page: str) -> str:
    candidates = []
    pattern = r"<(?:p|div|span|h[1-6])\b([^>]*)>(.*?)</(?:p|div|span|h[1-6])>"
    for attributes, content in re.findall(pattern, page, re.IGNORECASE | re.DOTALL):
        classes = html_attributes(attributes).get("class", "").lower()
        score = next(
            (
                score
                for name, score in (
                    ("site-subtitle", 4),
                    ("site-description", 3),
                    ("tagline", 2),
                    ("subtitle", 1),
                )
                if name in classes
            ),
            0,
        )
        value = _text(content, 320)
        if score and value:
            candidates.append((score, value))
    return max(candidates, default=(0, ""))[1]


def metadata(source: dict[str, Any], timeout: float) -> dict[str, Any]:
    page = fetch(source["website_url"], timeout, HEADERS).decode("utf-8", "replace")

    values = meta_values(page)
    title = re.search(r"<title>(.*?)</title>", page, re.IGNORECASE | re.DOTALL)
    title = _text(title.group(1), 320) if title else ""
    title_description = re.split(r"\s+[–—|]\s+", title, maxsplit=1)
    keywords = [
        keyword.strip()
        for keyword in values.get("keywords", "").split(",")
        if keyword.strip()
    ]
    return {
        "description": _header_description(page)
        or values.get("og:description", values.get("description", ""))
        or (title_description[1] if len(title_description) > 1 else ""),
        "keywords": list(dict.fromkeys(keywords)),
        "avatar_url": page_avatar(page, source["website_url"]),
        "source_url": source["website_url"],
    }


def normalize_post(item: Any) -> dict[str, Any]:
    data = item.model_dump() if hasattr(item, "model_dump") else dict(item)
    data["post_id"] = post_id(data["source_id"], data["url"])
    return data
