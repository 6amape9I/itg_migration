"""Table extraction helpers."""

from __future__ import annotations

from bs4.element import Tag


def extract_table_rows(table: Tag) -> list[list[str]]:
    rows: list[list[str]] = []
    for tr in table.find_all("tr"):
        cells = [
            cell.get_text(" ", strip=True)
            for cell in tr.find_all(["th", "td"], recursive=False)
        ]
        if any(cell for cell in cells):
            rows.append(cells)
    return rows


def table_to_text(rows: list[list[str]]) -> str:
    return "\n".join(" | ".join(cell for cell in row) for row in rows)


def table_to_markdown(rows: list[list[str]]) -> str:
    if not rows:
        return ""
    column_count = max((len(row) for row in rows), default=0)
    if column_count == 0:
        return ""

    padded = [_pad_row(row, column_count) for row in rows]
    header = padded[0]
    body = padded[1:]
    lines = [
        "| " + " | ".join(_escape_cell(cell) for cell in header) + " |",
        "| " + " | ".join("---" for _ in range(column_count)) + " |",
    ]
    lines.extend("| " + " | ".join(_escape_cell(cell) for cell in row) + " |" for row in body)
    return "\n".join(lines)


def infer_has_header(rows: list[list[str]]) -> bool:
    if not rows:
        return False
    if len(rows) == 1:
        return True
    first_width = len(rows[0])
    return first_width > 0 and all(cell.strip() for cell in rows[0])


def table_has_header_tag(table: Tag) -> bool:
    first_row = table.find("tr")
    if first_row is None:
        return False
    return first_row.find("th") is not None


def table_column_count(rows: list[list[str]]) -> int:
    return max((len(row) for row in rows), default=0)


def _pad_row(row: list[str], width: int) -> list[str]:
    return row + [""] * max(0, width - len(row))


def _escape_cell(value: str) -> str:
    return value.replace("|", "\\|").replace("\n", " ")
