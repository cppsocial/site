"""Site-wide SEO and discovery-file integrity tests run during builds."""

import re
import struct
import unittest
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
ORIGIN = "https://cpp.social"


class SeoFilesTests(unittest.TestCase):
    @staticmethod
    def sitemap_locations():
        class ConfigLoader(yaml.SafeLoader):
            pass

        ConfigLoader.add_constructor(
            "!import", lambda loader, node: loader.construct_scalar(node)
        )
        config = yaml.load(
            (ROOT / "config/sitemap.yaml").read_text(), Loader=ConfigLoader
        )
        navigation = yaml.safe_load((ROOT / "ui/navigation.yaml").read_text())
        footer = yaml.safe_load((ROOT / "ui/footer.yaml").read_text())
        paths = [
            *config["additional_paths"],
            *(page["path"] for page in [*navigation, *footer]),
        ]
        return [f"{ORIGIN}{path}" for path in paths]

    def test_sitemap_contains_every_html_page(self):
        locations = self.sitemap_locations()

        content = ROOT / "content"
        expected = set()
        for index in content.rglob("_index.yaml"):
            directory = index.parent.relative_to(content).as_posix()
            expected.add(f"{ORIGIN}/{directory}/" if directory != "." else f"{ORIGIN}/")

        self.assertEqual(set(locations), expected)
        self.assertEqual(len(locations), len(set(locations)))

        manifest = (ROOT / "content/_sitemap.yaml").read_text(encoding="utf-8")
        self.assertIn("$output: sitemap.xml", manifest)
        self.assertFalse((ROOT / "assets/sitemap.xml").exists())

    def test_robots_file_points_to_sitemap(self):
        robots = (ROOT / "assets/robots.txt").read_text(encoding="utf-8")

        self.assertIn("User-agent: *\nAllow: /", robots)
        self.assertIn(f"Sitemap: {ORIGIN}/sitemap.xml", robots)

    def test_every_html_page_has_a_unique_effective_seo_title(self):
        titles = []
        for index in (ROOT / "content").rglob("_index.yaml"):
            source = index.read_text(encoding="utf-8")
            seo_title = re.search(
                r"^seo_title:\s*(.+)$", source, re.MULTILINE
            )
            title = re.search(r"^title:\s*(.+)$", source, re.MULTILINE)
            self.assertIsNotNone(title, f"Missing title in {index}")
            titles.append((seo_title or title).group(1).strip())

        self.assertEqual(len(titles), len(set(titles)))

    def test_social_preview_has_vector_source_and_compatible_export(self):
        image_directory = ROOT / "assets/static/images"
        svg = (image_directory / "social-preview.svg").read_text(encoding="utf-8")
        self.assertIn('viewBox="0 0 1200 630"', svg)

        with (image_directory / "social-preview.png").open("rb") as preview:
            self.assertEqual(preview.read(8), b"\x89PNG\r\n\x1a\n")
            length = struct.unpack(">I", preview.read(4))[0]
            self.assertEqual(preview.read(4), b"IHDR")
            width, height = struct.unpack(">II", preview.read(length)[:8])

        self.assertEqual((width, height), (1200, 630))

    def test_base_template_emits_structured_and_social_metadata(self):
        template = (ROOT / "templates/layouts/base.html").read_text(encoding="utf-8")

        for expected in (
            "this.get('seo_title') or page_title|trim",
            'type="application/ld+json"',
            '"@type": "Organization"',
            '"@type": "WebSite"',
            'property="og:image"',
            'name="twitter:card" content="summary_large_image"',
        ):
            self.assertIn(expected, template)


if __name__ == "__main__":
    unittest.main()
