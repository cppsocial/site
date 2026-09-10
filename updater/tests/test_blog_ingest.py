import gzip
import unittest
from argparse import Namespace
from datetime import UTC, datetime
from unittest.mock import Mock, call, patch

from meta_updater.commands.blogs import ingest, run
from meta_updater.config import MetaUpdaterConfig
from meta_updater.shared.blogs import (
    feed_posts_and_cms,
    matches_post_url_family,
    post_url_family,
    sitemap_discovery,
    sitemap_entries,
    sitemap_post,
)


class SitemapDiscoveryTests(unittest.TestCase):
    def source(self, **values) -> dict:
        return {
            "id": "example",
            "title": "Example Blog",
            "website_url": "https://example.test/blog/",
            "rss_url": "https://example.test/feed.xml",
            **values,
        }

    @patch("meta_updater.shared.blogs.fetch")
    def test_robots_sitemap_and_nested_indexes_are_followed(self, fetch: Mock) -> None:
        documents = {
            "https://example.test/robots.txt": b"Sitemap: /maps/index.xml\n",
            "https://example.test/maps/index.xml": b"""
                <sitemapindex xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
                  <sitemap><loc>posts.xml.gz</loc></sitemap>
                </sitemapindex>
            """,
            "https://example.test/maps/posts.xml.gz": gzip.compress(b"""
                <urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
                  <url><loc>https://example.test/blog/first</loc>
                    <lastmod>2025-02-03</lastmod></url>
                </urlset>
            """),
        }
        fetch.side_effect = lambda url, *_: documents[url]

        entries = sitemap_entries(self.source(), 1)

        self.assertEqual(
            entries,
            [{"loc": "https://example.test/blog/first", "lastmod": "2025-02-03"}],
        )

    @patch("meta_updater.shared.blogs.fetch")
    def test_override_is_used_without_fetching_robots_or_default(self, fetch: Mock) -> None:
        fetch.return_value = b"""
            <urlset><url><loc>post/one</loc></url></urlset>
        """

        entries = sitemap_entries(self.source(sitemap_url="archive/map.xml"), 1)

        self.assertEqual(
            entries, [{"loc": "https://example.test/blog/archive/post/one"}])
        fetch.assert_called_once_with(
            "https://example.test/blog/archive/map.xml", 1, unittest.mock.ANY
        )

    @patch("meta_updater.shared.blogs.fetch")
    def test_conventional_sitemap_is_guessed_when_robots_is_missing(
        self, fetch: Mock
    ) -> None:
        def response(url, *_):
            if url.endswith("robots.txt"):
                raise OSError("no robots file")
            return b"<urlset><url><loc>/blog/post</loc></url></urlset>"

        fetch.side_effect = response

        entries = sitemap_entries(self.source(), 1)

        self.assertEqual(entries, [{"loc": "https://example.test/blog/post"}])
        self.assertEqual(fetch.call_args_list[1][0]
                         [0], "https://example.test/sitemap.xml")

    @patch("meta_updater.shared.blogs.fetch")
    def test_wordpress_detection_enables_core_sitemap_fallback(
        self, fetch: Mock
    ) -> None:
        def response(url, *_):
            if url.endswith("robots.txt"):
                raise OSError("no robots file")
            if url.endswith("wp-sitemap.xml"):
                return b"<urlset><url><loc>/blog/post</loc></url></urlset>"
            raise AssertionError(f"unexpected fallback: {url}")

        fetch.side_effect = response

        entries = sitemap_entries(self.source(), 1, cms="wordpress")

        self.assertEqual(entries, [{"loc": "https://example.test/blog/post"}])
        self.assertEqual(
            [item.args[0] for item in fetch.call_args_list],
            [
                "https://example.test/robots.txt",
                "https://example.test/wp-sitemap.xml",
            ],
        )

    @patch("meta_updater.shared.blogs.fetch")
    def test_non_blog_and_non_html_urls_are_filtered_before_ingest(
        self, fetch: Mock
    ) -> None:
        fetch.return_value = b"""
            <urlset>
              <url><loc>https://example.test/blog/2025/useful-post</loc></url>
              <url><loc>https://example.test/blog/about</loc></url>
              <url><loc>https://example.test/blog/tag/cpp</loc></url>
              <url><loc>https://example.test/blog/assets/banner.png</loc></url>
              <url><loc>https://example.test/products/compiler</loc></url>
              <url><loc>https://cdn.example.test/blog/mirror</loc></url>
              <url><loc>mailto:author@example.test</loc></url>
            </urlset>
        """

        entries = sitemap_entries(
            self.source(sitemap_url="https://example.test/map.xml"), 1
        )

        self.assertEqual(
            entries,
            [{"loc": "https://example.test/blog/2025/useful-post"}],
        )

    @patch("meta_updater.shared.blogs.fetch")
    def test_www_alias_and_html_suffix_are_allowed(self, fetch: Mock) -> None:
        fetch.return_value = b"""
            <urlset>
              <url><loc>https://www.example.test/blog/post.html</loc></url>
            </urlset>
        """

        entries = sitemap_entries(
            self.source(sitemap_url="https://example.test/map.xml"), 1
        )

        self.assertEqual(
            entries,
            [{"loc": "https://www.example.test/blog/post.html"}],
        )

    @patch("meta_updater.shared.blogs.fetch")
    def test_cms_index_fetches_only_post_sitemaps_when_available(
        self, fetch: Mock
    ) -> None:
        documents = {
            "https://example.test/blog/map.xml": b"""
                <sitemapindex>
                  <sitemap><loc>wp-sitemap-posts-page-1.xml</loc></sitemap>
                  <sitemap><loc>wp-sitemap-posts-attachment-1.xml</loc></sitemap>
                  <sitemap><loc>wp-sitemap-posts-post-1.xml</loc></sitemap>
                  <sitemap><loc>wp-sitemap-taxonomies-category-1.xml</loc></sitemap>
                </sitemapindex>
            """,
            "https://example.test/blog/wp-sitemap-posts-post-1.xml": b"""
                <urlset><url><loc>/blog/real-post</loc></url></urlset>
            """,
        }
        fetch.side_effect = lambda url, *_: documents[url]

        entries = sitemap_entries(self.source(sitemap_url="map.xml"), 1)

        self.assertEqual(
            entries,
            [{"loc": "https://example.test/blog/real-post"}],
        )
        self.assertEqual(
            [item.args[0] for item in fetch.call_args_list],
            [
                "https://example.test/blog/map.xml",
                "https://example.test/blog/wp-sitemap-posts-post-1.xml",
            ],
        )

    @patch("meta_updater.shared.blogs.fetch")
    def test_chirpy_filter_preserves_custom_post_permalinks(self, fetch: Mock) -> None:
        fetch.return_value = b"""
            <urlset>
              <url><loc>https://example.test/blog/posts/real-post/</loc></url>
              <url><loc>https://example.test/blog/c++/2025/01/02/dated/</loc></url>
              <url><loc>https://example.test/blog/custom-permalink</loc></url>
              <url><loc>https://example.test/blog/custom-post.html</loc></url>
              <url><loc>https://example.test/blog/categories/</loc></url>
              <url><loc>https://example.test/blog/categories/cpp/</loc></url>
              <url><loc>https://example.test/blog/tags/</loc></url>
              <url><loc>https://example.test/blog/tags/templates/</loc></url>
              <url><loc>https://example.test/blog/archives/</loc></url>
              <url><loc>https://example.test/blog/page2/</loc></url>
              <url><loc>https://example.test/blog/page/3/</loc></url>
              <url><loc>https://example.test/blog/downloads/example</loc></url>
            </urlset>
        """

        entries, listings = sitemap_discovery(
            self.source(sitemap_url="sitemap.xml"), 1
        )

        self.assertEqual(
            entries,
            [
                {"loc": "https://example.test/blog/posts/real-post/"},
                {"loc": "https://example.test/blog/c++/2025/01/02/dated/"},
                {"loc": "https://example.test/blog/custom-permalink"},
                {"loc": "https://example.test/blog/custom-post.html"},
            ],
        )
        self.assertEqual(
            listings,
            [
                "https://example.test/blog/archives/",
                "https://example.test/blog/page2/",
                "https://example.test/blog/page/3/",
            ],
        )


