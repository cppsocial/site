import re
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import yaml
from pydantic import TypeAdapter

from .files import update_bytes
from .runtime import log_operation_error

_SAFE_SOURCE_ID = re.compile(r"^[A-Za-z0-9_.-]+$")
_EARLIEST = datetime.min.replace(tzinfo=UTC)


def prune_records(
    records: list[dict[str, Any]],
    *,
    cutoff: datetime | None = None,
    limit: int | None = None,
) -> list[dict[str, Any]]:
    """Prune visible recent records while always retaining hidden stubs."""
    eligible = [
        item
        for item in records
        if item.get("hidden") is True
        or cutoff is None
        or item.get("published", _EARLIEST) >= cutoff
    ]
    if limit is None:
        return eligible
    hidden = [item for item in eligible if item.get("hidden") is True]
    visible = [item for item in eligible if item.get("hidden") is not True]
    return [*hidden, *visible[:limit]]


def merge_records(
    current: list[Any],
    updates: list[Any],
    *,
    id_field: str,
    normalize: Callable[[Any], dict[str, Any]],
    preserve_existing: bool = False,
) -> list[dict[str, Any]]:
    """Merge by stable ID, retaining unseen records and manual cache fields."""
    records = {}
    for value in current:
        raw = value.model_dump() if hasattr(value, "model_dump") else dict(value)
        item = raw if raw.get("hidden") is True else normalize(value)
        records[item[id_field]] = item
    preserved_ids = set(records)
    for value in updates:
        item = normalize(value)
        previous = records.get(item[id_field])
        if previous is not None and previous.get("hidden") is True:
            continue
        if preserve_existing and item[id_field] in preserved_ids:
            continue
        if item.get("cpp_relevance") is None and previous is not None:
            item["cpp_relevance"] = previous.get("cpp_relevance")
        records[item[id_field]] = item
    return list(records.values())


class RecentCache:
    """One editable, append-only recent-item cache per source."""

    def __init__(
        self,
        directory: Path,
        schema: Any,
        *,
        id_field: str,
        producer: str,
    ) -> None:
        self.directory = directory
        self.adapter = TypeAdapter(schema)
        self.id_field = id_field
        self.producer = producer

    def path(self, source_id: str) -> Path:
        if not _SAFE_SOURCE_ID.fullmatch(source_id):
            raise ValueError(f"unsafe recent-cache source id: {source_id!r}")
        return self.directory / f"{source_id}.yaml"

    def load(self, source_id: str) -> list[dict[str, Any]] | None:
        path = self.path(source_id)
        if not path.exists():
            return []
        try:
            raw = yaml.safe_load(path.read_text(encoding="utf-8")) or []
            if not isinstance(raw, list):
                raise ValueError("cache must contain a YAML list")
            result = []
            seen = set()
            for value in raw:
                if not isinstance(value, dict):
                    raise ValueError("cache entries must be mappings")
                item_id = str(value.get(self.id_field) or "")
                if not item_id:
                    raise ValueError(f"cache entries require {self.id_field}")
                if item_id in seen:
                    raise ValueError(f"duplicate {self.id_field}: {item_id}")
                seen.add(item_id)
                if value.get("hidden") is True:
                    result.append(dict(value))
                else:
                    result.append(
                        self.adapter.dump_python(
                            self.adapter.validate_python(value),
                            mode="python",
                            exclude_none=True,
                            exclude_defaults=True,
                        )
                    )
            return result
        except Exception as error:
            log_operation_error("recent cache load", error, path=path)
            return None

    def update(
        self, source_id: str, values: list[dict[str, Any]], check: bool = False
    ) -> bool:
        path = self.path(source_id)
        data = []
        for value in values:
            if value.get("hidden") is True:
                item = dict(value)
                if not item.get(self.id_field):
                    raise ValueError(f"hidden cache entries require {self.id_field}")
                data.append(item)
            else:
                data.append(
                    self.adapter.dump_python(
                        self.adapter.validate_python(value),
                        mode="python",
                        exclude_none=True,
                        exclude_defaults=True,
                    )
                )
        text = (
            f"# Maintained by {self.producer}. Manual edits are preserved.\n"
            f"# Set hidden: true and retain only {self.id_field} to suppress an item.\n"
            + yaml.safe_dump(data, allow_unicode=True, sort_keys=False, width=1000)
        )
        return update_bytes(path, text.encode(), check=check)

    def load_all(self) -> dict[str, list[dict[str, Any]]]:
        result = {}
        if not self.directory.is_dir():
            return result
        for path in sorted(self.directory.glob("*.yaml")):
            values = self.load(path.stem)
            if values is not None:
                result[path.stem] = values
        return result
