import tempfile
import unittest
from pathlib import Path

from meta_updater.shared.overrides import apply_metadata_overrides


class MetadataOverrideTests(unittest.TestCase):
    def test_corrections_and_hidden_items_are_applied(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "overrides.yaml"
            path.write_text(
                "items:\n"
                "  first:\n"
                "    title: Corrected\n"
                "    tags: [source-category]\n"
                "  second:\n"
                "    hidden: true\n",
                encoding="utf-8",
            )
            result = apply_metadata_overrides(
                [
                    {"id": "first", "title": "Wrong", "tags": []},
                    {"id": "second", "title": "Remove me", "tags": []},
                ],
                path,
                "items",
                id_field="id",
                allowed_fields={"title", "tags"},
            )
            self.assertEqual(
                result,
                [
                    {
                        "id": "first",
                        "title": "Corrected",
                        "tags": ["source-category"],
                        "hidden": False,
                    },
                    {
                        "id": "second",
                        "title": "Remove me",
                        "tags": [],
                        "hidden": True,
                    },
                ],
            )

    def test_unknown_ids_and_fields_are_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "overrides.yaml"
            path.write_text("items:\n  missing:\n    invented: value\n")
            with self.assertRaisesRegex(ValueError, "unsupported fields"):
                apply_metadata_overrides(
                    [{"id": "first"}],
                    path,
                    "items",
                    id_field="id",
                    allowed_fields={"title"},
                )


if __name__ == "__main__":
    unittest.main()
