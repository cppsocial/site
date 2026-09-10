import unittest

from schemas.blocks import Markdown
from schemas.markdown import select_sections
from schemas.pages import DocumentationEntry


class MarkdownSectionsTests(unittest.TestCase):
    SOURCE = """# Introduction
Not selected.

## Selected
Parent content.

### Child
Child content.

#### Grandchild
Grandchild content.

```text
## Not a real heading
```

## Other
Not selected either.

## Also selected
More content.
"""

    def test_includes_descendant_headings(self) -> None:
        selected = select_sections(self.SOURCE, ["Selected"])

        self.assertIn("### Child", selected)
        self.assertIn("#### Grandchild", selected)
        self.assertIn("## Not a real heading", selected)
        self.assertNotIn("## Other", selected)

    def test_preserves_source_order_without_overlapping_duplicates(self) -> None:
        selected = select_sections(
            self.SOURCE, ["Also selected", "Child", "Selected"]
        )

        self.assertLess(
            selected.index("## Selected"), selected.index("## Also selected")
        )
        self.assertEqual(selected.count("### Child"), 1)

    def test_rejects_a_missing_heading(self) -> None:
        with self.assertRaisesRegex(
            ValueError, "Markdown headings not found: 'Missing'"
        ):
            Markdown(content=self.SOURCE, include_headings=["Missing"])

    def test_applies_requested_markdown_extensions_after_selection(self) -> None:
        document = """# Ignore

## People

| Name | Role |
| ---- | ---- |
| Ada | Maintainer |
"""

        selected = Markdown(
            content=document,
            include_headings=["People"],
            markdown_extensions=["tables"],
        )

        self.assertIn("<table>", selected.content)
        self.assertNotIn("Ignore", selected.content)

    def test_documentation_renders_admonitions(self) -> None:
        document = DocumentationEntry(
            id="example",
            title="Example",
            content='!!! warning "Direct links only"\n    Do not use shorteners.\n',
        )

        self.assertIn('class="admonition warning"', document.rendered_content)
        self.assertIn('class="admonition-title"', document.rendered_content)


if __name__ == "__main__":
    unittest.main()
