"""CSV report placeholder."""

from __future__ import annotations

from pathlib import Path

import pandas as pd


def write_csv_report(path: Path, rows: list[dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame.from_records(rows).to_csv(path, index=False)
