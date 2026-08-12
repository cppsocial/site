import json
import os
import subprocess
import tempfile
from pathlib import Path
from typing import Any

from .common import (
    REPOSITORIES,
    clean_licenses,
    clean_list,
    github_url,
    repository_identity,
    repository_revision,
)
from ..shared.text import render_text


def _xmake_url(url: str) -> str:
    return url.removeprefix("git+")


def parse_xmake(root: Path) -> list[dict[str, Any]]:
    revision = repository_revision(root)
    exporter = Path(__file__).with_name("xmake_export.lua")

    with tempfile.TemporaryDirectory() as temporary:
        output = Path(temporary) / "packages.json"
        environment = os.environ.copy()
        environment["XMAKE_ROOT"] = "y"

        try:
            subprocess.run(
                [
                    "xmake",
                    "l",
                    str(exporter),
                    f"--repo={root.resolve()}",
                    f"--out={output}",
                ],
                check=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                env=environment,
            )
        except FileNotFoundError as error:
            raise RuntimeError(
                "xmake is required to parse xmake-repo"
            ) from error
        except subprocess.CalledProcessError as error:
            details = (error.stderr or error.stdout or "").strip()
            message = "xmake package exporter failed"
            if details:
                message += f":\n{details}"
            raise RuntimeError(message) from error

        data = json.loads(output.read_text(encoding="utf-8"))

    # Some recipes are intentionally not evaluable for the probe environments
    # (for example opencv-mobile). The exporter records these in `skipped`; they
    # should not make the entire registry update fail. Still fail if the exporter
    # could not load anything at all, which indicates a systemic problem.
    packages = data.get("packages", [])
    if not packages and data.get("skipped"):
        raise RuntimeError("xmake failed to load any package recipes")

    records = []

    for package in packages:
        name = package["name"]
        dependencies = clean_list(package.get("dependencies", []))
        components = clean_list(package.get("components", []))
        configs = [
            {
                "name": name,
                "description": value.get("description") or None,
                "values": clean_list(value.get("values", [])) or None,
                "default": value.get("default") or None,
            }
            for name, value in sorted((package.get("configs") or {}).items())
        ]

        versions = []
        source_urls = []

        for entry in package.get("versions", []):
            urls = clean_list(
                [_xmake_url(url) for url in entry.get("source_urls", [])]
            )
            source_urls.extend(urls)

            versions.append(
                {
                    "version": entry["version"],
                    "source_urls": urls,
                    "checksums": clean_list(entry.get("checksums", [])),
                }
            )

        source_urls = clean_list(source_urls)
        raw_urls = clean_list(
            [_xmake_url(url) for url in package.get("urls", [])]
        )

        repository = next(
            (
                identity
                for url in [*raw_urls, *source_urls]
                if (identity := repository_identity(url))
            ),
            "",
        )
        homepage = str(package.get("homepage") or "")
        if not repository:
            repository = repository_identity(homepage)

        rendered_description = render_text(str(package.get("description") or ""))
        records.append(
            {
                "id": f"xmake:{name}",
                "registry": "xmake",
                "name": name,
                "summary": rendered_description.summary_text,
                "description": rendered_description.body_html,
                "description_format": "html",
                "licenses": clean_licenses(package.get("licenses", [])),
                "homepage": homepage,
                "repository_url": repository,
                "source_urls": source_urls,
                "dependencies": dependencies,
                "components": components,
                "external_names": clean_list(package.get("extsources", [])),
                "platforms": clean_list(package.get("platforms", [])),
                "package_type": str(package.get("kind") or ""),
                "features": configs,
                "versions": versions,
                "recipe_url": github_url(
                    REPOSITORIES["xmake"],
                    revision,
                    Path(package["recipe"]),
                ),
            }
        )

    return records
