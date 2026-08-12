import re
from pathlib import Path
from typing import Any
from urllib.parse import quote, urljoin

from .common import clean_licenses, clean_list, repository_identity
from ..shared.text import render_text


CPPGET_BASE_URL = "https://pkg.cppget.org/1/"
CPPGET_WEBSITE = "https://cppget.org/"

CPPGET_CHANNELS = (
    "stable",
    "testing",
    "beta",
    "alpha",
)

_DEPENDENCY_NAME = re.compile(r"[A-Za-z0-9][A-Za-z0-9+_.-]*")


def _parse_manifests(path: Path):
    lines = path.read_text(encoding="utf-8").splitlines()
    record: dict[str, list[str]] = {}
    i = 0

    while i < len(lines):
        line = lines[i]
        i += 1

        if not line.strip() or line.startswith("#"):
            continue

        # ": 1" starts the first manifest and ":" starts subsequent ones.
        if line.startswith(":"):
            if record:
                yield record
                record = {}
            continue

        if line[:1].isspace():
            raise ValueError(f"orphaned manifest continuation: {line!r}")

        key, separator, value = line.partition(":")
        if not separator:
            raise ValueError(f"invalid manifest line: {line!r}")

        key = key.strip()
        value = value.lstrip()

        # Explicit multi-line values are delimited by lines containing a
        # single backslash. Both `key: \\` and `key:` followed by `\\` occur.
        multiline = value == "\\"
        if not value and i < len(lines) and lines[i] == "\\":
            i += 1
            multiline = True

        if multiline:
            values = []
            while i < len(lines) and lines[i] != "\\":
                values.append(lines[i])
                i += 1
            if i == len(lines):
                raise ValueError(f"unterminated value for {key!r}")
            i += 1
            value = "\n".join(values)
        else:
            # Values may continue on indented physical lines or after a
            # trailing backslash.
            values = [value]
            while i < len(lines):
                previous = values[-1].rstrip()
                escaped = previous.endswith("\\")
                indented = lines[i][:1].isspace()
                if not escaped and not indented:
                    break

                if escaped:
                    values[-1] = previous[:-1].rstrip()

                continuation = lines[i]
                i += 1
                if indented:
                    continuation = continuation[1:]
                values.append(continuation)

            value = "\n".join(values)

        record.setdefault(key, []).append(value)

    if record:
        yield record


def _one(manifest: dict[str, list[str]], key: str) -> str:
    values = manifest.get(key)
    return values[0] if values else ""


def _dependency_names(values: list[str]) -> list[str]:
    result = []

    for value in values:
        # Continuation whitespace is not meaningful for identifying the
        # dependency alternatives.
        text = " ".join(part.strip() for part in value.splitlines() if part.strip())
        text = text.lstrip()
        if text.startswith("*"):
            text = text[1:].lstrip()

        # Dependency groups have the form `{ foo bar baz } <constraint>`.
        if text.startswith("{") and (end := text.find("}")) != -1:
            for token in text[1:end].split():
                if _DEPENDENCY_NAME.fullmatch(token):
                    result.append(token)
            continue

        # Alternatives have the form `foo <constraint> | bar <constraint>`.
        # For the catalog we only need the package names, not bpkg's version
        # or configuration expression.
        for alternative in text.split("|"):
            alternative = alternative.lstrip()
            if alternative.startswith("*"):
                alternative = alternative[1:].lstrip()
            if match := _DEPENDENCY_NAME.match(alternative):
                result.append(match.group())

    return clean_list(result)


def _manifest_paths(root: Path):
    # Keep support for handing parse_cppget() one manifest directly, mostly
    # useful for tests and one-off inspection.
    if root.is_file():
        yield "stable", root
        return

    for channel in CPPGET_CHANNELS:
        path = root / channel / "packages.manifest"
        if path.exists():
            yield channel, path


def parse_cppget(root: Path) -> list[dict[str, Any]]:
    records: dict[str, dict[str, Any]] = {}
    version_records: dict[tuple[str, str], dict[str, Any]] = {}

    for channel, path in _manifest_paths(root):
        repository_url = urljoin(CPPGET_BASE_URL, f"{channel}/")

        for manifest in _parse_manifests(path):
            name = _one(manifest, "name")
            version = _one(manifest, "version")
            if not name or not version:
                continue

            location = _one(manifest, "location")
            source_hash = _one(manifest, "sha256sum")
            source_url = urljoin(repository_url, location) if location else ""

            homepage = _one(manifest, "url")
            src_url = _one(manifest, "src-url")
            repository = repository_identity(src_url or homepage)
            summary = _one(manifest, "summary")
            description_source = _one(manifest, "description") or summary
            description_type = _one(manifest, "description-type") or "text/markdown"
            rendered = render_text(description_source, media_type=description_type)
            dependencies = _dependency_names(manifest.get("depends", []))

            record = records.setdefault(
                name,
                {
                    "id": f"cppget:{name}",
                    "registry": "cppget",
                    "name": name,
                    "summary": render_text(summary).summary_text if summary else None,
                    "description": rendered.body_html,
                    "description_format": "html",
                    "licenses": clean_licenses(manifest.get("license", [])),
                    "homepage": homepage,
                    "repository_url": repository,
                    "documentation_url": _one(manifest, "doc-url") or None,
                    "topics": clean_list(
                        [*manifest.get("topics", []), *manifest.get("keywords", [])]
                    ),
                    "languages": clean_list(manifest.get("language", [])),
                    "package_type": _one(manifest, "type") or None,
                    "dependencies": [],
                    "components": [],
                    "versions": [],
                    "recipe_url": urljoin(CPPGET_WEBSITE, quote(name)),
                },
            )

            if not record["repository_url"] and repository:
                record["repository_url"] = repository
            if not record["description"] and rendered.body_html:
                record["description"] = rendered.body_html
            if not record["homepage"] and homepage:
                record["homepage"] = homepage
            if not record["licenses"] and manifest.get("license"):
                record["licenses"] = clean_licenses(manifest["license"])

            # Keep the last non-empty dependency set in the published
            # manifest/channel traversal order rather than unioning historical
            # dependencies from different versions.
            if dependencies:
                record["dependencies"] = dependencies

            checksums = (
                [f"sha256:{source_hash.casefold()}"] if source_hash else []
            )
            key = (name, version, channel)
            version_record = version_records.get(key)

            if version_record is None:
                version_record = {
                    "version": version,
                    "channel": channel,
                    "summary": render_text(summary).summary_text if summary else None,
                    "description": rendered.body_html or None,
                    "licenses": clean_licenses(manifest.get("license", [])) or None,
                    "homepage": homepage or None,
                    "documentation_url": _one(manifest, "doc-url") or None,
                    "dependencies": [{"name": item} for item in dependencies] or None,
                    "artifacts": [
                        {
                            "kind": "registry_package",
                            "url": source_url or None,
                            "checksums": checksums or None,
                        }
                    ]
                    if source_url or checksums
                    else None,
                }
                version_records[key] = version_record
                record["versions"].append(version_record)
            else:
                artifacts = version_record.setdefault("artifacts", [])
                artifacts.append(
                    {
                        "kind": "registry_package",
                        "url": source_url or None,
                        "checksums": checksums or None,
                    }
                )

    return list(records.values())
