import html
import re
import unicodedata
from dataclasses import dataclass
from html.parser import HTMLParser
from urllib.parse import urlsplit

import markdown

_MARKDOWN_SIGNAL = re.compile(
    r"(?m)^(?:#{1,6}\s|\s*[-*+]\s|\s*\d+[.)]\s|```)|"
    r"(?:\[[^\]]+\]\([^)]+\)|\*\*[^*]+\*\*|`[^`]+`)"
)
_SPACE = re.compile(r"\s+")
_BADGE_LINE = re.compile(r"(?i)^\s*(?:\[?!?\[[^]]*\]\([^)]*\)\]\([^)]*\)\s*)+$")
_HTML_COMMENT = re.compile(r"<!--.*?(?:-->|$)", re.DOTALL)
_MARKDOWN_HEADING = re.compile(
    r"(?s)^(?:#{1,6}\s+.+|.{1,120}\s+(?:={3,}|-{3,}))$"
)
_MARKDOWN_IMAGE = re.compile(
    r"!\[[^]]*\](?:\([^)]*\)|\[[^]]*\])"
)
_MARKDOWN_LINK = re.compile(r"(?<!!)\[([^]]*)\](?:\([^)]*\)|\[[^]]*\])")
_LOOSE_EMPHASIS = re.compile(r"\*\*\s+(.+?)\s+\*\*")
_HTML_TAG = re.compile(
    r"</?(?:a|abbr|b|blockquote|br|center|code|details|div|em|font|img|kbd|li|ol|p|picture|pre|small|span|strong|summary|table|tbody|td|tfoot|th|thead|tr|ul)\b[^>]*>",
    re.IGNORECASE,
)
_HEADING_SENTINEL = "\ue000"
_GENERIC_HEADINGS = {
    "announcements",
    "build status",
    "contents",
    "documentation",
    "homepage",
    "introduction",
    "table of contents",
}
_SAFE_TAGS = {
    "a",
    "blockquote",
    "br",
    "code",
    "em",
    "li",
    "ol",
    "p",
    "pre",
    "strong",
    "ul",
}
_SUPPRESSED_TAGS = {"h1", "h2", "h3", "h4", "h5", "h6", "script", "style"}


def sanitize_unicode(value: str) -> str:
    """Normalize fetched text and remove invisible/invalid Unicode controls."""
    normalized = unicodedata.normalize("NFC", value or "")
    return "".join(
        character
        for character in normalized
        if character in "\n\r\t"
        or (
            character != "\ufffd"
            and unicodedata.category(character) not in {"Cc", "Cf", "Cs"}
            and not 0xFDD0 <= ord(character) <= 0xFDEF
            and ord(character) & 0xFFFF not in {0xFFFE, 0xFFFF}
        )
    )


class _RootShape(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=False)
        self.depth = 0
        self.roots: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if self.depth == 0:
            self.roots.append(tag)
        self.depth += 1

    def handle_startendtag(
        self, tag: str, attrs: list[tuple[str, str | None]]
    ) -> None:
        if self.depth == 0:
            self.roots.append(tag)

    def handle_endtag(self, tag: str) -> None:
        self.depth = max(0, self.depth - 1)

    def handle_data(self, data: str) -> None:
        if self.depth == 0 and data.strip():
            self.roots.append("#text")


