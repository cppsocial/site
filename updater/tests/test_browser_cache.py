import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from site_generator import PluginFile, PluginResult
from site_plugins import browser


class BrowserDataCacheTests(unittest.TestCase):
    def config(self, root: Path) -> SimpleNamespace:
        data = root / "data"
        content = root / "content"
        output = root / "build"
        (data / "packages").mkdir(parents=True)
        content.mkdir()
        (data / "packages" / "catalog.yaml").write_text(
            "packages: []\n", encoding="utf-8"
        )
        return SimpleNamespace(root=root, data=data, content=content, output=output)

    @staticmethod
    def generate(config: SimpleNamespace) -> tuple[PluginResult, bool]:
        source = config.data / "packages" / "catalog.yaml"
        destination = config.output / "data" / "packages" / "index.json"
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text('{"count":0}\n', encoding="utf-8")
        return PluginResult([PluginFile(source, destination)]), True

    def test_matching_input_and_output_hashes_skip_generation(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            config = self.config(Path(temporary))
            with patch.object(
                browser, "_build_data", side_effect=self.generate
            ) as build:
                first = browser.build(config)
                second = browser.build(config)

            self.assertEqual(build.call_count, 1)
            self.assertEqual(len(first.generated), 1)
            self.assertEqual(second, PluginResult())
            manifest_path = config.root / ".cache" / browser.HASH_MANIFEST
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            self.assertEqual(manifest["algorithm"], "sha256")
            self.assertIn("data/packages/catalog.yaml", manifest["inputs"])
            self.assertEqual(set(manifest["outputs"]), {"packages/index.json"})

    def test_changed_output_forces_generation(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            config = self.config(Path(temporary))
            with patch.object(
                browser, "_build_data", side_effect=self.generate
            ) as build:
                browser.build(config)
                output = config.output / "data" / "packages" / "index.json"
                output.write_text('{"tampered":true}\n', encoding="utf-8")
                browser.build(config)

            self.assertEqual(build.call_count, 2)

    def test_changed_input_forces_generation(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            config = self.config(Path(temporary))
            with patch.object(
                browser, "_build_data", side_effect=self.generate
            ) as build:
                browser.build(config)
                source = config.data / "packages" / "catalog.yaml"
                source.write_text("packages: []\n# changed\n", encoding="utf-8")
                browser.build(config)

            self.assertEqual(build.call_count, 2)

    def test_changed_catalog_content_forces_data_generation(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            config = self.config(Path(temporary))
            youtube = config.content / "youtube"
            youtube.mkdir()
            channels = youtube / "channels.yaml"
            channels.write_text("cards: []\n", encoding="utf-8")
            with patch.object(
                browser, "_build_data", side_effect=self.generate
            ) as build:
                browser.build(config)
                channels.write_text("cards: []\n# changed\n", encoding="utf-8")
                browser.build(config)

            self.assertEqual(build.call_count, 2)

    def test_cache_inputs_include_shared_rendering_code(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            config = self.config(Path(temporary))

            self.assertIn(
                Path(browser.render_text.__code__.co_filename),
                browser._input_files(config),
            )

    def test_legacy_public_hash_manifest_is_removed(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            config = self.config(Path(temporary))
            legacy = config.output / "data" / browser.LEGACY_HASH_MANIFEST
            legacy.parent.mkdir(parents=True)
            legacy.write_text("{}\n", encoding="utf-8")

            with patch.object(browser, "_build_data", side_effect=self.generate):
                result = browser.build(config)

            self.assertFalse(legacy.exists())
            self.assertEqual(result.removed, [legacy])

    def test_search_snapshot_is_content_addressed(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary) / "packages"
            records = [
                {"id": f"package-{index}", "title": f"Package {index}"}
                for index in range(32)
            ]
            arguments = {
                "fields": {
                    "title": {"properties": ["title"], "boost": 10},
                },
                "exact": ["id", "title"],
            }
            self.assertTrue(
                browser._update_search_collection(output, records, **arguments)
            )
            before = json.loads((output / "index.json").read_text())

            records[7]["title"] = "Changed package"
            self.assertTrue(
                browser._update_search_collection(output, records, **arguments)
            )
            after = json.loads((output / "index.json").read_text())
            self.assertNotEqual(before["file"], after["file"])
            self.assertFalse((output / before["file"]).exists())
            self.assertTrue((output / after["file"]).exists())
            self.assertEqual(after["kind"], "search-records")
            self.assertEqual(after["count"], len(records))
            self.assertEqual(after["fields"], arguments["fields"])
            self.assertNotIn("bytes", after)
            self.assertNotIn("collection", after)

    def test_blog_records_resolve_author_from_canonical_sources(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            config = self.config(Path(temporary))
            sources = config.content / "blogs" / "sources.yaml"
            sources.parent.mkdir(parents=True)
            sources.write_text(
                "- id: example\n  title: Example Blog\n  author: Ada Example\n",
                encoding="utf-8",
            )
            posts = config.data / "blogs" / "posts"
            posts.mkdir(parents=True)
            (posts / "example.yaml").write_text(
                "- post_id: post-1\n"
                "  source_id: example\n"
                "  source_title: Example Blog\n"
                "  title: Search internals\n"
                "  url: https://example.test/search\n"
                "  published: 2026-01-02T00:00:00+00:00\n",
                encoding="utf-8",
            )

            records = browser._blog_records(config)

            self.assertEqual(records[0]["source"], "Example Blog")
            self.assertEqual(records[0]["author"], "Ada Example")

    def test_failed_generation_does_not_write_manifest(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            config = self.config(Path(temporary))
            with patch.object(
                browser, "_build_data", return_value=(PluginResult(), False)
            ):
                browser.build(config)

            self.assertFalse((config.root / ".cache" / browser.HASH_MANIFEST).exists())


if __name__ == "__main__":
    unittest.main()
