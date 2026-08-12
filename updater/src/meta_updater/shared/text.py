import html
import re
import unicodedata
from dataclasses import dataclass
from html.parser import HTMLParser

import markdown


_MARKDOWN_SIGNAL = re.compile(
    r"(?m)^(?:#{1,6}\s|\s*[-*+]\s|\s*\d+[.)]\s|```)|"
    r"(?:\[[^\]]+\]\([^)]+\)|\*\*[^*]+\*\*|`[^`]+`)"
)
_SPACE = re.compile(r"\s+")
_BADGE_LINE = re.compile(r"(?i)^\s*(?:\[?!?\[[^]]*\]\([^)]*\)\]\([^)]*\)\s*)+$")


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
    _BLOCKS = {"p", "div", "li", "pre", "blockquote", "h1", "h2", "h3", "h4", "h5", "h6"}

    def __init__(self) -> None:
        super().__init__()
        self.values: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag == "br":
            self.values.append("\n")

    def handle_endtag(self, tag: str) -> None:
        if tag in self._BLOCKS:
            self.values.append("\n\n")

    def handle_data(self, data: str) -> None:
        self.values.append(data)


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
    return value[start + 1 : end] if start >= 0 and end >= start else value


def _plain_text(value: str) -> str:
    parser = _PlainText()
    parser.feed(value)
    return _SPACE.sub(" ", html.unescape(" ".join(parser.values))).strip()


def _truncate(value: str, limit: int) -> tuple[str, bool]:
    if len(value) <= limit:
        return value, False
    shortened = value[: limit + 1].rsplit(" ", 1)[0].rstrip(" ,.;:-")
    if len(shortened) < limit // 2:
        shortened = value[:limit].rstrip()
    return shortened + "…", True


def _meaningful_source(value: str) -> str:
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


def render_text(
    value: str | None,
    *,
    media_type: str | None = None,
    summary_limit: int = 160,
    body_limit: int = 64_000,
    block_limit: int | None = None,
) -> RenderedText:
    """Render untrusted package prose and derive a bounded catalog summary.

    Raw HTML is escaped before Markdown rendering. This deliberately supports a
    small, safe input surface until a dedicated allow-list sanitizer is added.
    """
    source = unicodedata.normalize("NFKC", value or "").replace("\x00", "")
    body_truncated = len(source) > body_limit
    source = _meaningful_source(source[:body_limit])
    blocks = [part.strip() for part in re.split(r"\n\s*\n", source) if part.strip()]
    blocks_truncated = block_limit is not None and len(blocks) > block_limit
    source = "\n\n".join(blocks[:block_limit] if block_limit is not None else blocks)
    declared = (media_type or "").casefold()
    is_markdown = declared in {"text/markdown", "markdown"} or (
        not declared and bool(_MARKDOWN_SIGNAL.search(source))
    )
    detected = "markdown" if is_markdown else "plain"
    escaped = html.escape(source, quote=False)
    if is_markdown:
        body = markdown.markdown(escaped, extensions=[])
    else:
        paragraphs = [part.strip() for part in re.split(r"\n\s*\n", escaped) if part.strip()]
        body = "".join(f"<p>{part.replace(chr(10), '<br>')}</p>" for part in paragraphs)
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
    plain = "\n\n".join(part for part in blocks if part)
    return render_text(
        plain,
        media_type="text/plain",
        body_limit=body_limit,
        block_limit=block_limit,
    )
