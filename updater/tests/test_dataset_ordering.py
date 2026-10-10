import tempfile
import unittest
from pathlib import Path

import yaml

from meta_updater.shared.dataset import YamlDataset, sorted_mapping


class DatasetOrderingTests(unittest.TestCase):
    def test_keyed_metadata_is_written_by_stable_id(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "metadata.yaml"
            dataset = YamlDataset(
                path,
                dict[str, dict[str, str]],
                "test",
                canonicalize=sorted_mapping,
            )

            dataset.update({"z-channel": {"title": "Z"}, "a-channel": {"title": "A"}})

            self.assertEqual(
                list(yaml.safe_load(path.read_text(encoding="utf-8"))),
                ["a-channel", "z-channel"],
            )


if __name__ == "__main__":
    unittest.main()
