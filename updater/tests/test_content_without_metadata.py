"""Content-only additions must build before updater enrichment exists."""

import json
import shutil
import tempfile
import unittest
from datetime import UTC, datetime
from pathlib import Path

import yaml
from site_generator.config import load_config
from site_generator.site import build_site

ROOT = Path(__file__).resolve().parents[2]


class ContentWithoutMetadataTests(unittest.TestCase):
    def test_builds_new_entries_without_updater_data(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for name in ('content', 'config', 'ui', 'schemas', 'templates', 'data', 'docs'):
                shutil.copytree(ROOT / name, root / name)
            shutil.copy(ROOT / 'site.toml', root / 'site.toml')

            def write(path, value):
                (root / path).write_text(yaml.safe_dump(value), encoding='utf-8')

            def add_card(path, card):
                document = yaml.safe_load((root / path).read_text())
                document['cards'].append(card)
                write(path, document)

            channel_id = 'UCxHAlbZQNFU2LgEtiqd2Maw'
            add_card('content/youtube/channels.yaml', {
                'type': 'channel_card', 'channel_id': channel_id,
                'channel_type': 'creator', 'title': 'New channel',
            })
            add_card('content/communities/im.yaml', {
                'type': 'community_card', 'community_id': 'new-community',
                'platform': 'discord', 'title': 'New community',
                'description': 'community description',
                'path': 'https://discord.gg/example',
                'metadata_source': {'source': 'discord', 'key': 'example'},
            })
            # Keep the book fixture independent of the curated catalog.
            books_document = yaml.safe_load(
                (root / 'content/books/books.yaml').read_text())
            books_document['cards'] = []
            write('content/books/books.yaml', books_document)
            add_card('content/books/books.yaml', {
                'type': 'book_card', 'isbn': '9781593278885',
                'cover_url': 'https://example.com/cover.jpg',
            })
            write('content/blogs/sources.yaml', [{
                'id': 'new-blog', 'title': 'New blog',
                'description': 'blog description',
                'website_url': 'https://example.com/blog',
                'rss_url': 'https://example.com/feed.xml',
            }])
            write('content/events/events.yaml', [{
                'ical_uid': 'new-event', 'title': 'New event',
                'start_date': '2099-01-01', 'event_type': 'conference',
                'source_url': 'https://example.com/event',
            }])
            for path in ('youtube/channel-metadata.yaml', 'communities/metadata.yaml',
                         'books/metadata.yaml', 'blogs/metadata.yaml'):
                write('data/' + path, {})
            for path in ('youtube/videos', 'blogs/posts'):
                shutil.rmtree(root / 'data' / path)
                (root / 'data' / path).mkdir()
            write('data/blogs/posts/new-blog.yaml', [{
                'post_id': 'recent-post', 'source_id': 'new-blog',
                'source_title': 'New blog', 'title': 'Recent post',
                'url': 'https://example.com/blog/recent',
                'published': datetime(2099, 1, 1, tzinfo=UTC),
                'description': 'Use **vector** <Debug> without breaking the page.',
            }])
            write('data/events-imported.yaml', [])

            config = load_config(root / 'site.toml', {'minify': False})
            config.frontend = None
            config.assets.mkdir(exist_ok=True)
            build_site(config)

            youtube = (config.output / 'youtube/index.html').read_text()
            self.assertIn('New channel', youtube)
            self.assertIn(f'https://www.youtube.com/channel/{channel_id}', youtube)
            self.assertIn('data-channel-details', youtube)
            communities = (config.output / 'communities/index.html').read_text()
            self.assertIn('community description', communities)
            blogs = (config.output / 'blogs/index.html').read_text()
            self.assertIn('blog description', blogs)
            self.assertIn(
                'Use <strong>vector</strong> &lt;Debug&gt; without breaking the page.',
                blogs,
            )
            self.assertIn('Browse blogs', blogs)
            events = (config.output / 'events/index.html').read_text()
            self.assertIn('New event', events)
            books = json.loads((config.output / 'data/books/index.json').read_text())
            self.assertEqual(books['count'], 1)
            records = json.loads(
                (config.output / 'data/books' / books['file']).read_text())
            self.assertIn('9781593278885', json.dumps(records))
            self.assertIn('https://openlibrary.org/isbn/9781593278885',
                          json.dumps(records))
            self.assertIn('https://example.com/cover.jpg', json.dumps(records))

            # Later enrichment must replace the placeholders on the same card.
            write('data/youtube/channel-metadata.yaml', {channel_id: {
                'url': 'https://www.youtube.com/@new-channel',
                'description': 'Fetched channel description',
                'keywords': ['templates'],
            }})
            write('data/communities/metadata.yaml', {'new-community': {
                'member_count': 1234,
            }})
            build_site(config)
            youtube = (config.output / 'youtube/index.html').read_text()
            self.assertIn('Fetched channel description', youtube)
            self.assertIn('https://www.youtube.com/@new-channel', youtube)
            self.assertIn('data-search-tag="templates"', youtube)
            communities = (config.output / 'communities/index.html').read_text()
            self.assertIn('1,234', communities)


if __name__ == '__main__':
    unittest.main()
