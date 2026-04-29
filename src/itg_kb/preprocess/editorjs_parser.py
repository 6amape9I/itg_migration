"""Editor.js JSON detection and block extraction."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Any, Literal

from bs4 import BeautifulSoup

from itg_kb.core.hashing import stable_hash
from itg_kb.core.ids import make_block_id, slugify
from itg_kb.preprocess.html_cleaner import has_html_markup, normalize_whitespace
from itg_kb.preprocess.table_extractor import (
    infer_has_header,
    table_column_count,
    table_to_markdown,
    table_to_text,
)
from itg_kb.schemas.blocks import DocumentBlock

ContentFormat = Literal["editorjs_json", "html", "plain_text"]

EDITORJS_JSON_HINT_RE = re.compile(r'"blocks"\s*:', re.IGNORECASE)
JSON_MARKER_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = tuple(
    (marker, re.compile(rf'"{re.escape(marker)}"\s*:', re.IGNORECASE))
    for marker in (
        "blocks",
        "api",
        "styles",
        "toolbar",
        "version",
        "element",
        "readOnly",
        "sanitizer",
        "saver",
        "selection",
        "caret",
        "events",
        "i18n",
        "inlineToolbar",
        "listeners",
        "notifier",
        "tools",
        "tooltip",
        "ui",
    )
)

TECHNICAL_KEYS = {
    "api",
    "element",
    "styles",
    "toolbar",
    "version",
    "time",
    "id",
    "type",
    "readOnly",
    "sanitizer",
    "saver",
    "selection",
    "caret",
    "events",
    "i18n",
    "inlineToolbar",
    "listeners",
    "notifier",
    "tools",
    "tooltip",
    "ui",
    "nodes",
    "redactor",
    "wrapper",
    "block",
    "button",
    "inlineToolButton",
    "inlineToolButtonActive",
    "input",
    "loader",
    "settingsButton",
    "settingsButtonActive",
    "style",
    "level",
    "withHeadings",
    "withBorder",
    "withBackground",
    "stretched",
    "file",
    "url",
    "tunes",
    "inlineToolData",
    "inlineStyles",
    "markups",
    "alignment",
    "inlines",
}


@dataclass
class _BlockSpec:
    block_type: str
    text: str
    level: int | None = None
    metadata: dict[str, Any] = field(default_factory=dict)
    editorjs_block_id: str | None = None
    editorjs_type: str = "unknown"


def detect_content_format(raw_content: str | None) -> ContentFormat:
    """Detect S01's first-pass raw content format."""
    value = raw_content or ""
    stripped = value.strip()
    if stripped:
        try:
            parsed = json.loads(stripped)
        except json.JSONDecodeError:
            if stripped.startswith("{") and EDITORJS_JSON_HINT_RE.search(stripped[:4000]):
                return "editorjs_json"
        else:
            if isinstance(parsed, dict) and isinstance(parsed.get("blocks"), list):
                return "editorjs_json"
    return "html" if has_html_markup(value) else "plain_text"


def extract_editorjs_blocks(doc_id: str, raw_content: str) -> list[DocumentBlock]:
    """Extract human-readable blocks from an Editor.js document."""
    document = _load_editorjs_document(raw_content)
    specs = _extract_specs(document)
    if not specs:
        return []

    full_text = normalize_whitespace("\n".join(spec.text for spec in specs if spec.text))
    blocks: list[DocumentBlock] = []
    heading_stack: list[tuple[int, str]] = []
    cursor = 0

    for spec in specs:
        if spec.block_type == "heading" and spec.level is not None:
            effective_stack = [
                (item_level, item_text)
                for item_level, item_text in heading_stack
                if item_level < spec.level
            ]
            effective_stack.append((spec.level, spec.text))
        else:
            effective_stack = heading_stack

        parent_path = ["root"] + [
            f"h{item_level}:{slugify(item_text)}" for item_level, item_text in effective_stack
        ]
        heading_path = [item_text for _, item_text in effective_stack]
        block = _make_block(
            doc_id,
            len(blocks) + 1,
            spec.block_type,
            spec.text,
            level=spec.level,
            parent_path=parent_path,
            heading_path=heading_path,
            metadata={
                "source_format": "editorjs",
                "editorjs_type": spec.editorjs_type,
                **(
                    {"editorjs_block_id": spec.editorjs_block_id}
                    if spec.editorjs_block_id
                    else {}
                ),
                **spec.metadata,
            },
            cursor=cursor,
            full_text=full_text,
        )
        blocks.append(block)
        cursor = block.char_end or cursor
        if spec.block_type == "heading" and spec.level is not None:
            heading_stack = effective_stack

    return blocks


