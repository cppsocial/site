import unittest
from pathlib import Path
from unittest.mock import patch

from scripts.check_content_rules import (
    ID_PATTERN,
    ISBN_PATTERN,
    YOUTUBE_PATTERN,
    validate_identifiers,
    validate_schema_declarations,
)


class ContentRulesTests(unittest.TestCase):
    def test_documented_identifier_formats(self) -> None:
        self.assertIsNotNone(ID_PATTERN.fullmatch("stable_source-2"))
        self.assertIsNone(ID_PATTERN.fullmatch("Unstable Source"))
        self.assertIsNotNone(ISBN_PATTERN.fullmatch("9780321563842"))
        self.assertIsNone(ISBN_PATTERN.fullmatch("978-0-321-56384-2"))
        self.assertIsNotNone(
            YOUTUBE_PATTERN.fullmatch("UCxHAlbZQNFU2LgEtiqd2Maw")
        )
        self.assertIsNone(YOUTUBE_PATTERN.fullmatch("@channel-handle"))

    def test_rejects_duplicate_ids_across_related_files(self) -> None:
        records = {
            Path("one.yaml"): [{"community_id": "same-id"}],
            Path("two.yaml"): [{"community_id": "same-id"}],
        }
        datasets = (((Path("one.yaml"), Path("two.yaml")), "community_id", ID_PATTERN),)
        with patch("scripts.check_content_rules.DATASETS", datasets), patch(
            "scripts.check_content_rules.Path.exists", return_value=True
        ), patch("scripts.check_content_rules._records", side_effect=records.get):
            errors = validate_identifiers()

        self.assertEqual(len(errors), 1)
        self.assertIn("duplicate community_id same-id", errors[0])

    def test_rejects_changed_schema_declaration(self) -> None:
        path = Path("content/example.yaml")
        with patch("scripts.check_content_rules.Path.exists", return_value=True), patch(
            "scripts.check_content_rules.Path.read_text",
            return_value="$schema: schemas/new.json\n",
        ), patch(
            "scripts.check_content_rules.subprocess.check_output",
            return_value="$schema: schemas/old.json\n",
        ):
            errors = validate_schema_declarations("base", {path})

        self.assertEqual(len(errors), 1)
        self.assertIn("$schema declaration changed", errors[0])


if __name__ == "__main__":
    unittest.main()
