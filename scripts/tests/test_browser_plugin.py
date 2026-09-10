import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

from site_plugins.browser import _book_published_date, _book_records


class BookPublishedDateTests(unittest.TestCase):
    def test_preserves_available_date_precision(self) -> None:
        self.assertEqual(_book_published_date("Dec 05, 2014"), "2014-12-05")
        self.assertEqual(_book_published_date("June 2013"), "2013-06-01")
        self.assertEqual(_book_published_date("2019"), "2019-01-01")
        self.assertEqual(_book_published_date("January 21st, 2020"), "2020-01-21")


class BookRecordsTests(unittest.TestCase):
    def test_uses_curated_fields_until_metadata_is_generated(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            books = root / "content" / "books"
            metadata = root / "data" / "books"
            books.mkdir(parents=True)
            metadata.mkdir(parents=True)
            (books / "books.yaml").write_text(
                "cards:\n"
                "  - isbn: '9781593278885'\n"
                "    cover_url: https://example.com/cover.jpg\n",
                encoding="utf-8",
            )
            (metadata / "metadata.yaml").write_text("{}\n", encoding="utf-8")

            records = _book_records(
                SimpleNamespace(content=root / "content", data=root / "data")
            )

        self.assertEqual(
            records,
            [
                {
                    "title": "9781593278885",
                    "isbn_13": "9781593278885",
                    "url": "https://openlibrary.org/isbn/9781593278885",
                    "id": "9781593278885",
                    "cover_url": "https://example.com/cover.jpg",
                    "published": "",
                }
            ],
        )


if __name__ == "__main__":
    unittest.main()