class SitemapMetadataTests(unittest.TestCase):
    def test_feed_urls_can_teach_a_dated_custom_post_family(self) -> None:
        source = {
            "website_url": "https://example.test/",
        }
        family = post_url_family(
            source,
            [
                "https://example.test/c++/2025/01/02/first/",
                "https://example.test/c++/2026/03/04/second/",
            ],
        )

        self.assertEqual(family, ("c++", "{year}", "{month}", "{day}", "*"))
        assert family is not None
        self.assertTrue(
            matches_post_url_family(
                source, "https://example.test/c++/2017/12/31/old-post/", family
            )
        )
        self.assertFalse(
            matches_post_url_family(
                source, "https://example.test/for-hannah.html", family
            )
        )

    @patch("meta_updater.shared.blogs.fetch")
    def test_feed_supplies_posts_and_detects_jekyll(self, fetch: Mock) -> None:
        fetch.return_value = b"""
            <feed xmlns="http://www.w3.org/2005/Atom">
              <generator uri="https://jekyllrb.com/">Jekyll</generator>
              <entry>
                <title>Custom route</title>
                <link rel="alternate" href="https://example.test/custom" />
                <published>2025-01-02T03:04:05Z</published>
              </entry>
            </feed>
        """
        source = {
            "id": "example",
            "title": "Example Blog",
            "rss_url": "https://example.test/feed.xml",
        }

        found, cms = feed_posts_and_cms(source, 1)

        self.assertEqual(cms, "jekyll")
        self.assertEqual([item["url"] for item in found],
                         ["https://example.test/custom"])

    def test_json_ld_and_open_graph_create_complete_post(self) -> None:
        page = b"""
            <html><head>
              <meta property="og:title" content="Using C++ &amp; friends">
              <meta property="og:description" content="A useful article">
              <meta property="article:tag" content="C++">
              <meta property="article:tag" content="Templates">
              <link rel="canonical" href="/canonical-post">
              <script type="application/ld+json">
                {"@type":"BlogPosting", "datePublished":"2024-01-02T03:04:05Z",
                 "dateModified":"2024-02-03T04:05:06Z", "keywords":["C++", "Library"]}
              </script>
            </head></html>
        """
        source = {"id": "example", "title": "Example Blog"}

        post = sitemap_post(
            source,
            {"loc": "https://example.test/original", "lastmod": "2025-01-01"},
            page,
        )

        self.assertIsNotNone(post)
        assert post is not None
        self.assertEqual(post["title"], "Using C++ & friends")
        self.assertEqual(post["url"], "https://example.test/canonical-post")
        self.assertEqual(post["published"], datetime(2024, 1, 2, 3, 4, 5, tzinfo=UTC))
        self.assertEqual(post["updated"], datetime(2024, 2, 3, 4, 5, 6, tzinfo=UTC))
        self.assertEqual(post["tags"], ["C++", "Templates", "Library"])

    def test_lastmod_alone_does_not_turn_a_page_into_a_post(self) -> None:
        post = sitemap_post(
            {"id": "example", "title": "Example Blog"},
            {"loc": "https://example.test/about", "lastmod": "2025-01-01"},
            b"<html><title>About</title></html>",
        )

        self.assertIsNone(post)


