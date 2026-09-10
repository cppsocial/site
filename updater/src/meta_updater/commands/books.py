import argparse
import html
import json
import re
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any

import yaml
from schemas.blocks import BookMetadata

from ..config import MetaUpdaterConfig
from ..shared.dataset import YamlDataset
from ..shared.provenance import (
    cancel_provenance_tracking,
    finish_provenance_tracking,
    provenance_transaction,
    start_provenance_tracking,
    track_provenance,
)
from ..shared.runtime import (
    add_id_option,
    add_network_options,
    delayed,
    finish,
    log_operation_error,
    network_values,
    selected,
)
from ..shared.text import render_text, sanitize_unicode

DESCRIPTION = "Refresh book metadata from Open Library."
OPEN_LIBRARY = "https://openlibrary.org"
ISBN_PATTERN = re.compile(r"(?:97[89])?\d{9}[\dX]")


def configure(parser: argparse.ArgumentParser) -> None:
    add_network_options(parser)
    add_id_option(parser)
    parser.set_defaults(handler=run)


def valid_isbn(value: str) -> bool:
    if not ISBN_PATTERN.fullmatch(value):
        return False
    if len(value) == 10:
        digits = [10 if character == "X" else int(character) for character in value]
        checksum = sum((10 - index) * digit for index, digit in enumerate(digits))
        return checksum % 11 == 0
    return (
        sum(
            int(character) * (1 if index % 2 == 0 else 3)
            for index, character in enumerate(value)
        )
        % 10
        == 0
    )


def isbn10_from_isbn13(value: str) -> str:
    if len(value) != 13 or not value.startswith("978") or not valid_isbn(value):
        return ""
    body = value[3:-1]
    checksum = sum((10 - index) * int(digit) for index, digit in enumerate(body))
    check_digit = (11 - checksum % 11) % 11
    suffix = "X" if check_digit == 10 else str(check_digit)
    return body + suffix


def isbns(source: Path) -> list[str]:
    with source.open(encoding="utf-8") as file:
        group = yaml.safe_load(file)
    values = [
        str(card["isbn"]).replace("-", "")
        for card in group["cards"]
        if not card.get("hidden", False)
    ]
    invalid = [value for value in values if not valid_isbn(value)]
    if invalid:
        raise ValueError(f"invalid ISBNs: {', '.join(invalid)}")
    if len(values) != len(set(values)):
        raise ValueError("duplicate ISBN in curated books")
    return values


def request_json(path: str, timeout: float, retries: int = 4) -> Any:
    url = f"{OPEN_LIBRARY}{path}"
    request = urllib.request.Request(
        url,
        headers={
            "User-Agent": "cpp.social metadata updater (https://cpp.social/contributing/)"
        },
    )
    for attempt in range(retries):
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:
                result = json.load(response)
            track_provenance(url)
            return result
        except urllib.error.HTTPError as error:
            if error.code != 429 and error.code < 500:
                raise
            if attempt == retries - 1:
                raise
            retry_after = error.headers.get("Retry-After")
            time.sleep(float(retry_after) if retry_after else 2**attempt)
        except (urllib.error.URLError, ConnectionError, TimeoutError):
            if attempt == retries - 1:
                raise
            time.sleep(2**attempt)
    raise RuntimeError(f"failed to fetch {url}")


def text(value: Any) -> str:
    if isinstance(value, dict):
        value = value.get("value", "")
    return (
        sanitize_unicode(html.unescape(value)).strip()
        if isinstance(value, str)
        else ""
    )


def split_title(title_value: Any, subtitle_value: Any = "") -> tuple[str, str]:
    title = text(title_value)
    subtitle = text(subtitle_value)
    if subtitle or ": " not in title:
        return title, subtitle
    heading, remainder = title.split(": ", 1)
    if len(heading.split()) < 2:
        return title, subtitle
    return heading, remainder


def edition(isbn: str, timeout: float) -> dict[str, Any]:
    query = urllib.parse.urlencode(
        {"bibkeys": f"ISBN:{isbn}", "jscmd": "data", "format": "json"}
    )
    result = request_json(f"/api/books?{query}", timeout).get(f"ISBN:{isbn}")
    if not result:
        raise ValueError(f"Open Library has no edition for ISBN {isbn}")
    return result


