import argparse
import time
from datetime import UTC, date, datetime
from pathlib import Path

import yaml
from schemas.blogs import BlogMetadata, BlogSource, CachedBlogPost

from ..config import MetaUpdaterConfig
from ..shared.blogs import (
    HEADERS,
    feed_posts_and_cms,
    matches_post_url_family,
    metadata,
    normalize_post,
    page_links,
    post_listing_kind,
    post_url_family,
    posts,
    sitemap_discovery,
    sitemap_post,
)
from ..shared.dataset import YamlDataset
from ..shared.feeds import fetch
from ..shared.provenance import (
    cancel_provenance_tracking,
    finish_provenance_tracking,
    retain_provenance_urls,
    start_provenance_tracking,
    suppress_provenance,
    track_provenance,
)
from ..shared.recent import RecentCache, merge_records, prune_records
from ..shared.runtime import (
    add_id_option,
    add_network_action,
    add_network_options,
    delayed,
    finish,
    log_operation_error,
    network_values,
    selected,
)

DESCRIPTION = "Refresh blog metadata and per-source recent-post caches."


def configure(parser: argparse.ArgumentParser) -> None:
    add_network_options(parser)
    add_id_option(parser)
    actions = parser.add_subparsers(dest="command", required=True)
    for action in ("metadata", "posts", "all", "clean", "compact", "ingest"):
        add_network_action(actions, action)
    prune = add_network_action(actions, "prune")
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
        if item.get("hidden") is True and (
            "source_id" not in item or "tags" not in item
        ):
            result.append(item)
            continue
        excluded = excluded_by_source.get(item["source_id"], set())
        if not excluded.isdisjoint(
            tag.strip().casefold() for tag in item.get("tags", [])
        ):
            item["hidden"] = True
        result.append(item)
    return result


def merged(
    current: list,
    updates: list[dict],
) -> list[dict]:
    records = merge_records(
        current,
        updates,
        id_field="post_id",
        normalize=normalize_post,
        preserve_existing=True,
    )
    return sorted(
        records,
        key=lambda item: item.get("published") or datetime.min.replace(tzinfo=UTC),
        reverse=True,
    )


def refresh(
    args: argparse.Namespace,
    curated: list[dict],
    metadata_data: YamlDataset,
    post_data: RecentCache,
    timeout: float,
    delay: float,
) -> bool:
    visible = [item for item in curated if not item["hidden"]]
    changed = False
    if args.command in {"metadata", "all"}:
        # Refresh individual records without dropping metadata for channels
        # that are temporarily hidden or no longer fetched.
        try:
            values = metadata_data.load({})
        except Exception as error:
            log_operation_error(
                "blog metadata cache load", error, path=metadata_data.path
            )
            values = None
        for source in delayed(visible if values is not None else [], delay):
            try:
                value = metadata(source, timeout)
            except Exception as error:
                log_operation_error(
                    "blog metadata",
                    error,
                    source_id=source["id"],
                    source_title=source["title"],
                    url=source["website_url"],
                )
                continue
            values[source["id"]] = value
            print(f"metadata {source['title']}")
        if values is not None:
            changed = metadata_data.update(values, args.check)
    if args.command in {"posts", "all"}:
        # The cache is append-only during refresh. Explicit prune/clean
        # operations are responsible for intentional removal.
        for source in delayed(visible, delay):
            try:
                fetched = posts(source, timeout)
            except Exception as error:
                log_operation_error(
                    "blog posts",
                    error,
                    source_id=source["id"],
                    source_title=source["title"],
                    url=source["rss_url"],
                )
                continue
            cache = post_data.load(source["id"])
            if cache is None:
                continue
            cache = merged(cache, fetched)
            cache = mark_excluded_posts(cache, curated)
            changed = post_data.update(source["id"], cache, args.check) or changed
            print(f"posts {source['title']}: {len(fetched)}")
    return changed


