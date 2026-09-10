"""Refresh only metadata selected by changes in a pull request."""

import argparse
import subprocess
from pathlib import Path
from typing import Any

import yaml

TARGETS = {
    Path("content/blogs/sources.yaml"): ("id", ("blogs", "all")),
    Path("content/books/books.yaml"): ("isbn", ("books",)),
    Path("content/communities/forums.yaml"): (
        "community_id",
        ("communities",),
    ),
    Path("content/communities/im.yaml"): ("community_id", ("communities",)),
    Path("content/youtube/channels.yaml"): (
        "channel_id",
        ("youtube", "all"),
    ),
    Path("content/youtube/conferences.yaml"): (
        "channel_id",
        ("youtube", "all"),
    ),
    Path("content/youtube/organizations.yaml"): (
        "channel_id",
        ("youtube", "all"),
    ),
}


def changed_paths(base: str) -> set[Path]:
    output = subprocess.check_output(
        ["git", "diff", "--name-only", "-z", f"{base}...HEAD"]
    )
    return {Path(value.decode()) for value in output.split(b"\0") if value}


def _load(text: str, identifier: str) -> dict[str, Any]:
    document = yaml.safe_load(text)
    if isinstance(document, list):
        records = document
    elif isinstance(document, dict) and isinstance(document.get("cards"), list):
        records = document["cards"]
    else:
        records = []
    return {
        str(record[identifier]): record
        for record in records
        if isinstance(record, dict) and identifier in record
    }


def _previous(base: str, path: Path, identifier: str) -> dict[str, Any]:
    try:
        text = subprocess.check_output(
            ["git", "show", f"{base}:{path.as_posix()}"],
            text=True,
            stderr=subprocess.DEVNULL,
        )
    except subprocess.CalledProcessError:
        return {}
    return _load(text, identifier)


def targeted_commands(base: str, paths: set[Path]) -> list[list[str]]:
    commands: list[list[str]] = []
    for path, (identifier, command) in TARGETS.items():
        if path not in paths or not path.exists():
            continue
        current = _load(path.read_text(encoding="utf-8"), identifier)
        previous = _previous(base, path, identifier)
        for value in sorted(current):
            if current[value] != previous.get(value):
                commands.append(["meta-updater", *command, "--id", value])

    if Path("content/events/meetups.yaml") in paths:
        commands.append(["meta-updater", "events"])
    if Path("data/packages/overrides.yaml") in paths:
        commands.append(["meta-updater", "packages", "publish"])
    return commands


def main(arguments: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base", required=True, help="base commit SHA")
    args = parser.parse_args(arguments)
    commands = targeted_commands(args.base, changed_paths(args.base))
    if not commands:
        print("No metadata refresh is needed for the changed paths")
        return 0
    for command in commands:
        print("+", " ".join(command), flush=True)
        subprocess.run(command, check=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
