from collections.abc import Iterable
from pathlib import Path
from typing import Any

import yaml


def apply_metadata_overrides(
    records: list[dict[str, Any]],
    path: Path,
    collection: str,
    *,
    id_field: str,
    allowed_fields: Iterable[str],
) -> list[dict[str, Any]]:
    """Apply durable human corrections after ingest and before publication."""
    if not path.is_file():
        return records
    document = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    raw = document.get(collection, {})
    if not isinstance(raw, dict):
        raise ValueError(f"{path}: {collection} must be a mapping")

    allowed = set(allowed_fields)
    overrides: dict[str, dict[str, Any]] = {}
    for item_id, value in raw.items():
        if not isinstance(value, dict):
            raise ValueError(f"{path}: override for {item_id} must be a mapping")
        unknown = set(value) - allowed - {"hidden"}
        if unknown:
            names = ", ".join(sorted(unknown))
            raise ValueError(f"{path}: unsupported fields for {item_id}: {names}")
        if "hidden" in value and not isinstance(value["hidden"], bool):
            raise ValueError(f"{path}: hidden for {item_id} must be a boolean")
        overrides[str(item_id)] = value

    known = {str(item[id_field]) for item in records}
    missing = set(overrides) - known
    if missing:
        names = ", ".join(sorted(missing))
        raise ValueError(f"{path}: overrides reference unknown {collection}: {names}")

    result = []
    for value in records:
        item = dict(value)
        correction = overrides.get(str(item[id_field]), {})
        item["hidden"] = correction.get("hidden", False)
        item.update(
            {
                name: replacement
                for name, replacement in correction.items()
                if name != "hidden"
            }
        )
        result.append(item)
    return result
