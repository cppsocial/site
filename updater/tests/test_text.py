import unittest

from meta_updater.shared.text import excerpt_html, render_text


class TextRenderingTests(unittest.TestCase):
    def test_single_outer_paragraph_is_removed(self) -> None:
        rendered = render_text("A short package description.")
        self.assertEqual(rendered.body_html, "A short package description.")

    def test_multiple_paragraphs_keep_structural_tags(self) -> None:
        rendered = render_text("First paragraph.\n\nSecond paragraph.")
        self.assertEqual(
            rendered.body_html,
            "<p>First paragraph.</p><p>Second paragraph.</p>",
        )

    def test_raw_html_is_escaped(self) -> None:
        rendered = render_text("<script>alert(1)</script> **safe**")
        self.assertNotIn("<script>", rendered.body_html)
        self.assertIn("&lt;script&gt;", rendered.body_html)

    def test_summary_is_bounded(self) -> None:
        rendered = render_text("word " * 100, summary_limit=40)
        self.assertTrue(rendered.truncated)
        self.assertLessEqual(len(rendered.summary_text), 41)

    def test_body_is_bounded_before_rendering(self) -> None:
        rendered = render_text("word " * 100, body_limit=40)
        self.assertTrue(rendered.truncated)
        self.assertLess(len(rendered.body_html), 80)

    def test_body_keeps_only_two_source_blocks(self) -> None:
        rendered = render_text(
            "First.\n\nSecond.\n\nThird.",
            block_limit=2,
        )
        self.assertEqual(
            rendered.body_html,
            "<p>First.</p><p>Second.</p>",
        )
        self.assertTrue(rendered.truncated)

    def test_html_excerpt_preserves_two_blocks(self) -> None:
        rendered = excerpt_html(
            "<h1>Package</h1><p>Useful description.</p><p>Unneeded details.</p>"
        )
        self.assertEqual(
            rendered.body_html,
            "<p>Package</p><p>Useful description.</p>",
        )


if __name__ == "__main__":
    unittest.main()
