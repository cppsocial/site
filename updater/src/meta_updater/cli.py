import argparse
import importlib
import json
import subprocess
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

import yaml

from .config import load_config

COMMAND_MODULES = ("blogs", "books", "communities", "events", "packages", "youtube")


def parser(arguments: list[str] | None = None) -> argparse.ArgumentParser:
    bootstrap = argparse.ArgumentParser(add_help=False)
    bootstrap.add_argument("--config", type=Path, default=Path("meta.toml"))
    known, _ = bootstrap.parse_known_args(arguments)
    root = str(known.config.resolve().parent)
    if root not in sys.path:
        sys.path.insert(0, root)

    result = argparse.ArgumentParser(prog="meta-updater", parents=[bootstrap])
    commands = result.add_subparsers(dest="tool", required=True)
    for name in COMMAND_MODULES:
        command = importlib.import_module(f"meta_updater.commands.{name}")
        command.configure(commands.add_parser(name, help=command.DESCRIPTION))
    return result


def main() -> int:
    try:
        args = parser().parse_args()
        config = load_config(args.config)
        return args.handler(args, config)
    except (
        ET.ParseError,
        json.JSONDecodeError,
        OSError,
        subprocess.CalledProcessError,
        ValueError,
        yaml.YAMLError,
    ) as error:
        print(error, file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
