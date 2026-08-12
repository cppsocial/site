import argparse
import json
from collections import Counter
from pathlib import Path

import yaml
from schemas.packages import (
    MatchCatalog,
    PackageEntityCatalog,
    PackageOverrides,
    RegistryCatalog,
)

from ..config import MetaUpdaterConfig
from ..packages import PARSERS, amalgamate
from ..packages.common import REPOSITORIES, normalize_package_record
from ..packages.conan import inspect_recipes
from ..packages.sources import source_paths as manager_source_paths, source_revision
from ..shared.browser_data import update_browser_collection, update_keyed_collection
from ..shared.dataset import YamlDataset
from ..shared.provenance import (
    cancel_provenance_tracking,
    finish_provenance_tracking,
    start_provenance_tracking,
)
from ..shared.runtime import finish
from ..shared.text import excerpt_html, render_text

DESCRIPTION = "Build the cross-registry C++ package catalog."

RELEASE_PRESENTATION_FIELDS = (
    "summary",
    "description",
    "licenses",
    "homepage",
    "repository_url",
    "documentation_url",
)


def add_options(
    parser: argparse.ArgumentParser, *, suppress_defaults: bool = False
) -> None:
    defaults = {"default": argparse.SUPPRESS} if suppress_defaults else {}
    source_defaults = (
        {"default": argparse.SUPPRESS}
        if suppress_defaults
        else {"default": []}
    )
    parser.add_argument(
        "--source", action="append", metavar="MANAGER=PATH", **source_defaults
    )
    parser.add_argument(
        "--manager", action="append", choices=sorted(PARSERS), **defaults
    )
    parser.add_argument("--threshold", type=float, **defaults)
    parser.add_argument("--check", action="store_true", **defaults)
    parser.add_argument("--compact", action="store_true", **defaults)
    parser.add_argument("--refresh", action="store_true", **defaults)


def configure(parser: argparse.ArgumentParser) -> None:
    add_options(parser)
    actions = parser.add_subparsers(dest="action")
    matches = actions.add_parser(
        "matches", help="Recalculate matches from saved catalogs"
    )
    add_options(matches, suppress_defaults=True)
    ingest = actions.add_parser(
        "ingest", help="Refresh normalized manager catalogs only"
    )
    add_options(ingest, suppress_defaults=True)
    publish = actions.add_parser(
        "publish", help="Reconcile and publish packages from saved catalogs"
    )
    add_options(publish, suppress_defaults=True)
    inspect = actions.add_parser(
        "inspect", help="Inspect Conan Center recipes")
    inspect.add_argument("--path", type=Path)
    output = inspect.add_mutually_exclusive_group(required=True)
    output.add_argument("--list", action="store_true")
    output.add_argument("--all", action="store_true")
    output.add_argument("--package")
    parser.set_defaults(handler=run)

def source_paths(
    args: argparse.Namespace,
    config: MetaUpdaterConfig,
) -> dict[str, Path]:
    managers = args.manager or config.package_managers

    overrides = {}
    for value in args.source:
        manager, separator, path = value.partition("=")
        if not separator or manager not in PARSERS:
            raise ValueError(
                f"invalid --source {value!r}; expected MANAGER=PATH"
            )
        overrides[manager] = Path(path).resolve()

    return manager_source_paths(
        managers, overrides, config.package_cache, args.refresh
    )


def dataset(path: Path, schema: object) -> YamlDataset:
    return YamlDataset(
        path,
        schema,
        "meta-updater packages",
        "Normalized from package registry repositories; regenerate instead of editing.",
        exclude_defaults=True,
        exclude_none=True,
    )


def load_catalog(path: Path) -> list[dict]:
    value = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    packages = RegistryCatalog.model_validate(value).model_dump(
        exclude_none=True, exclude_defaults=True
    ).get("packages", [])
    return [normalize_package_record(package) for package in packages]


def load_entities(path: Path) -> list[dict]:
    if not path.exists():
        return []
    value = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    return PackageEntityCatalog.model_validate(value).model_dump(
        exclude_none=True, exclude_defaults=True
    ).get("entities", [])


