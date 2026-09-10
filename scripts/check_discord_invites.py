"""Validate changed Discord community records against Discord's public API."""

import argparse
import json
import subprocess
import sys
import urllib.request
from collections.abc import Callable
from pathlib import Path
from typing import Any

import yaml

DISCORD_API = "https://discord.com/api/v10/invites"
HEADERS = {
    "User-Agent": "cpp.social content checks (+https://cpp.social/contributing/)"
}


def _cards(document: Any) -> dict[str, dict[str, Any]]:
    if not isinstance(document, dict) or not isinstance(document.get("cards"), list):
        return {}
    return {
        card["community_id"]: card
        for card in document["cards"]
        if isinstance(card, dict) and "community_id" in card
    }


def changed_discord_cards(base: str, path: Path) -> list[dict[str, Any]]:
    current = _cards(yaml.safe_load(path.read_text(encoding="utf-8")))
    try:
        previous_text = subprocess.check_output(
            ["git", "show", f"{base}:{path.as_posix()}"],
            stderr=subprocess.DEVNULL,
        )
        previous = _cards(yaml.safe_load(previous_text))
    except subprocess.CalledProcessError:
        previous = {}
    return [
        card
        for community_id, card in current.items()
        if card != previous.get(community_id)
        and card.get("metadata_source", {}).get("source") == "discord"
    ]


def fetch_invite(code: str, timeout: float) -> dict[str, Any]:
    request = urllib.request.Request(
        f"{DISCORD_API}/{code}?with_counts=true", headers=HEADERS
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return json.load(response)


def validate_card(
    card: dict[str, Any], fetch: Callable[[str], dict[str, Any]]
) -> list[str]:
    community_id = card.get("community_id", "<missing community_id>")
    source = card.get("metadata_source", {})
    code = source.get("key", "")
    errors = []
    if card.get("platform") != "discord":
        errors.append(f"{community_id}: Discord metadata requires platform: discord")
    if card.get("path") != f"https://discord.gg/{code}":
        errors.append(
            f"{community_id}: path must be the direct https://discord.gg/{code} invite"
        )
    if not code:
        errors.append(f"{community_id}: Discord metadata key is empty")
        return errors
    try:
        invite = fetch(code)
    except Exception as error:  # noqa: BLE001 - report network and decoder failures
        errors.append(
            f"{community_id}: Discord could not resolve invite {code}: {error}"
        )
        return errors
    if invite.get("code") != code:
        errors.append(f"{community_id}: Discord resolved a different invite code")
    if invite.get("expires_at") is not None:
        errors.append(
            f"{community_id}: Discord invite expires at {invite['expires_at']}"
        )
    vanity = invite.get("guild", {}).get("vanity_url_code")
    if vanity and vanity.casefold() == code.casefold():
        errors.append(f"{community_id}: Discord invite uses the server vanity code")
    return errors


def main(arguments: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base", required=True, help="base commit SHA")
    parser.add_argument("--path", type=Path, required=True)
    parser.add_argument("--timeout", type=float, default=15)
    args = parser.parse_args(arguments)
    errors = []
    for card in changed_discord_cards(args.base, args.path):
        errors.extend(
            validate_card(card, lambda code: fetch_invite(code, args.timeout))
        )
    for error in errors:
        print(f"error: {error}", file=sys.stderr)
    if errors:
        return 1
    print("changed Discord invites are valid")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
