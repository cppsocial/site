import argparse
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

import yaml
from schemas.blocks import CachedVideo, ChannelMetadata

from ..config import MetaUpdaterConfig
from ..shared.dataset import YamlDataset
from ..shared.provenance import finish_provenance_tracking, start_provenance_tracking
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
from ..youtube import channel_metadata, channel_videos, normalize_video

DESCRIPTION = "Refresh YouTube metadata and per-channel recent-video caches."
GROUP_FILES = ("channels.yaml", "organizations.yaml", "conferences.yaml")


def configure(parser: argparse.ArgumentParser) -> None:
    add_network_options(parser)
    add_id_option(parser)
    actions = parser.add_subparsers(dest="command", required=True)
    for action in ("metadata", "videos", "all", "clean", "compact"):
        add_network_action(actions, action)
    prune = add_network_action(actions, "prune")
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


def merged(current: list[Any], updates: list[Any]) -> list[dict[str, Any]]:
    records = merge_records(
        current,
        updates,
        id_field="video_id",
        normalize=normalize_video,
        preserve_existing=True,
    )
    return sorted(
        records,
        key=lambda item: item.get("published") or datetime.min.replace(tzinfo=UTC),
        reverse=True,
    )


def corrected(cache: dict[str, list[Any]]) -> dict[str, list[dict[str, Any]]]:
    locations = {}
    records = []
    for channel_id, values in cache.items():
        for value in values:
            raw = value.model_dump() if hasattr(value, "model_dump") else dict(value)
            item = raw if raw.get("hidden") is True else normalize_video(value)
            locations[item["video_id"]] = channel_id
            records.append(item)
    result = {channel_id: [] for channel_id in cache}
    for item in records:
        result[locations[item["video_id"]]].append(item)
    for values in result.values():
        values.sort(
            key=lambda item: item.get("published") or datetime.min.replace(tzinfo=UTC),
            reverse=True,
        )
    return result


def refresh(
    args: argparse.Namespace,
    curated: list[dict[str, str]],
    metadata_data: YamlDataset,
    video_data: RecentCache,
    timeout: float,
    delay: float,
) -> bool:
    changed = False
    if args.command in {"metadata", "all"}:
        # Keep metadata for channels that are temporarily unavailable.
        try:
            metadata = metadata_data.load({})
        except Exception as error:
            log_operation_error(
                "YouTube metadata cache load", error, path=metadata_data.path
            )
            metadata = None
        for channel in delayed(curated if metadata is not None else [], delay):
            try:
                value = channel_metadata(channel["channel_id"], timeout)
            except Exception as error:
                log_operation_error(
                    "YouTube metadata",
                    error,
                    channel_id=channel["channel_id"],
                    channel_title=channel["title"],
                )
                continue
            metadata[channel["channel_id"]] = value
            print(f"metadata {channel['title']}")
        if metadata is not None:
            changed = metadata_data.update(metadata, args.check)
    if args.command in {"videos", "all"}:
        # A failed/empty feed must never replace the historical cache.
        for channel in delayed(curated, delay):
            channel_id = channel["channel_id"]
            try:
                updates = channel_videos(channel_id, timeout)
            except Exception as error:
                log_operation_error(
                    "YouTube videos",
                    error,
                    channel_id=channel_id,
                    channel_title=channel["title"],
                )
                continue
            cache = video_data.load(channel_id)
            if cache is None:
                continue
            values = corrected({channel_id: merged(cache, updates)})[channel_id]
            changed = video_data.update(channel_id, values, args.check) or changed
            print(f"videos {channel['title']}: {len(updates)}")
    return changed


def maintain(
    args: argparse.Namespace,
    curated: list[dict[str, str]],
    video_data: RecentCache,
) -> bool:
    # Keep historical channels in the YAML cache; only prune removes entries.
    cache = corrected(
        {
            channel_id: merged(items, [])
            for channel_id, items in video_data.load_all().items()
        }
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
            channel_id: prune_records(items, cutoff=cutoff, limit=args.keep_per_channel)
            for channel_id, items in cache.items()
        }
    changed = False
    for channel_id, values in cache.items():
        changed = video_data.update(channel_id, values, args.check) or changed
    return changed


def run(args: argparse.Namespace, config: MetaUpdaterConfig) -> int:
    timeout, delay = network_values(args, config)
    output = config.data / "youtube"
    metadata_data = YamlDataset(
        output / "channel-metadata.yaml",
        dict[str, ChannelMetadata],
        "meta-updater youtube metadata",
        "Descriptions and keywords come from public YouTube channel metadata.",
    )
    video_data = RecentCache(
        output / "videos",
        CachedVideo,
        id_field="video_id",
        producer="meta-updater youtube",
    )
    start_provenance_tracking(config.data / "youtube" / "provenance.yaml")

    curated = channels(config.content / "youtube")
    curated = selected(
        curated, args.ids, lambda item: item["channel_id"], "YouTube channel ID"
    )
    changed = (
        maintain(args, curated, video_data)
        if args.command in {"clean", "compact", "prune"}
        else refresh(args, curated, metadata_data, video_data, timeout, delay)
    )

    if changed:
        finish_provenance_tracking()

    return finish(changed, args.check, "YouTube")