class ManualIngestTests(unittest.TestCase):
    def test_ingest_requires_exactly_one_blog_id(self) -> None:
        config = MetaUpdaterConfig()
        for ids in (None, [], ["first", "second"]):
            with self.subTest(ids=ids), self.assertRaisesRegex(
                ValueError, "requires exactly one --id"
            ):
                run(
                    Namespace(
                        command="ingest",
                        ids=ids,
                        timeout=None,
                        delay=0,
                        check=False,
                    ),
                    config,
                )

    @patch("meta_updater.commands.blogs.time.sleep")
    @patch("meta_updater.commands.blogs.sitemap_post")
    @patch("meta_updater.commands.blogs.fetch")
    @patch("meta_updater.commands.blogs.sitemap_discovery")
    @patch("meta_updater.commands.blogs.feed_posts_and_cms")
    def test_ingest_fetches_and_merges_only_selected_source(
        self,
        feed: Mock,
        discovery: Mock,
        fetch: Mock,
        make_post: Mock,
        sleep: Mock,
    ) -> None:
        feed.return_value = ([], "jekyll")
        discovery.return_value = (
            [
                {"loc": "https://example.test/one"},
                {"loc": "https://example.test/two"},
            ],
            [],
        )
        fetch.side_effect = [b"one", b"two"]
        make_post.side_effect = [
            {
                "post_id": "one",
                "source_id": "example",
                "source_title": "Example",
                "title": "One",
                "url": "https://example.test/one",
                "published": datetime(2024, 1, 1, tzinfo=UTC),
                "tags": [],
            },
            None,
        ]
        post_data = Mock()
        post_data.load.return_value = []
        post_data.update.return_value = True
        source = {
            "id": "example",
            "title": "Example",
            "exclude_tags": [],
        }

        changed = ingest(
            Namespace(check=False), source, [source], post_data, 2, 0.1
        )

        self.assertTrue(changed)
        discovery.assert_called_once_with(source, 2, cms="jekyll")
        self.assertEqual(
            fetch.call_args_list,
            [
                call("https://example.test/one", 2, unittest.mock.ANY),
                call("https://example.test/two", 2, unittest.mock.ANY),
            ],
        )
        sleep.assert_called_once_with(0.1)
        post_data.update.assert_called_once()

    @patch("meta_updater.commands.blogs.time.sleep")
    @patch("meta_updater.commands.blogs.sitemap_post")
    @patch("meta_updater.commands.blogs.fetch")
    @patch("meta_updater.commands.blogs.sitemap_discovery")
    @patch("meta_updater.commands.blogs.feed_posts_and_cms")
    def test_ingest_does_not_refetch_feed_or_cached_urls(
        self,
        feed: Mock,
        discovery: Mock,
        fetch: Mock,
        make_post: Mock,
        sleep: Mock,
    ) -> None:
        feed.return_value = (
            [
                {
                    "post_id": "feed",
                    "source_id": "example",
                    "source_title": "Example",
                    "title": "From feed",
                    "url": "https://example.test/feed-post/",
                    "published": datetime(2025, 1, 1, tzinfo=UTC),
                    "tags": [],
                }
            ],
            "jekyll",
        )
        discovery.return_value = (
            [
                {"loc": "https://example.test/feed-post"},
                {"loc": "https://example.test/cached-post/"},
                {"loc": "https://example.test/archive-post"},
            ],
            [],
        )
        fetch.return_value = b"archive"
        make_post.return_value = {
            "post_id": "archive",
            "source_id": "example",
            "source_title": "Example",
            "title": "From archive",
            "url": "https://example.test/archive-post",
            "published": datetime(2020, 1, 1, tzinfo=UTC),
            "tags": [],
        }
        post_data = Mock()
        post_data.load.return_value = [
            {
                "post_id": "cached",
                "source_id": "example",
                "source_title": "Example",
                "title": "Cached",
                "url": "https://example.test/cached-post",
                "published": datetime(2024, 1, 1, tzinfo=UTC),
                "tags": [],
            }
        ]
        post_data.update.return_value = True
        source = {
            "id": "example",
            "title": "Example",
            "rss_url": "https://example.test/feed.xml",
            "website_url": "https://example.test/",
            "exclude_tags": [],
        }

        changed = ingest(
            Namespace(check=False), source, [source], post_data, 2, 0.1
        )

        self.assertTrue(changed)
        fetch.assert_called_once_with(
            "https://example.test/archive-post", 2, unittest.mock.ANY
        )
        sleep.assert_not_called()
        saved = post_data.update.call_args.args[1]
        self.assertEqual(
            {item["url"] for item in saved},
            {
                "https://example.test/feed-post/",
                "https://example.test/cached-post",
                "https://example.test/archive-post",
            },
        )

    @patch("meta_updater.commands.blogs.time.sleep")
    @patch("meta_updater.commands.blogs.sitemap_post")
    @patch("meta_updater.commands.blogs.fetch")
    @patch("meta_updater.commands.blogs.sitemap_discovery")
    @patch("meta_updater.commands.blogs.feed_posts_and_cms")
    def test_ingest_correlates_sitemap_urls_with_archive_links(
        self,
        feed: Mock,
        discovery: Mock,
        fetch: Mock,
        make_post: Mock,
        sleep: Mock,
    ) -> None:
        feed.return_value = (
            [
                {
                    "post_id": "recent-one",
                    "source_id": "example",
                    "source_title": "Example",
                    "title": "Recent one",
                    "url": "https://example.test/c++/2025/01/02/recent-one/",
                    "published": datetime(2025, 1, 2, tzinfo=UTC),
                    "tags": [],
                },
                {
                    "post_id": "recent-two",
                    "source_id": "example",
                    "source_title": "Example",
                    "title": "Recent two",
                    "url": "https://example.test/c++/2026/03/04/recent-two/",
                    "published": datetime(2026, 3, 4, tzinfo=UTC),
                    "tags": [],
                },
            ],
            "jekyll",
        )
        discovery.return_value = (
            [
                {"loc": "https://example.test/c++/2017/02/10/old-post/"},
                {"loc": "https://example.test/for-hannah.html"},
                {"loc": "https://example.test/iterator-abstraction"},
                {"loc": "https://example.test/consteval-propagation"},
            ],
            ["https://example.test/archives/"],
        )
        fetch.side_effect = [
            b"""
                <main id="archives">
                  <a href="/c++/2017/02/10/old-post/">Old post</a>
                  <a href="/for-hannah.html">Personal post</a>
                </main>
            """,
            b"old post",
        ]
        make_post.return_value = {
            "post_id": "old",
            "source_id": "example",
            "source_title": "Example",
            "title": "Old post",
            "url": "https://example.test/c++/2017/02/10/old-post/",
            "published": datetime(2017, 2, 10, tzinfo=UTC),
            "tags": [],
        }
        post_data = Mock()
        post_data.load.return_value = []
        post_data.update.return_value = True
        source = {
            "id": "example",
            "title": "Example",
            "rss_url": "https://example.test/feed.xml",
            "website_url": "https://example.test/",
            "exclude_tags": [],
        }

        changed = ingest(
            Namespace(check=False), source, [source], post_data, 2, 0.1
        )

        self.assertTrue(changed)
        self.assertEqual(
            [item.args[0] for item in fetch.call_args_list],
            [
                "https://example.test/archives/",
                "https://example.test/c++/2017/02/10/old-post/",
            ],
        )
        self.assertTrue(
            {
                "https://example.test/for-hannah.html",
                "https://example.test/iterator-abstraction",
                "https://example.test/consteval-propagation",
            }.isdisjoint(item.args[0] for item in fetch.call_args_list)
        )
        sleep.assert_called_once_with(0.1)


if __name__ == "__main__":
    unittest.main()
