from pathlib import Path
from typing import Any

from .common import (
    REPOSITORIES,
    clean_list,
    github_url,
    repository_identity,
    repository_revision,
)


def _cmake_bracket(text: str, start: int) -> tuple[str, int] | None:
    """Parse a CMake [=[...]=] bracket argument."""
    if start >= len(text) or text[start] != "[":
        return None

    i = start + 1
    while i < len(text) and text[i] == "=":
        i += 1

    if i >= len(text) or text[i] != "[":
        return None

    equals = text[start + 1: i]
    closing = "]" + equals + "]"
    end = text.find(closing, i + 1)

    if end == -1:
        raise ValueError("unterminated CMake bracket argument")

    return text[i + 1: end], end + len(closing)


def _cmake_tokens(text: str):
    """Tokenize the subset of CMake syntax needed for command calls."""
    i = 0

    while i < len(text):
        char = text[i]

        if char.isspace():
            i += 1
            continue

        # Line or bracket comment.
        if char == "#":
            bracket = _cmake_bracket(text, i + 1)
            if bracket is not None:
                _, i = bracket
            else:
                end = text.find("\n", i + 1)
                i = len(text) if end == -1 else end + 1
            continue

        if char in "()":
            yield char
            i += 1
            continue

        # Bracket argument: [=[...]=]
        bracket = _cmake_bracket(text, i)
        if bracket is not None:
            value, i = bracket
            yield value
            continue

        # Quoted argument.
        if char == '"':
            i += 1
            value = []

            while i < len(text):
                char = text[i]

                if char == '"':
                    i += 1
                    break

                if char == "\\" and i + 1 < len(text):
                    # CMake line continuation.
                    if text[i + 1] == "\n":
                        i += 2
                        continue

                    value.append(text[i + 1])
                    i += 2
                    continue

                value.append(char)
                i += 1
            else:
                raise ValueError("unterminated CMake quoted argument")

            yield "".join(value)
            continue

        # Unquoted argument.
        start = i
        while i < len(text) and not text[i].isspace() and text[i] not in "()#":
            i += 1

        if start == i:
            raise ValueError(
                f"unexpected CMake character at offset {i}: {text[i]!r}")

        yield text[start:i]


def _cmake_commands(text: str):
    """Yield (command_name, arguments) from CMake source."""
    tokens = list(_cmake_tokens(text))
    i = 0

    while i < len(tokens):
        name = tokens[i]

        if name in ("(", ")") or i + 1 >= len(tokens) or tokens[i + 1] != "(":
            i += 1
            continue

        i += 2
        depth = 1
        arguments = []

        while i < len(tokens) and depth:
            token = tokens[i]
            i += 1

            if token == "(":
                depth += 1
                arguments.append(token)
            elif token == ")":
                depth -= 1
                if depth:
                    arguments.append(token)
            else:
                arguments.append(token)

        if depth:
            raise ValueError(f"unterminated CMake command: {name}")

        yield name, arguments


def _hunter_versions(path: Path):
    text = path.read_text(encoding="utf-8")

    for command, arguments in _cmake_commands(text):
        if command.casefold() != "hunter_add_version":
            continue

        if len(arguments) % 2:
            raise ValueError(
                f"invalid hunter_add_version in {path}: {arguments!r}")

        values = dict(zip(arguments[::2], arguments[1::2]))

        try:
            yield {
                "name": values["PACKAGE_NAME"],
                "version": values["VERSION"],
                "url": values["URL"],
                "sha1": values["SHA1"],
            }
        except KeyError as error:
            raise ValueError(
                f"invalid hunter_add_version in {path}: missing {error.args[0]}"
            ) from error


def parse_hunter(root: Path) -> list[dict[str, Any]]:
    revision = repository_revision(root)
    records = []
    defaults = {}
    defaults_path = root / "cmake" / "configs" / "default.cmake"
    if defaults_path.is_file():
        for command, arguments in _cmake_commands(
            defaults_path.read_text(encoding="utf-8")
        ):
            if command.casefold() != "hunter_default_version" or len(arguments) < 3:
                continue
            if arguments[1].casefold() == "version":
                defaults[arguments[0]] = arguments[2]

    for recipe in sorted((root / "cmake" / "projects").glob("*/hunter.cmake")):
        versions = list(_hunter_versions(recipe))
        if not versions:
            continue

        names = {entry["name"] for entry in versions}
        if len(names) != 1:
            raise ValueError(
                f"multiple package names in {recipe}: {sorted(names)!r}")

        name = versions[0]["name"]
        source_urls = clean_list([entry["url"] for entry in versions])

        repository = next(
            (identity for url in source_urls if (
                identity := repository_identity(url))),
            "",
        )

        records.append(
            {
                "id": f"hunter:{name}",
                "registry": "hunter",
                "name": name,
                "repository_url": repository,
                "components": [],
                "versions": [
                    {
                        "version": entry["version"],
                        "artifacts": [
                            {
                                "kind": "upstream_source",
                                "url": entry["url"],
                                "checksums": [f"sha1:{entry['sha1'].casefold()}"],
                            }
                        ],
                    }
                    for entry in versions
                ],
                "default_version": defaults.get(name),
                "native_url": (
                    "https://hunter.readthedocs.io/en/latest/packages/pkg/"
                    f"{name}.html"
                ),
                "recipe_url": github_url(
                    REPOSITORIES["hunter"],
                    revision,
                    recipe.relative_to(root),
                ),
            }
        )

    return records
