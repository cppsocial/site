"""Warn when generated data is unrelated to content changed in the same PR."""

import argparse
import subprocess
from pathlib import Path

CONTENT_FAMILIES = {
    "blogs",
    "books",
    "communities",
    "events",
    "packages",
    "youtube",
}


def changed_paths(base: str) -> set[Path]:
    output = subprocess.check_output(
        ["git", "diff", "--name-only", "-z", f"{base}...HEAD"]
    )
    return {Path(value.decode()) for value in output.split(b"\0") if value}


def unrelated_generated_data(paths: set[Path]) -> list[Path]:
    changed_content = {
        path.parts[1]
        for path in paths
        if len(path.parts) > 1
        and path.parts[0] == "content"
        and path.parts[1] in CONTENT_FAMILIES
    }
    if not any(path.parts and path.parts[0] == "content" for path in paths):
        return []

    unrelated = []
    for path in paths:
        if not path.parts or path.parts[0] != "data":
            continue
        if path == Path("data/events-imported.yaml"):
            family = "events"
        elif len(path.parts) > 1 and path.parts[1] in CONTENT_FAMILIES:
            family = path.parts[1]
        else:
            family = "unknown"
        if family not in changed_content:
            unrelated.append(path)
    return sorted(unrelated)


def main(arguments: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base", required=True, help="base commit SHA")
    args = parser.parse_args(arguments)
    for path in unrelated_generated_data(changed_paths(args.base)):
        print(
            f"::warning file={path}::Generated data is not associated with a "
            "changed content family in this change. Keep only related updater output, "
            "or split this data maintenance into its own PR."
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
