import argparse
from datetime import UTC, datetime
from pathlib import Path

import yaml
from schemas.blocks import CommunityMetadata

from ..config import MetaUpdaterConfig
from ..shared.communities import metadata
from ..shared.dataset import YamlDataset
from ..shared.provenance import finish_provenance_tracking, start_provenance_tracking, track_provenance
from ..shared.runtime import add_network_options, delayed, finish, network_values

DESCRIPTION = "Refresh community platform metadata."
GROUPS = ("im.yaml", "forums.yaml")


def configure(parser: argparse.ArgumentParser) -> None:
    add_network_options(parser)
    parser.set_defaults(handler=run)


def communities(content: Path) -> list[dict[str, object]]:
    result = []
    for name in GROUPS:
        with (content / name).open(encoding="utf-8") as file:
            result.extend(yaml.safe_load(file)["cards"])
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
    metadata_result = {}
    for community in delayed(communities(config.content / "communities"), delay):
        source = community["metadata"]
        metadata_result[community["community_id"]] = metadata(source["source"], source["key"], timeout)
        print(f"metadata {community['title']}")

    changed = metadata_.update(metadata_result, args.check)
    if changed:
        finish_provenance_tracking()

    return finish(changed, args.check, "community")