def extract_editorjs_useful_text(raw_content: str) -> str:
    """Extract broad human text from Editor.js data for preservation checks."""
    document = _load_editorjs_document(raw_content)
    parts: list[str] = []
    for block in document.get("blocks") or []:
        if not isinstance(block, dict):
            continue
        editorjs_type = _clean_scalar(block.get("type")) or "unknown"
        if editorjs_type == "delimiter":
            continue
        data = block.get("data") if isinstance(block.get("data"), dict) else {}
        parts.extend(_human_text_values(data))
    return normalize_whitespace("\n".join(parts))


def find_json_markers(value: str | None) -> list[str]:
    """Return suspicious JSON/service keys found in normalized human text."""
    text = value or ""
    return [marker for marker, pattern in JSON_MARKER_PATTERNS if pattern.search(text)]


def has_json_markers(value: str | None) -> bool:
    return bool(find_json_markers(value))


def _load_editorjs_document(raw_content: str) -> dict[str, Any]:
    try:
        parsed = json.loads(raw_content)
    except json.JSONDecodeError as exc:
        raise ValueError(f"Invalid Editor.js JSON: {exc}") from exc
    if not isinstance(parsed, dict) or not isinstance(parsed.get("blocks"), list):
        raise ValueError("Editor.js JSON must contain top-level blocks list")
    return parsed


def _extract_specs(document: dict[str, Any]) -> list[_BlockSpec]:
    specs: list[_BlockSpec] = []
    for block in document.get("blocks") or []:
        if not isinstance(block, dict):
            continue
        editorjs_type = _clean_scalar(block.get("type")) or "unknown"
        editorjs_block_id = _clean_scalar(block.get("id")) or None
        data = block.get("data") if isinstance(block.get("data"), dict) else {}

        if editorjs_type == "delimiter":
            continue
        if editorjs_type == "header":
            text = _clean_text(data.get("text"))
            if text:
                specs.append(
                    _BlockSpec(
                        block_type="heading",
                        text=text,
                        level=_heading_level(data.get("level")),
                        editorjs_block_id=editorjs_block_id,
                        editorjs_type=editorjs_type,
                    )
                )
            continue
        if editorjs_type == "paragraph":
            text = _clean_text(data.get("text"))
            if text:
                specs.append(
                    _BlockSpec(
                        block_type="paragraph",
                        text=text,
                        editorjs_block_id=editorjs_block_id,
                        editorjs_type=editorjs_type,
                    )
                )
            continue
        if editorjs_type == "list":
            specs.extend(_list_specs(data, editorjs_block_id, editorjs_type))
            continue
        if editorjs_type == "table":
            spec = _table_spec(data, editorjs_block_id, editorjs_type)
            if spec is not None:
                specs.append(spec)
            continue
        if editorjs_type == "quote":
            text = _quote_text(data)
            if text:
                metadata = {}
                caption = _clean_text(data.get("caption"))
                if caption:
                    metadata["quote_caption"] = caption
                specs.append(
                    _BlockSpec(
                        block_type="blockquote",
                        text=text,
                        metadata=metadata,
                        editorjs_block_id=editorjs_block_id,
                        editorjs_type=editorjs_type,
                    )
                )
            continue

        text = normalize_whitespace("\n".join(_human_text_values(data)))
        if text:
            specs.append(
                _BlockSpec(
                    block_type="unknown",
                    text=text,
                    editorjs_block_id=editorjs_block_id,
                    editorjs_type=editorjs_type,
                )
            )
    return specs


