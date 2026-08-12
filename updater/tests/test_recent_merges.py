import tempfile
import unittest
from contextlib import redirect_stderr
from io import StringIO
from urllib.error import HTTPError
from unittest.mock import patch
from datetime import UTC, datetime
from pathlib import Path

from meta_updater.commands.blogs import merged as merged_posts
from meta_updater.commands.youtube import merged as merged_videos
from meta_updater.youtube import channel_videos


class RecentMergeTests(unittest.TestCase):
    @patch(
        "meta_updater.youtube.fetch",
        side_effect=HTTPError("url", 404, "missing", {}, None),
    )
    def test_youtube_404_feed_is_an_empty_channel(self, fetch):
        output = StringIO()
        with redirect_stderr(output):
            self.assertEqual(channel_videos("channel", 30), [])
        self.assertIn(
            "https://www.youtube.com/feeds/videos.xml?channel_id=channel",
            output.getvalue(),
        )
        fetch.assert_called_once()

    def test_blog_refresh_retains_old_posts_and_deduplicates_updates(self) -> None:
        old = {
            "source_id": "blog",
            "source_title": "Blog",
            "title": "Old",
            "url": "https://example.test/old",
            "published": datetime(2026, 1, 1, tzinfo=UTC),
            "tags": [],
        }
        first = {
            **old,
            "title": "First version",
            "url": "https://example.test/new",
            "published": datetime(2026, 2, 1, tzinfo=UTC),
        }
        latest = {**first, "title": "Latest version"}

        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            records = merged_posts(
                [old, old],
                [first, latest],
                root / "labels.yaml",
                root / "overrides.yaml",
            )

        self.assertEqual(len(records), 2)
        self.assertEqual(
            [item["title"] for item in records], ["Latest version", "Old"]
        )

    def test_youtube_refresh_retains_old_videos_and_deduplicates_updates(self) -> None:
        old = {
            "video_id": "old",
            "title": "Old",
            "url": "https://youtu.be/old",
            "published": datetime(2026, 1, 1, tzinfo=UTC),
        }
        first = {
            "video_id": "new",
            "title": "First version",
            "url": "https://youtu.be/new",
            "published": datetime(2026, 2, 1, tzinfo=UTC),
        }
        latest = {**first, "title": "Latest version"}

        with tempfile.TemporaryDirectory() as temporary:
            records = merged_videos(
                [old, old],
                [first, latest],
                Path(temporary) / "labels.yaml",
            )

        self.assertEqual(len(records), 2)
        self.assertEqual(
            [item["title"] for item in records], ["Latest version", "Old"]
        )


if __name__ == "__main__":
    unittest.main()
