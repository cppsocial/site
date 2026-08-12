import unittest

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
