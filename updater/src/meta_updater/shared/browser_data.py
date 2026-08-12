import base64
import hashlib
import json
import os
import re
import tempfile
import unicodedata
from collections import defaultdict
from collections.abc import Iterable
from pathlib import Path
from typing import Any

FORMAT_VERSION = 8
TARGET_CHUNK_BYTES = 128 * 1024
TARGET_ROUTE_BYTES = 8 * 1024
TARGET_ROUTE_BUNDLE_BYTES = 32 * 1024
MIN_QUERY_LENGTH = 2
SEARCH_FIELDS = ("title", "content", "source", "tags")
TOKEN_PATTERN = re.compile(r"[\w+#.-]+", re.UNICODE)


def search_terms(*values: object) -> list[str]:
    """Return stable, de-duplicated terms shared by routing and IndexedDB."""
    text = " ".join(str(value) for value in values if value)
    normalized = unicodedata.normalize("NFKC", text).casefold()
    return list(dict.fromkeys(TOKEN_PATTERN.findall(normalized)))


def update_browser_collection(
    directory: Path,
    records: list[dict[str, Any]],
    *,
    collection: str,
    fields: dict[str, dict[str, Any]],
    chunk_bytes: int = TARGET_CHUNK_BYTES,
    check: bool = False,
    compact: bool = False,
    metadata: dict[str, Any] | None = None,
) -> bool:
    """Update an append-only static collection and its prefix routing lexicon."""
    if chunk_bytes < 16 * 1024:
        raise ValueError("chunk_bytes must be at least 16 KiB")
    desired = _normalize_records(records)
    previous, old_files = _read_collection(directory)
    previous_epoch = previous.get("epoch", 0)
    if compact:
        previous = {}
    state, _, _ = _materialize(previous, directory)
    revision = int(previous.get("revision", 0))

    changed_records = sorted(
        (
            record
            for record_id, record in desired.items()
            if state.get(record_id) != record
        ),
        key=lambda record: (record.get("published", ""), record["id"]),
    )
    deleted_ids = sorted(state.keys() - desired.keys())
    operations: list[dict[str, Any]] = []
    if changed_records or deleted_ids:
        revision += 1
        operations.extend(changed_records)
        operations.extend(
            {"id": record_id, "_deleted": True} for record_id in deleted_ids
        )

    chunks = _append_chunks(previous, directory, operations, chunk_bytes)
    current_state, current_locations, _ = _materialize_chunks(chunks)
    if current_state != desired:
        raise ValueError("generated collection does not materialize to desired records")

    route_segments = _route_segments(current_state, current_locations, fields)
    chunk_descriptors = _chunk_descriptors(chunks)
    chunk_descriptors, chunk_files = _publish_data_chunks(
        list(zip(chunk_descriptors, chunks, strict=True)),
    )
    route_descriptors, route_files = _publish_payloads(
        route_segments,
        TARGET_ROUTE_BUNDLE_BYTES,
    )
    manifest = {
        **(metadata or {}),
        "version": FORMAT_VERSION,
        "collection": collection,
        "epoch": (
            previous_epoch + 1
            if compact and previous_epoch
            else previous.get("epoch", 1)
            if previous.get("version") == FORMAT_VERSION
            else 1
        ),
        "revision": revision,
        "count": len(current_state),
        "operation_count": sum(len(chunk["operations"]) for chunk in chunks),
        "chunk_target_bytes": chunk_bytes,
        "min_query_length": MIN_QUERY_LENGTH,
        "route_fields": list(fields),
        "fields": [
            {"name": "all", "label": "Everything"},
            *[
                {"name": name, **definition}
                for name, definition in fields.items()
                if name in SEARCH_FIELDS
            ],
        ],
        "chunks": chunk_descriptors,
        # Synchronization is deliberately independent from search routes.
        # Every descriptor is checked client-side; immutable/current chunks do
        # not require another download.
        "sync_chunks": [chunk["id"] for chunk in chunk_descriptors],
        "routes": route_descriptors,
    }
    files = {**chunk_files, **route_files, "index.json": _json(manifest)}

    changed = old_files != files
    if not changed or check:
        return changed
    directory.mkdir(parents=True, exist_ok=True)
    for name, text in files.items():
        _replace(directory / name, text)
    for name in old_files.keys() - files.keys():
        (directory / name).unlink()
    return True


