import tempfile
import unittest
from pathlib import Path

from meta_updater.shared.files import update_bytes
from meta_updater.shared.runtime import selected


class RecordSelectionTests(unittest.TestCase):
    def test_atomic_update_detects_changes_and_honors_check_mode(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "nested" / "data.bin"

            self.assertTrue(update_bytes(path, b"first", check=True))
            self.assertFalse(path.exists())
            self.assertTrue(update_bytes(path, b"first"))
            self.assertFalse(update_bytes(path, b"first"))
            self.assertEqual(path.read_bytes(), b"first")

    def test_no_ids_selects_every_record_in_source_order(self) -> None:
        values = [{"id": "first"}, {"id": "second"}]

        self.assertEqual(selected(values, None, lambda item: item["id"], "ID"), values)

    def test_requested_ids_are_selected_in_source_order(self) -> None:
        values = [{"id": "first"}, {"id": "second"}, {"id": "third"}]

        self.assertEqual(
            selected(values, ["third", "first"], lambda item: item["id"], "ID"),
            [values[0], values[2]],
        )

    def test_unknown_ids_are_rejected(self) -> None:
        with self.assertRaisesRegex(ValueError, "unknown channel ID: missing"):
            selected(
                [{"id": "known"}],
                ["missing"],
                lambda item: item["id"],
                "channel ID",
            )


if __name__ == "__main__":
    unittest.main()