def work(isbn: str, timeout: float) -> dict[str, Any]:
    fields = ",".join(
        (
            "key",
            "ratings_average",
            "ratings_count",
            "author_name",
            "subject",
            "description",
            "first_sentence",
        )
    )
    query = urllib.parse.urlencode({"isbn": isbn, "fields": fields, "limit": 1})
    result = request_json(f"/search.json?{query}", timeout).get("docs", [])
    if not result:
        raise ValueError(f"Open Library has no work for ISBN {isbn}")
    return result[0]


def description_text(*values: Any) -> str:
    for value in values:
        candidates = value if isinstance(value, list) else [value]
        for candidate in candidates:
            if source := text(candidate):
                return render_text(
                    source, summary_limit=600, body_limit=4_000
                ).summary_text
    return ""


def clean_subjects(values: list[Any]) -> list[str]:
    result = []
    for value in values:
        name = text(value.get("name") if isinstance(value, dict) else value)
        if not name or len(name) > 60 or name.casefold() == "open_syllabus_project":
            continue
        if name.casefold() not in {item.casefold() for item in result}:
            result.append(name)
    return result[:12]


def metadata(isbn: str, timeout: float) -> dict[str, Any]:
    exact = edition(isbn, timeout)
    summary = work(isbn, timeout)
    work_key = summary.get("key", "")
    title, subtitle = split_title(exact.get("title"), exact.get("subtitle"))
    cover = exact.get("cover", {})
    authors = [text(author.get("name")) for author in exact.get("authors", [])]
    authors.extend(text(author) for author in summary.get("author_name", []))
    authors = list(dict.fromkeys(author for author in authors if author))
    subjects = clean_subjects(exact.get("subjects", []) or summary.get("subject", []))
    identifiers = exact.get("identifiers", {})
    isbn_13_values = identifiers.get("isbn_13", [])
    isbn_10_values = identifiers.get("isbn_10", [])
    isbn_13 = str(isbn_13_values[0]) if isbn_13_values else isbn
    isbn_10 = str(isbn_10_values[0]) if isbn_10_values else isbn10_from_isbn13(isbn_13)
    rating = summary.get("ratings_average")
    rating_count = int(summary.get("ratings_count", 0))
    return {
        "title": title,
        "authors": authors,
        "subtitle": subtitle,
        "description": description_text(
            summary.get("description"), summary.get("first_sentence")
        ),
        "isbn_13": isbn_13,
        "isbn_10": isbn_10,
        "publisher": ", ".join(
            text(publisher.get("name"))
            for publisher in exact.get("publishers", [])
            if text(publisher.get("name"))
        ),
        "publish_date": text(exact.get("publish_date")),
        "pages": exact.get("number_of_pages"),
        "cover_url": cover.get("large", ""),
        "url": exact.get("url", f"{OPEN_LIBRARY}/isbn/{isbn}").replace(
            "http://", "https://"
        ),
        "work_key": work_key,
        "subjects": subjects,
        "rating": (
            round(float(rating), 3) if rating is not None and rating_count else None
        ),
        "rating_count": rating_count,
    }


def run(args: argparse.Namespace, config: MetaUpdaterConfig) -> int:
    timeout, delay = network_values(args, config)
    dataset = YamlDataset(
        config.data / "books" / "metadata.yaml",
        dict[str, BookMetadata],
        "meta-updater books",
        "Edition metadata, descriptions, covers, and ratings come from Open Library.",
        exclude_none=True,
        exclude_defaults=True,
    )
    start_provenance_tracking(
        config.data / "books" / "provenance.yaml",
        retain_existing=bool(args.ids),
    )
    curated = isbns(config.content / "books" / "books.yaml")
    curated = selected(curated, args.ids, lambda value: value, "ISBN")
    # Retain the last good record when a remote source is temporarily unavailable.
    values = dataset.load({})
    wanted = set(curated)
    if not args.ids:
        values = {isbn: value for isbn, value in values.items() if isbn in wanted}
    for isbn in delayed(curated, delay):
        try:
            with provenance_transaction():
                value = metadata(isbn, timeout)
        except Exception as error:
            log_operation_error("book metadata", error, isbn=isbn)
            continue
        values[isbn] = value
        print(f"metadata {isbn}: {values[isbn]['title']}")
    changed = dataset.update(values, args.check)
    if args.check:
        cancel_provenance_tracking()
    else:
        finish_provenance_tracking()
    return finish(changed, args.check, "book")
