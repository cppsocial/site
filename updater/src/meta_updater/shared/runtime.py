import argparse
import sys
import time
from collections.abc import Callable, Iterable, Iterator
from typing import Any

from meta_updater.config import MetaUpdaterConfig


class _AppendId(argparse.Action):
    def __call__(
        self,
        parser: argparse.ArgumentParser,
        namespace: argparse.Namespace,
        values: str,
        option_string: str | None = None,
    ) -> None:
        current = list(getattr(namespace, self.dest, None) or [])
        setattr(namespace, self.dest, [*current, values])


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


def add_id_option(
    parser: argparse.ArgumentParser, *, suppress_defaults: bool = False
) -> None:
    """Add a repeatable curated-record selector to a command parser."""
    defaults = {"default": argparse.SUPPRESS} if suppress_defaults else {}
    parser.add_argument(
        "--id",
        dest="ids",
        action=_AppendId,
        metavar="ID",
        help="update only this curated ID (repeatable)",
        **defaults,
    )


def add_network_action(
    actions: Any,
    name: str,
) -> argparse.ArgumentParser:
    """Add an action accepting shared network and record-selection options."""
    parser = actions.add_parser(name)
    add_network_options(parser, suppress_defaults=True)
    add_id_option(parser, suppress_defaults=True)
    return parser


def selected[T](
    values: Iterable[T], ids: list[str] | None, key: Callable[[T], str], label: str
) -> list[T]:
    """Select requested records in source order and reject unknown IDs."""
    records = list(values)
    if not ids:
        return records
    requested = set(ids)
    known = {key(value) for value in records}
    unknown = sorted(requested - known)
    if unknown:
        raise ValueError(f"unknown {label}: {', '.join(unknown)}")
    return [value for value in records if key(value) in requested]


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


def log_operation_error(operation: str, error: Exception, **context: Any) -> None:
    """Report a failed batch operation without losing its identifying context."""
    details = ", ".join(
        f"{name}={value!r}" for name, value in context.items() if value is not None
    )
    suffix = f" ({details})" if details else ""
    print(
        f"error: {operation} failed{suffix}: {type(error).__name__}: {error}",
        file=sys.stderr,
    )


def finish(changed: bool, check: bool, label: str) -> int:
    if check and changed:
        print(f"generated {label} data is stale", file=sys.stderr)
        return 1
    print("updated" if changed else "unchanged")
    return 0
