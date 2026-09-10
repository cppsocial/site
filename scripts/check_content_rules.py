"""Validate deterministic rules for curated content."""

import argparse
import re
import subprocess
import sys
from pathlib import Path
from typing import Any

import yaml

ID_PATTERN = re.compile(r"^[a-z0-9]+(?:[-_][a-z0-9]+)*$")
ISBN_PATTERN = re.compile(r"^[0-9]{13}$")
YOUTUBE_PATTERN = re.compile(r"^UC[A-Za-z0-9_-]{22}$")
EVENT_PATTERN = re.compile(r"^.+@cpp\.social$")

DATASETS = (
    ((Path("content/blogs/sources.yaml"),), "id", ID_PATTERN),
    ((Path("content/books/books.yaml"),), "isbn", ISBN_PATTERN),
    (
        (
            Path("content/communities/forums.yaml"),
            Path("content/communities/im.yaml"),
        ),
        "community_id",
        ID_PATTERN,
    ),
    ((Path("content/events/meetups.yaml"),), "source_id", ID_PATTERN),
    ((Path("content/events/events.yaml"),), "ical_uid", EVENT_PATTERN),
    (
        (
            Path("content/youtube/channels.yaml"),
            Path("content/youtube/conferences.yaml"),
            Path("content/youtube/organizations.yaml"),
        ),
        "channel_id",
        YOUTUBE_PATTERN,
    ),
)


def _records(path: Path) -> list[dict[str, Any]]:
    document = yaml.safe_load(path.read_text(encoding="utf-8"))
    if isinstance(document, list):
        values = document
    elif isinstance(document, dict) and isinstance(document.get("cards"), list):
        values = document["cards"]
    else:
        values = []
    return [value for value in values if isinstance(value, dict)]


def validate_identifiers() -> list[str]:
    errors = []
    for paths, field, pattern in DATASETS:
        seen: dict[str, Path] = {}
        for path in paths:
            if not path.exists():
                continue
            for record in _records(path):
                if field not in record:
                    continue
                value = str(record[field])
                if not pattern.fullmatch(value):
                    errors.append(f"{path}: invalid {field}: {value}")
                if value in seen:
                    errors.append(
                        f"{path}: duplicate {field} {value} "
                        f"(also in {seen[value]})"
                    )
                else:
                    seen[value] = path
    return errors


def _schema(text: str) -> str | None:
    match = re.search(r"(?m)^\$schema:\s*(.*?)\s*$", text)
    return match.group(1) if match else None


def changed_content_paths(base: str) -> set[Path]:
    output = subprocess.check_output(
        ["git", "diff", "--name-only", "-z", f"{base}...HEAD", "--", "content"]
    )
    return {Path(value.decode()) for value in output.split(b"\0") if value}


def validate_schema_declarations(base: str, paths: set[Path]) -> list[str]:
    errors = []
    for path in sorted(paths):
        if path.suffix not in {".yaml", ".yml"} or not path.exists():
            continue
        try:
            previous = subprocess.check_output(
                ["git", "show", f"{base}:{path.as_posix()}"],
                text=True,
                stderr=subprocess.DEVNULL,
            )
        except subprocess.CalledProcessError:
            continue
        before = _schema(previous)
        after = _schema(path.read_text(encoding="utf-8"))
        if before != after:
            errors.append(
                f"{path}: $schema declaration changed from {before!r} to {after!r}"
            )
    return errors


def main(arguments: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base", required=True, help="base commit SHA")
    args = parser.parse_args(arguments)
    errors = validate_identifiers()
    errors.extend(
        validate_schema_declarations(args.base, changed_content_paths(args.base))
    )
    for error in errors:
        print(f"error: {error}", file=sys.stderr)
    if errors:
        return 1
    print("machine-checkable content rules are satisfied")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
