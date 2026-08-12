import hashlib
import shutil
import subprocess
import urllib.request
from pathlib import Path

from ..shared.provenance import track_provenance
from .common import REPOSITORIES, repository_revision


CPPGET_BASE_URL = "https://pkg.cppget.org/1"
CPPGET_CHANNELS = ("stable", "testing", "beta", "alpha")


def update_cppget(path: Path, refresh: bool) -> None:
    path.mkdir(parents=True, exist_ok=True)
    for channel in CPPGET_CHANNELS:
        url = f"{CPPGET_BASE_URL}/{channel}/packages.manifest"
        target = path / channel / "packages.manifest"
        track_provenance(url)
        if target.exists() and not refresh:
            continue
        target.parent.mkdir(parents=True, exist_ok=True)
        temporary = target.with_suffix(".tmp")
        try:
            with urllib.request.urlopen(url) as response, temporary.open("wb") as output:
                shutil.copyfileobj(response, output)
            temporary.replace(target)
        finally:
            temporary.unlink(missing_ok=True)


def source_revision(manager: str, path: Path) -> str:
    if manager != "cppget":
        return repository_revision(path)
    digest = hashlib.sha256()
    found = False
    if path.is_file():
        digest.update(path.read_bytes())
        return digest.hexdigest()
    for channel in CPPGET_CHANNELS:
        manifest = path / channel / "packages.manifest"
        if not manifest.is_file():
            continue
        found = True
        digest.update(channel.encode())
        digest.update(b"\0")
        digest.update(manifest.read_bytes())
        digest.update(b"\0")
    return digest.hexdigest() if found else ""


def source_paths(managers: list[str], overrides: dict[str, Path], cache: Path,
                 refresh: bool) -> dict[str, Path]:
    paths = {}
    for manager in managers:
        path = overrides.get(manager, cache / manager)
        if manager == "cppget":
            update_cppget(path, refresh)
            paths[manager] = path
            continue
        repository = REPOSITORIES[manager]
        track_provenance(repository + ".git")
        if not path.exists():
            path.parent.mkdir(parents=True, exist_ok=True)
            subprocess.run(
                ["git", "clone", "--depth", "1", repository + ".git", str(path)],
                check=True,
            )
        elif refresh:
            subprocess.run(["git", "pull", "--ff-only"], cwd=path, check=True)
        paths[manager] = path
    return paths
