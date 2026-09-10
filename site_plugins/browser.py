import hashlib
import json
import re
import sys
from collections import Counter
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from pathlib import Path
from typing import Any

import brotli
import yaml
from meta_updater.shared.files import update_bytes
from meta_updater.shared.text import render_text
from site_generator import PluginFile, PluginResult, SiteConfig
from site_generator.browser_data import update_keyed_collection

from .catalog import browser_records

HASH_MANIFEST = "browser-data-hashes.json"
HASH_MANIFEST_VERSION = 11
LEGACY_HASH_MANIFEST = "hashes.json"
SEARCH_FORMAT_VERSION = 11
YAML_LOADER = getattr(yaml, "CSafeLoader", yaml.SafeLoader)


def _hash_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        while chunk := source.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def _input_files(config: SiteConfig) -> list[Path]:
    files = {
        path
        for directory in (
            config.data / "blogs" / "posts",
            config.data / "youtube" / "videos",
            config.data / "books",
            config.content / "books",
            config.content / "youtube",
        )
        for path in directory.glob("*.yaml")
        if path.is_file()
    }
    files.update(
        {
            Path(__file__),
            Path(__file__).with_name("catalog.py"),
            Path(render_text.__code__.co_filename),
        }
    )
    blog_sources = config.content / "blogs" / "sources.yaml"
    if blog_sources.is_file():
        files.add(blog_sources)
    files.update(
        path
        for path in (config.data / "packages").glob("*.yaml")
        if path.is_file() and path.stem not in {"matches", "provenance"}
    )
    return sorted(files, key=lambda path: path.resolve().as_posix())


def _manifest_name(config: SiteConfig, path: Path) -> str:
    resolved = path.resolve()
    try:
        return resolved.relative_to(config.root.resolve()).as_posix()
    except ValueError:
        return resolved.as_posix()


def _file_hashes(config: SiteConfig, paths: list[Path]) -> dict[str, str]:
    return {_manifest_name(config, path): _hash_file(path) for path in paths}


def _output_files(output: Path) -> list[Path]:
    if not output.is_dir():
        return []
    return sorted(
        (path for path in output.rglob("*") if path.is_file()),
        key=lambda path: path.relative_to(output).as_posix(),
    )


def _output_hashes(output: Path) -> dict[str, str]:
    return {
        path.relative_to(output).as_posix(): _hash_file(path)
        for path in _output_files(output)
    }


def _read_hash_manifest(path: Path) -> dict[str, Any] | None:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError, OSError, UnicodeError):
        return None
    if not isinstance(value, dict):
        return None
    return value


def _cache_matches(manifest: Path, inputs: dict[str, str], output: Path) -> bool:
    cached = _read_hash_manifest(manifest)
    return bool(
        cached
        and cached.get("version") == HASH_MANIFEST_VERSION
        and cached.get("algorithm") == "sha256"
        and cached.get("inputs") == inputs
        and cached.get("outputs") == _output_hashes(output)
    )


def _write_hash_manifest(
    path: Path, inputs: dict[str, str], outputs: dict[str, str]
) -> bool:
    encoded = (
        json.dumps(
            {
                "version": HASH_MANIFEST_VERSION,
                "algorithm": "sha256",
                "inputs": inputs,
                "outputs": outputs,
            },
            indent=2,
            sort_keys=True,
        )
        + "\n"
    ).encode()
    return update_bytes(path, encoded)


def _write_json(path: Path, value: Any) -> bool:
    encoded = json.dumps(value, separators=(",", ":"), sort_keys=True).encode()
    return update_bytes(path, encoded)


def _load_yaml(path: Path, default: Any) -> Any:
    # These catalogs are tens of megabytes. ``yaml.safe_load`` always selects
    # the pure-Python SafeLoader, even when PyYAML's equivalent LibYAML-backed
    # loader is installed. The C loader keeps the same safe tag set and parsed
    # values while making a clean build substantially faster.
    return yaml.load(path.read_text(encoding="utf-8"), Loader=YAML_LOADER) or default


def _render_description(value: str) -> str:
    return render_text(value, media_type="text/markdown").body_html


