from pathlib import Path

from itg_kb.preprocess.block_extractor import extract_blocks
from itg_kb.preprocess.html_cleaner import plain_text

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures"


def test_extracts_headings_and_paragraphs() -> None:
    html = (FIXTURES / "html_document_1.html").read_text(encoding="utf-8")
    blocks = extract_blocks("doc_test", html, plain_text=plain_text(html))
    assert any(block.type == "heading" and block.level == 1 for block in blocks)
    assert any(block.type == "paragraph" for block in blocks)


def test_extracts_tables() -> None:
    html = (FIXTURES / "html_document_2.html").read_text(encoding="utf-8")
    blocks = extract_blocks("doc_test", html, plain_text=plain_text(html))
    table = next(block for block in blocks if block.type == "table")
    assert "Параметр" in table.text
    assert table.metadata["rows"][1] == ["Температура", "37"]
    assert table.metadata["row_count"] == 2
    assert table.metadata["column_count"] == 2
    assert table.metadata["has_header"] is True
    assert "| Параметр | Значение |" in table.metadata["markdown"]
    assert table.heading_path == ["Показатели"]
    assert table.dom_path
    assert table.text_hash


def test_malformed_html_does_not_crash() -> None:
    blocks = extract_blocks("doc_test", "<h1>Кривой HTML<h2>Раздел<p>Текст")
    assert blocks
    assert any(block.type == "heading" for block in blocks)


def test_extracts_text_nodes_inside_div_without_paragraphs() -> None:
    html = (FIXTURES / "html_document_div_text.html").read_text(encoding="utf-8")
    blocks = extract_blocks("doc_test", html, plain_text=plain_text(html))
    texts = [block.text for block in blocks]

    assert "Текст прямо внутри div без отдельного paragraph." in texts
    assert "Дополнительный текст внутри section без p." in texts


def test_heading_path_tracks_current_heading() -> None:
    blocks = extract_blocks("doc_test", "<h1>Глава</h1><h2>Раздел</h2><p>Текст</p>")
    paragraph = next(block for block in blocks if block.type == "paragraph")

    assert paragraph.heading_path == ["Глава", "Раздел"]
    assert paragraph.parent_path[-2:] == ["h1:глава", "h2:раздел"]


def test_realish_malformed_html_keeps_useful_text() -> None:
    html = (FIXTURES / "html_document_broken_realish.html").read_text(encoding="utf-8")
    blocks = extract_blocks("doc_test", html, plain_text=plain_text(html))
    all_text = "\n".join(block.text for block in blocks)

    assert blocks
    assert "Важно перед приёмом препарата проверить назначение врача" in all_text
    assert any(block.type == "table" for block in blocks)
