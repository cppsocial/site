import tempfile
import unittest
from argparse import Namespace
from pathlib import Path
from unittest.mock import patch

import yaml

from meta_updater.commands.books import run as run_books
from meta_updater.commands.communities import run as run_communities
from meta_updater.config import MetaUpdaterConfig


class TargetedUpdateTests(unittest.TestCase):
    def config(self, root: Path) -> MetaUpdaterConfig:
        return MetaUpdaterConfig(
            content=root / "content", data=root / "data", delay=0
        )

    @patch("meta_updater.commands.books.metadata")
    def test_book_update_preserves_unselected_metadata(self, metadata) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            content = root / "content" / "books"
            data = root / "data" / "books"
            content.mkdir(parents=True)
            data.mkdir(parents=True)
            content.joinpath("books.yaml").write_text(
                """cards:
- {isbn: '9780321563842'}
- {isbn: '9781491903995'}
""",
                encoding="utf-8",
            )
            data.joinpath("metadata.yaml").write_text(
                """'9780321563842':
  title: Old selected title
  isbn_13: '9780321563842'
  url: https://example.test/selected
'9781491903995':
  title: Unselected title
  isbn_13: '9781491903995'
  url: https://example.test/unselected
""",
                encoding="utf-8",
            )
            metadata.return_value = {
                "title": "New selected title",
                "isbn_13": "9780321563842",
                "url": "https://example.test/selected",
            }

            result = run_books(
                Namespace(
                    timeout=None,
                    delay=0,
                    check=False,
                    ids=["9780321563842"],
                ),
                self.config(root),
            )

            values = yaml.safe_load(data.joinpath("metadata.yaml").read_text())
            self.assertEqual(result, 0)
            self.assertEqual(values["9780321563842"]["title"], "New selected title")
            self.assertEqual(values["9781491903995"]["title"], "Unselected title")

    @patch("meta_updater.commands.communities.metadata")
    def test_community_update_preserves_unselected_metadata(self, metadata) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            content = root / "content" / "communities"
            data = root / "data" / "communities"
            content.mkdir(parents=True)
            data.mkdir(parents=True)
            content.joinpath("im.yaml").write_text(
                """cards:
- community_id: selected
  title: Selected
  metadata_source: {source: web, key: 'https://example.test/selected'}
- community_id: unselected
  title: Unselected
  metadata_source: {source: web, key: 'https://example.test/unselected'}
""",
                encoding="utf-8",
            )
            data.joinpath("metadata.yaml").write_text(
                """selected: {description: Old selected}
unselected: {description: Keep this}
""",
                encoding="utf-8",
            )
            metadata.return_value = {"description": "New selected"}

            result = run_communities(
                Namespace(
                    timeout=None,
                    delay=0,
                    check=False,
                    ids=["selected"],
                ),
                self.config(root),
            )

            values = yaml.safe_load(data.joinpath("metadata.yaml").read_text())
            self.assertEqual(result, 0)
            self.assertEqual(values["selected"]["description"], "New selected")
            self.assertEqual(values["unselected"]["description"], "Keep this")

    @patch("meta_updater.commands.communities.metadata")
    def test_community_failure_preserves_last_good_metadata(self, metadata) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            content = root / "content" / "communities"
            data = root / "data" / "communities"
            content.mkdir(parents=True)
            data.mkdir(parents=True)
            content.joinpath("chat.yaml").write_text(
                """cards:
- community_id: reddit-cpp
  title: Reddit C++
  metadata_source: {source: reddit, key: cpp}
""",
                encoding="utf-8",
            )
            data.joinpath("metadata.yaml").write_text(
                """reddit-cpp:
  description: Last good description
  source_url: https://www.reddit.com/r/cpp/
""",
                encoding="utf-8",
            )
            metadata.side_effect = ValueError(
                "could not solve Reddit verification for r/cpp"
            )

            result = run_communities(
                Namespace(timeout=None, delay=0, check=False, ids=None),
                self.config(root),
            )

            values = yaml.safe_load(data.joinpath("metadata.yaml").read_text())
            self.assertEqual(result, 0)
            self.assertEqual(
                values["reddit-cpp"]["description"], "Last good description"
            )


if __name__ == "__main__":
    unittest.main()
