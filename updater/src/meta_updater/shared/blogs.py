import base64
import gzip
import hashlib
import html
import json
import re
import urllib.parse
import xml.etree.ElementTree as ET
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime
from typing import Any

from .feeds import feed_entries, fetch
from .images import attributes as html_attributes
from .images import meta_values, page_avatar
from .provenance import suppress_provenance
from .text import render_text, sanitize_unicode

HEADERS = {
    "User-Agent": "cpp.social feed updater (+https://cpp.social/contributing/)",
    "Accept-Language": "en-US,en;q=0.8",
}

ARTICLE_TYPES = {"article", "blogposting", "newsarticle", "techarticle"}

# These paths either cannot contain an HTML article or conventionally identify
# generated indexes and site chrome. Keep this list deliberately conservative:
# ambiguous pages are still fetched and rejected later by ``sitemap_post``.
NON_POST_PATH_PARTS = {
    "_next",
    "assets",
    "atom",
    "author",
    "authors",
    "categories",
    "category",
    "css",
    "downloads",
    "feed",
    "feeds",
    "fonts",
    "images",
    "img",
    "js",
    "media",
    "search",
    "static",
    "tag",
    "tags",
    "wp-admin",
    "wp-content",
    "wp-includes",
    "wp-json",
}
NON_POST_PAGE_NAMES = {
    "about",
    "about-us",
    "archive",
    "archives",
    "contact",
    "contact-us",
    "cookie-policy",
    "disclaimer",
    "privacy",
    "privacy-policy",
    "sitemap",
    "terms",
    "terms-and-conditions",
    "terms-of-service",
}
NON_HTML_SUFFIXES = {
    ".7z",
    ".avi",
    ".avif",
    ".bin",
    ".bz2",
    ".css",
    ".csv",
    ".doc",
    ".docx",
    ".eot",
    ".epub",
    ".gif",
    ".gz",
    ".ico",
    ".jpeg",
    ".jpg",
    ".js",
    ".json",
    ".m4a",
    ".mov",
    ".mp3",
    ".mp4",
    ".mpeg",
    ".ogg",
    ".otf",
    ".pdf",
    ".png",
    ".ppt",
    ".pptx",
    ".rar",
    ".rss",
    ".svg",
    ".tar",
    ".tgz",
    ".tif",
    ".tiff",
    ".ttf",
    ".txt",
    ".wav",
    ".webm",
    ".webp",
    ".woff",
    ".woff2",
    ".xls",
    ".xlsx",
    ".xml",
    ".zip",
}
POST_SITEMAP_NAMES = re.compile(
    r"^(?:wp-sitemap-posts-post(?:-\d+)?|post-sitemap\d*|sitemap-posts)"
    r"\.xml(?:\.gz)?$",
    re.IGNORECASE,
)
NON_POST_SITEMAP_NAMES = re.compile(
    r"^(?:"
    r"wp-sitemap-(?:posts-(?:attachment|page)|taxonomies|users)(?:-\w+)*(?:-\d+)?"
    r"|(?:author|category|page|post_tag|tag)-sitemap\d*"
    r"|sitemap-(?:authors|pages|tags)"
    r")\.xml(?:\.gz)?$",
    re.IGNORECASE,
)
PAGINATION_PATH_PART = re.compile(r"page\d+", re.IGNORECASE)
POST_LISTING_NAMES = {"archive", "archives", "blog", "posts", "timeline"}


def post_id(source_id: str, url: str) -> str:
    """Return a compact, stable ID without repeating the post URL."""
    identity = f"{source_id}\0{url}".encode()
    digest = hashlib.sha256(identity).digest()[:12]
    return base64.urlsafe_b64encode(digest).decode("ascii").rstrip("=")


def render_description(value: str) -> str:
    """Render feed text for compact browser storage without a redundant paragraph."""
    return render_text(value, media_type="text/markdown").body_html


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
    value = " ".join(sanitize_unicode(html.unescape(value)).split())
    return value if len(value) <= limit else value[: limit - 1].rstrip() + "…"


