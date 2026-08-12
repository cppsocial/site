import argparse
import time
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

import yaml
from schemas.blocks import CachedVideo, ChannelMetadata

from ..config import MetaUpdaterConfig
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
from ..youtube import channel_metadata, channel_videos, normalize_video

DESCRIPTION = "Refresh YouTube channel metadata, feeds, and browser search data."
GROUP_FILES = ("channels.yaml", "organizations.yaml", "conferences.yaml")


def configure(parser: argparse.ArgumentParser) -> None:
    add_network_options(parser)
    actions = parser.add_subparsers(dest="command", required=True)
    for action in ("metadata", "videos", "all", "clean", "compact"):
        add_network_options(actions.add_parser(action), suppress_defaults=True)
    prune = actions.add_parser("prune")
    add_network_options(prune, suppress_defaults=True)
    prune.add_argument("--keep-per-channel", type=int)
    prune.add_argument("--before", type=date.fromisoformat)
    parser.set_defaults(handler=run)


def channels(content: Path) -> list[dict[str, str]]:
    result = []
    for name in GROUP_FILES:
        with (content / name).open(encoding="utf-8") as file:
            result.extend(
                item
                for item in yaml.safe_load(file)["cards"]
                if not item.get("hidden", False)
            )
    ids = [item["channel_id"] for item in result]
    if len(ids) != len(set(ids)):
        raise ValueError("duplicate channel_id in curated YouTube files")
    return result


def merged(
    current: list[Any], updates: list[Any], relevance_path: Path
) -> list[dict[str, Any]]:
    records = merge_records(
        current, updates, id_field="video_id", normalize=normalize_video
    )
    records = apply_relevance_labels(
        records,
        load_relevance_labels(relevance_path, "youtube_videos"),
        id_field="video_id",
    )
    return sorted(records, key=lambda item: item["published"], reverse=True)


def corrected(
    cache: dict[str, list[Any]], overrides_path: Path
) -> dict[str, list[dict[str, Any]]]:
    locations = {}
    records = []
    for channel_id, values in cache.items():
        for value in values:
            item = normalize_video(value)
            locations[item["video_id"]] = channel_id
            records.append(item)
    records = apply_metadata_overrides(
        records,
        overrides_path,
        "youtube_videos",
        id_field="video_id",
        allowed_fields={
            "title",
            "published",
            "updated",
            "description",
            "thumbnail_url",
            "tags",
        },
    )
    result = {channel_id: [] for channel_id in cache}
    for item in records:
        result[locations[item["video_id"]]].append(item)
    for values in result.values():
        values.sort(key=lambda item: item["published"], reverse=True)
    return result


def update_browser_data(
    cache: dict[str, list[Any]],
    curated: list[dict[str, str]],
    output: Path,
    check: bool,
    compact: bool = False,
) -> bool:
    titles = {channel["channel_id"]: channel["title"] for channel in curated}
    records = []
    for channel_id, videos in cache.items():
        channel = titles[channel_id]
        for value in videos:
            video = normalize_video(value)
            published = video["published"].isoformat()
            record = {
                "id": video["video_id"],
                "title": video["title"],
                "channel": channel,
                "url": video["url"],
                "published": published,
                "thumbnail_url": video["thumbnail_url"],
                "description": video["description"],
            }
            if video["tags"]:
                record["tags"] = video["tags"]
            if video.get("cpp_relevance") is not None:
                record["cpp_relevance"] = video["cpp_relevance"]
            if not video.get("hidden", False):
                records.append(record)
    records.sort(key=lambda item: item["published"], reverse=True)
    return update_browser_collection(
        output,
        records,
        collection="youtube-videos",
        fields={
            "title": {"label": "Title", "property": "title"},
            "content": {"label": "Description", "property": "description"},
            "source": {"label": "Channel", "property": "channel"},
            "tags": {"label": "Tag", "property": "tags"},
        },
        check=check,
        compact=compact,
    )


