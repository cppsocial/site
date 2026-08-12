import argparse
import sys
import time
from collections.abc import Iterable, Iterator

from meta_updater.config import MetaUpdaterConfig


def add_network_options(
    parser: argparse.ArgumentParser,
    *,
    delay: bool = True,
    suppress_defaults: bool = False,
) -> None:
    """Add the options shared by network-backed updaters.

    Action parsers use ``suppress_defaults`` so an option supplied before the
    action is not overwritten by the action parser's defaults.  This lets the
    CLI consistently accept options on either side of an action name.
    """
    defaults = {"default": argparse.SUPPRESS} if suppress_defaults else {}
    parser.add_argument("--timeout", type=float, **defaults)
    if delay:
        parser.add_argument("--delay", type=float, **defaults)
    parser.add_argument("--check", action="store_true", **defaults)


def network_values(
    args: argparse.Namespace, config: MetaUpdaterConfig
) -> tuple[float, float]:
    timeout = args.timeout if args.timeout is not None else config.timeout
    delay = getattr(args, "delay", None)
    return timeout, delay if delay is not None else config.delay


def delayed[T](values: Iterable[T], delay: float) -> Iterator[T]:
    for index, value in enumerate(values):
        if index:
            time.sleep(delay)
        yield value


def finish(changed: bool, check: bool, label: str) -> int:
    if check and changed:
        print(f"generated {label} data is stale", file=sys.stderr)
        return 1
    print("updated" if changed else "unchanged")
    return 0
