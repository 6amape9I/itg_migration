"""Build S02A topic units from S01 structured blocks."""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any

from itg_kb.core.hashing import stable_hash
from itg_kb.schemas.tags import TopicUnit
from itg_kb.tagging.constants import (
    UNIT_DOCUMENT_TITLE,
    UNIT_FALLBACK_DOCUMENT,
    UNIT_HEADING_SECTION,
    UNIT_LIST,
    UNIT_PARAGRAPH_WINDOW,
    UNIT_TABLE,
)
from itg_kb.tagging.text import (
    ensure_string_list,
    normalize_spaces,
    safe_int,
    safe_optional_int,
    safe_text,
)

PARAGRAPH_WINDOW_BLOCKS = 5
PARAGRAPH_WINDOW_CHARS = 1800
SMALL_DOCUMENT_BLOCKS = 8
SMALL_DOCUMENT_CHARS = 2500
MIN_TABLE_TEXT_LENGTH = 8
MIN_LIST_ITEMS = 2


def build_topic_units_for_document(
    document: dict[str, Any], blocks: Iterable[dict[str, Any]]
) -> list[TopicUnit]:
    doc_id = safe_text(document.get("doc_id"))
    title = normalize_spaces(safe_text(document.get("title")))
    ordered_blocks = sorted(
        (dict(block) for block in blocks), key=lambda row: safe_int(row.get("order"))
    )
    for block in ordered_blocks:
        block["heading_path"] = ensure_string_list(block.get("heading_path"))

    units: list[TopicUnit] = []
    if title:
        units.append(
            _make_unit(
                doc_id=doc_id,
                unit_index=len(units),
                unit_type=UNIT_DOCUMENT_TITLE,
                title=title,
                heading_path=[],
                blocks=[],
                text=title,
                source_block_types=["title"],
                metadata={"source": "document_title"},
            )
        )

    if not ordered_blocks:
        if title:
            return units
        return [
            _make_unit(
                doc_id=doc_id,
                unit_index=0,
                unit_type=UNIT_FALLBACK_DOCUMENT,
                title=None,
                heading_path=[],
                blocks=[],
                text=safe_text(document.get("plain_text")),
                source_block_types=[],
                metadata={"source": "empty_fallback"},
                warnings=["no_blocks_for_ok_document"],
            )
        ]

    has_heading = any(safe_text(block.get("type")) == "heading" for block in ordered_blocks)
    if has_heading:
        for group in _consecutive_heading_groups(ordered_blocks):
            text = _blocks_text(group)
            if not text:
                continue
            heading_path = _group_heading_path(group)
            units.append(
                _make_unit(
                    doc_id=doc_id,
                    unit_index=len(units),
                    unit_type=UNIT_HEADING_SECTION,
                    title=heading_path[-1] if heading_path else None,
                    heading_path=heading_path,
                    blocks=group,
                    text=text,
                    source_block_types=_source_block_types(group),
                    metadata={"source": "heading_path_group"},
                )
            )
    else:
        total_text = _blocks_text(ordered_blocks)
        if len(ordered_blocks) <= SMALL_DOCUMENT_BLOCKS and len(total_text) <= SMALL_DOCUMENT_CHARS:
            units.append(
                _make_unit(
                    doc_id=doc_id,
                    unit_index=len(units),
                    unit_type=UNIT_FALLBACK_DOCUMENT,
                    title=title or None,
                    heading_path=[],
                    blocks=ordered_blocks,
                    text=total_text,
                    source_block_types=_source_block_types(ordered_blocks),
                    metadata={"source": "small_document_without_headings"},
                )
            )
        else:
            for window in _paragraph_windows(ordered_blocks):
                text = _blocks_text(window)
                if not text:
                    continue
                units.append(
                    _make_unit(
                        doc_id=doc_id,
                        unit_index=len(units),
                        unit_type=UNIT_PARAGRAPH_WINDOW,
                        title=title or None,
                        heading_path=[],
                        blocks=window,
                        text=text,
                        source_block_types=_source_block_types(window),
                        metadata={"source": "paragraph_window"},
                    )
                )

    for table_block in ordered_blocks:
        if safe_text(table_block.get("type")) != "table":
            continue
        table_text = normalize_spaces(safe_text(table_block.get("text")))
        if len(table_text) < MIN_TABLE_TEXT_LENGTH:
            continue
        heading_path = ensure_string_list(table_block.get("heading_path"))
        units.append(
            _make_unit(
                doc_id=doc_id,
                unit_index=len(units),
                unit_type=UNIT_TABLE,
                title=heading_path[-1] if heading_path else title or None,
                heading_path=heading_path,
                blocks=[table_block],
                text=safe_text(table_block.get("text")),
                source_block_types=["table"],
                metadata={"source": "table_block"},
            )
        )

    for list_group in _list_groups(ordered_blocks):
        heading_path = _group_heading_path(list_group)
        units.append(
            _make_unit(
                doc_id=doc_id,
                unit_index=len(units),
                unit_type=UNIT_LIST,
                title=heading_path[-1] if heading_path else title or None,
                heading_path=heading_path,
                blocks=list_group,
                text=_blocks_text(list_group),
                source_block_types=["list_item"],
                metadata={"source": "consecutive_list_items"},
            )
        )

    return units


