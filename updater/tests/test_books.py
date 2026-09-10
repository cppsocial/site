import io
import unittest
import urllib.error
from unittest.mock import patch
from urllib.parse import unquote

from meta_updater.commands.books import (
    clean_subjects,
    description_text,
    isbn10_from_isbn13,
    request_json,
    split_title,
    text,
    valid_isbn,
    work,
)


class BookMetadataTests(unittest.TestCase):
    def test_remote_text_is_unicode_sanitized(self) -> None:
        self.assertEqual(text("Caf\u0065\u0301\u200b\ufffd"), "Café")

    def test_description_prefers_full_text_and_accepts_api_shapes(self) -> None:
        self.assertEqual(
            description_text(
                {"type": "/type/text", "value": "A **useful** C++ reference."},
                ["Fallback sentence."],
            ),
            "A useful C++ reference.",
        )
        self.assertEqual(description_text(
            "", ["Fallback sentence."]), "Fallback sentence.")

    @patch("meta_updater.commands.books.request_json")
    def test_work_requests_description_fields(self, request_json) -> None:
        request_json.return_value = {"docs": [{"key": "/works/OL1W"}]}

        work("9780321563842", 10)

        path = unquote(request_json.call_args.args[0])
        self.assertIn("description", path)
        self.assertIn("first_sentence", path)

    def test_validates_isbn_checksums(self) -> None:
        self.assertTrue(valid_isbn("9780321563842"))
        self.assertTrue(valid_isbn("0321563840"))
        self.assertFalse(valid_isbn("9780321563843"))
        self.assertFalse(valid_isbn("not-an-isbn"))

    def test_derives_isbn10_from_bookland_isbn13(self) -> None:
        self.assertEqual(isbn10_from_isbn13("9780321563842"), "0321563840")
        self.assertEqual(isbn10_from_isbn13("9791234567896"), "")
        self.assertEqual(isbn10_from_isbn13("9780321563843"), "")

    def test_splits_compound_api_titles_without_overwriting_subtitles(self) -> None:
        self.assertEqual(
            split_title(
                "Effective Modern C++: 42 Specific Ways to Improve Your Use of C++"
            ),
            ("Effective Modern C++", "42 Specific Ways to Improve Your Use of C++"),
        )
        self.assertEqual(
            split_title("Programming: Principles and Practice Using C++"),
            ("Programming: Principles and Practice Using C++", ""),
        )
        self.assertEqual(
            split_title("C++ Crash Course", "A Fast-Paced Introduction"),
            ("C++ Crash Course", "A Fast-Paced Introduction"),
        )

    def test_subjects_are_cleaned_limited_and_deduplicated(self) -> None:
        subjects = clean_subjects(
            [
                {"name": "C++"},
                {"name": "c++"},
                {"name": "open_syllabus_project"},
                {"name": "Programming"},
                {"name": "x" * 61},
                *[f"Subject {index}" for index in range(20)],
            ]
        )
        self.assertEqual(subjects[:2], ["C++", "Programming"])
        self.assertEqual(len(subjects), 12)

    @patch("meta_updater.commands.books.track_provenance")
    @patch("meta_updater.commands.books.time.sleep")
    @patch("meta_updater.commands.books.urllib.request.urlopen")
    def test_request_json_retries_transient_connection_resets(
        self, urlopen, sleep, track_provenance
    ) -> None:
        response = unittest.mock.MagicMock()
        response.__enter__.return_value = io.BytesIO(b'{"ok": true}')
        urlopen.side_effect = [
            urllib.error.URLError(ConnectionResetError(104, "reset")),
            response,
        ]

        self.assertEqual(request_json("/example", 10), {"ok": True})
        self.assertEqual(urlopen.call_count, 2)
        sleep.assert_called_once_with(1)
        track_provenance.assert_called_once_with(
            "https://openlibrary.org/example"
        )


if __name__ == "__main__":
    unittest.main()