class _PlainText(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.values: list[str] = []

    def handle_data(self, data: str) -> None:
        self.values.append(data)


class _BlockText(HTMLParser):
    _BLOCKS = {
        "p", "div", "li", "pre", "blockquote", "h1", "h2", "h3", "h4", "h5", "h6"
    }

    def __init__(self) -> None:
        super().__init__()
        self.values: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag == "br":
            self.values.append("\n")
        elif tag in {"h1", "h2", "h3", "h4", "h5", "h6"}:
            self.values.append(f"\n\n{_HEADING_SENTINEL}")

    def handle_endtag(self, tag: str) -> None:
        if tag in self._BLOCKS:
            self.values.append("\n\n")

    def handle_data(self, data: str) -> None:
        self.values.append(data)


class _SafeHtml(HTMLParser):
    """Small allow-list sanitizer for package prose fragments."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.values: list[str] = []
        self.suppressed = 0

    def handle_starttag(
        self, tag: str, attrs: list[tuple[str, str | None]]
    ) -> None:
        tag = tag.casefold()
        if tag in _SUPPRESSED_TAGS:
            self.suppressed += 1
            return
        if self.suppressed or tag not in _SAFE_TAGS:
            return
        attributes = ""
        if tag == "a":
            values = dict(attrs)
            href = values.get("href") or ""
            scheme = urlsplit(href).scheme.casefold()
            if href and scheme in {"http", "https", "mailto"}:
                attributes = f' href="{html.escape(href, quote=True)}"'
        self.values.append(f"<{tag}{attributes}>")

    def handle_startendtag(
        self, tag: str, attrs: list[tuple[str, str | None]]
    ) -> None:
        self.handle_starttag(tag, attrs)

    def handle_endtag(self, tag: str) -> None:
        tag = tag.casefold()
        if tag in _SUPPRESSED_TAGS:
            self.suppressed = max(0, self.suppressed - 1)
            return
        if not self.suppressed and tag in _SAFE_TAGS and tag != "br":
            self.values.append(f"</{tag}>")

    def handle_data(self, data: str) -> None:
        if not self.suppressed:
            self.values.append(html.escape(data, quote=False))


@dataclass(frozen=True)
class RenderedText:
    summary_text: str
    summary_html: str
    body_html: str
    detected_format: str
    truncated: bool


def _strip_single_paragraph(value: str) -> str:
    parser = _RootShape()
    parser.feed(value)
    if parser.roots != ["p"]:
        return value
    start = value.find(">")
    end = value.rfind("</p>")
    return value[start + 1: end] if start >= 0 and end >= start else value


def _plain_text(value: str) -> str:
    parser = _PlainText()
    parser.feed(value)
    return _SPACE.sub(" ", html.unescape(" ".join(parser.values))).strip()


def sanitize_html(value: str | None) -> str:
    """Return a safe HTML fragment using only presentation-oriented tags."""
    parser = _SafeHtml()
    parser.feed(_HTML_COMMENT.sub("", value or ""))
    parser.close()
    sanitized = "".join(parser.values).strip()
    return re.sub(
        r"</(blockquote|h[1-6]|li|ol|p|pre|ul)>\s+(?=<)",
        r"</\1>",
        sanitized,
    )


def _truncate(value: str, limit: int) -> tuple[str, bool]:
    if len(value) <= limit:
        return value, False
    shortened = value[: limit + 1].rsplit(" ", 1)[0].rstrip(" ,.;:-")
    if len(shortened) < limit // 2:
        shortened = value[:limit].rstrip()
    return shortened + "…", True


def _meaningful_source(value: str) -> str:
    value = _HTML_COMMENT.sub("", value)
    lines = []
    for line in value.splitlines():
        normalized = unicodedata.normalize("NFKC", line).strip()
        if not normalized:
            if lines and lines[-1] != "":
                lines.append("")
            continue
        if _BADGE_LINE.fullmatch(normalized):
            continue
        if normalized.casefold() in {
            "table of contents",
            "contents",
            "build status",
            "documentation",
        }:
            continue
        lines.append(normalized)
    while lines and not lines[-1]:
        lines.pop()
    return "\n".join(lines)


def _useful_excerpt_block(value: str) -> str:
    """Discard README furniture while retaining actual descriptive prose."""
    value = _SPACE.sub(" ", _HTML_COMMENT.sub("", value)).strip()
    if not value or value.startswith(_HEADING_SENTINEL):
        return ""
    if _MARKDOWN_HEADING.fullmatch(value):
        return ""
    if value.casefold().strip("#*_` :=-") in _GENERIC_HEADINGS:
        return ""
    without_media = _MARKDOWN_IMAGE.sub(" ", value)
    without_media = _MARKDOWN_LINK.sub(r"\1", without_media)
    without_media = _LOOSE_EMPHASIS.sub(r"**\1**", without_media)
    without_media = _SPACE.sub(" ", _HTML_TAG.sub(" ", without_media)).strip()
    if not re.search(r"[\w+#]", without_media):
        return ""
    return without_media


def render_text(
    value: str | None,
    *,
    media_type: str | None = None,
    summary_limit: int = 160,
    body_limit: int = 64_000,
    block_limit: int | None = None,
) -> RenderedText:
    """Render untrusted prose and derive a bounded catalog summary.

    Markdown input is escaped before rendering. Declared HTML and the rendered
    result both pass through the same small allow-list sanitizer.
    """
    source = unicodedata.normalize("NFKC", value or "").replace("\x00", "")
    source = _HTML_COMMENT.sub("", source)
    source = _LOOSE_EMPHASIS.sub(r"**\1**", source)
    body_truncated = len(source) > body_limit
    source = _meaningful_source(source[:body_limit])
    blocks = [part.strip() for part in re.split(r"\n\s*\n", source) if part.strip()]
    blocks_truncated = block_limit is not None and len(blocks) > block_limit
    source = "\n\n".join(blocks[:block_limit] if block_limit is not None else blocks)
    declared = (media_type or "").casefold()
    is_html = declared in {"text/html", "html"}
    is_markdown = declared in {"text/markdown", "markdown"} or (
        not is_html and bool(_MARKDOWN_SIGNAL.search(source))
    )
    detected = "html" if is_html else "markdown" if is_markdown else "plain"
    escaped = html.escape(source, quote=False)
    if is_html:
        body = sanitize_html(source)
    elif is_markdown:
        body = markdown.markdown(escaped, extensions=[])
    else:
        paragraphs = [
            part.strip()
            for part in re.split(r"\n\s*\n", escaped)
            if part.strip()
        ]
        body = "".join(f"<p>{part.replace(chr(10), '<br>')}</p>" for part in paragraphs)
    body = sanitize_html(body)
    inline = _strip_single_paragraph(body)
    plain = _plain_text(body)
    summary, summary_truncated = _truncate(plain, summary_limit)
    return RenderedText(
        summary_text=summary,
        summary_html=html.escape(summary),
        body_html=inline if parser_single_paragraph(body) else body,
        detected_format=detected,
        truncated=body_truncated or blocks_truncated or summary_truncated,
    )


def parser_single_paragraph(value: str) -> bool:
    parser = _RootShape()
    parser.feed(value)
    return parser.roots == ["p"]


def excerpt_html(
    value: str | None,
    *,
    body_limit: int = 4_000,
    block_limit: int = 2,
) -> RenderedText:
    """Turn already-sanitized HTML into a small browser-delivery excerpt."""
    parser = _BlockText()
    parser.feed(value or "")
    blocks = [
        _SPACE.sub(" ", html.unescape(part)).strip()
        for part in re.split(r"\n\s*\n", "".join(parser.values))
    ]
    plain = "\n\n".join(
        useful for part in blocks if (useful := _useful_excerpt_block(part))
    )
    return render_text(
        plain,
        media_type="text/markdown",
        body_limit=body_limit,
        block_limit=block_limit,
    )
