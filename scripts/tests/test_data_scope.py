import unittest
from pathlib import Path

from scripts.check_data_scope import unrelated_generated_data


class DataScopeTests(unittest.TestCase):
    def test_reports_data_from_unrelated_families(self) -> None:
        paths = {
            Path("content/books/books.yaml"),
            Path("data/books/metadata.yaml"),
            Path("data/youtube/videos/example.yaml"),
            Path("data/events-imported.yaml"),
        }

        self.assertEqual(
            unrelated_generated_data(paths),
            [
                Path("data/events-imported.yaml"),
                Path("data/youtube/videos/example.yaml"),
            ],
        )

    def test_allows_data_from_each_changed_content_family(self) -> None:
        paths = {
            Path("content/events/meetups.yaml"),
            Path("data/events-imported.yaml"),
            Path("data/events/metadata.yaml"),
        }

        self.assertEqual(unrelated_generated_data(paths), [])

    def test_ignores_data_only_changes(self) -> None:
        paths = {Path("data/books/metadata.yaml")}

        self.assertEqual(unrelated_generated_data(paths), [])


if __name__ == "__main__":
    unittest.main()
