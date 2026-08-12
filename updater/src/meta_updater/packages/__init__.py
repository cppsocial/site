from collections.abc import Callable
from pathlib import Path
from typing import Any

from .conan import parse_conan as _parse_conan
from .matching import amalgamate, compare_packages
from .meson import parse_meson as _parse_meson
from .spack import parse_spack as _parse_spack
from .vcpkg import parse_vcpkg as _parse_vcpkg
from .bazel import parse_bazel as _parse_bazel
from .cppget import parse_cppget as _parse_cppget
from .hunter import parse_hunter as _parse_hunter
from .xmake import parse_xmake as _parse_xmake
from .common import normalize_package_record


def _normalized(parser: Callable[..., list[dict[str, Any]]]):
    def wrapped(root: Path, *args: Any, **kwargs: Any) -> list[dict[str, Any]]:
        return [normalize_package_record(item) for item in parser(root, *args, **kwargs)]

    return wrapped


parse_conan = _normalized(_parse_conan)
parse_meson = _normalized(_parse_meson)
parse_spack = _normalized(_parse_spack)
parse_vcpkg = _normalized(_parse_vcpkg)
parse_bazel = _normalized(_parse_bazel)
parse_cppget = _normalized(_parse_cppget)
parse_hunter = _normalized(_parse_hunter)
parse_xmake = _normalized(_parse_xmake)

PARSERS = {
    "conan": parse_conan,
    "meson": parse_meson,
    "spack": parse_spack,
    "vcpkg": parse_vcpkg,
    "bazel": parse_bazel,
    "cppget": parse_cppget,
    "hunter": parse_hunter,
    "xmake": parse_xmake,
}

__all__ = [
    "PARSERS",
    "amalgamate",
    "compare_packages",
    "parse_conan",
    "parse_meson",
    "parse_spack",
    "parse_vcpkg",
    "parse_bazel",
    "parse_cppget",
    "parse_hunter",
    "parse_xmake"
]