def _list_specs(
    data: dict[str, Any], editorjs_block_id: str | None, editorjs_type: str
) -> list[_BlockSpec]:
    list_type = _list_type(data.get("style"))
    items = data.get("items")
    specs: list[_BlockSpec] = []

    def append_item(item: Any, level: int) -> None:
        text = _list_item_text(item)
        if text:
            specs.append(
                _BlockSpec(
                    block_type="list_item",
                    text=text,
                    metadata={"list_type": list_type, "list_level": level},
                    editorjs_block_id=editorjs_block_id,
                    editorjs_type=editorjs_type,
                )
            )
        nested = item.get("items") if isinstance(item, dict) else None
        if isinstance(nested, list):
            for nested_item in nested:
                append_item(nested_item, level + 1)

    if isinstance(items, list):
        for item in items:
            append_item(item, 1)
    return specs


def _table_spec(
    data: dict[str, Any], editorjs_block_id: str | None, editorjs_type: str
) -> _BlockSpec | None:
    raw_rows = data.get("content") or data.get("rows")
    rows: list[list[str]] = []
    if isinstance(raw_rows, list):
        for raw_row in raw_rows:
            if isinstance(raw_row, list):
                row = [_clean_text(cell) for cell in raw_row]
            elif isinstance(raw_row, dict):
                cells = raw_row.get("cells") or raw_row.get("content")
                row = [_clean_text(cell) for cell in cells] if isinstance(cells, list) else []
            else:
                row = []
            if any(row):
                rows.append(row)
    text = table_to_text(rows)
    if not text:
        return None
    has_header = bool(data.get("withHeadings")) or infer_has_header(rows)
    return _BlockSpec(
        block_type="table",
        text=text,
        metadata={
            "rows": rows,
            "row_count": len(rows),
            "column_count": table_column_count(rows),
            "has_header": has_header,
            "has_header_tag": False,
            "markdown": table_to_markdown(rows),
        },
        editorjs_block_id=editorjs_block_id,
        editorjs_type=editorjs_type,
    )


def _quote_text(data: dict[str, Any]) -> str:
    parts = [_clean_text(data.get("text"))]
    caption = _clean_text(data.get("caption"))
    if caption:
        parts.append(caption)
    return normalize_whitespace("\n".join(part for part in parts if part))


def _list_item_text(item: Any) -> str:
    if isinstance(item, str):
        return _clean_text(item)
    if not isinstance(item, dict):
        return ""
    for key in ("content", "text"):
        text = _clean_text(item.get(key))
        if text:
            return text
    return normalize_whitespace("\n".join(_human_text_values(item)))


def _human_text_values(value: Any, *, key: str | None = None) -> list[str]:
    if key in TECHNICAL_KEYS:
        return []
    if isinstance(value, str):
        text = _clean_text(value)
        return [text] if text else []
    if isinstance(value, dict):
        texts: list[str] = []
        for child_key, child_value in value.items():
            texts.extend(_human_text_values(child_value, key=str(child_key)))
        return texts
    if isinstance(value, list):
        texts = []
        for item in value:
            texts.extend(_human_text_values(item))
        return texts
    return []


def _clean_text(value: Any) -> str:
    if value is None:
        return ""
    text = str(value)
    if has_html_markup(text):
        return _html_fragment_to_text(text)
    return normalize_whitespace(text)


def _html_fragment_to_text(value: str) -> str:
    soup = BeautifulSoup(value or "", "lxml")
    for tag in soup(["script", "style", "noscript"]):
        tag.decompose()
    for br in soup.find_all("br"):
        br.replace_with("\n")
    return normalize_whitespace(soup.get_text(" ", strip=False))


def _clean_scalar(value: Any) -> str:
    if value is None:
        return ""
    return normalize_whitespace(str(value))


def _heading_level(value: Any) -> int:
    try:
        level = int(value)
    except (TypeError, ValueError):
        return 2
    return min(max(level, 1), 6)


def _list_type(value: Any) -> str:
    style = _clean_scalar(value).lower()
    if style == "ordered":
        return "ordered"
    if style == "unordered":
        return "unordered"
    return "unknown"


def _make_block(
    doc_id: str,
    order: int,
    block_type: str,
    text: str,
    *,
    level: int | None = None,
    parent_path: list[str],
    heading_path: list[str],
    metadata: dict[str, Any],
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
        level=level,
        parent_path=parent_path,
        heading_path=heading_path,
        char_start=char_start,
        char_end=char_end,
        text_hash=stable_hash(normalize_whitespace(text), length=24),
        metadata=metadata,
    )
