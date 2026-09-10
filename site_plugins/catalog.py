import json
import re

from meta_updater.shared.text import excerpt_html, render_text

RELEASE_PRESENTATION_FIELDS = (
    "summary",
    "description",
    "licenses",
    "homepage",
    "repository_url",
    "documentation_url",
)

UNRESOLVED_URL_VARIABLE = re.compile(r"\$\{[^}]+\}")


def without_empty(values: dict) -> dict:
    return {
        key: value
        for key, value in values.items()
        if not (
            value is None
            or value is False
            or value == ""
            or isinstance(value, (list, dict, tuple, set))
            and not value
        )
    }


def browser_versions(versions: list[dict]) -> dict[str, object]:
    result = {}
    for version in versions:
        metadata = without_empty(
            {
                key: browser_detail_value(key, value)
                for key, value in version.items()
                if key != "version"
            }
        )
        release_id = str(version["version"])
        if (revision := version.get("packaging_revision")) and release_id == str(
            version.get("upstream_version") or release_id
        ):
            release_id += f"#{revision}"
        if channel := version.get("channel"):
            release_id += f"@{channel}"
        result[release_id] = (
            metadata["checksums"] if set(metadata) == {
                "checksums"} else metadata
        )
    return result


def browser_detail_value(key: str, value: object) -> object:
    if key == "description" and isinstance(value, str):
        return excerpt_html(value).body_html
    if key == "versions" and isinstance(value, list):
        return browser_versions(value)
    if key in {
        "documentation_url", "homepage", "native_url", "recipe_url", "repository_url"
    } and isinstance(value, str):
        return "" if UNRESOLVED_URL_VARIABLE.search(value) else value
    if key == "source_urls" and isinstance(value, list):
        return [
            url for url in value
            if not isinstance(url, str) or not UNRESOLVED_URL_VARIABLE.search(url)
        ]
    if key == "artifacts" and isinstance(value, list):
        artifacts = []
        for raw in value:
            artifact = dict(raw) if isinstance(raw, dict) else raw
            if (
                isinstance(artifact, dict)
                and isinstance(artifact.get("url"), str)
                and UNRESOLVED_URL_VARIABLE.search(artifact["url"])
            ):
                artifact.pop("url")
            artifacts.append(artifact)
        return artifacts
    return value


def compact_release_metadata(
    versions: dict[str, object], inherited: dict
) -> tuple[dict[str, object], list[dict]]:
    """Delta/group repeated release prose and links for browser delivery."""
    compacted: dict[str, object] = {}
    grouped: dict[str, tuple[dict, list[str]]] = {}
    for release_id, raw in versions.items():
        if not isinstance(raw, dict):
            compacted[release_id] = raw
            continue
        metadata = dict(raw)
        presentation = {}
        for field_name in RELEASE_PRESENTATION_FIELDS:
            if field_name not in metadata:
                continue
            value = metadata.pop(field_name)
            if value != inherited.get(field_name):
                presentation[field_name] = value
        compacted[release_id] = metadata
        if not presentation:
            continue
        key = json.dumps(presentation, sort_keys=True, separators=(",", ":"))
        if key not in grouped:
            grouped[key] = (presentation, [])
        grouped[key][1].append(release_id)

    groups = []
    for presentation, releases in grouped.values():
        if len(releases) == 1:
            release = compacted[releases[0]]
            if isinstance(release, dict):
                release.update(presentation)
            continue
        groups.append({"releases": releases, **presentation})
    return compacted, groups


def _summary_candidate(variant: dict) -> tuple[int, str]:
    dedicated = bool(variant.get("summary"))
    raw = variant.get("summary") or variant.get("description") or ""
    if not raw:
        return (0, "")
    rendered = (
        render_text(raw)
        if dedicated
        else excerpt_html(raw)
        if variant.get("description_format") == "html"
        else render_text(raw, media_type=variant.get("description_format"))
    )
    if not rendered.summary_text:
        return (0, "")
    manager_quality = {
        "cppget": 40,
        "vcpkg": 35,
        "conan": 34,
        "xmake": 33,
        "spack": 25,
    }.get(variant["registry"], 10)
    return (manager_quality + (50 if dedicated else 0), rendered.summary_text)


def _preferred_source(
    package_id: str,
    field_name: str,
    preferences: list[dict] | None,
) -> str:
    return next(
        (
            item["source"]
            for item in preferences or []
            if item["package"] == package_id and item["field"] == field_name
        ),
        "",
    )


