import tempfile
import unittest
from pathlib import Path
from urllib.parse import parse_qs

from meta_updater.commands.communities import communities
from meta_updater.commands.events import source_records
from meta_updater.shared.communities import _reddit_challenge_query


class CuratedSourceTests(unittest.TestCase):
    def test_current_reddit_javascript_challenge_field_is_supported(self) -> None:
        query = _reddit_challenge_query(
            """<script>await(async e=>e+e)("6dff5746684c60dc")</script>
<input name="js_challenge" value="1">
<input name="jsc_token" value="current-token">
"""
        )

        self.assertEqual(
            parse_qs(query, keep_blank_values=True),
            {
                "solution": ["6dff5746684c60dc6dff5746684c60dc"],
                "js_challenge": ["1"],
                "jsc_token": ["current-token"],
                "jsc_orig_r": [""],
            },
        )

    def test_legacy_reddit_challenge_field_remains_supported(self) -> None:
        query = _reddit_challenge_query(
            """<script>await(async e=>e+e)("abc123")</script>
<input name="token" value="legacy-token">
"""
        )
        self.assertEqual(parse_qs(query)["token"], ["legacy-token"])

    def test_community_metadata_source_is_read_from_displayed_record(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            content = Path(temporary)
            (content / "chat.yaml").write_text(
                """cards:
- community_id: example
  title: Example
  metadata_source: {source: reddit, key: cpp}
""",
                encoding="utf-8",
            )
            self.assertEqual(
                communities(content)[0]["metadata_source"],
                {"source": "reddit", "key": "cpp"},
            )

    def test_event_source_is_derived_from_meetup_card(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "meetups.yaml"
            path.write_text(
                """cards:
- type: meetup_card
  source_id: example
  timezone: Europe/Berlin
  title: Example Meetup
  path: https://www.meetup.com/example/
  metadata: {Location: "Berlin, Germany"}
  links:
  - {label: Calendar, path: https://www.meetup.com/example/events/ical/}
""",
                encoding="utf-8",
            )
            self.assertEqual(
                source_records(path),
                [
                    {
                        "id": "example",
                        "kind": "meetup_ical",
                        "url": "https://www.meetup.com/example/events/ical/",
                        "homepage": "https://www.meetup.com/example/",
                        "organizer": "Example Meetup",
                        "source_name": "Meetup",
                        "event_type": "meetup",
                        "format": "in_person",
                        "timezone": "Europe/Berlin",
                        "default_location": "Berlin, Germany",
                    }
                ],
            )


if __name__ == "__main__":
    unittest.main()
