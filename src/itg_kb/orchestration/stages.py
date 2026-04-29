"""Implemented S00/S01 stages and stage validation."""

from __future__ import annotations

import json
import math
import shutil
from collections import Counter
from collections.abc import Callable
from html import escape
from pathlib import Path
from typing import Any

import pandas as pd

from itg_kb.core.hashing import content_hash
from itg_kb.core.ids import make_doc_id
from itg_kb.core.paths import ProjectPaths
from itg_kb.core.run_context import utc_now_iso
from itg_kb.io.csv_loader import DEFAULT_CSV_FIELD_SIZE_LIMIT, load_csv_rows
from itg_kb.io.jsonl import write_jsonl
from itg_kb.io.parquet import write_parquet_records
from itg_kb.orchestration.checkpoints import existing_outputs, missing_outputs
from itg_kb.orchestration.reports import write_json
from itg_kb.preprocess.block_extractor import extract_blocks
from itg_kb.preprocess.editorjs_parser import (
    detect_content_format,
    extract_editorjs_blocks,
    extract_editorjs_useful_text,
    find_json_markers,
    has_json_markers,
)
from itg_kb.preprocess.html_cleaner import has_html_markup, normalize_whitespace, plain_text
from itg_kb.preprocess.markdown_renderer import render_blocks_markdown, render_markdown
from itg_kb.schemas.blocks import DocumentBlock
from itg_kb.schemas.documents import DocumentRecord, NormalizedDocument

SOURCE_ID_COLUMNS = ("source_id", "id", "document_id", "uuid")
S00_DOCUMENT_COLUMNS = {
    "doc_id",
    "source_row",
    "name",
    "raw_content",
    "content_hash",
    "raw_length",
    "has_html",
    "ingest_status",
    "metadata",
}
S01_BLOCK_COLUMNS = {
    "block_id",
    "doc_id",
    "order",
    "type",
    "text",
    "html",
    "level",
    "parent_path",
    "heading_path",
    "dom_path",
    "char_start",
    "char_end",
    "text_hash",
    "metadata",
}
S01_DOCUMENT_COLUMNS = {
    "doc_id",
    "title",
    "content_hash",
    "plain_text",
    "markdown",
    "block_count",
    "normalization_status",
    "error",
    "raw_length",
    "plain_text_length",
    "markdown_length",
    "text_preservation_ratio",
    "source_format",
    "raw_format_detected",
    "useful_text_length",
    "useful_text_ratio",
    "heading_count",
    "paragraph_count",
    "list_item_count",
    "table_count",
    "unknown_count",
    "has_tables",
    "has_headings",
    "has_warnings",
    "metadata",
}
S01_BLOCK_METRIC_COLUMNS = [
    "doc_id",
    "block_id",
    "order",
    "type",
    "text_length",
    "level",
    "row_count",
    "column_count",
    "heading_path",
]


def run_init_dirs(project_root: Path | str = ".") -> list[Path]:
    paths = ProjectPaths.from_root(project_root)
    return paths.ensure_data_dirs()


def run_ingest(input_path: Path | str, project_root: Path | str = ".") -> dict[str, Any]:
    paths = ProjectPaths.from_root(project_root)
    paths.ensure_data_dirs()
    started_at = utc_now_iso()
    resolved_input = _resolve_path(paths.root, input_path)

    load_result = load_csv_rows(resolved_input)
    errors: list[dict[str, Any]] = list(load_result.errors)
    required_missing = sorted({"name", "content"} - set(load_result.fieldnames))
    if required_missing:
        report = {
            "stage": "S00",
            "status": "failed",
            "started_at": started_at,
            "finished_at": utc_now_iso(),
            "input_path": str(resolved_input),
            "total_rows": len(load_result.rows),
            "ok_rows": 0,
            "empty_content_rows": 0,
            "failed_rows": len(load_result.rows) + len(errors),
            "errors_sample": errors[:20]
            + [
                {
                    "source_row": None,
                    "error": "MissingColumns",
                    "message": ", ".join(required_missing),
                }
            ],
            "outputs": [],
        }
        write_json(paths.reports_dir / "S00_ingest_report.json", report)
        return report

    records: list[DocumentRecord] = []
    manifest: list[dict[str, Any]] = []
    ok_rows = 0
    empty_content_rows = 0
    failed_rows = len(errors)

    for row in load_result.rows:
        source_row = int(row.get("__source_row__", len(records) + failed_rows + 1))
        try:
            name = _safe_str(row.get("name"))
            raw_content = _safe_str(row.get("content"))
            source_id = _extract_source_id(row)
            hash_value = content_hash(raw_content)
            status = "empty_content" if not raw_content.strip() else "ok"
            metadata = _extract_metadata(row)
            record = DocumentRecord(
                doc_id=make_doc_id(source_id=source_id, name=name, content_hash_value=hash_value),
                source_id=source_id,
                source_row=source_row,
                name=name,
                description=_safe_optional_str(row.get("description")),
                raw_content=raw_content,
                content_hash=hash_value,
                raw_length=len(raw_content),
                has_html=has_html_markup(raw_content),
                ingest_status=status,
                metadata=metadata,
            )
            records.append(record)
            manifest.append(
                {
                    "doc_id": record.doc_id,
                    "source_row": source_row,
                    "content_hash": record.content_hash,
                    "ingest_status": record.ingest_status,
                }
            )
            if status == "empty_content":
                empty_content_rows += 1
            else:
                ok_rows += 1
        except Exception as exc:
            failed_rows += 1
            errors.append(
                {"source_row": source_row, "error": type(exc).__name__, "message": str(exc)}
            )

    document_payload = [record.model_dump(mode="json") for record in records]
    write_parquet_records(paths.ingested_dir / "documents.parquet", document_payload)
    write_jsonl(paths.ingested_dir / "documents.jsonl", document_payload)
    write_jsonl(paths.ingested_dir / "manifest.jsonl", manifest)

    outputs = [str(path) for path in paths.s00_outputs]
    report = {
        "stage": "S00",
        "status": "ok" if failed_rows == 0 else "partial",
        "started_at": started_at,
        "finished_at": utc_now_iso(),
        "input_path": str(resolved_input),
        "total_rows": len(load_result.rows) + len(load_result.errors),
        "ok_rows": ok_rows,
        "empty_content_rows": empty_content_rows,
        "failed_rows": failed_rows,
        "errors_sample": errors[:20],
        "csv_field_size_limit": DEFAULT_CSV_FIELD_SIZE_LIMIT,
        "outputs": outputs,
    }
    write_json(paths.reports_dir / "S00_ingest_report.json", report)
    return report


