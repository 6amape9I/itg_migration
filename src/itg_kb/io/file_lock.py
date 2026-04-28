"""Small file lock placeholder.

The initial stages are single-process. This context manager keeps the import surface ready for a
future cross-process lock implementation without adding extra dependencies now.
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path


@contextmanager
def file_lock(_path: Path | str) -> Iterator[None]:
    yield
