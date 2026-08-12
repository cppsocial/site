import unittest

from meta_updater.commands.blogs import mark_excluded_posts


class BlogFilterTests(unittest.TestCase):
    def test_source_tags_exclude_matching_posts_case_insensitively(self) -> None:
        sources = [
            {
                "id": "example",
                "exclude_tags": [" Poetry "],
            },
            {
                "id": "another",
                "exclude_tags": [],
            },
        ]
        posts = [
            {"source_id": "example", "title": "C++", "tags": ["C++"]},
            {"source_id": "example", "title": "Poem", "tags": ["poetry"]},
            {"source_id": "another", "title": "Poem", "tags": ["Poetry"]},
        ]

        marked = mark_excluded_posts(posts, sources)
        self.assertNotIn("hidden", marked[0])
        self.assertTrue(marked[1]["hidden"])
        self.assertNotIn("hidden", marked[2])

    def test_any_matching_tag_hides_the_whole_post(self) -> None:
        sources = [{"id": "example", "exclude_tags": ["poetry", "travel"]}]
        posts = [
            {
                "source_id": "example",
                "title": "Mixed",
                "tags": ["math", "poetry"],
            }
        ]

        marked = mark_excluded_posts(posts, sources)

        self.assertEqual(len(marked), 1)
        self.assertTrue(marked[0]["hidden"])


if __name__ == "__main__":
    unittest.main()
