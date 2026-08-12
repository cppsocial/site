import ast
import hashlib
import json
import os
import shutil
import subprocess
import warnings
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any

import yaml

from ..shared.text import render_text

from .common import (
    REPOSITORIES,
    _class_metadata,
    _literal,
    clean_licenses,
    clean_list,
    github_url,
    option_value,
    repository_identity,
    repository_revision,
    scalar_strings,
    source_checksums,
)


def _conan_metadata(recipe: Path) -> dict[str, Any]:
    executable = shutil.which("conan")
    if not executable:
        return _class_metadata(recipe)
    digest = hashlib.sha256(recipe.read_bytes()).hexdigest()
    cache = (
        Path(
            os.environ.get(
                "CPP_SOCIAL_CONAN_CACHE",
                "/tmp/cpp-social-package-tools/conan-inspect-v2",
            )
        )
        / f"{digest}.json"
    )
    if cache.is_file():
        try:
            return json.loads(cache.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            pass
    try:
        output = subprocess.check_output(
            [executable, "inspect", str(recipe), "--format=json"],
            text=True,
            stderr=subprocess.DEVNULL,
        )
        result = json.loads(output)
        cache.parent.mkdir(parents=True, exist_ok=True)
        cache.write_text(json.dumps(result), encoding="utf-8")
        return result
    except (OSError, subprocess.CalledProcessError, json.JSONDecodeError):
        return _class_metadata(recipe)


def _conan_dependencies(recipe: Path, metadata: dict[str, Any]) -> list[str]:
    references = scalar_strings(metadata.get("requires"))
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", SyntaxWarning)
            tree = ast.parse(
                recipe.read_text(encoding="utf-8-sig"), filename=str(recipe)
            )
    except SyntaxError:
        tree = None
    for call in ast.walk(tree) if tree else []:
        if not isinstance(call, ast.Call) or not isinstance(call.func, ast.Attribute):
            continue
        if call.func.attr not in {"requires", "tool_requires", "test_requires"}:
            continue
        if call.args and isinstance(reference := _literal(call.args[0]), str):
            references.append(reference)
    return clean_list(reference.split("/", 1)[0] for reference in references)


def parse_conan(
    root: Path, package_names: set[str] | None = None
) -> list[dict[str, Any]]:
    revision = repository_revision(root)
    records = []
    config_paths = [
        path
        for path in sorted((root / "recipes").glob("*/config.yml"))
        if package_names is None or path.parent.name in package_names
    ]
    recipe_paths = []
    for config_path in config_paths:
        config = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
        folders = [
            value.get("folder")
            for value in (config.get("versions") or {}).values()
            if isinstance(value, dict) and value.get("folder")
        ]
        for folder in dict.fromkeys(folders):
            recipe = config_path.parent / folder / "conanfile.py"
            if recipe.is_file():
                recipe_paths.append(recipe)
    default_workers = min(16, max(4, (os.cpu_count() or 4) * 2))
    workers = max(
        1,
        min(32, int(os.environ.get("CPP_SOCIAL_CONAN_WORKERS", str(default_workers)))),
    )
    with ThreadPoolExecutor(max_workers=workers) as executor:
        recipe_metadata = dict(
            zip(recipe_paths, executor.map(_conan_metadata, recipe_paths), strict=True)
        )
    for config_path in config_paths:
        config = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
        folders: dict[str, list[str]] = defaultdict(list)
        for version, value in (config.get("versions") or {}).items():
            if isinstance(value, dict) and value.get("folder"):
                folders[str(value["folder"])].append(str(version))
        recipe_meta: dict[str, Any] = {}
        version_rows = []
        source_urls = []
        package_dependencies = []
        package_options: set[str] = set()
        package_defaults: dict[str, str] = {}
        for folder, versions in folders.items():
            folder_path = config_path.parent / folder
            recipe_path = folder_path / "conanfile.py"
            folder_meta = (
                recipe_metadata.get(recipe_path) or _conan_metadata(recipe_path)
                if recipe_path.is_file()
                else {}
            )
            if folder_meta and not recipe_meta:
                recipe_meta = folder_meta
            folder_dependencies = (
                _conan_dependencies(recipe_path, folder_meta)
                if recipe_path.is_file()
                else []
            )
            package_dependencies.extend(folder_dependencies)
            folder_options = (
                folder_meta.get("options_definitions")
                or folder_meta.get("options")
                or {}
            )
            package_options.update(folder_options.keys())
            package_defaults.update(
                {
                    option_name: option_value(value)
                    for option_name, value in (
                        folder_meta.get("default_options") or {}
                    ).items()
                }
            )
            folder_description = render_text(str(folder_meta.get("description") or ""))
            data_path = folder_path / "conandata.yml"
            data = (
                yaml.safe_load(data_path.read_text(encoding="utf-8"))
                if data_path.is_file()
                else {}
            )
            sources = (data or {}).get("sources", {})
            for version in versions:
                source = sources.get(version) or {}
                source_items = (
                    [item for item in source if isinstance(item, dict)]
                    if isinstance(source, list)
                    else [source]
                    if isinstance(source, dict)
                    else []
                )
                urls = [
                    url
                    for item in source_items
                    for url in scalar_strings(item.get("url"))
                ]
                checksums = [
                    checksum
                    for item in source_items
                    for checksum in source_checksums(item)
                ]
                source_urls.extend(urls)
                version_rows.append(
                    {
                        "version": version,
                        "source_urls": urls,
                        "checksums": checksums,
                        "summary": folder_description.summary_text or None,
                        "description": folder_description.body_html or None,
                        "licenses": clean_licenses(
                            scalar_strings(folder_meta.get("license"))
                        )
                        or None,
                        "homepage": str(folder_meta.get("homepage") or "") or None,
                        "dependencies": [
                            {"name": dependency} for dependency in folder_dependencies
                        ]
                        or None,
                        "features": [
                            {
                                "name": option_name,
                                "default": package_defaults.get(option_name),
                            }
                            for option_name in sorted(folder_options)
                        ]
                        or None,
                    }
                )
        name = str(recipe_meta.get("name") or config_path.parent.name)
        relative = config_path.relative_to(root)
        homepage = (
            recipe_meta.get("homepage")
            if isinstance(recipe_meta.get("homepage"), str)
            else ""
        )
        repository = repository_identity(homepage) or next(
            (identity for url in source_urls if (identity := repository_identity(url))),
            "",
        )
        rendered_description = render_text(str(recipe_meta.get("description") or ""))
        records.append(
            {
                "id": f"conan:{name}",
                "registry": "conan",
                "name": name,
                "summary": rendered_description.summary_text,
                "description": rendered_description.body_html,
                "description_format": "html",
                "licenses": clean_licenses(scalar_strings(recipe_meta.get("license"))),
                "homepage": homepage,
                "repository_url": repository,
                "source_urls": clean_list(source_urls),
                "topics": scalar_strings(recipe_meta.get("topics")),
                "languages": scalar_strings(recipe_meta.get("languages")),
                "package_type": str(recipe_meta.get("package_type") or ""),
                "deprecated": bool(recipe_meta.get("deprecated", False)),
                "authors": scalar_strings(recipe_meta.get("author")),
                "dependencies": clean_list(package_dependencies),
                "options": sorted(package_options),
                "default_options": package_defaults,
                "versions": version_rows,
                "native_url": f"https://conan.io/center/recipes/{name}",
                "recipe_url": github_url(REPOSITORIES["conan"], revision, relative),
            }
        )
    return records


def inspect_recipes(root: Path, package: str | None = None) -> list[dict[str, Any]]:
    """Load Conan Center recipes for the package inspection command."""
    if not (root / "recipes").is_dir():
        raise ValueError(f"Conan Center recipes not found below {root}")
    records = parse_conan(root, {package} if package else None)
    if package and not records:
        raise ValueError(f"package {package!r} was not found")
    return records
