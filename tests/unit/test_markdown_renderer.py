from itg_kb.preprocess.markdown_renderer import render_blocks_markdown
from itg_kb.schemas.blocks import DocumentBlock


def block(order: int, block_type: str, text: str, **kwargs: object) -> DocumentBlock:
    return DocumentBlock(
        block_id=f"blk_{order}",
        doc_id="doc_test",
        order=order,
        type=block_type,
        text=text,
        text_hash=f"hash_{order}",
        **kwargs,
    )


def test_render_blocks_markdown_for_review() -> None:
    markdown = render_blocks_markdown(
        [
            block(1, "heading", "Раздел", level=2),
            block(2, "list_item", "Пункт", metadata={"list_type": "unordered"}),
            block(
                3,
                "table",
                "A | B\n1 | 2",
                metadata={"markdown": "| A | B |\n| --- | --- |\n| 1 | 2 |"},
            ),
            block(4, "blockquote", "Цитата"),
            block(5, "raw_text", "Сырой текст"),
        ]
    )

    assert "## Раздел" in markdown
    assert "- Пункт" in markdown
    assert "| A | B |" in markdown
    assert "> Цитата" in markdown
    assert "Сырой текст" in markdown
