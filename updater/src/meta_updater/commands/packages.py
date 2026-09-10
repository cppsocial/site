import argparse
import copy
import json
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
from ..packages.sources import source_paths as manager_source_paths
from ..packages.sources import source_revision
from ..shared.dataset import YamlDataset
from ..shared.provenance import (
    cancel_provenance_tracking,
    finish_provenance_tracking,
    start_provenance_tracking,
)
from ..shared.runtime import finish, log_operation_error

DESCRIPTION = "Build the cross-registry C++ package catalog."


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
    managers: list[str] | None = None,
) -> dict[str, Path]:
    managers = managers or args.manager or config.package_managers

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


def load_overrides(path: Path) -> dict:
    value = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    return PackageOverrides.model_validate(value).model_dump(
        exclude_none=True, exclude_defaults=True
    )


def package_is_ignored(
    package_id: str,
    ignored: set[str],
    ignored_prefixes: tuple[str, ...] = (),
) -> bool:
    return package_id in ignored or package_id.startswith(ignored_prefixes)


def filter_ignored(
    packages: list[dict],
    ignored: set[str],
    ignored_prefixes: tuple[str, ...] = (),
) -> list[dict]:
    return [
        package
        for package in packages
        if not package_is_ignored(package["id"], ignored, ignored_prefixes)
    ]


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

    override_path = config.data / "packages" / "overrides.yaml"
    try:
        overrides = load_overrides(override_path)
    except Exception as error:
        log_operation_error("package overrides load", error, path=override_path)
        return 2
    ignored = set(overrides.get("ignored", []))
    ignored_prefixes = tuple(overrides.get("ignored_prefixes", []))
    overrides = copy.deepcopy(overrides)
    overrides["groups"] = [
        {
            **group,
            "packages": [
                value
                for value in group["packages"]
                if not package_is_ignored(value, ignored, ignored_prefixes)
            ],
        }
        for group in overrides.get("groups", [])
        if any(
            not package_is_ignored(value, ignored, ignored_prefixes)
            for value in group["packages"]
        )
    ]
    overrides["never_merge"] = [
        {**rule, "packages": values}
        for rule in overrides.get("never_merge", [])
        if (
            len(
                values := [
                    value
                    for value in rule["packages"]
                    if not package_is_ignored(value, ignored, ignored_prefixes)
                ]
            )
            == 2
        )
    ]

    tracks_sources = args.action not in {"matches", "publish"}
    if tracks_sources:
        start_provenance_tracking(config.data / "packages" / "provenance.yaml")
    changed = False
    had_refresh_failures = False
    package_data = config.data / "packages"
    if args.action in {"matches", "publish"}:
        catalogs = {}
        try:
            for manager in config.package_managers:
                path = package_data / f"{manager}.yaml"
                packages = filter_ignored(
                    load_catalog(path), ignored, ignored_prefixes
                )
                catalogs[manager] = packages
                raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
                normalized_by_id = {item["id"]: item for item in packages}
                retained = []
                for item in raw.get("packages") or []:
                    if package_is_ignored(
                        item.get("id", ""), ignored, ignored_prefixes
                    ):
                        continue
                    if args.compact:
                        item = normalized_by_id.get(item.get("id"), item)
                    retained.append(item)
                if retained != (raw.get("packages") or []):
                    raw["packages"] = retained
                    changed = (
                        dataset(path, RegistryCatalog).update(raw, args.check)
                        or changed
                    )
        except Exception as error:
            log_operation_error("saved package catalog load", error, path=path)
            return 2
    else:
        selected = args.manager or config.package_managers
        paths = {}
        catalogs = {}
        catalog_changed = False
        failed = set()
        for manager in selected:
            catalog_path = package_data / f"{manager}.yaml"
            try:
                path = source_paths(args, config, [manager])[manager]
                packages = [
                    normalize_package_record(package)
                    for package in PARSERS[manager](path)
                ]
                if not packages:
                    raise ValueError("refreshed catalog contained no packages")
                packages = filter_ignored(packages, ignored, ignored_prefixes)
            except Exception as error:
                failed.add(manager)
                had_refresh_failures = True
                log_operation_error("package catalog refresh", error, manager=manager)
                continue
            paths[manager] = path
            catalogs[manager] = packages
            value = {
                "registry": manager,
                "repository": REPOSITORIES[manager],
                "revision": source_revision(manager, paths[manager]),
                "packages": packages,
            }
            manager_changed = dataset(
                catalog_path, RegistryCatalog
            ).update(value, args.check)
            catalog_changed = manager_changed or catalog_changed
            changed = manager_changed or changed
            print(f"{manager}: {len(catalogs[manager])} packages")
        if args.action == "ingest":
            if changed and not args.check:
                finish_provenance_tracking()
            else:
                cancel_provenance_tracking()
            status = finish(changed, args.check, "package manager")
            return 2 if had_refresh_failures else status
        if args.manager and not catalog_changed:
            cancel_provenance_tracking()
            finish(False, args.check, "package manager")
            return 2 if had_refresh_failures else 0
        # A selected-manager update still reconciles against the saved catalogs
        # for every other manager. This keeps the operation end-to-end without
        # fetching or rewriting unrelated registries.
        for manager in config.package_managers:
            if manager not in catalogs:
                path = package_data / f"{manager}.yaml"
                try:
                    catalogs[manager] = filter_ignored(
                        load_catalog(path), ignored, ignored_prefixes
                    )
                except Exception as error:
                    log_operation_error(
                        "saved package catalog load", error, manager=manager, path=path
                    )
                    if manager in failed:
                        cancel_provenance_tracking()
                    return 2
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
            "name": package["name"],
            "aliases": package["aliases"],
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
        )
        if value
    ]
    suffix = f"; changed: {', '.join(changed_outputs)}" if changed_outputs else ""
    print(
        f"master: {len(master)} packages, {len(matches)} candidate matches{suffix}"
    )
    status = finish(changed, args.check, "package")
    return 2 if had_refresh_failures else status