def _consecutive_heading_groups(blocks: list[dict[str, Any]]) -> list[list[dict[str, Any]]]:
    groups: list[list[dict[str, Any]]] = []
    current_key: tuple[str, ...] | None = None
    current: list[dict[str, Any]] = []
    for block in blocks:
        heading_path = tuple(ensure_string_list(block.get("heading_path")))
        key = heading_path if heading_path else ("__root__",)
        if current and key != current_key:
            groups.append(current)
            current = []
        current_key = key
        current.append(block)
    if current:
        groups.append(current)
    return groups


def _paragraph_windows(blocks: list[dict[str, Any]]) -> list[list[dict[str, Any]]]:
    windows: list[list[dict[str, Any]]] = []
    current: list[dict[str, Any]] = []
    current_chars = 0
    for block in blocks:
        block_text = safe_text(block.get("text"))
        if current and (
            len(current) >= PARAGRAPH_WINDOW_BLOCKS
            or current_chars + len(block_text) > PARAGRAPH_WINDOW_CHARS
        ):
            windows.append(current)
            current = []
            current_chars = 0
        current.append(block)
        current_chars += len(block_text)
    if current:
        windows.append(current)
    return windows


def _list_groups(blocks: list[dict[str, Any]]) -> list[list[dict[str, Any]]]:
    groups: list[list[dict[str, Any]]] = []
    current: list[dict[str, Any]] = []
    current_heading_path: tuple[str, ...] | None = None
    for block in blocks:
        block_type = safe_text(block.get("type"))
        heading_path = tuple(ensure_string_list(block.get("heading_path")))
        if block_type == "list_item":
            if current and heading_path != current_heading_path:
                if len(current) >= MIN_LIST_ITEMS:
                    groups.append(current)
                current = []
            current_heading_path = heading_path
            current.append(block)
        else:
            if len(current) >= MIN_LIST_ITEMS:
                groups.append(current)
            current = []
            current_heading_path = None
    if len(current) >= MIN_LIST_ITEMS:
        groups.append(current)
    return groups


def _make_unit(
    *,
    doc_id: str,
    unit_index: int,
    unit_type: str,
    title: str | None,
    heading_path: list[str],
    blocks: list[dict[str, Any]],
    text: str,
    source_block_types: list[str],
    metadata: dict[str, Any],
    warnings: list[str] | None = None,
) -> TopicUnit:
    block_ids = [
        safe_text(block.get("block_id")) for block in blocks if safe_text(block.get("block_id"))
    ]
    char_starts = [
        value
        for value in (safe_optional_int(block.get("char_start")) for block in blocks)
        if value is not None
    ]
    char_ends = [
        value
        for value in (safe_optional_int(block.get("char_end")) for block in blocks)
        if value is not None
    ]
    clean_text = text.strip()
    unit_hash = stable_hash(
        {
            "doc_id": doc_id,
            "unit_index": unit_index,
            "unit_type": unit_type,
            "title": title,
            "block_ids": block_ids,
            "text": clean_text[:500],
        },
        length=20,
    )
    return TopicUnit(
        topic_unit_id=f"tu_{unit_hash}",
        doc_id=doc_id,
        unit_index=unit_index,
        unit_type=unit_type,
        title=title,
        heading_path=heading_path,
        block_ids=block_ids,
        text=clean_text,
        text_length=len(clean_text),
        char_start=min(char_starts) if char_starts else None,
        char_end=max(char_ends) if char_ends else None,
        source_block_types=source_block_types,
        metadata=metadata,
        warnings=warnings or [],
    )


def _blocks_text(blocks: list[dict[str, Any]]) -> str:
    return "\n".join(
        safe_text(block.get("text")).strip()
        for block in blocks
        if safe_text(block.get("text")).strip()
    )


def _group_heading_path(blocks: list[dict[str, Any]]) -> list[str]:
    for block in blocks:
        heading_path = ensure_string_list(block.get("heading_path"))
        if heading_path:
            return heading_path
    return []


def _source_block_types(blocks: list[dict[str, Any]]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for block in blocks:
        block_type = safe_text(block.get("type"))
        if block_type and block_type not in seen:
            seen.add(block_type)
            result.append(block_type)
    return result
