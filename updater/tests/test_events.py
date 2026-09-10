import unittest

from meta_updater.commands.events import ical_unescape


class EventIngestionTests(unittest.TestCase):
    def test_ical_text_is_unescaped_and_unicode_sanitized(self) -> None:
        self.assertEqual(
            ical_unescape("Caf\u0065\u0301\u200b\ufffd\\nC++\\, meetup"),
            "Café\nC++, meetup",
        )


if __name__ == "__main__":
    unittest.main()
