import tempfile
import unittest
from datetime import UTC, datetime
from pathlib import Path

from pydantic import ValidationError
from schemas.blocks import CachedVideo

from meta_updater.shared.blogs import post_id, render_description
from meta_updater.shared.relevance import load_relevance_labels, merge_records


class RelevanceTests(unittest.TestCase):
    def test_blog_id_is_compact_deterministic_and_source_scoped(self) -> None:
        url = "https://example.test/posts/cpp"
        value = post_id("example", url)
        self.assertEqual(len(value), 16)
        self.assertEqual(value, post_id("example", url))
        self.assertNotEqual(value, post_id("another", url))
        self.assertNotIn("example.test", value)

    def test_single_paragraph_description_has_no_redundant_wrapper(self) -> None:
        self.assertEqual(render_description("C++ & tools"), "C++ &amp; tools")
        self.assertEqual(
            render_description("First\n\nSecond"),
            "<p>First</p>\n<p>Second</p>",
        )

    def test_refresh_preserves_existing_relevance(self) -> None:
        current = [{"id": "one", "title": "old", "cpp_relevance": 0.0}]
        updates = [{"id": "one", "title": "new"}]
        values = merge_records(
            current, updates, id_field="id", normalize=lambda item: dict(item)
        )
        self.assertEqual(values, [{"id": "one", "title": "new", "cpp_relevance": 0.0}])

    def test_labels_are_bounded_numbers(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "labels.yaml"
            path.write_text("youtube_videos:\n  abc: 1\n")
            self.assertEqual(
                load_relevance_labels(path, "youtube_videos"), {"abc": 1.0}
            )
            path.write_text("youtube_videos:\n  abc: 1.1\n")
            with self.assertRaises(ValueError):
                load_relevance_labels(path, "youtube_videos")

    def test_schema_rejects_out_of_range_relevance(self) -> None:
        with self.assertRaises(ValidationError):
            CachedVideo(
                video_id="abc",
                title="Example",
                url="https://youtu.be/abc",
                published=datetime.now(UTC),
                cpp_relevance=-0.01,
            )


if __name__ == "__main__":
    unittest.main()