def _posts_from_document(
    source: dict[str, Any], document: bytes
) -> list[dict[str, Any]]:
    result = []
    for entry in feed_entries(document):
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
                "tags": [
                    cleaned
                    for value in entry["tags"]
                    if (cleaned := " ".join(sanitize_unicode(value).split()))
                ],
            }
        )
    if not result:
        raise ValueError(f"feed returned no usable posts for {source['id']}")
    return result


def _feed_cms(document: bytes) -> str:
    """Identify common publishing systems from standard feed generators."""
    try:
        root = ET.fromstring(document)
    except ET.ParseError:
        return ""
    generators = []
    for element in root.iter():
        if _local_name(element) == "generator":
            generators.extend([element.text or "", *element.attrib.values()])
    signal = " ".join(generators).casefold()
    for cms in ("wordpress", "jekyll", "ghost", "hugo", "blogger"):
        if cms in signal:
            return cms
    return ""


def feed_posts_and_cms(
    source: dict[str, Any], timeout: float
) -> tuple[list[dict[str, Any]], str]:
    """Read guaranteed post records and CMS information from the source feed."""
    document = fetch(source["rss_url"], timeout, HEADERS)
    return _posts_from_document(source, document), _feed_cms(document)


def posts(source: dict[str, Any], timeout: float) -> list[dict[str, Any]]:
    return feed_posts_and_cms(source, timeout)[0]


def _local_name(element: ET.Element) -> str:
    return element.tag.rsplit("}", 1)[-1].lower()


def _sitemap_document(document: bytes) -> ET.Element:
    if document.startswith(b"\x1f\x8b"):
        document = gzip.decompress(document)
    return ET.fromstring(document)


def _normalized_host(value: str) -> str:
    host = (urllib.parse.urlparse(value).hostname or "").casefold().rstrip(".")
    return host.removeprefix("www.")


def _relative_url_parts(source: dict[str, Any], value: str) -> list[str] | None:
    url = urllib.parse.urlparse(value)
    website = urllib.parse.urlparse(source["website_url"])
    path = urllib.parse.unquote(url.path)
    site_path = urllib.parse.unquote(website.path).rstrip("/")
    if site_path and path.rstrip("/") != site_path and not path.startswith(
        site_path + "/"
    ):
        return None
    relative = path[len(site_path):].strip("/") if site_path else path.strip("/")
    return [part.casefold() for part in relative.split("/") if part]


def _sitemap_candidate(source: dict[str, Any], entry: dict[str, str]) -> bool:
    """Return whether a sitemap URL is worth fetching as a possible post."""
    url = urllib.parse.urlparse(entry["loc"])
    if url.scheme.casefold() not in {"http", "https"}:
        return False
    if _normalized_host(entry["loc"]) != _normalized_host(source["website_url"]):
        return False

    parts = _relative_url_parts(source, entry["loc"])
    if not parts:
        return False

    if any(part in NON_POST_PATH_PARTS for part in parts):
        return False
    if parts[-1] in NON_POST_PAGE_NAMES:
        return False
    if any(PAGINATION_PATH_PART.fullmatch(part) for part in parts):
        return False
    if any(
        left == "page" and right.isdecimal()
        for left, right in zip(parts, parts[1:], strict=False)
    ):
        return False
    if any(parts[-1].endswith(suffix) for suffix in NON_HTML_SUFFIXES):
        return False

    query = urllib.parse.parse_qs(url.query, keep_blank_values=True)
    if {name.casefold() for name in query} & {
        "attachment_id",
        "feed",
        "preview",
        "s",
    }:
        return False
    return True


def post_listing_kind(source: dict[str, Any], value: str) -> str:
    """Classify sitemap URLs that may enumerate posts rather than be posts."""
    parts = _relative_url_parts(source, value)
    if parts == []:
        return "home"
    if not parts:
        return ""
    if parts[-1] in POST_LISTING_NAMES:
        return "archive"
    if any(PAGINATION_PATH_PART.fullmatch(part) for part in parts) or any(
        left == "page" and right.isdecimal()
        for left, right in zip(parts, parts[1:], strict=False)
    ):
        return "pagination"
    return ""