def ingest(
    args: argparse.Namespace,
    source: dict,
    curated: list[dict],
    post_data: RecentCache,
    timeout: float,
    delay: float,
) -> bool:
    """Manually backfill one blog from its feed and article-like site pages."""
    cache = post_data.load(source["id"])
    if cache is None:
        return False

    cms = ""
    try:
        fetched, cms = feed_posts_and_cms(source, timeout)
    except Exception as error:
        log_operation_error(
            "blog ingest feed",
            error,
            source_id=source["id"],
            url=source["rss_url"],
        )
        fetched = []
    try:
        entries, listings = sitemap_discovery(source, timeout, cms=cms)
    except Exception as error:
        if not fetched:
            raise
        log_operation_error(
            "blog ingest discovery",
            error,
            source_id=source["id"],
            url=source.get("sitemap_url") or source["website_url"],
        )
        entries = []
        listings = []

    linked_urls: set[str] = set()
    reliable_listing = False
    page_fetches = 0

    def fetch_page(url: str) -> bytes:
        nonlocal page_fetches
        if page_fetches:
            time.sleep(delay)
        page_fetches += 1
        # Discovery and candidate fetches are not provenance until their content
        # actually produces a post record below.
        with suppress_provenance():
            return fetch(url, timeout, HEADERS)

    for listing_url in listings:
        try:
            document = fetch_page(listing_url)
            linked_urls.update(page_links(source, listing_url, document))
            reliable_listing = (
                reliable_listing or post_listing_kind(source, listing_url) != "home"
            )
        except Exception as error:
            log_operation_error(
                "blog post listing",
                error,
                source_id=source["id"],
                url=listing_url,
            )

    linked_identities = {url.rstrip("/") for url in linked_urls}
    correlated = [
        entry for entry in entries if entry["loc"].rstrip("/") in linked_identities
    ]
    if reliable_listing and correlated:
        entries = correlated
        family = post_url_family(
            source, [item["url"] for item in fetched if item.get("url")]
        )
        family_matches = (
            [
                entry
                for entry in entries
                if matches_post_url_family(source, entry["loc"], family)
            ]
            if family
            else []
        )
        if family_matches:
            entries = family_matches

    known_urls = {
        item.get("url", "").rstrip("/")
        for item in [*cache, *fetched]
        if item.get("url")
    }
    candidates = [
        entry for entry in entries if entry["loc"].rstrip("/") not in known_urls
    ]
    for entry in candidates:
        print(entry)
        try:
            document = fetch_page(entry["loc"])
            post = sitemap_post(source, entry, document)
        except Exception as error:
            log_operation_error(
                "blog sitemap page",
                error,
                source_id=source["id"],
                url=entry["loc"],
            )
            continue
        if post is not None:
            fetched.append(post)
            track_provenance(entry["loc"])

    if not fetched:
        raise ValueError(f"sitemap returned no usable posts for {source['id']}")
    cache = mark_excluded_posts(merged(cache, fetched), curated)
    changed = post_data.update(source["id"], cache, args.check)
    print(
        f"ingested {source['title']}: {len(fetched)} posts "
        f"from the feed and {len(candidates)} sitemap URLs"
    )
    return changed


def maintain(
    args: argparse.Namespace,
    curated: list[dict],
    post_data: RecentCache,
) -> bool:
    # Maintenance must also retain historical records; only prune removes
    # entries from the cache.
    caches = post_data.load_all()
    cache = [item for values in caches.values() for item in values]
    cache = merged(cache, [])
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
        cache = prune_records(cache, cutoff=cutoff, limit=args.keep_total)
    grouped: dict[str, list[dict]] = {source_id: [] for source_id in caches}
    for item in cache:
        source_id = item.get("source_id")
        if source_id is None and item.get("hidden") is True:
            source_id = next(
                (
                    candidate
                    for candidate, values in caches.items()
                    if any(value.get("post_id") == item["post_id"] for value in values)
                ),
                None,
            )
        if source_id is not None:
            grouped.setdefault(source_id, []).append(item)
    changed = False
    for source_id, values in grouped.items():
        changed = post_data.update(source_id, values, args.check) or changed
    return changed


def run(args: argparse.Namespace, config: MetaUpdaterConfig) -> int:
    timeout, delay = network_values(args, config)
    if args.command == "ingest" and len(args.ids or []) != 1:
        raise ValueError("blogs ingest requires exactly one --id")
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
    post_data = RecentCache(
        output / "posts",
        CachedBlogPost,
        id_field="post_id",
        producer="meta-updater blogs",
    )
    maintenance = args.command in {"clean", "compact", "prune"}
    start_provenance_tracking(
        config.data / "blogs" / "provenance.yaml",
        retain_existing=bool(args.ids) or maintenance,
    )
    curated = sources(config.content / "blogs" / "sources.yaml")
    all_curated = curated
    curated = selected(curated, args.ids, lambda item: item["id"], "blog source ID")
    if args.command == "ingest":
        changed = ingest(args, curated[0], all_curated, post_data, timeout, delay)
    elif args.command in {"clean", "compact", "prune"}:
        changed = maintain(args, curated, post_data)
    else:
        changed = refresh(args, curated, metadata_data, post_data, timeout, delay)

    # Reconcile retained provenance against actual page inputs. This also cleans
    # discovery URLs recorded by older updater versions during targeted ingest.
    source_urls = {
        source[field]
        for source in all_curated
        for field in ("website_url", "rss_url")
        if source.get(field)
    }
    cached_urls = {
        item.get("url", "")
        for records in post_data.load_all().values()
        for item in records
        if item.get("url")
    }
    retain_provenance_urls(source_urls | cached_urls)
    if args.check:
        cancel_provenance_tracking()
    else:
        finish_provenance_tracking()
    return finish(changed, args.check, "blog")