def _select_field(
    package_id: str,
    variants: list[dict],
    field_name: str,
    preferences: list[dict] | None,
) -> tuple[object, str]:
    candidates = [
        (variant[field_name], variant["id"], variant["registry"])
        for variant in variants
        if variant.get(field_name)
    ]
    if not candidates:
        return None, ""
    preferred = _preferred_source(package_id, field_name, preferences)
    if selected := next((item for item in candidates if item[1] == preferred), None):
        return selected[0], selected[1]
    quality = {
        "vcpkg": 50,
        "cppget": 45,
        "conan": 40,
        "xmake": 35,
        "spack": 30,
        "bazel": 25,
        "meson": 20,
        "hunter": 15,
    }
    selected = max(
        candidates,
        key=lambda item: (quality.get(item[2], 0), -len(str(item[0])), item[1]),
    )
    return selected[0], selected[1]


def browser_records(
    master: list[dict],
    catalogs: dict[str, list[dict]],
    preferences: list[dict] | None = None,
) -> tuple[list[dict], list[dict]]:
    by_id = {
        package["id"]: package for values in catalogs.values() for package in values
    }
    master_by_variant = {
        reference["package_id"]: package
        for package in master
        for reference in package["packages"]
    }
    master_by_name = {}
    for package in master:
        for name in [package["name"], *package["aliases"]]:
            key = name.casefold()
            master_by_name[key] = package if key not in master_by_name else None
    summaries = []
    details = []
    for package in master:
        variants = []
        dependency_ids = set()
        for reference in package["packages"]:
            variant = by_id[reference["package_id"]]
            dependency_links = []
            dependencies = (
                variant.get("dependency_details")
                or variant.get("dependencies")
                or []
            )
            for dependency_value in dependencies:
                dependency = (
                    dependency_value
                    if isinstance(dependency_value, dict)
                    else {"name": dependency_value}
                )
                dependency_name = dependency["name"]
                target = master_by_variant.get(
                    f"{variant['registry']}:{dependency_name}"
                ) or master_by_name.get(dependency_name.casefold())
                if not target:
                    dependency_links.append(dependency)
                    continue
                link = {**dependency, "id": target["id"]}
                if target["id"] != package["id"]:
                    dependency_ids.add(target["id"])
                if dependency_name == target["id"]:
                    link.pop("name", None)
                dependency_links.append(link)
            variants.append(variant)
            detail = {
                "id": variant["id"],
                **{
                    key: browser_detail_value(key, value)
                    for key, value in variant.items()
                    if key not in {
                        "id", "registry", "name", "dependencies", "dependency_details"
                    }
                },
                "dependency_links": dependency_links,
            }
            if versions := detail.get("versions"):
                compacted, release_metadata = compact_release_metadata(
                    versions, detail
                )
                detail["versions"] = compacted
                if release_metadata:
                    detail["release_metadata"] = release_metadata
            details.append({"id": detail.pop("id"), **without_empty(detail)})
        preferred = _preferred_source(package["id"], "summary", preferences)
        candidates = [
            (*_summary_candidate(value), value["id"])
            for value in variants
            if _summary_candidate(value)[1]
        ]
        topics = []
        seen_topics = set()
        for topic in (
            topic for value in variants for topic in value.get("topics") or []
        ):
            normalized_topic = str(topic).strip()
            key = normalized_topic.casefold()
            if not normalized_topic or key in seen_topics:
                continue
            seen_topics.add(key)
            topics.append(normalized_topic)
        preferred_candidate = next(
            (candidate for candidate in candidates if candidate[2] == preferred), None
        )
        selected = preferred_candidate or max(candidates, default=(0, "", ""))
        description = selected[1]
        global_fields = {}
        for field_name in ("licenses",):
            value, _ = _select_field(
                package["id"], variants, field_name, preferences
            )
            if value:
                global_fields[field_name] = value
        summary = without_empty(
            {
                "id": package["id"],
                "aliases": package["aliases"],
                **global_fields,
                "content": description,
                "topics": topics,
                "packages": [
                    reference["package_id"] for reference in package["packages"]
                ],
                "managers": list(
                    dict.fromkeys(
                        reference["registry"] for reference in package["packages"]
                    )
                ),
                "dependencies": sorted(dependency_ids),
            }
        )
        if package["name"] != package["id"]:
            summary["title"] = package["name"]
        summaries.append(summary)
    return summaries, details