def run_normalize(
    project_root: Path | str = ".",
    *,
    limit: int | None = None,
    doc_id: str | None = None,
    force: bool = False,
) -> dict[str, Any]:
    paths = ProjectPaths.from_root(project_root)
    paths.ensure_data_dirs()
    started_at = utc_now_iso()
    input_path = paths.ingested_dir / "documents.parquet"
    target_doc_id = doc_id
    partial = limit is not None or target_doc_id is not None
    if _has_s01_artifacts(paths) and not force:
        report = {
            "stage": "S01",
            "status": "failed",
            "started_at": started_at,
            "finished_at": utc_now_iso(),
            "input_path": str(input_path),
            "total_documents": 0,
            "input_total_documents": 0,
            "ok_documents": 0,
            "empty_documents": 0,
            "failed_documents": 1,
            "total_blocks": 0,
            "blocks_by_type": {},
            "partial": partial,
            "limit": limit,
            "doc_id": target_doc_id,
            "force": force,
            "errors_sample": [
                {
                    "error": "ExistingS01Artifacts",
                    "message": "Use --force to overwrite S01 artifacts.",
                }
            ],
            "outputs": [],
        }
        write_json(paths.reports_dir / "S01_normalization_report.json", report)
        return report
    if force:
        _clear_s01_artifacts(paths)
        paths.ensure_data_dirs()

    if not input_path.exists():
        report = {
            "stage": "S01",
            "status": "failed",
            "started_at": started_at,
            "finished_at": utc_now_iso(),
            "input_path": str(input_path),
            "total_documents": 0,
            "input_total_documents": 0,
            "ok_documents": 0,
            "empty_documents": 0,
            "failed_documents": 1,
            "total_blocks": 0,
            "blocks_by_type": {},
            "partial": partial,
            "limit": limit,
            "doc_id": target_doc_id,
            "force": force,
            "errors_sample": [{"error": "MissingInput", "message": str(input_path)}],
            "outputs": [],
        }
        write_json(paths.reports_dir / "S01_normalization_report.json", report)
        return report

    all_rows = pd.read_parquet(input_path).to_dict(orient="records")
    rows = all_rows
    if target_doc_id is not None:
        rows = [row for row in rows if _safe_str(row.get("doc_id")) == target_doc_id]
        if not rows:
            report = {
                "stage": "S01",
                "status": "failed",
                "started_at": started_at,
                "finished_at": utc_now_iso(),
                "input_path": str(input_path),
                "total_documents": 0,
                "input_total_documents": len(all_rows),
                "ok_documents": 0,
                "empty_documents": 0,
                "failed_documents": 1,
                "total_blocks": 0,
                "blocks_by_type": {},
                "partial": True,
                "limit": limit,
                "doc_id": target_doc_id,
                "force": force,
                "errors_sample": [
                    {"error": "DocIdNotFound", "message": f"doc_id not found: {target_doc_id}"}
                ],
                "outputs": [],
            }
            write_json(paths.reports_dir / "S01_normalization_report.json", report)
            return report
    if limit is not None:
        rows = rows[: max(0, limit)]

    normalized_docs: list[NormalizedDocument] = []
    all_blocks: list[DocumentBlock] = []
    errors: list[dict[str, Any]] = []
    ok_documents = 0
    empty_documents = 0
    failed_documents = 0
    by_doc_dir = paths.normalized_dir / "by_doc"
    by_doc_dir.mkdir(parents=True, exist_ok=True)

    for row in rows:
        current_doc_id = _safe_str(row.get("doc_id"))
        try:
            raw_content = _safe_str(row.get("raw_content"))
            raw_length = _safe_int(row.get("raw_length"), default=len(raw_content))
            raw_format_detected = detect_content_format(raw_content)
            source_format = _source_format(raw_format_detected)
            if not raw_content.strip():
                empty_documents += 1
                source_format = "empty"
                raw_format_detected = "plain_text"
                normalized = NormalizedDocument(
                    doc_id=current_doc_id,
                    title=_safe_str(row.get("name")),
                    content_hash=_safe_str(row.get("content_hash")),
                    plain_text="",
                    markdown="",
                    block_count=0,
                    normalization_status="empty_content",
                    raw_length=raw_length,
                    plain_text_length=0,
                    markdown_length=0,
                    text_preservation_ratio=None,
                    source_format=source_format,
                    raw_format_detected=raw_format_detected,
                    useful_text_length=0,
                    useful_text_ratio=None,
                    metadata=_normalization_metadata(
                        source_format=source_format,
                        raw_format_detected=raw_format_detected,
                        useful_text_length=0,
                        useful_text_ratio=None,
                    ),
                )
                normalized_docs.append(normalized)
                _write_by_doc(by_doc_dir, normalized, [])
                continue

            warnings: list[dict[str, Any]] = []
            error: str | None = None
            if raw_format_detected == "editorjs_json":
                try:
                    source_useful_text = extract_editorjs_useful_text(raw_content)
                    blocks = extract_editorjs_blocks(current_doc_id, raw_content)
                except ValueError as exc:
                    blocks = []
                    direct_text = ""
                    markdown = ""
                    normalized_text = ""
                    source_useful_text = ""
                    error = str(exc)
                    warnings.append(
                        {
                            "warning": "editorjs_parse_failed",
                            "message": str(exc),
                        }
                    )
                else:
                    normalized_text = normalize_text_from_blocks(blocks)
                    direct_text = normalized_text
                    markdown = render_blocks_markdown(blocks)
            else:
                direct_text = plain_text(raw_content)
                source_useful_text = direct_text
                blocks = extract_blocks(current_doc_id, raw_content, plain_text=direct_text)
                markdown = render_blocks_markdown(blocks) or render_markdown(raw_content)
                normalized_text = normalize_text_from_blocks(blocks)

            normalization_status = "ok" if blocks else "no_blocks"
            if error is not None:
                normalization_status = "failed"
            block_counts = Counter(block.type for block in blocks)
            useful_text_length = len(normalize_whitespace(normalized_text))
            useful_text_ratio = _useful_text_ratio(useful_text_length, raw_length)
            if not blocks and error is None:
                warnings.append(
                    {
                        "warning": "no_useful_blocks",
                        "message": "No useful blocks extracted",
                    }
                )
            if useful_text_ratio is not None and useful_text_ratio < 0.10:
                warnings.append(
                    {
                        "warning": "low_useful_text_ratio",
                        "message": "Extracted useful text is less than 10% of raw content",
                        "useful_text_ratio": useful_text_ratio,
                    }
                )
            json_markers = sorted(
                set(find_json_markers(direct_text) + find_json_markers(markdown))
            )
            if json_markers:
                warnings.append(
                    {
                        "warning": "json_markers_in_normalized_text",
                        "message": "Normalized text contains JSON/service markers",
                        "markers": json_markers,
                    }
                )
            text_preservation_ratio = _text_preservation_ratio(
                normalized_text, source_useful_text
            )
            if text_preservation_ratio is not None and text_preservation_ratio < 0.80:
                warnings.append(
                    {
                        "warning": "low_text_preservation",
                        "message": "Normalized text is less than 80% of source useful text",
                        "text_preservation_ratio": text_preservation_ratio,
                    }
                )
            if raw_format_detected == "editorjs_json" and not blocks and not source_useful_text:
                text_preservation_ratio = None
            normalized = NormalizedDocument(
                doc_id=current_doc_id,
                title=_safe_str(row.get("name")),
                content_hash=_safe_str(row.get("content_hash")),
                plain_text=direct_text,
                markdown=markdown,
                block_count=len(blocks),
                normalization_status=normalization_status,
                error=error,
                raw_length=raw_length,
                plain_text_length=len(direct_text),
                markdown_length=len(markdown),
                text_preservation_ratio=text_preservation_ratio,
                source_format=source_format,
                raw_format_detected=raw_format_detected,
                useful_text_length=useful_text_length,
                useful_text_ratio=useful_text_ratio,
                heading_count=block_counts.get("heading", 0),
                paragraph_count=block_counts.get("paragraph", 0),
                list_item_count=block_counts.get("list_item", 0),
                table_count=block_counts.get("table", 0),
                unknown_count=block_counts.get("unknown", 0),
                has_tables=block_counts.get("table", 0) > 0,
                has_headings=block_counts.get("heading", 0) > 0,
                has_warnings=bool(warnings),
                metadata=_normalization_metadata(
                    source_format=source_format,
                    raw_format_detected=raw_format_detected,
                    useful_text_length=useful_text_length,
                    useful_text_ratio=useful_text_ratio,
                    warnings=warnings,
                    extra={
                        "source_useful_text_length": len(
                            normalize_whitespace(source_useful_text)
                        ),
                        "text_preservation_basis": (
                            "editorjs_useful_text"
                            if raw_format_detected == "editorjs_json"
                            else "direct_plain_text"
                        ),
                    },
                ),
            )
            normalized_docs.append(normalized)
            all_blocks.extend(blocks)
            _write_by_doc(by_doc_dir, normalized, blocks)
            if normalization_status == "ok":
                ok_documents += 1
            else:
                failed_documents += 1
                error_code = "EditorJsParseFailed" if error is not None else "NoBlocks"
                errors.append(
                    {
                        "doc_id": current_doc_id,
                        "error": error_code,
                        "message": error or "No blocks extracted",
                    }
                )
        except Exception as exc:
            failed_documents += 1
            raw_content = _safe_str(row.get("raw_content"))
            raw_format_detected = detect_content_format(raw_content)
            source_format = _source_format(raw_format_detected)
            errors.append(
                {"doc_id": current_doc_id, "error": type(exc).__name__, "message": str(exc)}
            )
            normalized_docs.append(
                NormalizedDocument(
                    doc_id=current_doc_id,
                    title=_safe_str(row.get("name")),
                    content_hash=_safe_str(row.get("content_hash")),
                    plain_text="",
                    markdown="",
                    block_count=0,
                    normalization_status="failed",
                    error=str(exc),
                    raw_length=_safe_int(row.get("raw_length"), default=0),
                    source_format=source_format,
                    raw_format_detected=raw_format_detected,
                    useful_text_length=0,
                    useful_text_ratio=None,
                    has_warnings=True,
                    metadata=_normalization_metadata(
                        source_format=source_format,
                        raw_format_detected=raw_format_detected,
                        useful_text_length=0,
                        useful_text_ratio=None,
                        warnings=[
                            {
                                "warning": "normalization_exception",
                                "message": str(exc),
                            }
                        ],
                    ),
                )
            )

    normalized_payload = [doc.model_dump(mode="json") for doc in normalized_docs]
    blocks_payload = [block.model_dump(mode="json") for block in all_blocks]
    write_parquet_records(
        paths.normalized_dir / "documents_normalized.parquet",
        normalized_payload,
        columns=list(NormalizedDocument.model_fields),
    )
    write_parquet_records(
        paths.normalized_dir / "blocks.parquet",
        blocks_payload,
        columns=list(DocumentBlock.model_fields),
    )
    write_parquet_records(
        paths.normalized_dir / "block_metrics.parquet",
        _block_metric_records(all_blocks),
        columns=S01_BLOCK_METRIC_COLUMNS,
    )

    block_counts = Counter(block.type for block in all_blocks)
    outputs = [str(path) for path in paths.s01_outputs]
    status = "partial" if partial and failed_documents == 0 else "ok"
    if failed_documents:
        status = "partial"
    report = {
        "stage": "S01",
        "status": status,
        "started_at": started_at,
        "finished_at": utc_now_iso(),
        "input_path": str(input_path),
        "total_documents": len(rows),
        "input_total_documents": len(all_rows),
        "ok_documents": ok_documents,
        "empty_documents": empty_documents,
        "failed_documents": failed_documents,
        "total_blocks": len(all_blocks),
        "blocks_by_type": dict(sorted(block_counts.items())),
        "partial": partial,
        "limit": limit,
        "doc_id": target_doc_id,
        "force": force,
        "errors_sample": errors[:20],
        "outputs": outputs,
    }
    write_json(paths.reports_dir / "S01_normalization_report.json", report)
    return report


