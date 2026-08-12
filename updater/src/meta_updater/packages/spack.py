from pathlib import Path
from typing import Any

from .common import (
    REPOSITORIES,
    _class_metadata,
    clean_licenses,
    clean_list,
    github_url,
    option_value,
    repository_identity,
    repository_revision,
    scalar_strings,
    source_checksums,
)
from ..shared.text import render_text


def parse_spack(root: Path) -> list[dict[str, Any]]:
    revision = repository_revision(root)
    base = root / "repos" / "spack_repo" / "builtin" / "packages"
    records = []
    for recipe in sorted(base.glob("*/package.py")):
        meta = _class_metadata(recipe)
        calls = meta.get("calls", {})
        name = recipe.parent.name.removeprefix("_").replace("_", "-")
        versions = [
            {
                "version": str(args[0]),
                "preferred": bool(keywords.get("preferred")) or None,
                "lifecycle": "deprecated" if keywords.get("deprecated") else None,
                "artifacts": [
                    {
                        "kind": "upstream_source",
                        "checksums": source_checksums(keywords),
                    }
                ]
                if source_checksums(keywords)
                else None,
            }
            for args, keywords in calls.get("version", [])
            if args and args[0] is not None
        ]
        git_urls = scalar_strings(meta.get("git"))
        source_urls = scalar_strings(meta.get("url"))
        repository = next(
            (
                identity
                for url in [*git_urls, str(meta.get("homepage") or ""), *source_urls]
                if (identity := repository_identity(url))
            ),
            "",
        )
        licenses = [
            str(args[0]) for args, _ in calls.get("license", []) if args and args[0]
        ]
        maintainers = [
            str(value)
            for args, _ in calls.get("maintainers", [])
            for value in args
            if value
        ]
        dependencies = [
            str(args[0]).split("@")[0].split("+")[0].split("~")[0]
            for args, _ in calls.get("depends_on", [])
            if args and args[0]
        ]
        dependency_details = [
            {
                "name": str(args[0]).split("@")[0].split("+")[0].split("~")[0],
                "constraint": str(args[0]) or None,
                "kind": ",".join(scalar_strings(keywords.get("type"))) or None,
                "condition": str(keywords.get("when") or "") or None,
            }
            for args, keywords in calls.get("depends_on", [])
            if args and args[0]
        ]
        options = [
            str(args[0]) for args, _ in calls.get("variant", []) if args and args[0]
        ]
        default_options = {
            str(args[0]): option_value(keywords["default"])
            for args, keywords in calls.get("variant", [])
            if args and args[0] and keywords.get("default") is not None
        }
        features = [
            {
                "name": str(args[0]),
                "description": str(keywords.get("description") or "") or None,
                "values": [str(value) for value in keywords.get("values", [])]
                if isinstance(keywords.get("values"), (list, tuple))
                else None,
                "default": option_value(keywords["default"])
                if keywords.get("default") is not None
                else None,
                "condition": str(keywords.get("when") or "") or None,
            }
            for args, keywords in calls.get("variant", [])
            if args and args[0]
        ]

        # filter out unrelated packages
        disallowed_prefixes = "py-", "perl-", "ruby-", "r-"
        disallowed_deps = "py-setuptool"
        if (any(name.startswith(p) for p in disallowed_prefixes)
            or any(map(lambda v:v in disallowed_deps, dependencies))):
            continue

        rendered_description = render_text(str(meta.get("description") or ""))
        records.append(
            {
                "id": f"spack:{name}",
                "registry": "spack",
                "name": name,
                "summary": rendered_description.summary_text,
                "description": rendered_description.body_html,
                "description_format": "html",
                "licenses": clean_licenses(licenses),
                "homepage": str(meta.get("homepage") or ""),
                "repository_url": repository,
                "source_urls": clean_list(source_urls),
                "maintainers": clean_list(maintainers),
                "topics": scalar_strings(meta.get("tags")),
                "dependencies": clean_list(dependencies),
                "dependency_details": dependency_details,
                "options": clean_list(options),
                "default_options": default_options,
                "features": features,
                "versions": versions,
                "recipe_url": github_url(
                    REPOSITORIES["spack"], revision, recipe.relative_to(root)
                ),
            }
        )
    return records
