"""DuckDB connection helper for local analytics."""

from __future__ import annotations

from pathlib import Path

import duckdb


def connect(path: Path | str = ":memory:") -> duckdb.DuckDBPyConnection:
    return duckdb.connect(str(path))