def run_audit_normalized(
    project_root: Path | str = ".", *, sample_size: int = 100
) -> dict[str, Any]:
    paths = ProjectPaths.from_root(project_root)
    paths.ensure_data_dirs()
    normalized_path = paths.normalized_dir / "documents_normalized.parquet"
    blocks_path = paths.normalized_dir / "blocks.parquet"
    ingested_path = paths.ingested_dir / "documents.parquet"
    errors: list[dict[str, Any]] = []

    normalized = _read_required_parquet(normalized_path, errors)
    blocks = _read_required_parquet(blocks_path, errors)
    ingested = _read_required_parquet(ingested_path, errors)
    if normalized is None or blocks is None or ingested is None:
        report = {
            "stage": "S01",
            "status": "failed",
            "total_documents": 0,
            "empty_documents": 0,
            "ok_documents": 0,
            "failed_documents": 0,
            "documents_without_blocks": 0,
            "total_blocks": 0,
            "blocks_by_type": {},
            "documents_by_source_format": {},
            "editorjs_documents": 0,
            "top_documents_with_json_markers": [],
            "documents_with_tables": 0,
            "documents_with_headings": 0,
            "low_text_preservation_documents": [],
            "top_largest_documents": [],
            "top_documents_by_block_count": [],
            "errors_sample": errors[:20],
        }
        write_json(paths.reports_dir / "S01_quality_report.json", report)
        return report

    normalized = _decode_json_columns(normalized, ["metadata"])
    blocks = _decode_json_columns(blocks, ["metadata", "parent_path", "heading_path"])
    ingested = _decode_json_columns(ingested, ["metadata"])

    block_type_counts = (
        blocks["type"].fillna("").astype(str).value_counts().sort_index().to_dict()
        if "type" in blocks.columns
        else {}
    )
    source_format_counts = (
        normalized["source_format"].fillna("").astype(str).value_counts().sort_index().to_dict()
        if "source_format" in normalized.columns
        else {}
    )
    json_marker_rows = normalized[_json_marker_mask(normalized)]
    low_text_preservation = _document_records(
        normalized[
            (normalized.get("text_preservation_ratio", pd.Series(dtype=float)).fillna(1.0) < 0.8)
            & (normalized.get("normalization_status", pd.Series(dtype=str)) != "empty_content")
        ].sort_values("text_preservation_ratio", na_position="last"),
        limit=20,
    )
    documents_without_blocks = normalized[
        (normalized.get("block_count", pd.Series(dtype=int)).fillna(0).astype(int) == 0)
        & (normalized.get("normalization_status", pd.Series(dtype=str)) != "empty_content")
    ]
    error_rows = normalized[
        normalized.get("normalization_status", pd.Series(dtype=str)).isin(["failed", "no_blocks"])
        | normalized.get("error", pd.Series(dtype=object)).notna()
    ]

    sample_reasons = _select_audit_samples(normalized, sample_size=sample_size)
    _write_audit_samples(paths, sample_reasons, normalized, blocks, ingested)

    report = {
        "stage": "S01",
        "status": "ok",
        "total_documents": int(len(normalized)),
        "empty_documents": int(
            (normalized.get("normalization_status", pd.Series(dtype=str)) == "empty_content").sum()
        ),
        "ok_documents": int(
            (normalized.get("normalization_status", pd.Series(dtype=str)) == "ok").sum()
        ),
        "failed_documents": int(
            normalized.get("normalization_status", pd.Series(dtype=str))
            .isin(["failed", "no_blocks"])
            .sum()
        ),
        "documents_without_blocks": int(len(documents_without_blocks)),
        "total_blocks": int(len(blocks)),
        "blocks_by_type": block_type_counts,
        "documents_by_source_format": source_format_counts,
        "editorjs_documents": int(source_format_counts.get("editorjs", 0)),
        "top_documents_with_json_markers": _document_records(json_marker_rows, limit=20),
        "documents_with_tables": int(normalized.get("has_tables", pd.Series(dtype=bool)).sum()),
        "documents_with_headings": int(normalized.get("has_headings", pd.Series(dtype=bool)).sum()),
        "low_text_preservation_documents": low_text_preservation,
        "documents_without_blocks_sample": _document_records(documents_without_blocks, limit=20),
        "top_largest_documents": _document_records(
            normalized.sort_values("raw_length", ascending=False, na_position="last"), limit=20
        ),
        "top_documents_by_block_count": _document_records(
            normalized.sort_values("block_count", ascending=False, na_position="last"), limit=20
        ),
        "top_documents_by_unknown_count": _document_records(
            normalized.sort_values("unknown_count", ascending=False, na_position="last"), limit=20
        ),
        "sample_size_requested": sample_size,
        "sample_size_actual": len(sample_reasons),
        "errors_sample": _document_records(error_rows, limit=20),
    }
    write_json(paths.reports_dir / "S01_quality_report.json", report)
    (paths.reports_dir / "S01_quality_report.md").write_text(
        _render_quality_report_markdown(report), encoding="utf-8"
    )
    (paths.reports_dir / "S01_sample_index.md").write_text(
        _render_sample_index_markdown(paths, sample_reasons, normalized), encoding="utf-8"
    )
    return report


