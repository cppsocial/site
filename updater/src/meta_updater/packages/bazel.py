import ast
import base64
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


def _bazel_repository_url(value: str) -> str:
    if value.startswith("github:"):
        return f"https://github.com/{value.removeprefix('github:')}"
    return value


def _bazel_checksums(integrity: str) -> list[str]:
    checksums = []
    for value in integrity.split():
        algorithm, encoded = value.split("-", 1)
        digest = base64.b64decode(encoded, validate=True).hex()
        checksums.append(f"{algorithm.casefold()}:{digest}")
    return checksums


def _bazel_literal(node: ast.expr | None, constants: dict[str, Any]) -> Any:
    if node is None:
        return None
    if isinstance(node, ast.Name):
        return constants.get(node.id)

    try:
        return ast.literal_eval(node)
    except (ValueError, TypeError):
        return None


def _bazel_module(path: Path) -> tuple[list[dict[str, Any]], list[str]]:
    try:
        tree = ast.parse(
            path.read_text(encoding="utf-8"),
            filename=str(path),
        )
    except (OSError, SyntaxError):
        return [], []

    constants: dict[str, Any] = {}
    dependencies: list[dict[str, Any]] = []
    compatibility: list[str] = []

    for statement in tree.body:
        # MODULE.bazel occasionally uses constants such as:
        #
        # IS_RELEASE = True
        # bazel_dep(..., dev_dependency = IS_RELEASE)
        if (
            isinstance(statement, ast.Assign)
            and len(statement.targets) == 1
            and isinstance(statement.targets[0], ast.Name)
        ):
            value = _bazel_literal(statement.value, constants)
            if value is not None:
                constants[statement.targets[0].id] = value
            continue

        if not isinstance(statement, ast.Expr):
            continue

        call = statement.value
        if (
            not isinstance(call, ast.Call)
            or not isinstance(call.func, ast.Name)
            or call.func.id not in {"bazel_dep", "module"}
        ):
            continue

        arguments = {
            keyword.arg: keyword.value
            for keyword in call.keywords
            if keyword.arg is not None
        }
        if call.func.id == "module":
            values = _bazel_literal(arguments.get("bazel_compatibility"), constants)
            if isinstance(values, list):
                compatibility.extend(str(value) for value in values)
            continue

        name_node = arguments.get("name")
        if name_node is None and call.args:
            name_node = call.args[0]

        name = _bazel_literal(name_node, constants)
        dev_dependency = _bazel_literal(
            arguments.get("dev_dependency", ast.Constant(False)),
            constants,
        )

        version = _bazel_literal(arguments.get("version"), constants)
        if isinstance(name, str) and name:
            dependency: dict[str, Any] = {"name": name}
            if isinstance(version, str) and version:
                dependency["constraint"] = version
            if dev_dependency is True:
                dependency["kind"] = "dev"
            dependencies.append(dependency)

    unique = {json.dumps(value, sort_keys=True): value for value in dependencies}
    return list(unique.values()), clean_list(compatibility)


def _bazel_maintainers(values: object) -> list[str]:
    result = []
    for value in values if isinstance(values, list) else []:
        if isinstance(value, str):
            result.append(value)
            continue
        if not isinstance(value, dict):
            continue

        name = str(value.get("name") or "")
        github = str(value.get("github") or "")
        email = str(value.get("email") or "")
        if name and github:
            result.append(f"{name} (@{github})")
        elif name:
            result.append(name)
        elif github:
            result.append(f"@{github}")
        elif email:
            result.append(email)

    return clean_list(result)


def parse_bazel(root: Path) -> list[dict[str, Any]]:
    revision = repository_revision(root)
    records = []

    for metadata_path in sorted((root / "modules").glob("*/metadata.json")):
        module_root = metadata_path.parent
        name = module_root.name
        metadata = json.loads(metadata_path.read_text(encoding="utf-8"))

        repositories = [
            _bazel_repository_url(value)
            for value in metadata.get("repository", [])
            if isinstance(value, str)
        ]
        repository = next(
            (
                identity
                for value in repositories
                if (identity := repository_identity(value))
            ),
            "",
        )

        versions = []
        source_urls = []
        dependencies = []

        # BCR keeps metadata.json versions sorted by Bazel's Version ordering.
        # Overwriting only with non-empty dependency sets therefore folds the
        # latest non-empty set into the package-level catalog field.
        for version in metadata.get("versions", []):
            version = str(version)
            version_root = module_root / version
            source_path = version_root / "source.json"
            if not source_path.is_file():
                continue

            source = json.loads(source_path.read_text(encoding="utf-8"))
            urls = clean_list(
                [
                    source.get("url", ""),
                    *source.get("mirror_urls", []),
                ]
            )
            source_urls.extend(urls)

            version_dependencies, compatibility = _bazel_module(
                version_root / "MODULE.bazel"
            )
            if version_dependencies:
                dependencies = [
                    item["name"]
                    for item in version_dependencies
                    if item.get("kind") != "dev"
                ]

            yanked_reason = (metadata.get("yanked_versions") or {}).get(version)
            upstream_version, marker, packaging_revision = version.partition(".bcr.")

            versions.append(
                {
                    "version": upstream_version if marker else version,
                    "packaging_revision": packaging_revision or None,
                    "lifecycle": "yanked" if yanked_reason else None,
                    "lifecycle_reason": yanked_reason or None,
                    "dependencies": version_dependencies or None,
                    "compatibility": compatibility or None,
                    "artifacts": [
                        {
                            "kind": "upstream_source",
                            "url": url,
                            "checksums": _bazel_checksums(
                                source.get("integrity", "")
                            )
                            or None,
                        }
                        for url in urls
                    ],
                }
            )

        records.append(
            {
                "id": f"bazel:{name}",
                "registry": "bazel",
                "name": name,
                "homepage": str(metadata.get("homepage") or ""),
                "repository_url": repository,
                "source_urls": clean_list(source_urls),
                "maintainers": _bazel_maintainers(metadata.get("maintainers", [])),
                "deprecated": bool(metadata.get("deprecated")),
                "deprecation_reason": str(metadata.get("deprecated") or "") or None,
                "dependencies": dependencies,
                "components": [],
                "versions": versions,
                "recipe_url": github_url(
                    REPOSITORIES["bazel"],
                    revision,
                    metadata_path.relative_to(root),
                ),
            }
        )

    return records
