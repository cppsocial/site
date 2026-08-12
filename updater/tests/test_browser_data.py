import base64
import json
import tempfile
import unittest
from pathlib import Path

from meta_updater.shared import browser_data
from meta_updater.shared.browser_data import (
    update_browser_collection,
    update_keyed_collection,
)

FIELDS = {
    "title": {"label": "Title", "property": "title"},
    "content": {"label": "Content", "property": "description"},
    "source": {"label": "Source", "property": "source"},
    "tags": {"label": "Tag", "property": "tags"},
}


def record(index: int, *, title: str | None = None) -> dict:
    return {
        "id": f"item-{index}",
        "title": title or f"CMake package {index}",
        "description": ("portable compiler tooling " * 40) + str(index),
        "source": "example",
        "tags": ["build", "c++"],
        "published": f"2026-01-{(index % 28) + 1:02d}T00:00:00+00:00",
        "url": f"https://example.test/{index}",
    }


def manifest(directory: Path) -> dict:
    return json.loads((directory / "index.json").read_text())


def logical_payload(directory: Path, descriptor: dict) -> dict:
    payload = json.loads((directory / descriptor["file"]).read_text())
    return payload.get("chunks", {}).get(descriptor["id"], payload)


def materialize(directory: Path) -> tuple[dict[str, dict], list[dict]]:
    current: dict[str, dict] = {}
    operations = []
    for descriptor in manifest(directory)["chunks"]:
        for operation in logical_payload(directory, descriptor)["operations"]:
            operations.append(operation)
            if operation.get("_deleted"):
                current.pop(operation["id"], None)
            else:
                current[operation["id"]] = operation
    return current, operations


def decode_route_terms(value: str) -> list[str]:
    padding = "=" * ((4 - len(value) % 4) % 4)
    data = base64.urlsafe_b64decode(value + padding)
    offset = 0
    previous = b""
    result = []

    def varint() -> int:
        nonlocal offset
        value = 0
        shift = 0
        while True:
            byte = data[offset]
            offset += 1
            value |= (byte & 0x7F) << shift
            if not byte & 0x80:
                return value
            shift += 7

    while offset < len(data):
        shared = varint()
        suffix_length = varint()
        term = previous[:shared] + data[offset : offset + suffix_length]
        offset += suffix_length
        posting_length = varint()
        offset += posting_length
        result.append(term.decode())
        previous = term
    return result


