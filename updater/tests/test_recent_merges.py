import tempfile
import unittest
from contextlib import redirect_stderr
from datetime import UTC, datetime
from io import StringIO
from pathlib import Path
from unittest.mock import patch
from urllib.error import HTTPError

from schemas.blogs import CachedBlogPost

from meta_updater.commands.blogs import merged as merged_posts
from meta_updater.commands.youtube import merged as merged_videos
from meta_updater.shared.blogs import post_id
from meta_updater.shared.recent import RecentCache, prune_records
from meta_updater.youtube import channel_videos


class RecentMergeTests(unittest.TestCase):
    def test_prune_records_preserves_hidden_stubs_and_applies_visible_limit(
        self,
    ) -> None:
        old = {
            "video_id": "old",
            "published": datetime(2025, 1, 1, tzinfo=UTC),
        }
        new = {
            "video_id": "new",
            "published": datetime(2026, 1, 1, tzinfo=UTC),
        }
        hidden = {"video_id": "hidden", "hidden": True}

        self.assertEqual(
            prune_records(
                [new, old, hidden],
                cutoff=datetime(2025, 6, 1, tzinfo=UTC),
                limit=1,
            ),
            [hidden, new],
        )

    def test_prune_records_keeps_source_order_without_a_limit(self) -> None:
        hidden = {"video_id": "hidden", "hidden": True}
        visible = {
            "video_id": "visible",
            "published": datetime(2026, 1, 1, tzinfo=UTC),
        }
        self.assertEqual(prune_records([visible, hidden]), [visible, hidden])

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
        self.assertEqual(fetch.call_count, 3)

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

        records = merged_posts([old, old], [first, latest])

        self.assertEqual(len(records), 2)
        self.assertEqual([item["title"] for item in records], ["Latest version", "Old"])

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

        records = merged_videos([old, old], [first, latest])

        self.assertEqual(len(records), 2)
        self.assertEqual([item["title"] for item in records], ["Latest version", "Old"])

    def test_recent_feed_text_is_unicode_sanitized(self) -> None:
        published = datetime(2026, 1, 1, tzinfo=UTC)
        posts = merged_posts(
            [],
            [
                {
                    "source_id": "blog",
                    "source_title": "Blog\u200b",
                    "title": "Caf\u0065\u0301\ufffd",
                    "description": "Useful\u200b text",
                    "url": "https://example.test/post",
                    "published": published,
                    "tags": ["C++\u200b"],
                }
            ],
        )
        videos = merged_videos(
            [],
            [
                {
                    "video_id": "video",
                    "title": "Caf\u0065\u0301\ufffd",
                    "description": "Useful\u200b text",
                    "url": "https://youtu.be/video",
                    "published": published,
                    "tags": ["C++\u200b"],
                }
            ],
        )
        self.assertEqual(posts[0]["title"], "Café")
        self.assertEqual(posts[0]["description"], "Useful text")
        self.assertEqual(posts[0]["tags"], ["C++"])
        self.assertEqual(videos[0]["title"], "Café")
        self.assertEqual(videos[0]["description"], "Useful text")
        self.assertEqual(videos[0]["tags"], ["C++"])

    def test_hidden_blog_stub_is_not_readded_or_expanded(self) -> None:
        url = "https://example.test/hidden"
        hidden = {"post_id": post_id("blog", url), "hidden": True}
        fetched = {
            "source_id": "blog",
            "source_title": "Blog",
            "title": "Fetched",
            "url": url,
            "published": datetime(2026, 1, 1, tzinfo=UTC),
            "tags": [],
        }
        records = merged_posts([hidden], [fetched])
        self.assertEqual(records, [hidden])

    def test_hidden_video_stub_is_not_readded_or_expanded(self) -> None:
        hidden = {"video_id": "hidden", "hidden": True}
        fetched = {
            "video_id": "hidden",
            "title": "Fetched",
            "url": "https://youtu.be/hidden",
            "published": datetime(2026, 1, 1, tzinfo=UTC),
        }
        records = merged_videos([hidden], [fetched])
        self.assertEqual(records, [hidden])

    def test_refresh_preserves_inline_blog_relevance(self) -> None:
        current = {
            "source_id": "blog",
            "source_title": "Blog",
            "title": "Manually retained title",
            "url": "https://example.test/existing",
            "published": datetime(2026, 1, 1, tzinfo=UTC),
            "tags": [],
            "cpp_relevance": 0.0,
        }
        fetched = {**current, "title": "Fetched replacement"}
        fetched.pop("cpp_relevance")

        with tempfile.TemporaryDirectory() as temporary:
            cache = RecentCache(
                Path(temporary),
                CachedBlogPost,
                id_field="post_id",
                producer="test",
            )
            current["post_id"] = post_id(current["source_id"], current["url"])
            cache.update("blog", [current])
            records = merged_posts(cache.load("blog"), [fetched])
            cache.update("blog", records)

            self.assertEqual(cache.load("blog")[0]["cpp_relevance"], 0.0)

    def test_refresh_does_not_replace_an_existing_recent_entry(self) -> None:
        current = {
            "video_id": "existing",
            "title": "Manually retained title",
            "url": "https://youtu.be/existing",
            "published": datetime(2026, 1, 1, tzinfo=UTC),
        }
        fetched = {**current, "title": "Fetched replacement"}
        records = merged_videos([current], [fetched])
        self.assertEqual(records[0]["title"], "Manually retained title")


if __name__ == "__main__":
    unittest.main()
