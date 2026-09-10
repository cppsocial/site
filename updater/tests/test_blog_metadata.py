import unittest
from argparse import Namespace
from contextlib import redirect_stderr
from io import StringIO
from unittest.mock import Mock, patch

from meta_updater.commands.blogs import refresh
from meta_updater.shared.images import image_url, page_avatar


class BlogMetadataTests(unittest.TestCase):
    def test_root_page_is_not_treated_as_an_image(self) -> None:
        self.assertEqual(image_url("https://example.com/forum/", "/"), "")

    def test_relative_image_url_is_resolved(self) -> None:
        self.assertEqual(
            image_url("https://example.com/forum/", "/logo.svg"),
            "https://example.com/logo.svg",
        )

    def test_avatar_outside_header_beats_broken_theme_icons(self) -> None:
        page = """
        <html>
          <head>
            <link rel="apple-touch-icon" sizes="180x180"
                  href="/assets/missing-180.png">
          </head>
          <body>
            <aside><img src="/assets/author.jpg" alt="avatar"></aside>
          </body>
        </html>
        """
        self.assertEqual(
            page_avatar(page, "https://example.com/"),
            "https://example.com/assets/author.jpg",
        )

    def test_unlabelled_content_image_does_not_replace_favicon(self) -> None:
        page = """
        <img src="/posts/screenshot.png" alt="Example output">
        <link rel="icon" href="/favicon.png">
        """
        self.assertEqual(
            page_avatar(page, "https://example.com/blog/"),
            "https://example.com/favicon.png",
        )


class BlogRefreshFailureTests(unittest.TestCase):
    def source(self, source_id: str) -> dict:
        return {
            "id": source_id,
            "title": source_id.title(),
            "website_url": f"https://{source_id}.example/",
            "rss_url": f"https://{source_id}.example/feed.xml",
            "hidden": False,
            "exclude_tags": [],
        }

    @patch("meta_updater.commands.blogs.metadata")
    def test_metadata_failure_logs_context_and_continues(self, metadata: Mock) -> None:
        metadata.side_effect = [OSError("connection failed"), {"description": "ok"}]
        dataset = Mock()
        dataset.load.return_value = {"first": {"description": "cached"}}
        stderr = StringIO()

        with redirect_stderr(stderr):
            refresh(
                Namespace(command="metadata", check=False),
                [self.source("first"), self.source("second")],
                dataset,
                Mock(),
                1,
                0,
            )

        dataset.update.assert_called_once_with(
            {
                "first": {"description": "cached"},
                "second": {"description": "ok"},
            },
            False,
        )
        message = stderr.getvalue()
        self.assertIn("blog metadata failed", message)
        self.assertIn("source_id='first'", message)
        self.assertIn("url='https://first.example/'", message)
        self.assertIn("OSError: connection failed", message)

    @patch("meta_updater.commands.blogs.merged", return_value=[])
    @patch("meta_updater.commands.blogs.posts")
    def test_feed_failure_logs_url_and_continues(
        self, posts: Mock, merged: Mock
    ) -> None:
        successful_post = {"post_id": "post"}
        posts.side_effect = [ValueError("bad feed"), [successful_post]]
        post_data = Mock()
        post_data.load.return_value = []
        post_data.update.return_value = False
        stderr = StringIO()

        with redirect_stderr(stderr):
            refresh(
                Namespace(command="posts", check=False),
                [self.source("first"), self.source("second")],
                Mock(),
                post_data,
                1,
                0,
            )

        merged.assert_called_once_with(
            [],
            [successful_post],
        )
        message = stderr.getvalue()
        self.assertIn("blog posts failed", message)
        self.assertIn("source_title='First'", message)
        self.assertIn("url='https://first.example/feed.xml'", message)
        self.assertIn("ValueError: bad feed", message)