def update_keyed_collection(
    directory: Path,
    records: Iterable[dict[str, Any]],
    *,
    collection: str,
    bucket_count: int = 256,
    check: bool = False,
) -> bool:
    if bucket_count < 1 or bucket_count & (bucket_count - 1):
        raise ValueError("bucket_count must be a positive power of two")
    desired = _normalize_records(records)
    buckets: defaultdict[int, list[dict[str, Any]]] = defaultdict(list)
    for record_id, record in desired.items():
        buckets[_fnv1a(record_id) % bucket_count].append(record)
    files: dict[str, str] = {}
    descriptors = []
    for index, values in sorted(buckets.items()):
        payload = {
            "records": {
                value["id"]: {key: item for key, item in value.items() if key != "id"}
                for value in sorted(values, key=lambda item: item["id"])
            }
        }
        text = _json(payload)
        revision = hashlib.sha256(text.encode()).hexdigest()[:16]
        name = f"bucket-{index:03d}-{revision}.json"
        files[name] = text
        descriptors.append(
            {
                "index": index,
                "revision": revision,
                "file": name,
                "bytes": len(text.encode()),
                "records": len(values),
            }
        )
    manifest = {
        "version": FORMAT_VERSION,
        "kind": "keyed-records",
        "collection": collection,
        "bucket_count": bucket_count,
        "count": len(desired),
        "buckets": descriptors,
    }
    files["index.json"] = _json(manifest)
    old_files = {
        path.name: path.read_text(encoding="utf-8")
        for path in directory.glob("*.json")
        if path.is_file()
    }
    changed = old_files != files
    if not changed or check:
        return changed
    directory.mkdir(parents=True, exist_ok=True)
    for name, text in files.items():
        _replace(directory / name, text)
    for name in old_files.keys() - files.keys():
        (directory / name).unlink()
    return True


def _fnv1a(value: str) -> int:
    result = 0x811C9DC5
    for byte in value.encode():
        result = ((result ^ byte) * 0x01000193) & 0xFFFFFFFF
    return result


def _normalize_records(
    records: Iterable[dict[str, Any]],
) -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}
    for raw in records:
        record = dict(raw)
        record_id = str(record.get("id", ""))
        if not record_id:
            raise ValueError("browser records require a non-empty id")
        if record_id in result:
            raise ValueError(f"duplicate browser record id: {record_id}")
        record.pop("search", None)
        record["id"] = record_id
        result[record_id] = record
    return result


def _read_collection(directory: Path) -> tuple[dict[str, Any], dict[str, str]]:
    files = {
        path.name: path.read_text(encoding="utf-8")
        for path in directory.glob("*.json")
        if path.is_file()
    }
    try:
        manifest = json.loads(files.get("index.json", "{}"))
    except json.JSONDecodeError:
        manifest = {}
    if manifest.get("version") != FORMAT_VERSION:
        manifest = {}
    return manifest, files


def _materialize(
    manifest: dict[str, Any], directory: Path
) -> tuple[dict[str, dict[str, Any]], dict[str, int], int]:
    return _materialize_chunks(_logical_payloads(manifest.get("chunks", []), directory))


def _materialize_chunks(
    chunks: list[dict[str, Any]],
) -> tuple[dict[str, dict[str, Any]], dict[str, int], int]:
    state: dict[str, dict[str, Any]] = {}
    locations: dict[str, int] = {}
    sequence = 0
    for chunk_index, chunk in enumerate(chunks):
        for operation in chunk.get("operations", []):
            sequence += 1
            record_id = operation["id"]
            if operation.get("_deleted", False):
                state.pop(record_id, None)
                locations.pop(record_id, None)
            else:
                state[record_id] = {
                    key: value for key, value in operation.items() if key != "_deleted"
                }
                locations[record_id] = chunk_index
    return state, locations, sequence


def _append_chunks(
    manifest: dict[str, Any],
    directory: Path,
    operations: list[dict[str, Any]],
    chunk_bytes: int,
) -> list[dict[str, Any]]:
    chunks = _logical_payloads(manifest.get("chunks", []), directory)
    pending = list(operations)
    if chunks and pending:
        current = chunks.pop()
        pending = list(current["operations"]) + pending
    elif chunks:
        return chunks
    while pending:
        take = _fit_count(pending, chunk_bytes)
        chunks.append({"operations": pending[:take]})
        pending = pending[take:]
    return chunks


