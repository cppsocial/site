import ast
import json
import re
import subprocess
import warnings
from collections import defaultdict
from collections.abc import Iterable
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit, urlunsplit

REPOSITORIES = {
    "conan": "https://github.com/conan-io/conan-center-index",
    "vcpkg": "https://github.com/microsoft/vcpkg",
    "spack": "https://github.com/spack/spack-packages",
    "meson": "https://github.com/mesonbuild/wrapdb",
    "bazel": "https://github.com/bazelbuild/bazel-central-registry",
    "cppget": "https://pkg.cppget.org/1/",
    "hunter": "https://github.com/cpp-pm/hunter",
    "xmake": "https://github.com/xmake-io/xmake-repo",
}


def repository_revision(path: Path) -> str:
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "HEAD"],
            cwd=path,
            text=True,
            stderr=subprocess.DEVNULL,
        ).strip()
    except (OSError, subprocess.CalledProcessError):
        return ""


def clean_list(values: Iterable[object]) -> list[str]:
    return list(
        dict.fromkeys(str(value).strip() for value in values if str(value).strip())
    )


def clean_licenses(values: Iterable[object]) -> list[str]:
    missing = {"noassertion", "unknown", "unspecified"}
    aliases = {
        "apache 2.0": "Apache-2.0",
        "apache-2": "Apache-2.0",
        "boost": "BSL-1.0",
        "boost software license": "BSL-1.0",
        "bsd-2": "BSD-2-Clause",
        "bsd-3": "BSD-3-Clause",
        "gplv2": "GPL-2.0-only",
        "gplv3": "GPL-3.0-only",
        "lgplv2.1": "LGPL-2.1-only",
        "mit license": "MIT",
        "zlib license": "Zlib",
    }
    result = []
    for value in clean_list(values):
        if value.casefold() in missing:
            continue
        result.append(aliases.get(value.casefold(), value))
    return list(dict.fromkeys(result))


_SPDX_TOKEN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9.+-]*$")


def spdx_license_url(identifier: str) -> str:
    """Return the canonical SPDX page for one identifier, not an expression."""
    if not _SPDX_TOKEN.fullmatch(identifier):
        return ""
    return f"https://spdx.org/licenses/{identifier}.html"


def scalar_strings(value: object) -> list[str]:
    if isinstance(value, str):
        return [value]
    if isinstance(value, (list, tuple)):
        return [item for item in value if isinstance(item, str)]
    return []


def source_checksums(values: dict[str, Any]) -> list[str]:
    return [
        f"{algorithm}:{digest.casefold()}"
        for algorithm in ("md5", "sha1", "sha256", "sha512")
        if isinstance(digest := values.get(algorithm), str) and digest
    ]


def version_identity(registry: str, version: str) -> tuple[str, str]:
    """Return the comparable upstream version and an inferred package revision.

    The original manager spelling remains the release identifier. This only
    supplies the comparison key used across registries.
    """
    upstream = version.strip()
    revision = ""
    if re.match(r"^[vV]\d", upstream):
        upstream = upstream[1:]
    if registry == "cppget":
        match = re.match(r"^(.*)\+(\d+)$", upstream)
        if match:
            upstream, revision = match.groups()
    elif registry == "hunter":
        match = re.match(
            r"^(.*?)(?:[-_.]hunter(?:[-_.]?([0-9]+))?)$",
            upstream,
            re.IGNORECASE,
        )
        if match:
            upstream = match.group(1)
            revision = "hunter" + (f"-{match.group(2)}" if match.group(2) else "")
    return upstream, revision


