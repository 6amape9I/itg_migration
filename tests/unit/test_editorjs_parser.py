import json
from pathlib import Path

from itg_kb.preprocess.editorjs_parser import (
    detect_content_format,
    extract_editorjs_blocks,
    extract_editorjs_useful_text,
)

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures"


def test_detects_editorjs_before_html_markup() -> None:
    raw = (FIXTURES / "editorjs_document.json").read_text(encoding="utf-8")

    assert detect_content_format(raw) == "editorjs_json"


def test_extracts_editorjs_header_and_paragraph_without_service_text() -> None:
    raw = (FIXTURES / "editorjs_document.json").read_text(encoding="utf-8")

    blocks = extract_editorjs_blocks("doc_0a0ad5b9a5b8d6e1243e", raw)
    heading = blocks[0]
    paragraph = blocks[1]
    all_text = "\n".join(block.text for block in blocks)
    all_metadata = json.dumps([block.metadata for block in blocks], ensure_ascii=False)

    assert heading.type == "heading"
    assert heading.level == 3
    assert paragraph.type == "paragraph"
    assert "Режим дозирования и схемы приема" in paragraph.text
    assert (
        "При большинстве инфекций рекомендуемая доза составляет 250 мг 2 раза в сутки."
        in paragraph.text
    )
    assert "Внутрь." in paragraph.text
    assert "api" not in all_text
    assert "styles" not in all_text
    assert "toolbar" not in all_text
    assert "version" not in all_text
    assert "api" not in all_metadata
    assert "styles" not in all_metadata
    assert "toolbar" not in all_metadata
    assert "version" not in all_metadata
    assert paragraph.metadata["source_format"] == "editorjs"
    assert paragraph.metadata["editorjs_block_id"] == "Zx05Oyfw3"
    assert paragraph.metadata["editorjs_type"] == "paragraph"
    assert paragraph.heading_path == [heading.text]
    assert paragraph.parent_path[-1].startswith("h3:")
    assert paragraph.text_hash


def test_extracts_editorjs_list_table_and_quote() -> None:
    raw = json.dumps(
        {
            "blocks": [
                {"id": "h1", "type": "header", "data": {"text": "Раздел", "level": 2}},
                {
                    "id": "l1",
                    "type": "list",
                    "data": {"style": "ordered", "items": ["Первый", {"content": "Второй"}]},
                },
                {
                    "id": "t1",
                    "type": "table",
                    "data": {
                        "withHeadings": True,
                        "content": [["Параметр", "Значение"], ["Температура", "37"]],
                    },
                },
                {"id": "q1", "type": "quote", "data": {"text": "Цитата", "caption": "Автор"}},
            ]
        },
        ensure_ascii=False,
    )

    blocks = extract_editorjs_blocks("doc_test", raw)

    assert [block.type for block in blocks] == [
        "heading",
        "list_item",
        "list_item",
        "table",
        "blockquote",
    ]
    assert blocks[1].metadata["list_type"] == "ordered"
    assert blocks[3].metadata["rows"][1] == ["Температура", "37"]
    assert blocks[3].metadata["row_count"] == 2
    assert "| Параметр | Значение |" in blocks[3].metadata["markdown"]
    assert blocks[4].text == "Цитата\nАвтор"


def test_useful_text_ignores_image_urls_but_keeps_captions() -> None:
    raw = json.dumps(
        {
            "blocks": [
                {
                    "id": "img1",
                    "type": "image",
                    "data": {
                        "url": "https://example.test/image.png",
                        "caption": "Подпись к изображению",
                        "withBorder": False,
                    },
                }
            ]
        },
        ensure_ascii=False,
    )

    blocks = extract_editorjs_blocks("doc_test", raw)
    useful_text = extract_editorjs_useful_text(raw)

    assert useful_text == "Подпись к изображению"
    assert blocks[0].text == "Подпись к изображению"
    assert "https://example.test" not in useful_text
