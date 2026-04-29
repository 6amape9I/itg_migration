"""Extract normalized document blocks from HTML or plain text."""

from __future__ import annotations

import re
from typing import Any

from bs4.element import NavigableString, Tag

from itg_kb.core.hashing import stable_hash
from itg_kb.core.ids import make_block_id, slugify
from itg_kb.preprocess.html_cleaner import clean_soup, has_html_markup, normalize_whitespace
from itg_kb.preprocess.table_extractor import (
    extract_table_rows,
    infer_has_header,
    table_column_count,
    table_has_header_tag,
    table_to_markdown,
    table_to_text,
)
from itg_kb.schemas.blocks import DocumentBlock

BLOCK_TAGS = {"h1", "h2", "h3", "h4", "h5", "h6", "p", "li", "table", "blockquote"}
INLINE_MARK_TAGS = {"strong", "b", "em", "i", "u", "sup", "sub"}


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

    def append_block(
        block_type: str,
        text: str,
        *,
        html: str | None = None,
        level: int | None = None,
        metadata: dict[str, Any] | None = None,
        dom_path: str | None = None,
    ) -> None:
        nonlocal cursor, heading_stack
        if not text:
            return
        if block_type == "heading" and level is not None:
            effective_stack = [
                (item_level, item_text)
                for item_level, item_text in heading_stack
                if item_level < level
            ]
            effective_stack.append((level, text))
        else:
            effective_stack = heading_stack
        parent_path = ["root"] + [
            f"h{item_level}:{slugify(item_text)}" for item_level, item_text in effective_stack
        ]
        heading_path = [item_text for _, item_text in effective_stack]
        block = _make_block(
            doc_id,
            len(blocks) + 1,
            block_type,
            text,
            html=html,
            level=level,
            parent_path=parent_path,
            heading_path=heading_path,
            dom_path=dom_path,
            metadata=metadata,
            cursor=cursor,
            full_text=full_text,
        )
        blocks.append(block)
        cursor = block.char_end or cursor
        if block_type == "heading" and level is not None:
            heading_stack = effective_stack

    def visit(node: Tag) -> None:
        for child in node.children:
            if isinstance(child, NavigableString):
                text = normalize_whitespace(str(child))
                if text:
                    append_block(
                        "paragraph",
                        text,
                        metadata={
                            "source": "text_node",
                            "container": getattr(child.parent, "name", None),
                        },
                        dom_path=_dom_path(child.parent) if isinstance(child.parent, Tag) else None,
                    )
                continue
            if not isinstance(child, Tag):
                continue
            tag_name = child.name.lower()
            if tag_name in BLOCK_TAGS:
                block_type, text, level, metadata = _block_from_tag(child)
                append_block(
                    block_type,
                    text,
                    html=str(child),
                    level=level,
                    metadata=metadata,
                    dom_path=_dom_path(child),
                )
                if tag_name == "li":
                    _visit_nested_blocks(child, append_block)
            else:
                if _has_block_descendant(child):
                    visit(child)
                else:
                    text = normalize_whitespace(child.get_text(" ", strip=True))
                    if text:
                        append_block(
                            "paragraph",
                            text,
                            html=str(child),
                            metadata={
                                "source": "inline_or_container",
                                "container": tag_name,
                                **_inline_metadata(child),
                            },
                            dom_path=_dom_path(child),
                        )

    visit(body)
    return blocks