def page_links(source: dict[str, Any], page_url: str, document: bytes) -> set[str]:
    """Extract in-publication HTTP links from a post listing page."""
    page = document.decode("utf-8", "replace")
    result = set()
    for tag in re.findall(r"<a\b[^>]*>", page, re.IGNORECASE):
        href = html_attributes(tag).get("href", "").strip()
        if not href:
            continue
        url = urllib.parse.urljoin(page_url, html.unescape(href))
        parsed = urllib.parse.urlparse(url)
        if parsed.scheme.casefold() not in {"http", "https"}:
            continue
        if _normalized_host(url) != _normalized_host(source["website_url"]):
            continue
        if _relative_url_parts(source, url) is None:
            continue
        result.add(urllib.parse.urlunparse(parsed._replace(fragment="")))
    return result


def post_url_family(
    source: dict[str, Any], urls: list[str]
) -> tuple[str, ...] | None:
    """Learn a stable post path shape from the source's recent feed URLs."""
    paths = [_relative_url_parts(source, url) for url in urls]
    if len(paths) < 2 or any(not parts for parts in paths):
        return None
    complete = [parts for parts in paths if parts]
    depths = {len(parts) for parts in complete}
    if len(depths) != 1:
        return None

    family = []
    for index, column in enumerate(zip(*complete, strict=True)):
        values = set(column)
        if all(re.fullmatch(r"(?:19|20|21)\d{2}", value) for value in values):
            family.append("{year}")
        elif index > 0 and family[-1] == "{year}" and all(
            value.isdecimal() and 1 <= int(value) <= 12 for value in values
        ):
            family.append("{month}")
        elif index > 0 and family[-1] == "{month}" and all(
            value.isdecimal() and 1 <= int(value) <= 31 for value in values
        ):
            family.append("{day}")
        elif len(values) == 1:
            family.append(next(iter(values)))
        else:
            family.append("*")
    family[-1] = "*"
    if len(family) == 1 or all(part == "*" for part in family):
        return None
    return tuple(family)


def matches_post_url_family(
    source: dict[str, Any], value: str, family: tuple[str, ...]
) -> bool:
    parts = _relative_url_parts(source, value)
    if not parts or len(parts) != len(family):
        return False
    for part, expected in zip(parts, family, strict=True):
        if expected == "*":
            continue
        if expected == "{year}" and re.fullmatch(r"(?:19|20|21)\d{2}", part):
            continue
        if expected == "{month}" and part.isdecimal() and 1 <= int(part) <= 12:
            continue
        if expected == "{day}" and part.isdecimal() and 1 <= int(part) <= 31:
            continue
        if part != expected:
            return False
    return True


def _post_sitemap_urls(index_url: str, locations: list[str]) -> list[str]:
    """Prefer CMS-provided post maps and discard known non-post maps."""
    urls = [urllib.parse.urljoin(index_url, location) for location in locations]

    def filename(url: str) -> str:
        return urllib.parse.unquote(urllib.parse.urlparse(url).path).rsplit("/", 1)[-1]

    post_urls = [url for url in urls if POST_SITEMAP_NAMES.fullmatch(filename(url))]
    if post_urls:
        return post_urls
    return [
        url
        for url in urls
        if not NON_POST_SITEMAP_NAMES.fullmatch(filename(url))
    ]


def _robots_sitemaps(source: dict[str, Any], timeout: float) -> list[str]:
    website = urllib.parse.urlparse(source["website_url"])
    robots_url = urllib.parse.urlunparse(
        (website.scheme, website.netloc, "/robots.txt", "", "", "")
    )
    try:
        with suppress_provenance():
            document = fetch(robots_url, timeout, HEADERS).decode(
                "utf-8", "replace"
            )
    except OSError:
        return []
    return list(
        dict.fromkeys(
            urllib.parse.urljoin(robots_url, match.strip())
            for match in re.findall(
                r"^\s*sitemap\s*:\s*(\S+)", document, re.IGNORECASE | re.MULTILINE
            )
        )
    )


