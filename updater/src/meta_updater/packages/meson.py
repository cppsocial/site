import configparser
import json
from pathlib import Path
from typing import Any

from .common import (
    REPOSITORIES,
    clean_list,
    github_url,
    repository_identity,
    repository_revision,
)


def parse_meson(root: Path) -> list[dict[str, Any]]:
    revision = repository_revision(root)
    releases_path = root / "releases.json"
    releases = (
        json.loads(releases_path.read_text(encoding="utf-8"))
        if releases_path.is_file()
        else {}
    )
    records = []
    for wrap in sorted((root / "subprojects").glob("*.wrap")):
        parser = configparser.ConfigParser(interpolation=None, strict=False)
        parser.read(wrap, encoding="utf-8")
        section = parser["wrap-file"] if parser.has_section("wrap-file") else {}
        name = wrap.stem
        source_url = section.get("source_url", "")
        source_hash = section.get("source_hash", "")
        directory = section.get("directory", "")
        version = ""
        if directory.startswith(name + "-"):
            version = directory[len(name) + 1 :]
        release = releases.get(name, {})
        dependency_names = clean_list(release.get("dependency_names", []))
        program_names = clean_list(release.get("program_names", []))
        if parser.has_section("provide"):
            dependency_names = dependency_names or clean_list(
                parser["provide"].get("dependency_names", "").split()
            )
            program_names = program_names or clean_list(
                parser["provide"].get("program_names", "").split()
            )
        repository = repository_identity(source_url)
        versions = []
        for release_id in release.get("versions", []):
            upstream, separator, packaging_revision = str(release_id).rpartition("-")
            if not separator:
                upstream, packaging_revision = str(release_id), ""
            artifacts = [
                {
                    "kind": "registry_package",
                    "url": (
                        f"https://wrapdb.mesonbuild.com/v2/"
                        f"{name}_{release_id}/{name}.wrap"
                    ),
                }
            ]
            if upstream == version and source_url:
                artifacts.append(
                    {
                        "kind": "upstream_source",
                        "url": source_url,
                        "filename": section.get("source_filename") or None,
                        "checksums": [f"sha256:{source_hash.casefold()}"]
                        if source_hash
                        else None,
                    }
                )
            versions.append(
                {
                    "version": upstream,
                    "packaging_revision": packaging_revision or None,
                    "capabilities": [*dependency_names, *program_names] or None,
                    "artifacts": artifacts,
                }
            )
        if not versions and version:
            versions.append(
                {
                    "version": version,
                    "artifacts": [
                        {
                            "kind": "upstream_source",
                            "url": source_url or None,
                            "checksums": [f"sha256:{source_hash.casefold()}"]
                            if source_hash
                            else None,
                        }
                    ],
                }
            )
        records.append(
            {
                "id": f"meson:{name}",
                "registry": "meson",
                "name": name,
                "repository_url": repository,
                "components": [*dependency_names, *program_names],
                "versions": versions,
                "recipe_url": github_url(
                    REPOSITORIES["meson"], revision, wrap.relative_to(root)
                ),
            }
        )
    return records
