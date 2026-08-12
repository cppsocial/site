import hashlib
import re
from collections import Counter, defaultdict
from dataclasses import dataclass
from difflib import SequenceMatcher
from typing import Any
from urllib.parse import urlsplit

from .common import clean_licenses, clean_list, repository_identity


def _spelling_name(value: str) -> str:
    return re.sub(r"[-_.+]", "", value.casefold())


def _alias_name(value: str) -> str:
    return _spelling_name(value).removeprefix("lib")


def _master_id(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", value.casefold()).strip("-") or "package"


def _host_path(value: str) -> str:
    if not value:
        return ""
    parsed = urlsplit(value)
    return (
        parsed.netloc.casefold().removeprefix("www.")
        + parsed.path.rstrip("/").casefold()
    )


def _identity(package: dict[str, Any]) -> str:
    return repository_identity(package.get("repository_url", ""))


def _identities(package: dict[str, Any]) -> set[str]:
    values = {
        package.get("repository_url", ""),
        *(release.get("repository_url", "") for release in package.get("versions") or []),
        *(artifact.get("url", "") for artifact in _artifacts(package, "upstream_source")),
    }
    return {
        identity for value in values if (identity := repository_identity(str(value)))
    }


def _artifacts(package: dict[str, Any], kind: str | None = None):
    for release in package.get("versions") or []:
        for artifact in release.get("artifacts") or []:
            if kind is None or artifact.get("kind") == kind:
                yield artifact


def _source_urls(package: dict[str, Any]) -> set[str]:
    return {
        str(artifact.get("url") or "")
        for artifact in _artifacts(package, "upstream_source")
        if artifact.get("url")
    }


def _source_checksums(package: dict[str, Any]) -> set[str]:
    return {
        checksum
        for artifact in _artifacts(package, "upstream_source")
        for checksum in artifact.get("checksums") or []
    }


def compare_packages(
    left: dict[str, Any],
    right: dict[str, Any],
    homepage_counts: dict[str, Counter[str]] | None = None,
) -> dict[str, Any] | None:
    if left["registry"] == right["registry"]:
        return None
    evidence = []
    repositories = _identities(left) & _identities(right)
    if repositories:
        evidence.append({"signal": "same upstream repository", "weight": 1.0})
    source_urls = _source_urls(left) & _source_urls(right)
    if source_urls:
        evidence.append({"signal": "same distributed source URL", "weight": 1.0})
    left_checksums = _source_checksums(left)
    right_checksums = _source_checksums(right)
    if left_checksums & right_checksums:
        evidence.append({"signal": "same distributed source checksum", "weight": 1.0})
    if left["name"].casefold() == right["name"].casefold():
        evidence.append({"signal": "same exact name", "weight": 0.95})
    elif _spelling_name(left["name"]) == _spelling_name(right["name"]):
        evidence.append({"signal": "same normalized spelling", "weight": 0.75})
    elif _alias_name(left["name"]) == _alias_name(right["name"]):
        evidence.append({"signal": "library-prefix alias", "weight": 0.6})
    else:
        evidence.append({"signal": "substantially different names", "weight": -0.3})
    left_home, right_home = (
        _host_path(left.get("homepage", "")),
        _host_path(right.get("homepage", "")),
    )
    if left_home and left_home == right_home:
        counts = (homepage_counts or {}).get(left_home, Counter())
        repeated = any(count > 1 for count in counts.values())
        evidence.append(
            {
                "signal": "shared package-family homepage"
                if repeated
                else "same homepage",
                "weight": 0.0 if repeated else 0.3,
            }
        )
    authors = {value.casefold().strip() for value in left.get("authors") or []} & {
        value.casefold().strip() for value in right.get("authors") or []
    }
    if authors:
        evidence.append({"signal": "shared author", "weight": 0.66})
    maintainers = set(left.get("maintainers") or []) & set(
        right.get("maintainers") or []
    )
    if maintainers:
        evidence.append({"signal": "shared maintainer", "weight": 0.18})
    left_licenses = {
        value.casefold() for value in clean_licenses(left.get("licenses") or [])
    }
    right_licenses = {
        value.casefold() for value in clean_licenses(right.get("licenses") or [])
    }
    licenses = left_licenses & right_licenses
    if licenses:
        evidence.append({"signal": "shared license", "weight": 0.05})
    elif left_licenses and right_licenses:
        evidence.append({"signal": "conflicting licenses", "weight": -0.12})
    certain = any(item["weight"] == 1.0 for item in evidence)
    descriptions = (left.get("description", ""), right.get("description", ""))
    if all(descriptions):
        similarity = SequenceMatcher(
            None, *[value.casefold() for value in descriptions]
        ).ratio()
        if similarity >= 0.65:
            evidence.append(
                {"signal": "similar description", "weight": round(similarity * 0.12, 4)}
            )
        elif similarity < 0.25:
            evidence.append({"signal": "conflicting descriptions", "weight": -0.07})
    package_types = (left.get("package_type", ""), right.get("package_type", ""))
    if all(package_types) and package_types[0] != package_types[1]:
        evidence.append({"signal": "conflicting package types", "weight": -0.15})
    versions = {item.get("version", "") for item in left.get("versions") or []} & {
        item.get("version", "") for item in right.get("versions") or []
    }
    if versions:
        evidence.append({"signal": "shared distributed version", "weight": 0.12})
    if not evidence:
        return None
    confidence = 1.0
    for item in evidence:
        if item["weight"] > 0:
            confidence *= 1.0 - item["weight"]
    confidence = 1.0 - confidence
    if not certain:
        penalty = sum(item["weight"] for item in evidence if item["weight"] < 0)
        confidence *= max(0.0, 1.0 + penalty)
    confidence = round(confidence, 4)
    if confidence < 0.45:
        return None
    return {
        "left": left["id"],
        "right": right["id"],
        "confidence": confidence,
        "evidence": evidence,
    }


@dataclass
class _UnionFind:
    parents: dict[str, str]
    registries: dict[str, set[str]]
    members: dict[str, list[dict[str, Any]]]
    protected: set[str]
    forbidden: set[frozenset[str]]

    def find(self, value: str) -> str:
        self.parents.setdefault(value, value)
        if self.parents[value] != value:
            self.parents[value] = self.find(self.parents[value])
        return self.parents[value]

    def union(self, left: str, right: str, force: bool = False) -> str:
        left_root, right_root = self.find(left), self.find(right)
        if not force and (left_root in self.protected or right_root in self.protected):
            return "none"
        if left_root == right_root:
            return "merge"
        if not force and any(
            frozenset((left_package["id"], right_package["id"])) in self.forbidden
            for left_package in self.members[left_root]
            for right_package in self.members[right_root]
        ):
            return "conflict"
        overlap = self.registries[left_root] & self.registries[right_root]
        if (
            overlap
            and not force
            and not _alias_groups_compatible(
                self.members[left_root], self.members[right_root], overlap
            )
        ):
            return "conflict"
        self.parents[right_root] = left_root
        self.registries[left_root] |= self.registries.pop(right_root)
        self.members[left_root].extend(self.members.pop(right_root))
        if right_root in self.protected:
            self.protected.remove(right_root)
            self.protected.add(left_root)
        return "manual_merge" if force else "merge"


def _package_checksums(package: dict[str, Any]) -> set[str]:
    return _source_checksums(package)


def _same_code_identity(left: dict[str, Any], right: dict[str, Any]) -> bool:
    if _source_urls(left) & _source_urls(right) or _package_checksums(
        left
    ) & _package_checksums(right):
        return True
    repositories = _identities(left) & _identities(right)
    descriptions = (left.get("description", ""), right.get("description", ""))
    return bool(
        repositories
        and all(descriptions)
        and SequenceMatcher(
            None, descriptions[0].casefold(), descriptions[1].casefold()
        ).ratio()
        >= 0.65
    )


def _alias_groups_compatible(
    left: list[dict[str, Any]],
    right: list[dict[str, Any]],
    overlapping_registries: set[str],
) -> bool:
    for registry in overlapping_registries:
        pairs = (
            (left_package, right_package)
            for left_package in left
            if left_package["registry"] == registry
            for right_package in right
            if right_package["registry"] == registry
        )
        for left_package, right_package in pairs:
            if not _same_code_identity(left_package, right_package):
                return False
            descriptions = (
                left_package.get("description", ""),
                right_package.get("description", ""),
            )
            if (
                all(descriptions)
                and SequenceMatcher(
                    None, descriptions[0].casefold(), descriptions[1].casefold()
                ).ratio()
                < 0.65
            ):
                return False
            package_types = (
                left_package.get("package_type", ""),
                right_package.get("package_type", ""),
            )
            if all(package_types) and package_types[0] != package_types[1]:
                return False
    return True


def _merge_priority(match: dict[str, Any]) -> int:
    signals = {item["signal"] for item in match["evidence"]}
    for priority, signal in (
        (7, "same exact name"),
        (6, "same normalized spelling"),
        (5, "same distributed source checksum"),
        (4, "same distributed source URL"),
        (3, "library-prefix alias"),
        (1, "same upstream repository"),
    ):
        if signal in signals:
            return priority
    return 0


def amalgamate(
    catalogs: dict[str, list[dict[str, Any]]],
    threshold: float = 0.82,
    overrides: list[dict[str, Any]] | dict[str, Any] | None = None,
    previous_entities: list[dict[str, Any]] | None = None,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    packages = [package for values in catalogs.values() for package in values]
    homepage_counts: defaultdict[str, Counter[str]] = defaultdict(Counter)
    for package in packages:
        if homepage := _host_path(package.get("homepage", "")):
            homepage_counts[homepage][package["registry"]] += 1
    blocks: defaultdict[str, list[dict[str, Any]]] = defaultdict(list)
    for package in packages:
        keys = {
            f"spelling:{_spelling_name(package['name'])}",
            f"alias:{_alias_name(package['name'])}",
            *(f"source:{value}" for value in _source_urls(package)),
            *(
                f"checksum:{checksum}"
                for checksum in _source_checksums(package)
            ),
            *(
                f"author:{value.casefold().strip()}"
                for value in package.get("authors") or []
            ),
        }
        if repository := _identity(package):
            keys.add(f"repo:{repository}")
        if homepage := _host_path(package.get("homepage", "")):
            keys.add(f"homepage:{homepage}")
        for key in keys:
            if key:
                blocks[key].append(package)
    seen = set()
    matches = []
    override_config = overrides if isinstance(overrides, dict) else {}
    identity_overrides = (
        override_config.get("groups") or []
        if isinstance(overrides, dict)
        else overrides or []
    )
    forbidden = {
        frozenset(pair)
        for rule in override_config.get("never_merge") or []
        for pair in [rule.get("packages") or []]
        if len(pair) == 2
    }
    union = _UnionFind(
        {},
        {package["id"]: {package["registry"]} for package in packages},
        {package["id"]: [package] for package in packages},
        set(),
        forbidden,
    )
    packages_by_id = {package["id"]: package for package in packages}
    override_by_package = {}
    for override in identity_overrides:
        package_ids = [
            package_id
            for package_id in override["packages"]
            if package_id in packages_by_id
        ]
        missing = [
            package_id
            for package_id in override["packages"]
            if package_id not in packages_by_id
        ]
        if missing:
            raise ValueError(
                f"package override references unknown IDs: {', '.join(missing)}"
            )
        package_ids.extend(
            package_id
            for package_id in override.get("optional_packages") or []
            if package_id in packages_by_id and package_id not in package_ids
        )
        if not package_ids:
            raise ValueError("package override groups require at least one package ID")
        for package_id in package_ids:
            override_by_package.setdefault(package_id, override)
        for left, right in zip(package_ids, package_ids[1:], strict=False):
            decision = union.union(left, right, force=True)
            matches.append(
                {
                    "left": left,
                    "right": right,
                    "confidence": 1.0,
                    "decision": decision,
                    "evidence": [
                        {"signal": "manual package group override", "weight": 1.0}
                    ],
                }
            )
    for values in blocks.values():
        for index, left in enumerate(values):
            for right in values[index + 1 :]:
                pair = tuple(sorted((left["id"], right["id"])))
                if pair in seen:
                    continue
                seen.add(pair)
                ordered = sorted((left, right), key=lambda item: item["id"])
                match = compare_packages(ordered[0], ordered[1], homepage_counts)
                if match is None:
                    continue
                matches.append(match)
    for match in sorted(
        matches,
        key=lambda item: (
            -_merge_priority(item),
            -item["confidence"],
            item["left"],
            item["right"],
        ),
    ):
        if match.get("decision") == "manual_merge":
            continue
        match["decision"] = (
            "none"
            if match["confidence"] < threshold
            else union.union(match["left"], match["right"])
        )
    groups: defaultdict[str, list[dict[str, Any]]] = defaultdict(list)
    for package in packages:
        groups[union.find(package["id"])].append(package)
    master = []
    for values in groups.values():
        names = Counter(package["name"] for package in values)
        override = next(
            (
                override_by_package[package["id"]]
                for package in values
                if package["id"] in override_by_package
            ),
            None,
        )
        name = (
            override.get("name")
            if override and override.get("name")
            else min(
                names,
                key=lambda item: (-names[item], len(item), item.casefold(), item),
            )
        )
        aliases = sorted(
            (
                {package["name"] for package in values}
                | set((override.get("aliases") or []) if override else [])
            )
            - {name},
            key=lambda item: (item.casefold(), item),
        )
        licenses = clean_list(
            license_name
            for package in values
            for license_name in package.get("licenses") or []
        )
        references = [
            {
                "registry": package["registry"],
                "package_id": package["id"],
                "metadata_file": f"/data/packages/{package['registry']}.yaml",
                "recipe_url": package["recipe_url"],
            }
            for package in sorted(
                values, key=lambda item: (item["registry"], item["id"])
            )
        ]
        master.append(
            {
                **({"curated_id": override["id"]} if override and override.get("id") else {}),
                "name": name,
                "aliases": aliases,
                "licenses": sorted(licenses),
                "packages": references,
            }
        )
    assigned: set[str] = set()
    previous = {
        item["id"]: set(item.get("packages") or []) for item in previous_entities or []
    }
    candidates = []
    for index, package in enumerate(master):
        package_ids = {item["package_id"] for item in package["packages"]}
        for entity_id, old_ids in previous.items():
            if overlap := len(package_ids & old_ids):
                candidates.append((-overlap, entity_id, index))
    for _, entity_id, index in sorted(candidates):
        if "id" not in master[index] and entity_id not in assigned:
            master[index]["id"] = entity_id
            assigned.add(entity_id)
    for package in master:
        if curated_id := package.pop("curated_id", None):
            if curated_id in assigned and package.get("id") != curated_id:
                raise ValueError(f"curated package entity ID is not unique: {curated_id}")
            package["id"] = curated_id
            assigned.add(curated_id)
    id_counts = Counter(_master_id(package["name"]) for package in master if "id" not in package)
    for package in master:
        if "id" in package:
            continue
        base = _master_id(package["name"])
        if id_counts[base] == 1 and base not in assigned:
            package["id"] = base
            assigned.add(base)
            continue
        package_ids = "\n".join(
            reference["package_id"] for reference in package["packages"]
        )
        candidate = f"{base}-{hashlib.sha256(package_ids.encode()).hexdigest()[:8]}"
        package["id"] = candidate
        assigned.add(candidate)
    return sorted(master, key=lambda item: (item["name"].casefold(), item["name"])), sorted(
        matches, key=lambda item: (-item["confidence"], item["left"], item["right"])
    )
