import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from scripts.update_preview_metadata import targeted_commands


class PreviewMetadataTests(unittest.TestCase):
    def test_targets_only_added_or_changed_records(self) -> None:
        current = """\
- id: unchanged
  title: Same
- id: changed
  title: New title
- id: added
  title: Added
"""
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "content/blogs/sources.yaml"
            path.parent.mkdir(parents=True)
            path.write_text(current, encoding="utf-8")
            with patch("scripts.update_preview_metadata.TARGETS", {
                path: ("id", ("blogs", "all"))
            }), patch(
                "scripts.update_preview_metadata._previous",
                return_value={
                    "unchanged": {"id": "unchanged", "title": "Same"},
                    "changed": {"id": "changed", "title": "Old title"},
                    "removed": {"id": "removed", "title": "Removed"},
                },
            ):
                commands = targeted_commands("base", {path})

        self.assertEqual(
            commands,
            [
                ["meta-updater", "blogs", "all", "--id", "added"],
                ["meta-updater", "blogs", "all", "--id", "changed"],
            ],
        )

    def test_runs_only_whole_dataset_updates_that_were_touched(self) -> None:
        commands = targeted_commands(
            "base",
            {
                Path("content/events/meetups.yaml"),
                Path("content/events/events.yaml"),
                Path("data/packages/overrides.yaml"),
            },
        )

        self.assertEqual(
            commands,
            [
                ["meta-updater", "events"],
                ["meta-updater", "packages", "publish"],
            ],
        )


if __name__ == "__main__":
    unittest.main()