class BrowserCollectionTests(unittest.TestCase):
    def update(
        self,
        directory: Path,
        records: list[dict],
        *,
        check: bool = False,
        compact: bool = False,
    ) -> bool:
        return update_browser_collection(
            directory,
            records,
            collection="test-items",
            fields=FIELDS,
            chunk_bytes=16 * 1024,
            check=check,
            compact=compact,
        )

    def test_manifest_has_no_record_entries_and_chunks_are_bounded(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            self.assertTrue(self.update(directory, [record(i) for i in range(30)]))
            index = manifest(directory)
            self.assertEqual(index["version"], 8)
            self.assertNotIn("entries", index)
            self.assertGreater(len(index["chunks"]), 1)
            self.assertTrue(
                all(chunk["bytes"] <= 16 * 1024 for chunk in index["chunks"])
            )
            self.assertTrue(
                all(
                    (directory / chunk["file"]).stat().st_size <= 16 * 1024
                    for chunk in index["chunks"]
                )
            )
            self.assertTrue(all(chunk["sealed"] for chunk in index["chunks"][:-1]))
            self.assertFalse(index["chunks"][-1]["sealed"])
            for chunk in index["chunks"]:
                self.assertTrue(chunk["file"].startswith("chunk-"))
                text = (directory / chunk["file"]).read_text()
                self.assertTrue(text.endswith("\n"))
                self.assertTrue(text.startswith('{"operations":['))
                self.assertNotIn("\n  ", text)
                self.assertNotIn('"chunks":', text)

    def test_update_and_delete_append_ordered_operations(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            original = [record(i) for i in range(30)]
            self.update(directory, original)
            old = manifest(directory)
            old_sealed = [
                (chunk["id"], chunk["revision"], chunk["file"])
                for chunk in old["chunks"][:-1]
            ]

            changed = [record(i) for i in range(1, 30)]
            changed[4] = record(5, title="Updated title")
            changed.append(record(31))
            self.update(directory, changed)

            new = manifest(directory)
            self.assertEqual(
                new["sync_chunks"], [chunk["id"] for chunk in new["chunks"]]
            )
            self.assertEqual(
                old_sealed,
                [
                    (chunk["id"], chunk["revision"], chunk["file"])
                    for chunk in new["chunks"][: len(old_sealed)]
                ],
            )
            state, operations = materialize(directory)
            self.assertNotIn("item-0", state)
            self.assertEqual(state["item-5"]["title"], "Updated title")
            self.assertIn("item-31", state)
            tombstones = [
                operation for operation in operations if operation.get("_deleted")
            ]
            self.assertEqual(len(tombstones), 1)
            self.assertNotIn("_deleted", state["item-5"])
            changed_operations = operations[old["operation_count"] :]
            self.assertEqual(len(changed_operations), 3)
            self.assertEqual(new["revision"], old["revision"] + 1)
            self.assertTrue(
                all("_revision" not in operation for operation in operations)
            )
            self.assertEqual(
                [chunk["start"] for chunk in new["chunks"]],
                [
                    0,
                    *[
                        sum(item["operations"] for item in new["chunks"][:index])
                        for index in range(1, len(new["chunks"]))
                    ],
                ],
            )

    def test_check_is_read_only_and_compaction_changes_epoch(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            records = [record(i) for i in range(10)]
            self.update(directory, records)
            before = {path.name: path.read_bytes() for path in directory.iterdir()}
            self.assertFalse(self.update(directory, records, check=True))
            self.assertEqual(
                before,
                {path.name: path.read_bytes() for path in directory.iterdir()},
            )
            old_epoch = manifest(directory)["epoch"]
            self.update(directory, records, compact=True)
            index = manifest(directory)
            self.assertEqual(index["epoch"], old_epoch + 1)
            self.assertEqual(index["operation_count"], index["count"])

    def test_routes_are_metadata_only_and_payloads_are_indirect(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            self.update(
                directory,
                [record(1), record(2, title="Coroutine guide"), record(3, title="C")],
            )
            index = manifest(directory)
            self.assertTrue(index["routes"])
            self.assertTrue(all("data" not in route for route in index["routes"]))
            self.assertTrue(
                all(
                    {"id", "revision", "file", "first", "last"} <= route.keys()
                    for route in index["routes"]
                )
            )

            decoded = [
                term
                for route in index["routes"]
                for term in decode_route_terms(
                    logical_payload(directory, route)["data"]
                )
            ]
            self.assertIn("cmake", decoded)
            self.assertIn("coroutine", decoded)
            self.assertEqual(decoded.count("cmake"), 1)
            self.assertNotIn("c", decoded)
            self.assertLess((directory / "index.json").stat().st_size, 10 * 1024)

    def test_keyed_collection_uses_bounded_hash_buckets(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            records = [record(index) for index in range(80)]
            self.assertTrue(
                update_keyed_collection(
                    directory,
                    records,
                    collection="details",
                    bucket_count=16,
                )
            )
            index = manifest(directory)
            self.assertEqual(index["kind"], "keyed-records")
            self.assertEqual(index["count"], 80)
            self.assertLessEqual(len(index["buckets"]), 16)
            materialized = {}
            for bucket in index["buckets"]:
                payload = json.loads((directory / bucket["file"]).read_text())
                materialized.update(payload["records"])
            self.assertEqual(set(materialized), {item["id"] for item in records})
            self.assertTrue(all("id" not in item for item in materialized.values()))
            self.assertFalse(
                update_keyed_collection(
                    directory,
                    records,
                    collection="details",
                    bucket_count=16,
                    check=True,
                )
            )

    def test_keyed_collection_records_use_named_fields(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            records = [
                {"id": "first", "title": "First", "optional": None},
                {"id": "second", "values": [1, 2]},
            ]
            update_keyed_collection(
                directory,
                records,
                collection="details",
                bucket_count=2,
            )
            index = manifest(directory)
            decoded = {}
            for descriptor in index["buckets"]:
                payload = json.loads((directory / descriptor["file"]).read_text())
                decoded.update(payload["records"])
            self.assertNotIn("record_encoding", index)
            self.assertNotIn("record_fields", index)
            self.assertEqual(
                decoded,
                {
                    record["id"]: {
                        key: value for key, value in record.items() if key != "id"
                    }
                    for record in records
                },
            )

    def test_route_chunks_share_bounded_physical_payloads(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            records = [record(index, title=f"cterm{index:04d}") for index in range(80)]
            original_route = browser_data.TARGET_ROUTE_BYTES
            original_bundle = browser_data.TARGET_ROUTE_BUNDLE_BYTES
            try:
                browser_data.TARGET_ROUTE_BYTES = 120
                browser_data.TARGET_ROUTE_BUNDLE_BYTES = 700
                self.update(directory, records)
            finally:
                browser_data.TARGET_ROUTE_BYTES = original_route
                browser_data.TARGET_ROUTE_BUNDLE_BYTES = original_bundle

            index = manifest(directory)
            routes = index["routes"]
            self.assertGreater(len(routes), 2)
            self.assertEqual(
                [route["first"] for route in routes],
                sorted(route["first"] for route in routes),
            )
            self.assertTrue(all(route["first"] <= route["last"] for route in routes))
            route_files = [route["file"] for route in routes]
            self.assertLess(len(set(route_files)), len(route_files))
            self.assertTrue(all("data" not in route for route in routes))
            self.assertLess((directory / "index.json").stat().st_size, 10 * 1024)


if __name__ == "__main__":
    unittest.main()
