import json
import re
from pathlib import Path
from typing import Any

from .common import (
    REPOSITORIES,
    clean_licenses,
    clean_list,
    github_url,
    repository_identity,
    repository_revision,
    scalar_strings,
)
from ..shared.text import render_text


def _dependencies(values: object) -> list[str]:
    result = []
    for value in values if isinstance(values, list) else []:
        name = value if isinstance(value, str) else value.get("name", "")
        if name:
            result.append(name)
    return clean_list(result)


def _version_value(data: dict[str, Any]) -> str:
    for key in ("version", "version-semver", "version-date", "version-string"):
        if key in data:
            return str(data[key])
    return ""


def _first_cmake_source(text: str) -> tuple[str, str]:
    names = {
        "vcpkg_download_distfile",
        "vcpkg_from_bitbucket",
        "vcpkg_from_git",
        "vcpkg_from_github",
        "vcpkg_from_gitlab",
        "vcpkg_from_sourceforge",
    }
    for match in re.finditer(r"\b([A-Za-z0-9_]+)\s*\(", text):
        if match.group(1).casefold() not in names:
            continue
        depth = 1
        quote = ""
        escaped = False
        for index in range(match.end(), len(text)):
            character = text[index]
            if escaped:
                escaped = False
                continue
            if character == "\\":
                escaped = True
                continue
            if quote:
                if character == quote:
                    quote = ""
                continue
            if character in {'"', "'"}:
                quote = character
            elif character == "(":
                depth += 1
            elif character == ")":
                depth -= 1
                if depth == 0:
                    return match.group(1).casefold(), text[match.end() : index]
    return "", ""


def _vcpkg_upstream(text: str, homepage: str) -> tuple[str, list[str], list[str]]:
    function, body = _first_cmake_source(text)
    source_urls = clean_list(re.findall(r"https?://[^\s\")]+", body))
    checksums = [
        f"{algorithm.casefold()}:{digest.casefold()}"
        for algorithm, digest in re.findall(
            r"\b(MD5|SHA1|SHA256|SHA512)\s+([0-9a-fA-F]+)",
            body,
        )
    ]
    repository = ""
    repo_match = re.search(r"\bREPO\s+([A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+)", body)
    hosts = {
        "vcpkg_from_github": "github.com",
        "vcpkg_from_gitlab": "gitlab.com",
        "vcpkg_from_bitbucket": "bitbucket.org",
    }
    if repo_match and function in hosts:
        repository = f"https://{hosts[function]}/{repo_match.group(1)}"
        ref_match = re.search(r"\bREF\s+(?:\"([^\"]+)\"|([^\s)]+))", body)
        if ref_match and function == "vcpkg_from_github":
            reference = next(value for value in ref_match.groups() if value)
            source_urls.append(f"{repository}/archive/{reference}.tar.gz")
    if not repository:
        repository = repository_identity(homepage)
    if not repository:
        repository = next(
            (identity for url in source_urls if (identity := repository_identity(url))),
            "",
        )
    return repository, source_urls, checksums


def parse_vcpkg(root: Path) -> list[dict[str, Any]]:
    revision = repository_revision(root)
    records = []
    for manifest in sorted((root / "ports").glob("*/vcpkg.json")):
        data = json.loads(manifest.read_text(encoding="utf-8"))
        name = str(data.get("name") or manifest.parent.name)
        version_file = root / "versions" / f"{name[:1]}-" / f"{name}.json"
        versions = []
        if version_file.is_file():
            history = json.loads(version_file.read_text(encoding="utf-8"))
            for item in history.get("versions", []):
                version = _version_value(item)
                if version:
                    port_revision = int(item.get("port-version") or 0)
                    versions.append(
                        {
                            "version": version,
                            "packaging_revision": port_revision or None,
                            "recipe_url": (
                                f"https://github.com/microsoft/vcpkg/tree/"
                                f"{item['git-tree']}/ports/{name}"
                            )
                            if item.get("git-tree")
                            else None,
                        }
                    )
        if not versions and (version := _version_value(data)):
            versions.append({"version": version})
        portfile = manifest.parent / "portfile.cmake"
        text = (
            portfile.read_text(encoding="utf-8", errors="replace")
            if portfile.is_file()
            else ""
        )
        homepage = str(data.get("homepage", ""))
        repository, source_urls, checksums = _vcpkg_upstream(text, homepage)
        current_version = _version_value(data)
        for version in versions:
            if version["version"] == current_version:
                version["artifacts"] = [
                    {
                        "kind": "upstream_source",
                        "url": url,
                        "checksums": checksums or None,
                    }
                    for url in source_urls
                ] or ([{"kind": "upstream_source", "checksums": checksums}] if checksums else [])
        descriptions = scalar_strings(data.get("description"))
        rendered_description = render_text(" ".join(descriptions))
        dependencies = _dependencies(data.get("dependencies", []))
        default_features = data.get("default-features", [])
        if not isinstance(default_features, list):
            default_features = []
        default_feature_names = [
            value if isinstance(value, str) else value.get("name", "")
            for value in default_features
            if isinstance(value, (str, dict))
        ]
        for feature in data.get("features", {}).values():
            dependencies.extend(_dependencies(feature.get("dependencies", [])))
        features = [
            {
                "name": feature_name,
                "description": " ".join(
                    scalar_strings(feature.get("description"))
                )
                or None,
                "default": "enabled" if feature_name in default_feature_names else None,
            }
            for feature_name, feature in data.get("features", {}).items()
        ]
        current_release = next(
            (item for item in versions if item["version"] == current_version), None
        )
        if current_release is not None:
            current_release.update(
                {
                    "summary": rendered_description.summary_text,
                    "licenses": clean_licenses(scalar_strings(data.get("license"))) or None,
                    "homepage": homepage or None,
                    "documentation_url": str(data.get("documentation") or "") or None,
                    "dependencies": [{"name": item} for item in clean_list(dependencies)] or None,
                    "features": features or None,
                    "compatibility": scalar_strings(data.get("supports")) or None,
                }
            )
        relative = manifest.relative_to(root)

        records.append(
            {
                "id": f"vcpkg:{name}",
                "registry": "vcpkg",
                "name": name,
                "summary": rendered_description.summary_text,
                "description": rendered_description.body_html,
                "description_format": "html",
                "documentation_url": str(data.get("documentation") or ""),
                "licenses": clean_licenses(scalar_strings(data.get("license"))),
                "homepage": homepage,
                "repository_url": repository,
                "source_urls": clean_list(source_urls),
                "platforms": scalar_strings(data.get("supports")),
                "dependencies": clean_list(dependencies),
                "options": sorted(data.get("features", {})),
                "default_options": {
                    name: "enabled" for name in default_feature_names if name
                },
                "versions": versions,
                "recipe_url": github_url(REPOSITORIES["vcpkg"], revision, relative),
            }
        )
    return records
