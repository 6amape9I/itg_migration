"""Table extraction helpers."""

from __future__ import annotations

from bs4.element import Tag


def extract_table_rows(table: Tag) -> list[list[str]]:
    rows: list[list[str]] = []
    for tr in table.find_all("tr"):
        cells = [
            cell.get_text(" ", strip=True)
            for cell in tr.find_all(["th", "td"])
            if cell.get_text(" ", strip=True)
        ]
        if cells:
            rows.append(cells)
    return rows


def table_to_text(rows: list[list[str]]) -> str:
    return "\n".join(" | ".join(cell for cell in row) for row in rows)
