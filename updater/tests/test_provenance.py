import tempfile
import unittest
from pathlib import Path

import yaml

from meta_updater.shared.provenance import (
    finish_provenance_tracking,
    retain_provenance_urls,
    start_provenance_tracking,
    track_provenance,
)


class ProvenanceTests(unittest.TestCase):
    def test_reconciliation_removes_discovery_and_rejected_urls(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "provenance.yaml"
            path.write_text(
                "retrieved_at: '2026-01-01'\n"
                "source_urls:\n"
                "- https://example.test/feed.xml\n"
                "- https://example.test/sitemap.xml\n"
                "- https://example.test/rejected-page\n",
                encoding="utf-8",
            )
            start_provenance_tracking(path)
            track_provenance("https://example.test/accepted-post")
            retain_provenance_urls(
                {
                    "https://example.test/feed.xml",
                    "https://example.test/accepted-post",
                }
            )
            finish_provenance_tracking()

            result = yaml.safe_load(path.read_text(encoding="utf-8"))
            self.assertEqual(
                result["source_urls"],
                [
                    "https://example.test/feed.xml",
                    "https://example.test/accepted-post",
                ],
            )


if __name__ == "__main__":
    unittest.main()