def sitemap_discovery(
    source: dict[str, Any], timeout: float, *, cms: str = ""
) -> tuple[list[dict[str, str]], list[str]]:
    """Discover post candidates and post-listing pages from sitemap(s)."""
    override = source.get("sitemap_url", "").strip()
    if override:
        roots = [urllib.parse.urljoin(source["website_url"], override)]
        fallbacks: list[str] = []
    else:
        roots = _robots_sitemaps(source, timeout)
        website = urllib.parse.urlparse(source["website_url"])
        conventional = urllib.parse.urlunparse(
            (website.scheme, website.netloc, "/sitemap.xml", "", "", "")
        )
        fallbacks = [conventional]
        if cms == "wordpress":
            fallbacks = [
                urllib.parse.urlunparse(
                    (website.scheme, website.netloc, path, "", "", "")
                )
                for path in ("/wp-sitemap.xml", "/sitemap_index.xml", "/sitemap.xml")
            ]
        if not roots:
            roots = [fallbacks.pop(0)]

    pending = list(roots)
    visited: set[str] = set()
    result: list[dict[str, str]] = []
    listings: list[str] = []
    failures: list[Exception] = []
    while pending or (not result and any(url not in visited for url in fallbacks)):
        if not pending:
            pending.append(next(url for url in fallbacks if url not in visited))
        sitemap_url = pending.pop(0)
        if sitemap_url in visited:
            continue
        visited.add(sitemap_url)
        try:
            with suppress_provenance():
                root = _sitemap_document(fetch(sitemap_url, timeout, HEADERS))
        except (OSError, ET.ParseError, gzip.BadGzipFile) as error:
            failures.append(error)
            continue
        if _local_name(root) == "sitemapindex":
            locations = []
            for item in root:
                location = next(
                    (child.text or "" for child in item if _local_name(child) == "loc"),
                    "",
                ).strip()
                if location:
                    locations.append(location)
            pending.extend(_post_sitemap_urls(sitemap_url, locations))
            continue
        if _local_name(root) != "urlset":
            continue
        page_entries: list[dict[str, str]] = []
        for item in root:
            values: dict[str, str] = {}
            for child in item.iter():
                name = _local_name(child)
                value = " ".join((child.text or "").split())
                if name in {"loc", "lastmod", "publication_date", "title"} and value:
                    values.setdefault(name, value)
            if values.get("loc"):
                values["loc"] = urllib.parse.urljoin(sitemap_url, values["loc"])
                page_entries.append(values)
                if post_listing_kind(source, values["loc"]):
                    listings.append(values["loc"])
        result.extend(
            values
            for values in page_entries
            if _sitemap_candidate(source, values)
        )

    if not result:
        if failures and len(failures) == len(visited):
            raise ValueError(
                f"no readable sitemap found for {source['id']}: {failures[-1]}"
            )
        raise ValueError(f"sitemap returned no URLs for {source['id']}")
    unique: dict[str, dict[str, str]] = {}
    for item in result:
        unique.setdefault(item["loc"], item)
    return list(unique.values()), list(dict.fromkeys(listings))


def sitemap_entries(
    source: dict[str, Any], timeout: float, *, cms: str = ""
) -> list[dict[str, str]]:
    """Discover and recursively read a blog's sitemap(s)."""
    return sitemap_discovery(source, timeout, cms=cms)[0]


def _json_articles(page: str) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []

    def visit(value: Any) -> None:
        if isinstance(value, list):
            for item in value:
                visit(item)
        elif isinstance(value, dict):
            article_type = value.get("@type", "")
            types = article_type if isinstance(article_type, list) else [article_type]
            if any(str(item).casefold() in ARTICLE_TYPES for item in types):
                result.append(value)
            if "@graph" in value:
                visit(value["@graph"])

    for content in re.findall(
        r"<script\b[^>]*type\s*=\s*['\"]application/ld\+json['\"][^>]*>(.*?)</script>",
        page,
        re.IGNORECASE | re.DOTALL,
    ):
        try:
            visit(json.loads(html.unescape(content)))
        except json.JSONDecodeError:
            continue
    return result


def _first(*values: Any) -> str:
    for value in values:
        if isinstance(value, str) and value.strip():
            return value.strip()
    return ""


def _page_meta_values(page: str, name: str) -> list[str]:
    result = []
    for tag in re.findall(r"<meta\s+[^>]+>", page, re.IGNORECASE):
        values = html_attributes(tag)
        identity = values.get("property") or values.get(
            "name") or values.get("itemprop")
        if identity and identity.casefold() == name.casefold() and values.get("content"):
            result.append(values["content"].strip())
    return result


