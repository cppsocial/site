from collections.abc import Callable
from pathlib import Path
from typing import Any

import yaml


def load_relevance_labels(path: Path, collection: str) -> dict[str, float]:
    """Load durable human labels for one generated collection."""
    if not path.is_file():
        return {}
    raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    values = raw.get(collection, {})
    if not isinstance(values, dict):
        raise ValueError(f"{path}: {collection} must be a mapping")
    result = {}
    for item_id, value in values.items():
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise ValueError(f"{path}: relevance for {item_id} must be a number")
        score = float(value)
        if not 0.0 <= score <= 1.0:
            raise ValueError(f"{path}: relevance for {item_id} must be between 0 and 1")
        result[str(item_id)] = score
    return result


def merge_records(
    current: list[Any],
    updates: list[Any],
    *,
    id_field: str,
    normalize: Callable[[Any], dict[str, Any]],
) -> list[dict[str, Any]]:
    """Merge by stable ID, retaining unseen records and preventing duplicates."""
    records = {item[id_field]: item for item in map(normalize, current)}
    for value in updates:
        item = normalize(value)
        previous = records.get(item[id_field])
        if item.get("cpp_relevance") is None and previous is not None:
            item["cpp_relevance"] = previous.get("cpp_relevance")
        records[item[id_field]] = item
    return list(records.values())


def apply_relevance_labels(
    records: list[dict[str, Any]],
    labels: dict[str, float],
    *,
    id_field: str,
) -> list[dict[str, Any]]:
    result = []
    for value in records:
        item = dict(value)
        if item[id_field] in labels:
            item["cpp_relevance"] = labels[item[id_field]]
        result.append(item)
    return result