def _visible_recent(directory: Path, id_field: str) -> list[dict[str, Any]]:
    if not directory.is_dir():
        raise FileNotFoundError(directory)
    records = []
    for path in sorted(directory.glob("*.yaml")):
        values = _load_yaml(path, [])
        if not isinstance(values, list):
            raise TypeError(f"{path}: expected a list")
        for value in values:
            if not isinstance(value, dict) or not value.get(id_field):
                raise ValueError(f"{path}: entry requires {id_field}")
            if value.get("hidden") is not True:
                records.append(value)
    return records


def _blog_records(config: SiteConfig) -> list[dict[str, Any]]:
    sources = _load_yaml(config.content / "blogs" / "sources.yaml", [])
    authors = {
        source["id"]: source.get("author", "")
        for source in sources
        if isinstance(source, dict) and source.get("id")
    }
    result = []
    for post in _visible_recent(config.data / "blogs" / "posts", "post_id"):
        record = {
            "id": post["post_id"],
            "title": post["title"],
            "source": post["source_title"],
            "url": post["url"],
            "published": post["published"].isoformat(),
            "description": _render_description(post.get("description", "")),
        }
        if author := authors.get(post.get("source_id", "")):
            record["author"] = author
        if post.get("tags"):
            record["tags"] = post["tags"]
        if post.get("cpp_relevance") is not None:
            record["cpp_relevance"] = post["cpp_relevance"]
        result.append(record)
    return sorted(result, key=lambda item: item["published"], reverse=True)


def _channel_titles(content: Path) -> dict[str, str]:
    result = {}
    for name in ("channels.yaml", "organizations.yaml", "conferences.yaml"):
        path = content / name
        if not path.is_file():
            continue
        document = _load_yaml(path, {})
        for card in document.get("cards", []) if isinstance(document, dict) else []:
            if card.get("channel_id") and not card.get("hidden", False):
                result[card["channel_id"]] = card["title"]
    return result


def _youtube_records(config: SiteConfig) -> list[dict[str, Any]]:
    titles = _channel_titles(config.content / "youtube")
    result = []
    videos = config.data / "youtube" / "videos"
    if not videos.is_dir():
        raise FileNotFoundError(videos)
    for path in sorted(videos.glob("*.yaml")):
        channel_id = path.stem
        if channel_id not in titles:
            continue
        values = _load_yaml(path, [])
        if not isinstance(values, list):
            raise TypeError(f"{path}: expected a list")
        for video in values:
            if not isinstance(video, dict) or not video.get("video_id"):
                raise ValueError(f"{path}: entry requires video_id")
            if video.get("hidden") is True:
                continue
            record = {
                "id": video["video_id"],
                "title": video["title"],
                "channel": titles[channel_id],
                "url": video["url"],
                "published": video["published"].isoformat(),
                "thumbnail_url": video.get("thumbnail_url", ""),
                "description": video.get("description", ""),
            }
            if video.get("tags"):
                record["tags"] = video["tags"]
            if video.get("cpp_relevance") is not None:
                record["cpp_relevance"] = video["cpp_relevance"]
            result.append(record)
    return sorted(result, key=lambda item: item["published"], reverse=True)


def _book_records(config: SiteConfig) -> list[dict[str, Any]]:
    metadata = _load_yaml(config.data / "books" / "metadata.yaml", {})
    document = _load_yaml(config.content / "books" / "books.yaml", {})
    cards = document.get("cards", []) if isinstance(document, dict) else []
    result = []
    for card in cards:
        if card.get("hidden") is True:
            continue
        isbn = str(card.get("isbn", ""))
        book = metadata.get(isbn)
        if not isbn or not isinstance(book, dict):
            raise ValueError(f"book metadata is missing for ISBN {isbn or '<empty>'}")
        published_label = str(book.get("publish_date", ""))
        record = {
            **book,
            "id": isbn,
            "cover_url": card.get("cover_url") or book.get("cover_url", ""),
            "published": _book_published_date(published_label),
        }
        result.append(record)
    return sorted(
        result, key=lambda item: (item["published"], item["title"]), reverse=True
    )


