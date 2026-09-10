import unittest

from scripts.check_discord_invites import validate_card


class DiscordInviteTests(unittest.TestCase):
    def card(self) -> dict:
        return {
            "community_id": "example",
            "metadata_source": {"source": "discord", "key": "Ab3dE9xYz2"},
            "platform": "discord",
            "path": "https://discord.gg/Ab3dE9xYz2",
        }

    def test_accepts_active_permanent_non_vanity_invite(self) -> None:
        errors = validate_card(
            self.card(),
            lambda code: {
                "code": code,
                "expires_at": None,
                "guild": {"vanity_url_code": "example"},
            },
        )

        self.assertEqual(errors, [])

    def test_rejects_expiring_vanity_invite_and_indirect_path(self) -> None:
        card = self.card()
        card["path"] = "https://example.test/join"
        errors = validate_card(
            card,
            lambda code: {
                "code": code,
                "expires_at": "2026-09-01T00:00:00+00:00",
                "guild": {"vanity_url_code": code.lower()},
            },
        )

        self.assertEqual(len(errors), 3)
        self.assertTrue(any("direct" in error for error in errors))
        self.assertTrue(any("expires" in error for error in errors))
        self.assertTrue(any("vanity" in error for error in errors))


if __name__ == "__main__":
    unittest.main()
