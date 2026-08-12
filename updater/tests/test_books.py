import unittest

from meta_updater.commands.books import (
    clean_subjects,
    isbn10_from_isbn13,
    split_title,
    valid_isbn,
)


class BookMetadataTests(unittest.TestCase):
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


if __name__ == "__main__":
    unittest.main()
