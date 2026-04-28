from pathlib import Path

from itg_kb.preprocess.html_cleaner import has_html_markup, plain_text

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures"


def test_plain_text_keeps_html_text() -> None:
    html = (FIXTURES / "html_document_1.html").read_text(encoding="utf-8")
    assert has_html_markup(html)
    text = plain_text(html)
    assert "Гастрит" in text
    assert "Симптомы" in text


def test_plain_text_handles_plain_input() -> None:
    text = plain_text("Первая строка\n\nВторая строка")
    assert text == "Первая строка\n\nВторая строка"