def _book_published_date(label: str) -> str:
    value = re.sub(r"(?<=\d)(?:st|nd|rd|th)\b", "", label.strip(), flags=re.IGNORECASE)
    for pattern in (
        "%Y-%m-%d",
        "%B %d, %Y",
        "%b %d, %Y",
        "%B %Y",
        "%b %Y",
        "%Y-%m",
        "%Y",
    ):
        try:
            # The source describes a calendar date, not an instant or timezone.
            return datetime.strptime(value, pattern).date().isoformat()  # noqa: DTZ007
        except ValueError:
            pass
    year = next(iter(re.findall(r"\b(?:1[0-9]{3}|20[0-9]{2})\b", value)), "")
    return f"{year}-01-01" if year else ""


def _apply_corrections(catalogs: dict[str, list[dict]], values: list[dict]) -> None:
    by_id = {item["id"]: item for catalog in catalogs.values() for item in catalog}
    for correction in values:
        target = by_id.get(correction.get("package"))
        if target is None:
            continue
        if version := correction.get("version"):
            target = next(
                (
                    item
                    for item in target.get("versions", [])
                    if item.get("version") == version
                ),
                None,
            )
            if target is None:
                continue
        field = correction["field"]
        operation = correction.get("operation", "replace")
        if operation == "remove":
            target.pop(field, None)
        elif operation == "add":
            additions = correction.get("value")
            additions = additions if isinstance(additions, list) else [additions]
            target[field] = list(dict.fromkeys([*target.get(field, []), *additions]))
        else:
            target[field] = correction.get("value")


def _package_data(config: SiteConfig) -> tuple[list[dict], list[dict], list[str]]:
    root = config.data / "packages"
    overrides = _load_yaml(root / "overrides.yaml", {})
    ignored = set(overrides.get("ignored", []))
    ignored_prefixes = tuple(overrides.get("ignored_prefixes", []))
    reserved = {"entities", "matches", "overrides", "provenance"}
    catalogs = {}
    for path in sorted(root.glob("*.yaml")):
        if path.stem in reserved:
            continue
        document = _load_yaml(path, {})
        packages = document.get("packages", [])
        if not isinstance(packages, list):
            raise TypeError(f"{path}: packages must be a list")
        catalogs[path.stem] = [
            item
            for item in packages
            if item.get("id") not in ignored
            and not item.get("id", "").startswith(ignored_prefixes)
        ]
    _apply_corrections(catalogs, overrides.get("corrections", []))
    by_id = {item["id"]: item for values in catalogs.values() for item in values}
    entities = _load_yaml(root / "entities.yaml", {}).get("entities", [])
    master = []
    for entity in entities:
        package_ids = [value for value in entity["packages"] if value in by_id]
        if not package_ids:
            continue
        variants = [by_id[value] for value in package_ids]
        names = Counter(item["name"] for item in variants)
        name = entity.get("name") or min(
            names,
            key=lambda value: (-names[value], len(value), value.casefold(), value),
        )
        aliases = entity.get("aliases")
        if aliases is None:
            aliases = sorted({item["name"] for item in variants} - {name})
        master.append(
            {
                "id": entity["id"],
                "name": name,
                "aliases": aliases,
                "packages": [
                    {"package_id": value, "registry": value.split(":", 1)[0]}
                    for value in package_ids
                ],
            }
        )
    summaries, details = browser_records(master, catalogs, overrides.get("preferences"))
    return summaries, details, sorted(catalogs)


def _tracked_update(
    source: Path,
    directory: Path,
    update: Callable[[], bool],
) -> PluginResult:
    result = PluginResult()
    before = {path for path in directory.iterdir()} if directory.is_dir() else set()
    if not update():
        return result
    after = {path for path in directory.iterdir()} if directory.is_dir() else set()
    result.generated.extend(PluginFile(source, path) for path in sorted(after))
    result.removed.extend(sorted(before - after))
    return result


