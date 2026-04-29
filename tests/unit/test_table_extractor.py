from bs4 import BeautifulSoup

from itg_kb.preprocess.table_extractor import (
    extract_table_rows,
    infer_has_header,
    table_column_count,
    table_has_header_tag,
    table_to_markdown,
)


def test_table_extractor_detects_th_header_and_markdown() -> None:
    soup = BeautifulSoup(
        "<table><tr><th>Параметр</th><th>Значение</th></tr>"
        "<tr><td>Температура</td><td>37</td></tr></table>",
        "lxml",
    )
    table = soup.find("table")
    assert table is not None

    rows = extract_table_rows(table)

    assert rows == [["Параметр", "Значение"], ["Температура", "37"]]
    assert table_has_header_tag(table) is True
    assert infer_has_header(rows) is True
    assert "| Параметр | Значение |" in table_to_markdown(rows)


def test_table_extractor_handles_ragged_rows() -> None:
    soup = BeautifulSoup(
        "<table><tr><td>A</td><td>B</td><td>C</td></tr><tr><td>1</td></tr></table>",
        "lxml",
    )
    table = soup.find("table")
    assert table is not None

    rows = extract_table_rows(table)
    markdown = table_to_markdown(rows)

    assert table_column_count(rows) == 3
    assert "| 1 |  |  |" in markdown
