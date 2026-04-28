"""CSV loading that keeps processing errors local to rows where possible."""

from __future__ import annotations

import csv
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class CsvLoadResult:
    rows: list[dict[str, Any]] = field(default_factory=list)
    fieldnames: list[str] = field(default_factory=list)
    errors: list[dict[str, Any]] = field(default_factory=list)


def load_csv_rows(path: Path | str) -> CsvLoadResult:
    source = Path(path)
    result = CsvLoadResult()
    try:
        with source.open("r", encoding="utf-8-sig", newline="") as handle:
            reader = csv.DictReader(handle)
            result.fieldnames = list(reader.fieldnames or [])
            for row_index, row in enumerate(reader, start=1):
                try:
                    extras = row.pop(None, None)
                    if extras:
                        row["__extra_values__"] = extras
                    row["__source_row__"] = row_index
                    result.rows.append(row)
                except Exception as exc:  # pragma: no cover - defensive row isolation
                    result.errors.append(
                        {"source_row": row_index, "error": type(exc).__name__, "message": str(exc)}
                    )
    except Exception as exc:
        result.errors.append({"source_row": None, "error": type(exc).__name__, "message": str(exc)})
    return result
