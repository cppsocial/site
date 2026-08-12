import os
import tomllib
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field


class MetaUpdaterConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    content: Path = Path("content")
    data: Path = Path("data")
    browser_data: Path = Path("data/web")
    package_cache: Path = Field(
        default_factory=lambda: Path(
            os.environ.get("CPP_SOCIAL_PACKAGE_CACHE",
                           "/tmp/cpp-social-packages")
        )
    )
    timeout: float = 30
    delay: float = 0.25
    package_threshold: float = 0.82
    package_managers: list[str] = Field(
        default_factory=lambda: ["conan", "meson", "spack",
                                 "vcpkg", "bazel", "cppget", "hunter", "xmake"]
    )


def load_config(path: Path) -> MetaUpdaterConfig:
    with path.open("rb") as file:
        values = tomllib.load(file)
    config = MetaUpdaterConfig.model_validate(
        values.get("meta_updater", values))
    base = path.parent.resolve()
    resolved = config.model_dump()
    for name in ("content", "data", "browser_data", "package_cache"):
        value = resolved[name]
        resolved[name] = value if value.is_absolute() else (base /
                                                            value).resolve()
    return MetaUpdaterConfig.model_validate(resolved)