def _fit_count(operations: list[dict[str, Any]], limit: int) -> int:
    low, high = 1, len(operations)
    while low < high:
        middle = (low + high + 1) // 2
        size = len(_json({"operations": operations[:middle]}).encode())
        if size <= limit:
            low = middle
        else:
            high = middle - 1
    return low


def _chunk_descriptors(chunks: list[dict[str, Any]]) -> list[dict[str, Any]]:
    result = []
    start = 0
    for index, chunk in enumerate(chunks):
        result.append(_chunk_descriptor(chunk, index, len(chunks), start))
        start += len(chunk["operations"])
    return result


def _chunk_descriptor(
    chunk: dict[str, Any], index: int, total: int, start: int
) -> dict[str, Any]:
    operations = chunk["operations"]
    text = _json(chunk)
    dates = [
        operation["published"]
        for operation in operations
        if not operation.get("_deleted") and operation.get("published")
    ]
    return {
        "id": f"data-{index:05d}",
        "revision": _digest(chunk),
        "bytes": len(text.encode()),
        "operations": len(operations),
        "start": start,
        "min_published": min(dates, default=""),
        "max_published": max(dates, default=""),
        "sealed": index < total - 1,
    }


def _route_segments(
    state: dict[str, dict[str, Any]],
    locations: dict[str, int],
    fields: dict[str, dict[str, Any]],
) -> list[tuple[dict[str, Any], dict[str, Any]]]:
    postings: dict[str, dict[int, set[int]]] = defaultdict(lambda: defaultdict(set))
    for record_id, record in state.items():
        chunk = locations[record_id]
        for field_index, (_, definition) in enumerate(fields.items()):
            properties = definition.get("properties") or [definition["property"]]
            values = []
            for property_name in properties:
                value = record.get(property_name, "")
                values.extend(value if isinstance(value, list) else [value])
            for term in search_terms(*values):
                if len(term) >= MIN_QUERY_LENGTH:
                    postings[term][field_index].add(chunk)

    chunk_count = max(locations.values(), default=-1) + 1
    roots: dict[str, list[str]] = defaultdict(list)
    for term in sorted(postings):
        roots[term[:MIN_QUERY_LENGTH]].append(term)

    atomic_groups = [
        group
        for root_terms in roots.values()
        for group in _bounded_route_groups(root_terms, postings, chunk_count)
    ]
    groups: list[list[str]] = []
    current: list[str] = []
    for group in atomic_groups:
        combined = [*current, *group]
        combined_size = len(
            _json({"data": _encode_route(combined, postings, chunk_count)}).encode()
        )
        if current and combined_size > TARGET_ROUTE_BYTES:
            groups.append(current)
            current = list(group)
        else:
            current = combined
    if current:
        groups.append(current)

    segments = []
    for group in groups:
        data = _encode_route(group, postings, chunk_count)
        payload = {"data": data}
        text = _json(payload)
        digest = hashlib.sha256(text.encode()).hexdigest()[:24]
        descriptor = {
            "id": f"route-{len(segments):05d}",
            "revision": digest,
            "first": group[0],
            "last": group[-1],
        }
        segments.append((descriptor, payload))
    return segments


def _bounded_route_groups(
    terms: list[str],
    postings: dict[str, dict[int, set[int]]],
    chunk_count: int,
) -> list[list[str]]:
    data = _encode_route(terms, postings, chunk_count)
    if len(_json({"data": data}).encode()) <= (TARGET_ROUTE_BYTES) or len(terms) == 1:
        return [terms]
    middle = len(terms) // 2
    return [
        *_bounded_route_groups(terms[:middle], postings, chunk_count),
        *_bounded_route_groups(terms[middle:], postings, chunk_count),
    ]


def _logical_payloads(
    descriptors: list[dict[str, Any]], directory: Path
) -> list[dict[str, Any]]:
    files: dict[str, dict[str, Any]] = {}
    result = []
    for descriptor in descriptors:
        name = descriptor["file"]
        if name not in files:
            path = directory / name
            if not path.is_file():
                raise ValueError(f"manifest references missing payload: {path}")
            files[name] = json.loads(path.read_text(encoding="utf-8"))
        payload = files[name]
        if "chunks" not in payload:
            result.append(payload)
            continue
        try:
            result.append(payload["chunks"][descriptor["id"]])
        except KeyError as error:
            raise ValueError(
                f"payload {name} does not contain {descriptor['id']}"
            ) from error
    return result