def pipeline_status(project_root: Path | str = ".") -> list[dict[str, Any]]:
    paths = ProjectPaths.from_root(project_root)
    paths.ensure_data_dirs()
    status = [
        {"stage": "S00", "outputs": existing_outputs(paths.s00_outputs)},
        {"stage": "S01", "outputs": existing_outputs(paths.s01_outputs)},
    ]
    write_json(paths.reports_dir / "pipeline_status.json", {"stages": status})
    return status


def validate_stage(stage: str, project_root: Path | str = ".") -> dict[str, Any]:
    paths = ProjectPaths.from_root(project_root)
    normalized_stage = stage.upper()
    if normalized_stage == "S00":
        return _validate_s00(paths)
    elif normalized_stage == "S01":
        return _validate_s01(paths)
    return {
        "stage": normalized_stage,
        "valid": False,
        "missing": [],
        "errors": [{"error": "UnknownStage", "message": f"Unknown stage: {stage}"}],
        "outputs": [],
    }


def _validate_s00(paths: ProjectPaths) -> dict[str, Any]:
    outputs = paths.s00_outputs
    missing = missing_outputs(outputs)
    errors: list[dict[str, Any]] = []

    documents_path = paths.ingested_dir / "documents.parquet"
    documents = _read_parquet_for_validation(documents_path, errors)
    if documents is not None:
        _validate_columns(documents_path, documents, S00_DOCUMENT_COLUMNS, errors)

    _validate_readable(paths.ingested_dir / "documents.jsonl", _read_jsonl_file, errors)
    _validate_readable(paths.ingested_dir / "manifest.jsonl", _read_jsonl_file, errors)
    _validate_readable(paths.reports_dir / "S00_ingest_report.json", _read_json_file, errors)

    return _validation_result("S00", outputs, missing, errors)


