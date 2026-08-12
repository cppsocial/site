import argparse
import time
from datetime import UTC, date, datetime
from pathlib import Path

import yaml
from schemas.blogs import BlogMetadata, BlogSource, CachedBlogPost

from ..config import MetaUpdaterConfig
from ..shared.blogs import metadata, normalize_post, posts, render_description
from ..shared.browser_data import update_browser_collection
from ..shared.dataset import YamlDataset
from ..shared.overrides import apply_metadata_overrides
from ..shared.provenance import finish_provenance_tracking, start_provenance_tracking
from ..shared.relevance import (
    apply_relevance_labels,
    load_relevance_labels,
    merge_records,
)
from ..shared.runtime import add_network_options, finish, network_values

DESCRIPTION = "Refresh blog metadata, feeds, and browser search data."


def configure(parser: argparse.ArgumentParser) -> None:
    add_network_options(parser)
    actions = parser.add_subparsers(dest="command", required=True)
    for action in ("metadata", "posts", "all", "clean", "compact"):
        add_network_options(actions.add_parser(action), suppress_defaults=True)
    prune = actions.add_parser("prune")
    add_network_options(prune, suppress_defaults=True)
    prune.add_argument("--keep-total", type=int)
    prune.add_argument("--before", type=date.fromisoformat)
    parser.set_defaults(handler=run)


def sources(source_path: Path) -> list[dict]:
    with source_path.open(encoding="utf-8") as file:
        records = yaml.safe_load(file)
    records = [BlogSource.model_validate(item).model_dump() for item in records]
    ids = [item["id"] for item in records]
    if len(ids) != len(set(ids)):
        raise ValueError("duplicate blog source id")
    return records


def mark_excluded_posts(records: list, curated: list[dict]) -> list[dict]:
    """Hide, but retain, posts carrying a source-specific excluded tag."""
    excluded_by_source = {
        source["id"]: {tag.strip().casefold() for tag in source["exclude_tags"]}
        for source in curated
        if source["exclude_tags"]
    }
    result = []
    for value in records:
        item = value.model_dump() if hasattr(value, "model_dump") else dict(value)
        excluded = excluded_by_source.get(item["source_id"], set())
        if not excluded.isdisjoint(tag.strip().casefold() for tag in item["tags"]):
            item["hidden"] = True
        result.append(item)
    return result


def merged(
    current: list, updates: list[dict], relevance_path: Path, overrides_path: Path
) -> list[dict]:
    records = merge_records(
        current, updates, id_field="post_id", normalize=normalize_post
    )
    records = apply_relevance_labels(
        records,
        load_relevance_labels(relevance_path, "blog_posts"),
        id_field="post_id",
    )
    records = apply_metadata_overrides(
        records,
        overrides_path,
        "blog_posts",
        id_field="post_id",
        allowed_fields={
            "title",
            "source_title",
            "published",
            "updated",
            "description",
            "tags",
        },
    )
    return sorted(records, key=lambda item: item["published"], reverse=True)


def update_browser_data(
    cache: list[dict], output: Path, check: bool, compact: bool = False
) -> bool:
    records = []
    for value in cache:
        post = normalize_post(value)
        published = post["published"].isoformat()
        record = {
            "id": post["post_id"],
            "title": post["title"],
            "source": post["source_title"],
            "url": post["url"],
            "published": published,
            "description": render_description(post["description"]),
        }
        if post["tags"]:
            record["tags"] = post["tags"]
        if post.get("cpp_relevance") is not None:
            record["cpp_relevance"] = post["cpp_relevance"]
        if not post.get("hidden", False):
            records.append(record)
    return update_browser_collection(
        output,
        records,
        collection="blog-posts",
        fields={
            "title": {"label": "Title", "property": "title"},
            "content": {"label": "Content", "property": "description"},
            "source": {"label": "Blog", "property": "source"},
            "tags": {"label": "Tag", "property": "tags"},
        },
        check=check,
        compact=compact,
    )