def normalize_package_record(package: dict[str, Any]) -> dict[str, Any]:
    """Convert legacy URL/checksum pairs to scoped, typed artifacts.

    Parsers can migrate independently while catalog output and matching use one
    representation. Empty optional values are omitted to keep YAML and JSON
    payloads compact.
    """
    result = dict(package)
    registry = str(result.get("registry") or "")
    artifact_kind = (
        "registry_package"
        if registry in {"cppget", "meson"}
        else "upstream_source"
    )
    normalized_versions = []
    for raw in result.get("versions") or []:
        version = dict(raw)
        exact_version = str(version.get("version") or "")
        upstream, inferred_revision = version_identity(registry, exact_version)
        if upstream and upstream != exact_version and not version.get("upstream_version"):
            version["upstream_version"] = upstream
        if inferred_revision and not version.get("packaging_revision"):
            version["packaging_revision"] = inferred_revision
        artifacts = [dict(item) for item in version.get("artifacts") or []]
        urls = clean_list(version.pop("source_urls", []) or [])
        checksums = clean_list(version.pop("checksums", []) or [])
        known_urls = {str(item.get("url") or "") for item in artifacts}
        for url in urls:
            if url in known_urls:
                continue
            artifact: dict[str, Any] = {"kind": artifact_kind, "url": url}
            if checksums and len(urls) == 1:
                artifact["checksums"] = checksums
            artifacts.append(artifact)
        if checksums and not urls and artifacts and not any(
            item.get("checksums") for item in artifacts
        ):
            artifacts[0]["checksums"] = checksums
        elif checksums and not urls and not artifacts:
            artifacts.append({"kind": artifact_kind, "checksums": checksums})
        if artifacts:
            version["artifacts"] = artifacts
        normalized_versions.append(_without_empty(version))
    if normalized_versions:
        result["versions"] = normalized_versions
    else:
        result.pop("versions", None)
    result.pop("source_urls", None)
    return _without_empty(result)


def _without_empty(values: dict[str, Any]) -> dict[str, Any]:
    result = {}
    for key, value in values.items():
        if value is None or value == "" or value is False:
            continue
        if isinstance(value, (list, dict, tuple, set)) and not value:
            continue
        result[key] = value
    return result


def github_url(repository: str, revision: str, relative: Path) -> str:
    return f"{repository}/blob/{revision or 'HEAD'}/{relative.as_posix()}"


def _literal(node: ast.AST) -> Any:
    try:
        return ast.literal_eval(node)
    except (ValueError, TypeError):
        return None


def _class_metadata(path: Path) -> dict[str, Any]:
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", SyntaxWarning)
            tree = ast.parse(path.read_text(encoding="utf-8-sig"), filename=str(path))
    except SyntaxError:
        return {}
    classes = [node for node in tree.body if isinstance(node, ast.ClassDef)]
    package = next(
        (node for node in classes if node.name.endswith(("Conan", "Package"))), None
    )
    package = package or (classes[0] if classes else None)
    if package is None:
        return {}
    result: dict[str, Any] = {"description": ast.get_docstring(package) or ""}
    for statement in package.body:
        if not isinstance(statement, ast.Assign) or len(statement.targets) != 1:
            continue
        target = statement.targets[0]
        if isinstance(target, ast.Name):
            result[target.id] = _literal(statement.value)
    calls: defaultdict[str, list[tuple[list[Any], dict[str, Any]]]] = defaultdict(list)
    for statement in package.body:
        if not isinstance(statement, ast.Expr) or not isinstance(
            statement.value, ast.Call
        ):
            continue
        call = statement.value
        if not isinstance(call.func, ast.Name):
            continue
        calls[call.func.id].append(
            (
                [_literal(arg) for arg in call.args],
                {item.arg: _literal(item.value) for item in call.keywords if item.arg},
            )
        )
    result["calls"] = calls
    return result


def option_value(value: object) -> str:
    if isinstance(value, bool):
        return str(value).lower()
    if isinstance(value, (str, int, float)):
        return str(value)
    return json.dumps(value, sort_keys=True)


def repository_identity(value: str) -> str:
    if not value:
        return ""
    parsed = urlsplit(value.strip())
    host = parsed.netloc.casefold().removeprefix("www.")
    if host not in {"github.com", "gitlab.com", "bitbucket.org", "codeberg.org"}:
        return ""
    parts = [part for part in parsed.path.split("/") if part]
    if len(parts) < 2:
        return ""
    path = "/".join(parts[:2]).removesuffix(".git").casefold()
    return urlunsplit(("https", host, "/" + path, "", ""))