def apply_corrections(
    catalogs: dict[str, list[dict]], corrections: list[dict] | None
) -> None:
    by_id = {
        package["id"]: package for values in catalogs.values() for package in values
    }
    for correction in corrections or []:
        package = by_id.get(correction["package"])
        if package is None:
            continue
        target = package
        if version := correction.get("version"):
            target = next(
                (
                    release
                    for release in package.get("versions") or []
                    if release.get("version") == version
                ),
                None,
            )
            if target is None:
                continue
        field_name = correction["field"]
        operation = correction.get("operation", "replace")
        if operation == "remove":
            target.pop(field_name, None)
        elif operation == "add":
            current = target.setdefault(field_name, [])
            additions = correction.get("value")
            additions = additions if isinstance(additions, list) else [additions]
            target[field_name] = list(dict.fromkeys([*current, *additions]))
        else:
            target[field_name] = correction.get("value")


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
        if revision := version.get("packaging_revision"):
            if release_id == str(version.get("upstream_version") or release_id):
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
    raw = variant.get("summary") or variant.get("description") or ""
    if not raw:
        return (0, "")
    rendered = render_text(
        raw,
        media_type=variant.get("description_format"),
    )
    if not rendered.summary_text:
        return (0, "")
    dedicated = bool(variant.get("summary"))
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
        for reference in package["packages"]:
            variant = by_id[reference["package_id"]]
            dependency_links = []
            dependencies = variant.get("dependency_details") or variant.get("dependencies") or []
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
        topics = list(
            dict.fromkeys(
                topic for value in variants for topic in value.get("topics") or []
            )
        )
        preferred_candidate = next(
            (candidate for candidate in candidates if candidate[2] == preferred), None
        )
        selected = preferred_candidate or max(candidates, default=(0, "", ""))
        description = selected[1]
        global_fields = {}
        field_sources = {"summary": selected[2]} if selected[2] else {}
        for field_name in (
            "licenses",
            "homepage",
            "repository_url",
            "documentation_url",
        ):
            value, source = _select_field(
                package["id"], variants, field_name, preferences
            )
            if value:
                global_fields[field_name] = value
                field_sources[field_name] = source
        summary = without_empty(
            {
                "id": package["id"],
                "aliases": package["aliases"],
                **global_fields,
                "field_sources": field_sources,
                "content": description,
                "topics": topics,
                "summary_source": selected[2],
                "packages": [
                    reference["package_id"] for reference in package["packages"]
                ],
                "managers": list(
                    dict.fromkeys(
                        reference["registry"] for reference in package["packages"]
                    )
                ),
            }
        )
        if package["name"] != package["id"]:
            summary["title"] = package["name"]
        summaries.append(summary)
    return summaries, details