def refresh(
    args: argparse.Namespace,
    curated: list[dict],
    metadata_data: YamlDataset,
    post_data: YamlDataset,
    relevance_path: Path,
    overrides_path: Path,
    web_output: Path,
    timeout: float,
    delay: float,
) -> bool:
    visible = [item for item in curated if not item["hidden"]]
    changed = False
    if args.command in {"metadata", "all"}:
        # Refresh individual records without dropping metadata for channels
        # that are temporarily hidden or no longer fetched.
        values = metadata_data.load({})
        for index, source in enumerate(visible):
            if index:
                time.sleep(delay)
            values[source["id"]] = metadata(source, timeout)
            print(f"metadata {source['title']}")
        changed = metadata_data.update(values, args.check)
    if args.command in {"posts", "all"}:
        # The cache is append-only during refresh. Explicit prune/clean
        # operations are responsible for intentional removal.
        cache = post_data.load([])
        updates = []
        for index, source in enumerate(visible):
            if index:
                time.sleep(delay)
            fetched = posts(source, timeout)
            updates.extend(fetched)
            print(f"posts {source['title']}: {len(fetched)}")
        cache = merged(cache, updates, relevance_path, overrides_path)
        cache = mark_excluded_posts(cache, curated)
        changed = post_data.update(cache, args.check) or changed
        changed = update_browser_data(cache, web_output, args.check) or changed
    return changed


def maintain(
    args: argparse.Namespace,
    curated: list[dict],
    post_data: YamlDataset,
    relevance_path: Path,
    overrides_path: Path,
    web_output: Path,
) -> bool:
    # Maintenance must also retain historical records; only prune removes
    # entries from the cache.
    cache = merged(
        post_data.load([]),
        [],
        relevance_path,
        overrides_path,
    )
    cache = mark_excluded_posts(cache, curated)
    if args.command == "prune":
        if args.keep_total is None and args.before is None:
            raise ValueError("prune requires --keep-total and/or --before")
        if args.keep_total is not None and args.keep_total < 0:
            raise ValueError("--keep-total must be non-negative")
        cutoff = (
            datetime.combine(args.before, datetime.min.time(), UTC)
            if args.before
            else None
        )
        if cutoff:
            cache = [item for item in cache if item["published"] >= cutoff]
        if args.keep_total is not None:
            cache = cache[: args.keep_total]
    changed = post_data.update(cache, args.check)
    return (
        update_browser_data(
            cache, web_output, args.check, compact=args.command == "compact"
        )
        or changed
    )


def run(args: argparse.Namespace, config: MetaUpdaterConfig) -> int:
    timeout, delay = network_values(args, config)
    output = config.data / "blogs"
    metadata_data = YamlDataset(
        output / "metadata.yaml",
        dict[str, BlogMetadata],
        "meta-updater blogs metadata",
        (
            "Descriptions, keywords, and avatars come from each blog's public "
            "metadata and visible page."
        ),
        exclude_defaults=True,
    )
    post_data = YamlDataset(
        output / "post-cache.yaml",
        list[CachedBlogPost],
        "meta-updater blogs posts",
        "Posts are retained across updates for future cross-blog search.",
        exclude_none=True,
        exclude_defaults=True,
    )
    start_provenance_tracking(config.data / "blogs" / "provenance.yaml")
    curated = sources(config.content / "blogs" / "sources.yaml")
    common = (
        config.content / "relevance-labels.yaml",
        config.content / "metadata-overrides.yaml",
        config.browser_data / "blog-posts",
    )
    changed = (
        maintain(args, curated, post_data, *common)
        if args.command in {"clean", "compact", "prune"}
        else refresh(args, curated, metadata_data, post_data, *common, timeout, delay)
    )

    if changed:
        finish_provenance_tracking()
    return finish(changed, args.check, "blog")