def _validate_s01(paths: ProjectPaths) -> dict[str, Any]:
    outputs = paths.s01_outputs
    missing = missing_outputs(outputs)
    errors: list[dict[str, Any]] = []
    warnings: list[dict[str, Any]] = []

    normalized_path = paths.normalized_dir / "documents_normalized.parquet"
    blocks_path = paths.normalized_dir / "blocks.parquet"
    ingested_path = paths.ingested_dir / "documents.parquet"
    normalization_report_path = paths.reports_dir / "S01_normalization_report.json"
    quality_report_path = paths.reports_dir / "S01_quality_report.json"

    normalized = _read_parquet_for_validation(normalized_path, errors)
    blocks = _read_parquet_for_validation(blocks_path, errors)
    ingested = _read_parquet_for_validation(ingested_path, errors)
    normalization_report = _read_json_for_validation(normalization_report_path, errors)

    if not ingested_path.exists():
        errors.append(
            {
                "artifact": str(ingested_path),
                "error": "MissingDependency",
                "message": "S01 validation requires S00 documents.parquet",
            }
        )
    if normalized is not None:
        _validate_columns(normalized_path, normalized, S01_DOCUMENT_COLUMNS, errors)
        _warn_no_blocks_documents(normalized, warnings)
    if blocks is not None:
        _validate_columns(blocks_path, blocks, S01_BLOCK_COLUMNS, errors)
    if normalized is not None and ingested is not None:
        _validate_normalized_coverage(
            ingested_path,
            normalized_path,
            ingested,
            normalized,
            errors,
            normalization_report=normalization_report,
        )
    if normalized is not None and blocks is not None:
        _validate_block_counts(normalized_path, blocks_path, normalized, blocks, errors)
        _validate_plain_text_has_no_json_markers(normalized_path, normalized, errors)
    if normalized is not None and ingested is not None and blocks is not None:
        _validate_nonempty_documents_have_blocks(
            ingested_path, blocks_path, ingested, normalized, blocks, errors
        )

    if normalization_report_path.exists() and normalization_report is None:
        pass
    elif not normalization_report_path.exists():
        pass
    if quality_report_path.exists():
        _validate_readable(quality_report_path, _read_json_file, errors)
    else:
        warnings.append(
            {
                "artifact": str(quality_report_path),
                "warning": "MissingOptionalQualityReport",
                "message": "Run audit-normalized to create S01_quality_report.json.",
            }
        )

    return _validation_result("S01", outputs, missing, errors, warnings=warnings)