def _block_from_tag(tag: Tag) -> tuple[str, str, int | None, dict[str, Any]]:
    tag_name = tag.name.lower()
    if tag_name in {"h1", "h2", "h3", "h4", "h5", "h6"}:
        metadata = _inline_metadata(tag)
        text = normalize_whitespace(tag.get_text(" ", strip=True))
        return "heading", text, int(tag_name[1]), metadata
    if tag_name == "table":
        rows = extract_table_rows(tag)
        text = table_to_text(rows) or normalize_whitespace(tag.get_text(" ", strip=True))
        has_header_tag = table_has_header_tag(tag)
        return (
            "table",
            text,
            None,
            {
                "rows": rows,
                "row_count": len(rows),
                "column_count": table_column_count(rows),
                "has_header": has_header_tag or infer_has_header(rows),
                "has_header_tag": has_header_tag,
                "markdown": table_to_markdown(rows),
            },
        )
    if tag_name == "li":
        return (
            "list_item",
            _list_item_text(tag),
            None,
            {
                "list_type": _list_type(tag),
                "list_level": _list_level(tag),
                **_inline_metadata(tag),
            },
        )
    if tag_name == "blockquote":
        text = normalize_whitespace(tag.get_text(" ", strip=True))
        return "blockquote", text, None, _inline_metadata(tag)
    if tag_name == "p":
        text = normalize_whitespace(tag.get_text(" ", strip=True))
        return "paragraph", text, None, _inline_metadata(tag)
    return "unknown", normalize_whitespace(tag.get_text(" ", strip=True)), None, {}


def _visit_nested_blocks(child: Tag, append_block: Any) -> None:
    for nested in child.find_all(list(BLOCK_TAGS), recursive=True):
        if nested is child:
            continue
        nested_type, text, level, metadata = _block_from_tag(nested)
        append_block(
            nested_type,
            text,
            html=str(nested),
            level=level,
            metadata=metadata,
            dom_path=_dom_path(nested),
        )


def _has_block_descendant(tag: Tag) -> bool:
    return tag.find(list(BLOCK_TAGS)) is not None


def _inline_metadata(tag: Tag) -> dict[str, Any]:
    metadata: dict[str, Any] = {}
    inline_marks = sorted({item.name.lower() for item in tag.find_all(INLINE_MARK_TAGS)})
    if inline_marks:
        metadata["inline_marks"] = inline_marks
    links = []
    for link in tag.find_all("a"):
        href = link.get("href")
        text = normalize_whitespace(link.get_text(" ", strip=True))
        if href or text:
            links.append({"text": text, "href": href})
    if links:
        metadata["links"] = links
    return metadata


def _list_item_text(tag: Tag) -> str:
    parts: list[str] = []
    for child in tag.children:
        if isinstance(child, NavigableString):
            text = normalize_whitespace(str(child))
            if text:
                parts.append(text)
            continue
        if not isinstance(child, Tag):
            continue
        if child.name and child.name.lower() in {"ul", "ol", "table"}:
            continue
        text = normalize_whitespace(child.get_text(" ", strip=True))
        if text:
            parts.append(text)
    text = normalize_whitespace(" ".join(parts))
    return text or normalize_whitespace(tag.get_text(" ", strip=True))


def _list_type(tag: Tag) -> str:
    list_parent = tag.find_parent(["ol", "ul"])
    if list_parent is None:
        return "unknown"
    return "ordered" if list_parent.name.lower() == "ol" else "unordered"


def _list_level(tag: Tag) -> int:
    return len(tag.find_parents(["ol", "ul"]))


def _dom_path(tag: Tag | None) -> str | None:
    if tag is None:
        return None
    parts: list[str] = []
    current: Tag | None = tag
    while isinstance(current, Tag) and current.name not in {None, "[document]"}:
        name = current.name.lower()
        index = 1
        for sibling in current.previous_siblings:
            if isinstance(sibling, Tag) and sibling.name == current.name:
                index += 1
        parts.append(f"{name}[{index}]")
        current = current.parent if isinstance(current.parent, Tag) else None
    return "/".join(reversed(parts)) if parts else None


def _make_block(
    doc_id: str,
    order: int,
    block_type: str,
    text: str,
    *,
    html: str | None = None,
    level: int | None = None,
    parent_path: list[str] | None = None,
    heading_path: list[str] | None = None,
    dom_path: str | None = None,
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
        heading_path=heading_path or [],
        dom_path=dom_path,
        char_start=char_start,
        char_end=char_end,
        text_hash=stable_hash(normalize_whitespace(text), length=24),
        metadata=metadata or {},
    )