def refresh(
    args: argparse.Namespace,
    curated: list[dict[str, str]],
    metadata_data: YamlDataset,
    video_data: YamlDataset,
    relevance_path: Path,
    overrides_path: Path,
    web_output: Path,
    timeout: float,
    delay: float,
) -> bool:
    changed = False
    if args.command in {"metadata", "all"}:
        # Keep metadata for channels that are temporarily unavailable.
        metadata = metadata_data.load({})
        for index, channel in enumerate(curated):
            if index:
                time.sleep(delay)
            metadata[channel["channel_id"]] = channel_metadata(
                channel["channel_id"], timeout
            )
            print(f"metadata {channel['title']}")
        changed = metadata_data.update(metadata, args.check)
    if args.command in {"videos", "all"}:
        # A failed/empty feed must never replace the historical cache.
        cache = video_data.load({})
        for index, channel in enumerate(curated):
            if index:
                time.sleep(delay)
            channel_id = channel["channel_id"]
            updates = channel_videos(channel_id, timeout)
            cache[channel_id] = merged(
                cache.get(channel_id, []), updates, relevance_path
            )
            print(f"videos {channel['title']}: {len(updates)}")
        cache = corrected(cache, overrides_path)
        changed = video_data.update(cache, args.check) or changed
        known = {channel["channel_id"] for channel in curated}
        browser_cache = {
            channel_id: items
            for channel_id, items in cache.items()
            if channel_id in known
        }
        changed = update_browser_data(
            browser_cache,
            curated,
            web_output,
            args.check,
        ) or changed
    return changed


def maintain(
    args: argparse.Namespace,
    curated: list[dict[str, str]],
    video_data: YamlDataset,
    relevance_path: Path,
    overrides_path: Path,
    web_output: Path,
) -> bool:
    # Keep historical channels in the YAML cache; only prune removes entries.
    cache = corrected(
        {
            channel_id: merged(items, [], relevance_path)
            for channel_id, items in video_data.load({}).items()
        },
        overrides_path,
    )
    if args.command == "prune":
        if args.keep_per_channel is None and args.before is None:
            raise ValueError("prune requires --keep-per-channel and/or --before")
        if args.keep_per_channel is not None and args.keep_per_channel < 0:
            raise ValueError("--keep-per-channel must be non-negative")
        cutoff = (
            datetime.combine(args.before, datetime.min.time(), UTC)
            if args.before
            else None
        )
        cache = {
            channel_id: [
                item for item in items if cutoff is None or item["published"] >= cutoff
            ][: args.keep_per_channel]
            if args.keep_per_channel is not None
            else [
                item for item in items if cutoff is None or item["published"] >= cutoff
            ]
            for channel_id, items in cache.items()
        }
    changed = video_data.update(cache, args.check)
    known = {channel["channel_id"] for channel in curated}
    browser_cache = {
        channel_id: items
        for channel_id, items in cache.items()
        if channel_id in known
    }
    return (
        update_browser_data(
            browser_cache,
            curated,
            web_output,
            args.check,
            compact=args.command == "compact",
        )
        or changed
    )


def run(args: argparse.Namespace, config: MetaUpdaterConfig) -> int:
    timeout, delay = network_values(args, config)
    output = config.data / "youtube"
    metadata_data = YamlDataset(
        output / "channel-metadata.yaml",
        dict[str, ChannelMetadata],
        "meta-updater youtube metadata",
        "Descriptions and keywords come from public YouTube channel metadata.",
    )
    video_data = YamlDataset(
        output / "video-cache.yaml",
        dict[str, list[CachedVideo]],
        "meta-updater youtube videos",
        "Entries are retained across updates for future cross-channel search.",
        exclude_none=True,
        exclude_defaults=True,
    )
    start_provenance_tracking(config.data / "youtube" / "provenance.yaml")

    curated = channels(config.content / "youtube")
    common = (
        config.content / "relevance-labels.yaml",
        config.content / "metadata-overrides.yaml",
        config.browser_data / "youtube-videos",
    )
    changed = (
        maintain(args, curated, video_data, *common)
        if args.command in {"clean", "compact", "prune"}
        else refresh(args, curated, metadata_data, video_data, *common, timeout, delay)
    )

    if changed:
        finish_provenance_tracking()

    return finish(changed, args.check, "YouTube")
