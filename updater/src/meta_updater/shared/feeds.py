import time
import urllib.error
import urllib.request
import xml.etree.ElementTree as ET
from typing import Any
from .provenance import track_provenance

ATOM = "http://www.w3.org/2005/Atom"
MEDIA = "http://search.yahoo.com/mrss/"


def _entry_tags(element: ET.Element, media: ET.Element | None = None) -> list[str]:
    """Return only category/tag values explicitly supplied by the feed entry."""
    values = []
    for child in element:
        local_name = child.tag.rsplit("}", 1)[-1].lower()
        if local_name not in {"category", "subject"}:
            continue
        scheme = child.get("scheme", "")
        term = child.get("term", "")
        if "schemas.google.com/g/2005#kind" in scheme or term.endswith("#video"):
            continue
        value = child.get("label") or term or child.text or ""
        value = " ".join(value.split())
        if value:
            values.append(value)
    if media is not None:
        for child in media:
            local_name = child.tag.rsplit("}", 1)[-1].lower()
            if local_name == "keywords" and child.text:
                values.extend(part.strip() for part in child.text.split(","))
            elif local_name == "category":
                value = child.get("label") or child.text or ""
                if value.strip():
                    values.append(value.strip())
    return list(dict.fromkeys(value for value in values if value))


def fetch(url: str, timeout: float, headers: dict[str, str], retries: int = 4) -> bytes:
    request = urllib.request.Request(url, headers=headers)
    track_provenance(url)
    for attempt in range(retries):
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:
                return response.read()
        except urllib.error.HTTPError as error:
            if error.code != 429 and error.code < 500:
                raise
            if attempt == retries - 1:
                raise
            retry_after = error.headers.get("Retry-After")
            time.sleep(float(retry_after) if retry_after else 2**attempt)
        except urllib.error.URLError:
            if attempt == retries - 1:
                raise
            time.sleep(2**attempt)
    raise RuntimeError(f"failed to fetch {url}")


def atom_entries(
    document: bytes, extensions: dict[str, str] | None = None
) -> list[dict[str, Any]]:
    root = ET.fromstring(document)
    result = []
    for element in root.findall(f"{{{ATOM}}}entry"):
        link = element.find(f"{{{ATOM}}}link[@rel='alternate']")
        media = element.find(f"{{{MEDIA}}}group")
        thumbnail = media.find(f"{{{MEDIA}}}thumbnail") if media is not None else None
        entry = {
            "id": element.findtext(f"{{{ATOM}}}id", "").strip(),
            "title": element.findtext(f"{{{ATOM}}}title", "").strip(),
            "url": link.get("href", "") if link is not None else "",
            "published": element.findtext(f"{{{ATOM}}}published", "").strip(),
            "updated": element.findtext(f"{{{ATOM}}}updated", "").strip(),
            "description": media.findtext(f"{{{MEDIA}}}description", "").strip()
            if media is not None
            else "",
            "thumbnail_url": thumbnail.get("url", "") if thumbnail is not None else "",
            "tags": _entry_tags(element, media),
        }
        for name, path in (extensions or {}).items():
            entry[name] = element.findtext(path, "").strip()
        result.append(entry)
    return result


def feed_entries(document: bytes) -> list[dict[str, Any]]:
    root = ET.fromstring(document)
    if root.tag == f"{{{ATOM}}}feed":
        entries = atom_entries(document)
        for entry, element in zip(
            entries, root.findall(f"{{{ATOM}}}entry"), strict=True
        ):
            if not entry["description"]:
                entry["description"] = (
                    element.findtext(f"{{{ATOM}}}summary", "")
                    or element.findtext(f"{{{ATOM}}}content", "")
                ).strip()
        return entries

    channel = root.find("channel") if root.tag == "rss" else root
    result = []
    for item in channel.findall("item"):
        link = item.findtext("link", "").strip()
        atom_link = next(
            (
                element
                for element in item.findall(f"{{{ATOM}}}link")
                if element.get("rel") == "alternate"
            ),
            None,
        )
        result.append(
            {
                "id": item.findtext("guid", "").strip() or link,
                "title": item.findtext("title", "").strip(),
                "url": link
                or (atom_link.get("href", "") if atom_link is not None else ""),
                "published": item.findtext("pubDate", "").strip(),
                "updated": item.findtext(f"{{{ATOM}}}updated", "").strip(),
                "description": (
                    item.findtext("description", "")
                    or item.findtext(
                        "{http://purl.org/rss/1.0/modules/content/}encoded", ""
                    )
                ).strip(),
                "thumbnail_url": "",
                "tags": _entry_tags(item),
            }
        )
    return result
