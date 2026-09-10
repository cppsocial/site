import unittest

from site_plugins.browser import _book_published_date


class BookPublishedDateTests(unittest.TestCase):
    def test_preserves_available_date_precision(self) -> None:
        self.assertEqual(_book_published_date("Dec 05, 2014"), "2014-12-05")
        self.assertEqual(_book_published_date("June 2013"), "2013-06-01")
        self.assertEqual(_book_published_date("2019"), "2019-01-01")
        self.assertEqual(_book_published_date("January 21st, 2020"), "2020-01-21")


if __name__ == "__main__":
    unittest.main()