def _validation_result(
    stage: str,
    outputs: list[Path],
    missing: list[str],
    errors: list[dict[str, Any]],
    *,
    warnings: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    return {
        "stage": stage,
        "valid": not missing and not errors,
        "missing": missing,
        "errors": errors,
        "warnings": warnings or [],
        "outputs": [str(path) for path in outputs],
    }


def _has_s01_artifacts(paths: ProjectPaths) -> bool:
    if any(path.exists() for path in paths.s01_outputs):
        return True
    by_doc_dir = paths.normalized_dir / "by_doc"
    return by_doc_dir.exists() and any(by_doc_dir.iterdir())


def _clear_s01_artifacts(paths: ProjectPaths) -> None:
    for path in [
        paths.normalized_dir / "documents_normalized.parquet",
        paths.normalized_dir / "blocks.parquet",
        paths.normalized_dir / "block_metrics.parquet",
        paths.reports_dir / "S01_normalization_report.json",
        paths.reports_dir / "S01_quality_report.json",
        paths.reports_dir / "S01_quality_report.md",
        paths.reports_dir / "S01_sample_index.md",
    ]:
        if path.exists():
            path.unlink()
    for directory in [paths.normalized_dir / "by_doc", paths.reports_dir / "samples"]:
        if directory.exists():
            shutil.rmtree(directory)


def normalize_text_from_blocks(blocks: list[DocumentBlock]) -> str:
    return normalize_whitespace("\n".join(block.text for block in blocks if block.text))


def _text_preservation_ratio(normalized_text: str, direct_text: str) -> float | None:
    direct_length = len(normalize_whitespace(direct_text))
    if direct_length == 0:
        return None
    return round(min(len(normalize_whitespace(normalized_text)) / direct_length, 1.0), 4)


def _source_format(raw_format_detected: str) -> str:
    return "editorjs" if raw_format_detected == "editorjs_json" else raw_format_detected


def _useful_text_ratio(useful_text_length: int, raw_length: int) -> float | None:
    if raw_length <= 0:
        return None
    return round(min(useful_text_length / raw_length, 1.0), 4)


def _normalization_metadata(
    *,
    source_format: str,
    raw_format_detected: str,
    useful_text_length: int,
    useful_text_ratio: float | None,
    warnings: list[dict[str, Any]] | None = None,
    extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    metadata: dict[str, Any] = {
        "source_format": source_format,
        "raw_format_detected": raw_format_detected,
        "useful_text_length": useful_text_length,
        "useful_text_ratio": useful_text_ratio,
    }
    if extra:
        metadata.update(extra)
    if warnings:
        metadata["warnings"] = warnings
    return metadata


def _block_metric_records(blocks: list[DocumentBlock]) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for block in blocks:
        metadata = block.metadata or {}
        records.append(
            {
                "doc_id": block.doc_id,
                "block_id": block.block_id,
                "order": block.order,
                "type": block.type,
                "text_length": len(block.text),
                "level": block.level,
                "row_count": metadata.get("row_count"),
                "column_count": metadata.get("column_count"),
                "heading_path": block.heading_path,
            }
        )
    return records


def _read_required_parquet(path: Path, errors: list[dict[str, Any]]) -> pd.DataFrame | None:
    if not path.exists():
        errors.append(
            {"artifact": str(path), "error": "MissingArtifact", "message": str(path)}
        )
        return None
    try:
        return pd.read_parquet(path)
    except Exception as exc:
        errors.append(_artifact_error(path, "UnreadableParquet", exc))
        return None


def _read_parquet_for_validation(path: Path, errors: list[dict[str, Any]]) -> pd.DataFrame | None:
    if not path.exists():
        return None
    try:
        return pd.read_parquet(path)
    except Exception as exc:
        errors.append(_artifact_error(path, "UnreadableParquet", exc))
        return None


def _validate_readable(
    path: Path, reader: Callable[[Path], object], errors: list[dict[str, Any]]
) -> None:
    if not path.exists():
        return
    try:
        reader(path)
    except Exception as exc:
        errors.append(_artifact_error(path, "UnreadableArtifact", exc))


def _validate_columns(
    path: Path,
    dataframe: pd.DataFrame,
    required_columns: set[str],
    errors: list[dict[str, Any]],
) -> None:
    missing_columns = sorted(required_columns - set(dataframe.columns))
    if missing_columns:
        errors.append(
            {
                "artifact": str(path),
                "error": "MissingColumns",
                "message": ", ".join(missing_columns),
            }
        )


def _warn_no_blocks_documents(
    normalized: pd.DataFrame, warnings: list[dict[str, Any]]
) -> None:
    if "normalization_status" not in normalized.columns:
        return
    no_blocks = normalized[
        normalized.get("normalization_status", pd.Series(dtype=str)) == "no_blocks"
    ]
    if no_blocks.empty:
        return
    warnings.append(
        {
            "warning": "NoBlocksDocuments",
            "message": f"{len(no_blocks)} normalized documents have no extracted blocks",
            "sample": _document_records(no_blocks, limit=20),
        }
    )


def _validate_normalized_coverage(
    ingested_path: Path,
    normalized_path: Path,
    ingested: pd.DataFrame,
    normalized: pd.DataFrame,
    errors: list[dict[str, Any]],
    *,
    normalization_report: dict[str, Any] | None = None,
) -> None:
    if "doc_id" not in ingested.columns:
        errors.append(
            {
                "artifact": str(ingested_path),
                "error": "MissingColumns",
                "message": "doc_id",
            }
        )
        return
    if "doc_id" not in normalized.columns:
        errors.append(
            {
                "artifact": str(normalized_path),
                "error": "MissingColumns",
                "message": "doc_id",
            }
        )
        return

    ingested_doc_ids = set(ingested["doc_id"].dropna().astype(str))
    normalized_doc_ids = set(normalized["doc_id"].dropna().astype(str))
    missing_doc_ids = sorted(ingested_doc_ids - normalized_doc_ids)
    if missing_doc_ids:
        if normalization_report and normalization_report.get("partial") is True:
            return
        errors.append(
            {
                "artifact": str(normalized_path),
                "error": "MissingNormalizedDocuments",
                "message": f"{len(missing_doc_ids)} ingested doc_id values are not normalized",
                "sample": missing_doc_ids[:20],
            }
        )


def _validate_block_counts(
    normalized_path: Path,
    blocks_path: Path,
    normalized: pd.DataFrame,
    blocks: pd.DataFrame,
    errors: list[dict[str, Any]],
) -> None:
    if "doc_id" not in normalized.columns or "block_count" not in normalized.columns:
        return
    if "doc_id" not in blocks.columns:
        return
    actual = blocks["doc_id"].dropna().astype(str).value_counts().to_dict()
    mismatches: list[dict[str, Any]] = []
    for row in normalized.to_dict(orient="records"):
        doc_id = _safe_str(row.get("doc_id"))
        expected = _safe_int(row.get("block_count"), default=0)
        found = int(actual.get(doc_id, 0))
        if expected != found:
            mismatches.append({"doc_id": doc_id, "expected": expected, "actual": found})
    if mismatches:
        errors.append(
            {
                "artifact": str(normalized_path),
                "related_artifact": str(blocks_path),
                "error": "BlockCountMismatch",
                "message": f"{len(mismatches)} normalized documents have inconsistent block_count",
                "sample": mismatches[:20],
            }
        )


def _validate_plain_text_has_no_json_markers(
    normalized_path: Path, normalized: pd.DataFrame, errors: list[dict[str, Any]]
) -> None:
    if "plain_text" not in normalized.columns or "doc_id" not in normalized.columns:
        return
    polluted: list[dict[str, Any]] = []
    for row in normalized.to_dict(orient="records"):
        markers = find_json_markers(_safe_str(row.get("plain_text")))
        if markers:
            polluted.append(
                {
                    "doc_id": _safe_str(row.get("doc_id")),
                    "markers": sorted(set(markers)),
                }
            )
    if polluted:
        errors.append(
            {
                "artifact": str(normalized_path),
                "error": "JsonMarkersInPlainText",
                "message": (
                    f"{len(polluted)} normalized documents contain JSON markers in plain_text"
                ),
                "sample": polluted[:20],
            }
        )


def _validate_nonempty_documents_have_blocks(
    ingested_path: Path,
    blocks_path: Path,
    ingested: pd.DataFrame,
    normalized: pd.DataFrame,
    blocks: pd.DataFrame,
    errors: list[dict[str, Any]],
) -> None:
    if "doc_id" not in ingested.columns or "raw_content" not in ingested.columns:
        return
    if "doc_id" not in normalized.columns:
        return
    ingested_nonempty = {
        _safe_str(row.get("doc_id"))
        for row in ingested.to_dict(orient="records")
        if _safe_str(row.get("raw_content")).strip()
    }
    normalized_ok_doc_ids = {
        _safe_str(row.get("doc_id"))
        for row in normalized.to_dict(orient="records")
        if _safe_str(row.get("normalization_status")) == "ok"
    }
    checked_doc_ids = ingested_nonempty & normalized_ok_doc_ids
    if checked_doc_ids and blocks.empty:
        errors.append(
            {
                "artifact": str(blocks_path),
                "error": "EmptyBlocksForNonemptyDocuments",
                "message": "blocks.parquet is empty while normalized nonempty documents exist",
            }
        )
        return
    actual = (
        blocks["doc_id"].dropna().astype(str).value_counts().to_dict()
        if "doc_id" in blocks.columns
        else {}
    )
    missing_blocks = sorted(doc_id for doc_id in checked_doc_ids if int(actual.get(doc_id, 0)) == 0)
    if missing_blocks:
        errors.append(
            {
                "artifact": str(blocks_path),
                "related_artifact": str(ingested_path),
                "error": "NoBlocksForNonemptyDocuments",
                "message": f"{len(missing_blocks)} nonempty normalized documents have no blocks",
                "sample": missing_blocks[:20],
            }
        )


def _read_json_for_validation(
    path: Path, errors: list[dict[str, Any]]
) -> dict[str, Any] | None:
    if not path.exists():
        return None
    try:
        payload = _read_json_file(path)
    except Exception as exc:
        errors.append(_artifact_error(path, "UnreadableArtifact", exc))
        return None
    return payload if isinstance(payload, dict) else None


def _decode_json_columns(dataframe: pd.DataFrame, columns: list[str]) -> pd.DataFrame:
    decoded = dataframe.copy()
    for column in columns:
        if column not in decoded.columns:
            continue
        decoded[column] = decoded[column].map(_decode_json_value)
    return decoded


def _decode_json_value(value: Any) -> Any:
    if value is None:
        return value
    if isinstance(value, float) and math.isnan(value):
        return None
    if isinstance(value, str):
        stripped = value.strip()
        if stripped.startswith(("{", "[")):
            try:
                return json.loads(stripped)
            except json.JSONDecodeError:
                return value
    return value


def _document_records(dataframe: pd.DataFrame, *, limit: int) -> list[dict[str, Any]]:
    fields = [
        "doc_id",
        "title",
        "source_format",
        "raw_format_detected",
        "block_count",
        "table_count",
        "unknown_count",
        "raw_length",
        "useful_text_length",
        "useful_text_ratio",
        "text_preservation_ratio",
        "normalization_status",
        "error",
    ]
    records: list[dict[str, Any]] = []
    for row in dataframe.head(limit).to_dict(orient="records"):
        records.append(
            {
                field: _json_ready(row.get(field))
                for field in fields
                if field in row and _json_ready(row.get(field)) is not None
            }
        )
    return records


def _json_marker_mask(dataframe: pd.DataFrame) -> pd.Series:
    if "plain_text" not in dataframe.columns:
        return pd.Series(False, index=dataframe.index)
    return dataframe["plain_text"].fillna("").astype(str).map(has_json_markers)


def _select_audit_samples(
    normalized: pd.DataFrame, *, sample_size: int
) -> dict[str, list[str]]:
    selected: dict[str, list[str]] = {}
    if sample_size <= 0 or normalized.empty or "doc_id" not in normalized.columns:
        return selected
    bucket_size = max(1, math.ceil(sample_size / 5))

    def add(frame: pd.DataFrame, reason: str, limit: int = bucket_size) -> None:
        added = 0
        for row in frame.to_dict(orient="records"):
            if len(selected) >= sample_size:
                return
            doc_id = _safe_str(row.get("doc_id"))
            if not doc_id:
                continue
            is_new_doc = doc_id not in selected
            selected.setdefault(doc_id, [])
            if reason not in selected[doc_id]:
                selected[doc_id].append(reason)
            if is_new_doc:
                added += 1
            if added >= limit:
                return

    add(normalized.sample(frac=1, random_state=42), "random")
    add(normalized.sort_values("raw_length", ascending=False, na_position="last"), "largest")
    add(normalized[normalized.get("has_tables", pd.Series(dtype=bool)).fillna(False)], "table")
    add(normalized.sort_values("block_count", ascending=False, na_position="last"), "many_blocks")
    suspicious = normalized[
        (normalized.get("block_count", pd.Series(dtype=int)).fillna(0).astype(int) == 0)
        | (normalized.get("text_preservation_ratio", pd.Series(dtype=float)).fillna(1.0) < 0.8)
        | (normalized.get("unknown_count", pd.Series(dtype=int)).fillna(0).astype(int) > 0)
        | _json_marker_mask(normalized)
        | normalized.get("normalization_status", pd.Series(dtype=str)).isin(["failed", "no_blocks"])
        | (
            (normalized.get("markdown", pd.Series(dtype=str)).fillna("").astype(str).str.strip()
            == "")
            & (normalized.get("raw_length", pd.Series(dtype=int)).fillna(0).astype(int) > 0)
        )
    ]
    add(suspicious, "suspicious")
    if len(selected) < sample_size:
        add(normalized.sample(frac=1, random_state=7), "fill", limit=sample_size - len(selected))
    return selected


def _write_audit_samples(
    paths: ProjectPaths,
    sample_reasons: dict[str, list[str]],
    normalized: pd.DataFrame,
    blocks: pd.DataFrame,
    ingested: pd.DataFrame,
) -> None:
    samples_dir = paths.reports_dir / "samples"
    if samples_dir.exists():
        shutil.rmtree(samples_dir)
    samples_dir.mkdir(parents=True, exist_ok=True)
    normalized_by_doc = {
        _safe_str(row.get("doc_id")): row for row in normalized.to_dict(orient="records")
    }
    ingested_by_doc = {
        _safe_str(row.get("doc_id")): row for row in ingested.to_dict(orient="records")
    }
    blocks_by_doc: dict[str, list[dict[str, Any]]] = {}
    if "doc_id" in blocks.columns:
        for row in blocks.to_dict(orient="records"):
            blocks_by_doc.setdefault(_safe_str(row.get("doc_id")), []).append(row)

    for doc_id, reasons in sample_reasons.items():
        normalized_row = normalized_by_doc.get(doc_id, {})
        ingested_row = ingested_by_doc.get(doc_id, {})
        doc_blocks = sorted(blocks_by_doc.get(doc_id, []), key=lambda row: row.get("order") or 0)
        payload = _json_ready(
            {
                "doc_id": doc_id,
                "reasons": reasons,
                "normalized": normalized_row,
                "ingested": {
                    "source_row": ingested_row.get("source_row"),
                    "name": ingested_row.get("name"),
                    "raw_length": ingested_row.get("raw_length"),
                    "content_hash": ingested_row.get("content_hash"),
                },
                "blocks": doc_blocks,
            }
        )
        (samples_dir / f"{doc_id}.json").write_text(
            json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        markdown = _safe_str(normalized_row.get("markdown"))
        (samples_dir / f"{doc_id}.md").write_text(
            markdown + ("\n" if markdown else ""), encoding="utf-8"
        )
        (samples_dir / f"{doc_id}.html").write_text(
            _render_sample_html(doc_id, normalized_row, ingested_row), encoding="utf-8"
        )


def _render_sample_html(
    doc_id: str, normalized_row: dict[str, Any], ingested_row: dict[str, Any]
) -> str:
    title = _safe_str(normalized_row.get("title") or ingested_row.get("name") or doc_id)
    markdown = _safe_str(normalized_row.get("markdown"))
    raw_content = _safe_str(ingested_row.get("raw_content"))
    lines = [
        "<!doctype html>",
        "<html>",
        "<head><meta charset=\"utf-8\"><title>" + escape(title) + "</title></head>",
        "<body>",
        "<h1>" + escape(title) + "</h1>",
        "<h2>Normalized Markdown</h2>",
        "<pre>" + escape(markdown) + "</pre>",
    ]
    if not _is_editorjs_row(normalized_row):
        lines.extend(["<h2>Raw Content</h2>", "<pre>" + escape(raw_content) + "</pre>"])
    lines.extend(["</body>", "</html>"])
    return "\n".join(lines)


def _is_editorjs_row(normalized_row: dict[str, Any]) -> bool:
    return (
        _safe_str(normalized_row.get("source_format")) == "editorjs"
        or _safe_str(normalized_row.get("raw_format_detected")) == "editorjs_json"
    )


def _render_quality_report_markdown(report: dict[str, Any]) -> str:
    lines = [
        "# S01 quality report",
        "",
        "## Summary",
        "",
        f"- Total documents: {report['total_documents']}",
        f"- Empty documents: {report['empty_documents']}",
        f"- OK documents: {report['ok_documents']}",
        f"- Failed/no-block documents: {report['failed_documents']}",
        f"- Documents without blocks: {report['documents_without_blocks']}",
        f"- Total blocks: {report['total_blocks']}",
        f"- Editor.js documents: {report.get('editorjs_documents', 0)}",
        f"- Documents with tables: {report['documents_with_tables']}",
        f"- Documents with headings: {report['documents_with_headings']}",
        "",
        "## Documents By Source Format",
        "",
    ]
    for source_format, count in report.get("documents_by_source_format", {}).items():
        lines.append(f"- {source_format}: {count}")
    lines.extend(
        [
            "",
            "## JSON Marker Documents",
            "",
            *_markdown_doc_list(report.get("top_documents_with_json_markers", [])),
            "",
            "## Blocks By Type",
            "",
        ]
    )
    for block_type, count in report.get("blocks_by_type", {}).items():
        lines.append(f"- {block_type}: {count}")
    lines.extend(["", "## Low Text Preservation", ""])
    lines.extend(_markdown_doc_list(report.get("low_text_preservation_documents", [])))
    lines.extend(["", "## Documents Without Blocks", ""])
    lines.extend(_markdown_doc_list(report.get("documents_without_blocks_sample", [])))
    lines.extend(["", "## Largest Documents", ""])
    lines.extend(_markdown_doc_list(report.get("top_largest_documents", [])))
    lines.extend(["", "## Recommendation", ""])
    if report.get("documents_without_blocks") or report.get("low_text_preservation_documents"):
        lines.append("Review S01 samples before enabling S02.")
    else:
        lines.append("S01 has no obvious parser-level blockers; sample review is still required.")
    return "\n".join(lines).rstrip() + "\n"


def _render_sample_index_markdown(
    paths: ProjectPaths, sample_reasons: dict[str, list[str]], normalized: pd.DataFrame
) -> str:
    normalized_by_doc = {
        _safe_str(row.get("doc_id")): row for row in normalized.to_dict(orient="records")
    }
    lines = ["# S01 sample index", ""]
    for doc_id, reasons in sorted(sample_reasons.items()):
        row = normalized_by_doc.get(doc_id, {})
        lines.extend(
            [
                f"## {doc_id}",
                "",
                f"- Name/source: {_safe_str(row.get('title'))}",
                f"- Reason: {', '.join(reasons)}",
                f"- Block count: {_safe_str(row.get('block_count'))}",
                f"- Table count: {_safe_str(row.get('table_count'))}",
                f"- Text preservation ratio: {_safe_str(row.get('text_preservation_ratio'))}",
                f"- Markdown: samples/{doc_id}.md",
                f"- JSON: samples/{doc_id}.json",
                f"- HTML: samples/{doc_id}.html",
                "",
            ]
        )
    if not sample_reasons:
        lines.append("No samples selected.")
    lines.append(f"Report directory: {paths.reports_dir}")
    return "\n".join(lines).rstrip() + "\n"


def _markdown_doc_list(records: list[dict[str, Any]]) -> list[str]:
    if not records:
        return ["- none"]
    return [
        "- "
        + ", ".join(f"{key}={value}" for key, value in record.items() if value not in (None, ""))
        for record in records
    ]


def _json_ready(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(key): _json_ready(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_json_ready(item) for item in value]
    try:
        if pd.isna(value):
            return None
    except (TypeError, ValueError):
        pass
    if hasattr(value, "item"):
        return value.item()
    return value


def _read_json_file(path: Path) -> object:
    return json.loads(path.read_text(encoding="utf-8"))


def _read_jsonl_file(path: Path) -> list[object]:
    records: list[object] = []
    with path.open("r", encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, start=1):
            if not line.strip():
                continue
            try:
                records.append(json.loads(line))
            except json.JSONDecodeError as exc:
                raise ValueError(f"Invalid JSONL at line {line_number}: {exc}") from exc
    return records


def _artifact_error(path: Path, error: str, exc: Exception) -> dict[str, Any]:
    return {"artifact": str(path), "error": error, "message": str(exc)}


def _resolve_path(root: Path, path: Path | str) -> Path:
    candidate = Path(path)
    return candidate if candidate.is_absolute() else root / candidate


def _safe_str(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, float) and math.isnan(value):
        return ""
    return str(value)


def _safe_int(value: Any, *, default: int = 0) -> int:
    if value is None:
        return default
    if isinstance(value, float) and math.isnan(value):
        return default
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _safe_optional_str(value: Any) -> str | None:
    text = _safe_str(value)
    return text if text else None


def _extract_source_id(row: dict[str, Any]) -> str | None:
    for column in SOURCE_ID_COLUMNS:
        value = _safe_optional_str(row.get(column))
        if value:
            return value
    return None


def _extract_metadata(row: dict[str, Any]) -> dict[str, Any]:
    known = {"name", "content", "description", "__source_row__", *SOURCE_ID_COLUMNS}
    metadata = {
        key: value for key, value in row.items() if key not in known and value not in (None, "")
    }
    extras = metadata.pop("__extra_values__", None)
    if extras:
        metadata["extra_values"] = extras
    return metadata


def _write_by_doc(
    by_doc_dir: Path, normalized: NormalizedDocument, blocks: list[DocumentBlock]
) -> None:
    payload = normalized.model_dump(mode="json")
    payload["blocks"] = [block.model_dump(mode="json") for block in blocks]
    json_path = by_doc_dir / f"{normalized.doc_id}.normalized.json"
    md_path = by_doc_dir / f"{normalized.doc_id}.md"
    structure_path = by_doc_dir / f"{normalized.doc_id}.structure.json"
    json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    md_path.write_text(
        normalized.markdown + ("\n" if normalized.markdown else ""), encoding="utf-8"
    )
    structure = {
        "doc_id": normalized.doc_id,
        "title": normalized.title,
        "normalization_status": normalized.normalization_status,
        "block_count": normalized.block_count,
        "blocks": [
            {
                "order": block.order,
                "type": block.type,
                "level": block.level,
                "text": block.text,
                "heading_path": block.heading_path,
                "dom_path": block.dom_path,
                "metadata": block.metadata,
            }
            for block in blocks
        ],
    }
    structure_path.write_text(
        json.dumps(structure, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
