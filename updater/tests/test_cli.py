import unittest

from meta_updater.cli import parser


class CliTests(unittest.TestCase):
    def parse(self, *arguments: str):
        return parser(list(arguments)).parse_args(list(arguments))

    def test_network_options_work_before_or_after_blog_action(self) -> None:
        before = self.parse("blogs", "--check", "all", "--timeout", "5")
        after = self.parse("blogs", "all", "--check", "--timeout", "5")

        self.assertTrue(before.check)
        self.assertEqual(before.timeout, 5)
        self.assertTrue(after.check)
        self.assertEqual(after.timeout, 5)

    def test_network_options_work_after_youtube_action(self) -> None:
        args = self.parse("youtube", "videos", "--delay", "0")

        self.assertEqual(args.command, "videos")
        self.assertEqual(args.delay, 0)

    def test_package_options_work_after_action(self) -> None:
        args = self.parse(
            "packages", "ingest", "--manager", "conan", "--refresh", "--check"
        )

        self.assertEqual(args.action, "ingest")
        self.assertEqual(args.manager, ["conan"])
        self.assertTrue(args.refresh)
        self.assertTrue(args.check)


if __name__ == "__main__":
    unittest.main()