def run(args: argparse.Namespace, config: MetaUpdaterConfig) -> int:
    if args.action == "inspect":
        records = inspect_recipes(
            args.path or config.package_cache / "conan", args.package
        )
        if args.list:
            print("\n".join(package["name"] for package in records))
        elif args.package:
            print(json.dumps(records[0], indent=2))
        else:
            print(json.dumps(records, indent=2))
        return 0
    threshold = (
        args.threshold if args.threshold is not None else config.package_threshold
    )
    if not 0 <= threshold <= 1:
        raise ValueError("--threshold must be between zero and one")
    unknown = set(config.package_managers) - PARSERS.keys()
    if unknown:
        raise ValueError(
            f"unknown configured package managers: {', '.join(sorted(unknown))}"
        )

    tracks_sources = args.action not in {"matches", "publish"}
    if tracks_sources:
        start_provenance_tracking(config.data / "packages" / "provenance.yaml")
    changed = False
    package_data = config.data / "packages"
    if args.action in {"matches", "publish"}:
        catalogs = {
            manager: load_catalog(package_data / f"{manager}.yaml")
            for manager in config.package_managers
        }
    else:
        paths = source_paths(args, config)
        catalogs = {
            manager: [normalize_package_record(package) for package in PARSERS[manager](path)]
            for manager, path in paths.items()
        }
        catalog_changed = False
        for manager, packages in catalogs.items():
            value = {
                "registry": manager,
                "repository": REPOSITORIES[manager],
                "revision": source_revision(manager, paths[manager]),
                "packages": packages,
            }
            manager_changed = dataset(
                package_data / f"{manager}.yaml", RegistryCatalog
            ).update(value, args.check)
            catalog_changed = manager_changed or catalog_changed
            changed = manager_changed or changed
            print(f"{manager}: {len(packages)} packages")
        if args.action == "ingest":
            if changed and not args.check:
                finish_provenance_tracking()
            else:
                cancel_provenance_tracking()
            return finish(changed, args.check, "package manager")
        if args.manager and not catalog_changed:
            cancel_provenance_tracking()
            return finish(False, args.check, "package manager")
        # A selected-manager update still reconciles against the saved catalogs
        # for every other manager. This keeps the operation end-to-end without
        # fetching or rewriting unrelated registries.
        for manager in config.package_managers:
            if manager not in catalogs:
                catalogs[manager] = load_catalog(package_data / f"{manager}.yaml")
    overrides = PackageOverrides.model_validate(
        yaml.safe_load(
            (config.content / "packages" / "package-overrides.yaml").read_text(
                encoding="utf-8"
            )
        )
        or {}
    ).model_dump(exclude_none=True, exclude_defaults=True)
    apply_corrections(catalogs, overrides.get("corrections"))
    previous_entities = load_entities(package_data / "entities.yaml")
    master, matches = amalgamate(
        catalogs,
        threshold,
        overrides,
        previous_entities=previous_entities,
    )
    legacy_master = package_data / "master.yaml"
    if legacy_master.exists():
        changed = True
        if not args.check:
            legacy_master.unlink()
    matches_changed = dataset(package_data / "matches.yaml", MatchCatalog).update(
        {"threshold": threshold, "matches": matches}, args.check
    )
    changed = matches_changed or changed
    entities = [
        {
            "id": package["id"],
            "packages": [item["package_id"] for item in package["packages"]],
        }
        for package in master
    ]
    entities_changed = dataset(
        package_data / "entities.yaml", PackageEntityCatalog
    ).update(
        {"entities": entities}, args.check
    )
    changed = entities_changed or changed
    summaries, details = browser_records(
        master, catalogs, overrides.get("preferences")
    )
    manager_counts = Counter(
        manager
        for summary in summaries
        for manager in {
            package_id.split(":", 1)[0] for package_id in summary["packages"]
        }
    )
    summaries_changed = update_browser_collection(
            config.browser_data / "packages",
            summaries,
            collection="packages",
            fields={
                "title": {"label": "Name", "properties": ["id", "title", "aliases"]},
                "content": {
                    "label": "Description",
                    "properties": ["content", "topics"],
                },
            },
            check=args.check,
            compact=args.compact and not args.check,
            metadata={
                "manager_counts": dict(sorted(manager_counts.items())),
                "preview": sorted(summaries, key=lambda item: item["id"])[:30],
            },
    )
    changed = summaries_changed or changed
    details_root = config.browser_data / "package-details"
    details_by_manager: dict[str, list[dict]] = {
        manager: [] for manager in config.package_managers
    }
    for detail in details:
        manager = detail["id"].split(":", 1)[0]
        details_by_manager.setdefault(manager, []).append(detail)
    details_changed = False
    for manager, manager_details in details_by_manager.items():
        manager_changed = update_keyed_collection(
            details_root / manager,
            manager_details,
            collection=f"package-details-{manager}",
            bucket_count=256,
            check=args.check,
        )
        details_changed = manager_changed or details_changed
    legacy_detail_files = list(details_root.glob("*.json"))
    if legacy_detail_files:
        details_changed = True
        if not args.check:
            for path in legacy_detail_files:
                path.unlink()
    changed = details_changed or changed
    if tracks_sources:
        if changed and not args.check:
            finish_provenance_tracking()
        else:
            cancel_provenance_tracking()
    changed_outputs = [
        name
        for name, value in (
            ("matches", matches_changed),
            ("entities", entities_changed),
            ("summaries", summaries_changed),
            ("details", details_changed),
        )
        if value
    ]
    suffix = f"; changed: {', '.join(changed_outputs)}" if changed_outputs else ""
    print(
        f"master: {len(master)} packages, {len(matches)} candidate matches{suffix}"
    )
    return finish(changed, args.check, "package")