def _update_search_collection(
    directory: Path,
    records: list[dict[str, Any]],
    *,
    fields: dict[str, dict[str, Any]],
    exact: list[str],
    qualifiers: dict[str, dict[str, Any]] | None = None,
    metadata: dict[str, Any] | None = None,
) -> bool:
    """Publish one immutable snapshot without client-side persistence state."""
    normalized: dict[str, dict[str, Any]] = {}
    for raw in records:
        record = dict(raw)
        record_id = str(record.get("id", ""))
        if not record_id:
            raise ValueError("browser records require a non-empty id")
        if record_id in normalized:
            raise ValueError(f"duplicate browser record id: {record_id}")
        record["id"] = record_id
        normalized[record_id] = record

    snapshot = json.dumps(
        {"records": sorted(normalized.values(), key=lambda value: value["id"])},
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode()
    snapshot_hash = hashlib.sha256(snapshot).hexdigest()
    snapshot_name = f"records-{snapshot_hash[:16]}.json"
    files = {snapshot_name: snapshot}
    revision_source = json.dumps(
        {
            "snapshot": snapshot_hash,
            "fields": fields,
            "exact": exact,
            "qualifiers": qualifiers,
            "version": SEARCH_FORMAT_VERSION,
        },
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode()
    manifest = {
        **(metadata or {}),
        "version": SEARCH_FORMAT_VERSION,
        "kind": "search-records",
        "revision": hashlib.sha256(revision_source).hexdigest()[:24],
        "count": len(normalized),
        "min_query_length": 2,
        "fields": fields,
        "exact": exact,
        "qualifiers": qualifiers or {},
        "file": snapshot_name,
    }
    files["index.json"] = json.dumps(
        manifest,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode()
    files.update(
        {
            f"{name}.br": brotli.compress(value, mode=brotli.MODE_TEXT, quality=11)
            for name, value in list(files.items())
        }
    )

    current = (
        {
            path.name: path.read_bytes()
            for path in directory.iterdir()
            if path.is_file()
            and (path.name.endswith(".json") or path.name.endswith(".br"))
        }
        if directory.is_dir()
        else {}
    )
    if current == files:
        return False
    directory.mkdir(parents=True, exist_ok=True)
    for name, value in files.items():
        update_bytes(directory / name, value)
    for name in current.keys() - files.keys():
        (directory / name).unlink(missing_ok=True)
    return True


def _feed_search_fields(source_property: str) -> dict[str, dict[str, Any]]:
    return {
        "title": {"properties": ["title"], "boost": 10},
        "content": {"properties": ["description"]},
        "source": {"properties": [source_property], "boost": 4},
        "tags": {"properties": ["tags"], "boost": 3},
    }


def _build_data(config: SiteConfig) -> tuple[PluginResult, bool]:
    result = PluginResult()
    successful = True
    output = config.output / "data"
    books = _book_records(config)
    jobs = (
        (
            config.data / "books",
            output / "books",
            lambda: _update_search_collection(
                output / "books",
                books,
                fields={
                    "title": {
                        "properties": ["title"],
                        "boost": 10,
                    },
                    "content": {
                        "properties": ["subtitle", "description"],
                    },
                    "source": {
                        "properties": ["authors"],
                        "boost": 5,
                    },
                    "tags": {
                        "properties": ["subjects"],
                        "boost": 3,
                    },
                    "metadata": {
                        "properties": [
                            "publisher",
                            "publish_date",
                            "isbn_13",
                            "isbn_10",
                        ],
                    },
                },
                exact=["title"],
                qualifiers={"author": {"properties": ["authors"]}},
                metadata={
                    "date_histogram": dict(
                        sorted(
                            Counter(
                                record["published"][:4]
                                for record in books
                                if record["published"]
                            ).items()
                        )
                    )
                },
            ),
        ),
        (
            config.data / "blogs" / "posts",
            output / "blog-posts",
            lambda: _update_search_collection(
                output / "blog-posts",
                _blog_records(config),
                fields=_feed_search_fields("source"),
                exact=["title"],
                qualifiers={"author": {"properties": ["author"]}},
            ),
        ),
        (
            config.data / "youtube" / "videos",
            output / "youtube-videos",
            lambda: _update_search_collection(
                output / "youtube-videos",
                _youtube_records(config),
                fields=_feed_search_fields("channel"),
                exact=["title"],
                qualifiers={"author": {"properties": ["channel"]}},
            ),
        ),
    )
    for source, directory, update in jobs:
        try:
            result.extend(_tracked_update(source, directory, update))
        except Exception as error:  # noqa: BLE001 - isolate independent catalogs
            successful = False
            print(
                f"error: browser catalog build failed ({source}): {error}",
                file=sys.stderr,
            )

    try:
        summaries, details, managers = _package_data(config)
        graph = {
            "nodes": [
                {
                    "id": item["id"],
                    "label": item.get("title", item["id"]),
                    "managers": item["managers"],
                    "dependencies": item.get("dependencies", []),
                }
                for item in summaries
            ]
        }
        search_summaries = [
            {key: value for key, value in item.items() if key != "dependencies"}
            for item in summaries
        ]
        manager_counts = Counter(
            manager for item in summaries for manager in set(item["managers"])
        )
        package_jobs: list[tuple[Path, Path, Callable[[], bool]]] = [
            (
                config.data / "packages",
                output / "packages",
                lambda: _update_search_collection(
                    output / "packages",
                    search_summaries,
                    fields={
                        "title": {
                            "properties": ["id", "title", "aliases"],
                            "boost": 12,
                        },
                        "content": {
                            "properties": ["content", "topics"],
                        },
                        "tags": {
                            "properties": ["topics"],
                            "boost": 4,
                        },
                    },
                    exact=["id", "title"],
                    qualifiers={
                        "manager": {
                            "properties": ["managers"],
                            "match": "exact",
                        },
                        "name": {"properties": ["id", "title", "aliases"]},
                    },
                    metadata={
                        "manager_counts": dict(sorted(manager_counts.items())),
                        "preview": sorted(
                            search_summaries, key=lambda item: item["id"]
                        )[:30],
                    },
                ),
            )
        ]
        graph_path = output / "package-graph.json"
        if _write_json(graph_path, graph):
            result.generated.append(PluginFile(config.data / "packages", graph_path))
        details_by_manager = {manager: [] for manager in managers}
        for detail in details:
            details_by_manager[detail["id"].split(":", 1)[0]].append(detail)
        for manager, values in details_by_manager.items():
            directory = output / "package-details" / manager
            package_jobs.append(
                (
                    config.data / "packages" / f"{manager}.yaml",
                    directory,
                    lambda directory=directory, values=values, manager=manager: (
                        update_keyed_collection(
                            directory,
                            values,
                            collection=f"package-details-{manager}",
                            bucket_count=256,
                        )
                    ),
                )
            )
        # Brotli's maximum-quality compressor dominates a clean build and
        # releases the GIL. Each collection writes to a distinct directory, so
        # generate them concurrently while retaining deterministic contents.
        with ThreadPoolExecutor(max_workers=len(package_jobs)) as executor:
            updates = executor.map(lambda job: _tracked_update(*job), package_jobs)
            for update_result in updates:
                result.extend(update_result)
    except Exception as error:  # noqa: BLE001 - report plugin errors without aborting site
        successful = False
        print(f"error: package browser catalog build failed: {error}", file=sys.stderr)
    return result, successful


def build(config: SiteConfig) -> PluginResult:
    output = config.output / "data"
    manifest = config.root / ".cache" / HASH_MANIFEST
    removed = []
    legacy_manifest = output / LEGACY_HASH_MANIFEST
    if legacy_manifest.is_file():
        legacy_manifest.unlink()
        removed.append(legacy_manifest)
    inputs = _file_hashes(config, _input_files(config))
    if _cache_matches(manifest, inputs, output):
        print("Browser data is up to date; skipping generation.", flush=True)
        return PluginResult(removed=removed)

    result, successful = _build_data(config)
    result.removed.extend(removed)
    current_inputs = _file_hashes(config, _input_files(config))
    if successful and current_inputs == inputs:
        _write_hash_manifest(manifest, inputs, _output_hashes(output))
    return result
