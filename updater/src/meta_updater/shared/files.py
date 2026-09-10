import os
import tempfile
from pathlib import Path


def update_bytes(path: Path, value: bytes, *, check: bool = False) -> bool:
    """Atomically replace a file when its content changed."""
    if path.is_file() and path.read_bytes() == value:
        return False
    if check:
        return True
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile("wb", dir=path.parent, delete=False) as file:
        file.write(value)
        temporary = Path(file.name)
    os.replace(temporary, path)
    return True
