import html
import re
import urllib.parse
from collections.abc import Iterable


def attributes(tag: str) -> dict[str, str]:
    return {
        name.lower(): html.unescape(value)
        for name, _, value in re.findall(r"([\w:-]+)\s*=\s*([\"' ])([^\"']*)\2", tag)
    }


def image_url(base_url: str, value: str) -> str:
    value = html.unescape(value).strip()
    if not value or urllib.parse.urlparse(value).path in {"", "/"}:
        return ""
    return urllib.parse.urljoin(base_url, value)


def meta_values(page: str) -> dict[str, str]:
    values = {}
    for tag in re.findall(r"<meta\s+[^>]+>", page, re.IGNORECASE):
        values_for_tag = attributes(tag)
        name = values_for_tag.get("property") or values_for_tag.get("name")
        if name and values_for_tag.get("content"):
            values[name.lower()] = values_for_tag["content"].strip()
    return values


def favicon(page: str, base_url: str) -> str:
    icons = []
    for tag in re.findall(r"<link\b[^>]*>", page, re.IGNORECASE):
        values = attributes(tag)
        relation = values.get("rel", "").lower()
        source = image_url(base_url, values.get("href", ""))
        if "icon" not in relation or not source:
            continue
        size = max(
            (int(value) for value in re.findall(r"\d+", values.get("sizes", ""))),
            default=0,
        )
        icons.append(("apple-touch" in relation, size, source))
    return max(icons, default=(False, 0, ""))[2]


def page_avatar(
    page: str,
    base_url: str,
    names: Iterable[str] = ("avatar", "logo", "portrait"),
) -> str:
    names = tuple(name.lower() for name in names)
    header = re.search(
        r"<header\b[^>]*>(.*?)</header>", page, re.IGNORECASE | re.DOTALL
    )
    areas = [header.group(1)] if header else []
    areas.append(page)
    for area in areas:
        images = re.findall(r"<img\b[^>]*>", area, re.IGNORECASE)
        preferred = sorted(
            images,
            key=lambda tag: any(
                name
                in (
                    attributes(tag).get("class", "")
                    + " "
                    + attributes(tag).get("alt", "")
                ).lower()
                for name in names
            ),
            reverse=True,
        )
        for tag in preferred:
            values = attributes(tag)
            identity = (values.get("class", "") + " " + values.get("alt", "")).lower()
            if any(name in identity for name in names):
                if source := image_url(base_url, values.get("src", "")):
                    return source
    return favicon(page, base_url)
