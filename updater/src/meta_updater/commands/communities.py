import argparse
from pathlib import Path

import yaml
from schemas.blocks import CommunityMetadata

from ..config import MetaUpdaterConfig
from ..shared.communities import metadata
from ..shared.dataset import YamlDataset
from ..shared.provenance import (
    cancel_provenance_tracking,
    finish_provenance_tracking,
    provenance_transaction,
    retain_provenance_urls,
    start_provenance_tracking,
)
from ..shared.runtime import (
    add_id_option,
    add_network_options,
    delayed,
    finish,
    log_operation_error,
    network_values,
    selected,
)

DESCRIPTION = "Refresh community platform metadata."


def configure(parser: argparse.ArgumentParser) -> None:
    add_network_options(parser)
    add_id_option(parser)
    parser.set_defaults(handler=run)


def communities(content: Path) -> list[dict[str, object]]:
    result = []
    for path in sorted(content.glob("*.yaml")):
        if path.name.startswith("_"):
            continue
        with path.open(encoding="utf-8") as file:
            group = yaml.safe_load(file)
        if isinstance(group, dict) and "cards" in group:
            result.extend(group["cards"])
    ids = [item["community_id"] for item in result]
    if len(ids) != len(set(ids)):
        raise ValueError("duplicate community_id")
    return result


def run(args: argparse.Namespace, config: MetaUpdaterConfig) -> int:
    timeout, delay = network_values(args, config)
    metadata_: YamlDataset = YamlDataset(
        config.data / "communities" / "metadata.yaml",
        dict[str, CommunityMetadata],
        "meta-updater communities",
        "Descriptions, artwork, and activity figures come from the linked platforms.",
    )
    start_provenance_tracking(config.data / "communities" / "provenance.yaml")
    curated = communities(config.content / "communities")
    curated = selected(
        curated, args.ids, lambda item: item["community_id"], "community ID"
    )
    # Keep the last good value when a platform temporarily blocks or throttles us.
    metadata_result = metadata_.load({})
    curated_ids = {community["community_id"] for community in curated}
    if not args.ids:
        metadata_result = {
            community_id: value
            for community_id, value in metadata_result.items()
            if community_id in curated_ids
        }
    for community in delayed(curated, delay):
        source = community["metadata_source"]
        try:
            with provenance_transaction():
                value = metadata(source["source"], source["key"], timeout)
        except Exception as error:
            log_operation_error(
                "community metadata",
                error,
                community_id=community["community_id"],
                source=source["source"],
            )
            continue
        metadata_result[community["community_id"]] = value
        print(f"metadata {community['title']}")

    changed = metadata_.update(metadata_result, args.check)
    source_urls = {
        value.source_url if hasattr(
            value, "source_url") else value.get("source_url", "")
        for value in metadata_result.values()
    }
    retain_provenance_urls({url for url in source_urls if url})
    if args.check:
        cancel_provenance_tracking()
    else:
        finish_provenance_tracking()

    return finish(changed, args.check, "community")
