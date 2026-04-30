from itg_kb.tagging.topic_units import build_topic_units_for_document


def test_topic_units_preserve_headings_tables_lists_and_block_ids() -> None:
    document = {"doc_id": "doc_test", "title": "Гастрит: симптомы и лечение"}
    blocks = [
        _block("b1", 1, "heading", "Гастрит", ["Гастрит"]),
        _block("b2", 2, "paragraph", "Гастрит - воспаление.", ["Гастрит"]),
        _block("b3", 3, "list_item", "Боль", ["Гастрит"]),
        _block("b4", 4, "list_item", "Тошнота", ["Гастрит"]),
        _block("b5", 5, "table", "Параметр | Значение\nТемпература | 37", ["Гастрит"]),
    ]

    units = build_topic_units_for_document(document, blocks)

    unit_types = {unit.unit_type for unit in units}
    assert {"document_title", "heading_section", "list_unit", "table_unit"} <= unit_types
    heading = next(unit for unit in units if unit.unit_type == "heading_section")
    assert heading.heading_path == ["Гастрит"]
    assert {"b1", "b2", "b3", "b4", "b5"} <= set(heading.block_ids)
    table = next(unit for unit in units if unit.unit_type == "table_unit")
    assert table.block_ids == ["b5"]


def test_topic_units_create_paragraph_windows_without_headings() -> None:
    document = {"doc_id": "doc_test", "title": "Документ без заголовков"}
    blocks = [
        _block(f"b{index}", index, "paragraph", f"Абзац {index} " + ("текст " * 80), [])
        for index in range(1, 10)
    ]

    units = build_topic_units_for_document(document, blocks)

    paragraph_windows = [unit for unit in units if unit.unit_type == "paragraph_window"]
    assert len(paragraph_windows) >= 2
    assert {block_id for unit in paragraph_windows for block_id in unit.block_ids} == {
        f"b{index}" for index in range(1, 10)
    }


def _block(
    block_id: str, order: int, block_type: str, text: str, heading_path: list[str]
) -> dict[str, object]:
    return {
        "block_id": block_id,
        "doc_id": "doc_test",
        "order": order,
        "type": block_type,
        "text": text,
        "heading_path": heading_path,
        "char_start": order * 10,
        "char_end": order * 10 + len(text),
        "metadata": {},
    }