def _publish_data_chunks(
    items: list[tuple[dict[str, Any], dict[str, Any]]],
) -> tuple[list[dict[str, Any]], dict[str, str]]:
    """Publish record metadata as one readable JSON file per logical chunk."""
    descriptors = [dict(descriptor) for descriptor, _ in items]
    files: dict[str, str] = {}
    for descriptor, (_, payload) in zip(descriptors, items, strict=True):
        name = f"chunk-{descriptor['revision']}.json"
        descriptor["file"] = name
        files[name] = _json(payload)
    return descriptors, files


def _publish_payloads(
    items: list[tuple[dict[str, Any], dict[str, Any]]],
    target_bytes: int,
) -> tuple[list[dict[str, Any]], dict[str, str]]:
    descriptors = [dict(descriptor) for descriptor, _ in items]
    files: dict[str, str] = {}
    locations: dict[str, str] = {}
    pending: dict[str, dict[str, Any]] = {}

    def flush() -> None:
        if not pending:
            return
        payload = {"version": FORMAT_VERSION, "chunks": dict(pending)}
        text = _json(payload)
        name = f"payload-{hashlib.sha256(text.encode()).hexdigest()[:24]}.json"
        files[name] = text
        locations.update({logical_id: name for logical_id in pending})
        pending.clear()

    for descriptor, payload in items:
        logical_id = descriptor["id"]
        trial = {"version": FORMAT_VERSION, "chunks": {**pending, logical_id: payload}}
        if pending and len(_json(trial).encode()) > target_bytes:
            flush()
        pending[logical_id] = payload
        if (
            len(_json({"version": FORMAT_VERSION, "chunks": pending}).encode())
            >= target_bytes
        ):
            flush()
    flush()

    for descriptor in descriptors:
        descriptor["file"] = locations[descriptor["id"]]
    return descriptors, files


def _digest(value: Any) -> str:
    return hashlib.sha256(_json(value).encode()).hexdigest()[:16]


def _encode_route(
    terms: list[str],
    postings: dict[str, dict[int, set[int]]],
    chunk_count: int,
) -> str:
    previous = b""
    output = bytearray()
    all_chunks = set(range(chunk_count))
    for term in terms:
        encoded_term = term.encode()
        shared = 0
        for left, right in zip(previous, encoded_term, strict=False):
            if left != right:
                break
            shared += 1
        suffix = encoded_term[shared:]
        encoded_postings = _encode_postings(postings[term], all_chunks)

        _write_varint(output, shared)
        _write_varint(output, len(suffix))
        output.extend(suffix)
        _write_varint(output, len(encoded_postings))
        output.extend(encoded_postings)
        previous = encoded_term
    return base64.urlsafe_b64encode(output).decode().rstrip("=")


def _encode_postings(postings: dict[int, set[int]], all_chunks: set[int]) -> bytearray:
    grouped: dict[tuple[bool, tuple[int, ...]], int] = defaultdict(int)
    for field_index, chunks in postings.items():
        excluded = all_chunks - chunks
        complement = len(excluded) < len(chunks)
        values = tuple(sorted(excluded if complement else chunks))
        grouped[(complement, values)] |= 1 << field_index

    output = bytearray()
    for (complement, values), field_mask in sorted(grouped.items()):
        _write_varint(output, (field_mask << 1) | int(complement))
        deltas = (
            [
                values[0],
                *(
                    right - left
                    for left, right in zip(values, values[1:], strict=False)
                ),
            ]
            if values
            else []
        )
        for delta in deltas:
            _write_varint(output, delta + 1)
        output.append(0)
    return output


def _write_varint(output: bytearray, value: int) -> None:
    while value >= 0x80:
        output.append((value & 0x7F) | 0x80)
        value >>= 7
    output.append(value)


def _pretty_json(value: Any) -> str:
    return (
        json.dumps(
            value,
            ensure_ascii=False,
            indent=2,
            sort_keys=False,
        )
        + "\n"
    )


def _json(value: Any) -> str:
    return (
        json.dumps(
            value,
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=False,
        )
        + "\n"
    )


def _replace(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        "w", encoding="utf-8", dir=path.parent, delete=False
    ) as file:
        file.write(text)
        temporary = Path(file.name)
    os.replace(temporary, path)
