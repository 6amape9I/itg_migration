"""Parquet helpers."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pandas as pd


def write_parquet_records(path: Path | str, records: list[dict[str, Any]]) -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    dataframe = pd.DataFrame.from_records(records)
    for column in dataframe.columns:
        if dataframe[column].map(lambda value: isinstance(value, dict | list)).any():
            dataframe[column] = dataframe[column].map(_json_or_none)
    dataframe.to_parquet(target, index=False)


def read_parquet_records(path: Path | str) -> list[dict[str, Any]]:
    return pd.read_parquet(Path(path)).to_dict(orient="records")


def _json_or_none(value: Any) -> str | None:
    if isinstance(value, dict | list):
        return json.dumps(value, ensure_ascii=False, sort_keys=True)
    return value
