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


def test_malformed_html_does_not_crash() -> None:
    blocks = extract_blocks("doc_test", "<h1>Кривой HTML<h2>Раздел<p>Текст")
    assert blocks
    assert any(block.type == "heading" for block in blocks)
