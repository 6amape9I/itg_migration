"""Extract normalized document blocks from HTML or plain text."""

from __future__ import annotations

import re
from typing import Any

from bs4.element import Tag

from itg_kb.core.ids import make_block_id, slugify
from itg_kb.preprocess.html_cleaner import clean_soup, has_html_markup, normalize_whitespace
from itg_kb.preprocess.table_extractor import extract_table_rows, table_to_text
from itg_kb.schemas.blocks import DocumentBlock

BLOCK_TAGS = {"h1", "h2", "h3", "h4", "h5", "h6", "p", "li", "table", "blockquote"}


def extract_blocks(
    doc_id: str, raw_content: str, *, plain_text: str | None = None
) -> list[DocumentBlock]:
    if not raw_content.strip():
        return []
    if not has_html_markup(raw_content):
        return _extract_plain_blocks(doc_id, raw_content, plain_text=plain_text)
    blocks = _extract_html_blocks(doc_id, raw_content, plain_text=plain_text)
    if blocks:
        return blocks
    return _extract_plain_blocks(doc_id, raw_content, plain_text=plain_text)


def _extract_plain_blocks(
    doc_id: str, raw_content: str, *, plain_text: str | None = None
) -> list[DocumentBlock]:
    full_text = plain_text if plain_text is not None else normalize_whitespace(raw_content)
    cursor = 0
    blocks: list[DocumentBlock] = []
    for line in full_text.splitlines():
        text = line.strip()
        if not text:
            continue
        block_type = "list_item" if re.match(r"^([-*•]|\d+[.)])\s+", text) else "paragraph"
        blocks.append(
            _make_block(
                doc_id, len(blocks) + 1, block_type, text, cursor=cursor, full_text=full_text
            )
        )
        cursor = blocks[-1].char_end or cursor
    return blocks


def _extract_html_blocks(
    doc_id: str, raw_content: str, *, plain_text: str | None = None
) -> list[DocumentBlock]:
    soup = clean_soup(raw_content)
    body = soup.body or soup
    full_text = (
        plain_text
        if plain_text is not None
        else normalize_whitespace(body.get_text("\n", strip=True))
    )
    blocks: list[DocumentBlock] = []
    heading_stack: list[tuple[int, str]] = []
    cursor = 0

    for tag in body.find_all(BLOCK_TAGS):
        if _has_block_parent(tag):
            continue
        block_type, text, level, metadata = _block_from_tag(tag)
        if not text:
            continue
        parent_path = ["root"] + [item[1] for item in heading_stack]
        block = _make_block(
            doc_id,
            len(blocks) + 1,
            block_type,
            text,
            html=str(tag),
            level=level,
            parent_path=parent_path,
            metadata=metadata,
            cursor=cursor,
            full_text=full_text,
        )
        blocks.append(block)
        cursor = block.char_end or cursor
        if block_type == "heading" and level is not None:
            heading_stack = [
                (item_level, item_path)
                for item_level, item_path in heading_stack
                if item_level < level
            ]
            heading_stack.append((level, f"h{level}:{slugify(text)}"))
    return blocks


def _has_block_parent(tag: Tag) -> bool:
    for parent in tag.parents:
        parent_name = getattr(parent, "name", None)
        if parent_name in BLOCK_TAGS:
            return True
    return False


def _block_from_tag(tag: Tag) -> tuple[str, str, int | None, dict[str, Any]]:
    tag_name = tag.name.lower()
    if tag_name in {"h1", "h2", "h3", "h4", "h5", "h6"}:
        return "heading", normalize_whitespace(tag.get_text(" ", strip=True)), int(tag_name[1]), {}
    if tag_name == "table":
        rows = extract_table_rows(tag)
        text = table_to_text(rows) or normalize_whitespace(tag.get_text(" ", strip=True))
        return "table", text, None, {"rows": rows}
    if tag_name == "li":
        return "list_item", normalize_whitespace(tag.get_text(" ", strip=True)), None, {}
    if tag_name == "blockquote":
        return "blockquote", normalize_whitespace(tag.get_text(" ", strip=True)), None, {}
    if tag_name == "p":
        return "paragraph", normalize_whitespace(tag.get_text(" ", strip=True)), None, {}
    return "unknown", normalize_whitespace(tag.get_text(" ", strip=True)), None, {}


def _make_block(
    doc_id: str,
    order: int,
    block_type: str,
    text: str,
    *,
    html: str | None = None,
    level: int | None = None,
    parent_path: list[str] | None = None,
    metadata: dict[str, Any] | None = None,
    cursor: int,
    full_text: str,
) -> DocumentBlock:
    start = full_text.find(text, cursor)
    char_start = start if start >= 0 else None
    char_end = start + len(text) if start >= 0 else None
    return DocumentBlock(
        block_id=make_block_id(doc_id=doc_id, order=order, block_text=text),
        doc_id=doc_id,
        order=order,
        type=block_type,
        text=text,
        html=html,
        level=level,
        parent_path=parent_path or ["root"],
        char_start=char_start,
        char_end=char_end,
        metadata=metadata or {},
    )
