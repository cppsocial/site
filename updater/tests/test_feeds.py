import unittest

from meta_updater.shared.feeds import feed_entries


class FeedTagTests(unittest.TestCase):
    def test_rss_categories_and_namespaced_subjects_are_preserved(self) -> None:
        document = b"""<?xml version="1.0"?>
<rss version="2.0" xmlns:dc="http://purl.org/dc/elements/1.1/">
  <channel><item>
    <title>Example</title><link>https://example.test/post</link>
    <pubDate>Sun, 09 Aug 2026 00:00:00 +0000</pubDate>
    <category>C++</category><category>Compilers</category>
    <dc:subject>Language design</dc:subject>
  </item></channel>
</rss>"""
        self.assertEqual(
            feed_entries(document)[0]["tags"],
            ["C++", "Compilers", "Language design"],
        )

    def test_atom_category_label_is_preferred_to_machine_term(self) -> None:
        document = b"""<?xml version="1.0"?>
<feed xmlns="http://www.w3.org/2005/Atom">
  <entry><id>one</id><title>Example</title>
    <link rel="alternate" href="https://example.test/post"/>
    <published>2026-08-09T00:00:00Z</published>
    <category term="language-design" label="Language design"/>
  </entry>
</feed>"""
        self.assertEqual(feed_entries(document)[0]["tags"], ["Language design"])

    def test_media_keywords_are_used_but_youtube_kind_is_not_a_tag(self) -> None:
        document = b"""<?xml version="1.0"?>
<feed xmlns="http://www.w3.org/2005/Atom"
      xmlns:media="http://search.yahoo.com/mrss/">
  <entry><id>one</id><title>Example</title>
    <link rel="alternate" href="https://example.test/video"/>
    <published>2026-08-09T00:00:00Z</published>
    <category scheme="http://schemas.google.com/g/2005#kind"
              term="http://gdata.youtube.com/schemas/2007#video"/>
    <media:group><media:keywords>C++, Compilers</media:keywords></media:group>
  </entry>
</feed>"""
        self.assertEqual(feed_entries(document)[0]["tags"], ["C++", "Compilers"])

    def test_entries_without_categories_have_no_tags(self) -> None:
        document = b"""<rss><channel><item>
  <title>Example</title><link>https://example.test/post</link>
  <pubDate>Sun, 09 Aug 2026 00:00:00 +0000</pubDate>
</item></channel></rss>"""
        self.assertEqual(feed_entries(document)[0]["tags"], [])


if __name__ == "__main__":
    unittest.main()