def _page_date(page: str, identities: tuple[str, ...]) -> str:
    for tag in re.findall(r"<time\b[^>]*>", page, re.IGNORECASE):
        values = html_attributes(tag)
        identity = " ".join(
            (values.get("itemprop", ""), values.get("class", ""))
        ).casefold()
        if any(name.casefold() in identity for name in identities):
            if value := values.get("datetime") or values.get("content"):
                return value
    return ""


def _optional_datetime(value: str) -> datetime | None:
    try:
        return _datetime(value)
    except (TypeError, ValueError, OverflowError):
        return None


def sitemap_post(
    source: dict[str, Any], entry: dict[str, str], page_document: bytes
) -> dict[str, Any] | None:
    """Build a complete cached post from article metadata on a sitemap page."""
    url = entry["loc"]
    page = page_document.decode("utf-8", "replace")
    values = meta_values(page)
    articles = _json_articles(page)
    article = articles[0] if articles else {}

    published_value = _first(
        values.get("article:published_time"),
        values.get("datepublished"),
        values.get("date"),
        *_page_meta_values(page, "datePublished"),
        article.get("datePublished"),
        _page_date(page, ("datePublished", "published", "posted", "entry-date")),
        entry.get("publication_date"),
    )
    published = _optional_datetime(published_value)
    if published is None:
        return None

    title_element = re.search(
        r"<title\b[^>]*>(.*?)</title>", page, re.IGNORECASE | re.DOTALL
    )
    heading = re.search(r"<h1\b[^>]*>(.*?)</h1>", page, re.IGNORECASE | re.DOTALL)
    title = _text(
        _first(
            values.get("og:title"),
            values.get("twitter:title"),
            values.get("title"),
            article.get("headline"),
            article.get("name"),
            heading.group(1) if heading else "",
            entry.get("title"),
            title_element.group(1) if title_element else "",
        ),
        180,
    )
    if not title:
        return None

    canonical = next(
        (
            html_attributes(tag).get("href", "")
            for tag in re.findall(r"<link\b[^>]*>", page, re.IGNORECASE)
            if "canonical" in html_attributes(tag).get("rel", "").casefold()
        ),
        "",
    )
    canonical = urllib.parse.urljoin(url, canonical) if canonical else url
    updated = _optional_datetime(
        _first(
            values.get("article:modified_time"),
            values.get("datemodified"),
            *_page_meta_values(page, "dateModified"),
            article.get("dateModified"),
            _page_date(page, ("dateModified", "modified", "updated")),
            entry.get("lastmod"),
        )
    )
    description = _text(
        _first(
            values.get("og:description"),
            values.get("twitter:description"),
            values.get("description"),
            article.get("description"),
        )
    )
    keywords: list[str] = []
    for value in [
        *_page_meta_values(page, "article:tag"),
        values.get("keywords", ""),
        values.get("news_keywords", ""),
        article.get("keywords", ""),
    ]:
        if isinstance(value, list):
            keywords.extend(str(item).strip() for item in value)
        elif isinstance(value, str):
            keywords.extend(item.strip() for item in value.split(","))
    tags = list(dict.fromkeys(item for item in keywords if item))
    return {
        "post_id": post_id(source["id"], canonical),
        "source_id": source["id"],
        "source_title": source["title"],
        "title": title,
        "url": canonical,
        "published": published,
        "updated": updated,
        "description": description,
        "tags": tags,
    }


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
        "description": _text(
            _header_description(page)
            or values.get("og:description", values.get("description", ""))
            or (title_description[1] if len(title_description) > 1 else ""),
            500,
        ),
        "keywords": list(dict.fromkeys(sanitize_unicode(value) for value in keywords)),
        "avatar_url": page_avatar(page, source["website_url"]),
        "source_url": source["website_url"],
    }


def normalize_post(item: Any) -> dict[str, Any]:
    data = item.model_dump() if hasattr(item, "model_dump") else dict(item)
    data["post_id"] = post_id(data["source_id"], data["url"])
    for field_name in ("source_title", "title", "description"):
        if field_name in data:
            data[field_name] = sanitize_unicode(data[field_name])
    data["tags"] = [sanitize_unicode(value) for value in data.get("tags", [])]
    return data
