"""Implemented S00/S01 stages and stage validation."""

from __future__ import annotations

import json
import math
from collections import Counter
from collections.abc import Callable
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
from itg_kb.preprocess.html_cleaner import has_html_markup, plain_text
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
    "char_start",
    "char_end",
    "metadata",
}


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


def run_normalize(project_root: Path | str = ".") -> dict[str, Any]:
    paths = ProjectPaths.from_root(project_root)
    paths.ensure_data_dirs()
    started_at = utc_now_iso()
    input_path = paths.ingested_dir / "documents.parquet"
    if not input_path.exists():
        report = {
            "stage": "S01",
            "status": "failed",
            "started_at": started_at,
            "finished_at": utc_now_iso(),
            "input_path": str(input_path),
            "total_documents": 0,
            "ok_documents": 0,
            "empty_documents": 0,
            "failed_documents": 1,
            "total_blocks": 0,
            "blocks_by_type": {},
            "errors_sample": [{"error": "MissingInput", "message": str(input_path)}],
            "outputs": [],
        }
        write_json(paths.reports_dir / "S01_normalization_report.json", report)
        return report

    rows = pd.read_parquet(input_path).to_dict(orient="records")
    normalized_docs: list[NormalizedDocument] = []
    all_blocks: list[DocumentBlock] = []
    errors: list[dict[str, Any]] = []
    ok_documents = 0
    empty_documents = 0
    failed_documents = 0
    by_doc_dir = paths.normalized_dir / "by_doc"
    by_doc_dir.mkdir(parents=True, exist_ok=True)

    for row in rows:
        doc_id = _safe_str(row.get("doc_id"))
        try:
            raw_content = _safe_str(row.get("raw_content"))
            if not raw_content.strip():
                empty_documents += 1
                normalized = NormalizedDocument(
                    doc_id=doc_id,
                    title=_safe_str(row.get("name")),
                    content_hash=_safe_str(row.get("content_hash")),
                    plain_text="",
                    markdown="",
                    block_count=0,
                    normalization_status="empty_content",
                )
                normalized_docs.append(normalized)
                _write_by_doc(by_doc_dir, normalized, [])
                continue

            text = plain_text(raw_content)
            blocks = extract_blocks(doc_id, raw_content, plain_text=text)
            markdown = render_blocks_markdown(blocks) or render_markdown(raw_content)
            normalized = NormalizedDocument(
                doc_id=doc_id,
                title=_safe_str(row.get("name")),
                content_hash=_safe_str(row.get("content_hash")),
                plain_text=text,
                markdown=markdown,
                block_count=len(blocks),
                normalization_status="ok" if blocks else "no_blocks",
            )
            normalized_docs.append(normalized)
            all_blocks.extend(blocks)
            _write_by_doc(by_doc_dir, normalized, blocks)
            if blocks:
                ok_documents += 1
            else:
                failed_documents += 1
                errors.append(
                    {"doc_id": doc_id, "error": "NoBlocks", "message": "No blocks extracted"}
                )
        except Exception as exc:
            failed_documents += 1
            errors.append({"doc_id": doc_id, "error": type(exc).__name__, "message": str(exc)})
            normalized_docs.append(
                NormalizedDocument(
                    doc_id=doc_id,
                    title=_safe_str(row.get("name")),
                    content_hash=_safe_str(row.get("content_hash")),
                    plain_text="",
                    markdown="",
                    block_count=0,
                    normalization_status="failed",
                    error=str(exc),
                )
            )

    normalized_payload = [doc.model_dump(mode="json") for doc in normalized_docs]
    blocks_payload = [block.model_dump(mode="json") for block in all_blocks]
    write_parquet_records(paths.normalized_dir / "documents_normalized.parquet", normalized_payload)
    write_parquet_records(paths.normalized_dir / "blocks.parquet", blocks_payload)

    block_counts = Counter(block.type for block in all_blocks)
    outputs = [str(path) for path in paths.s01_outputs]
    report = {
        "stage": "S01",
        "status": "ok" if failed_documents == 0 else "partial",
        "started_at": started_at,
        "finished_at": utc_now_iso(),
        "input_path": str(input_path),
        "total_documents": len(rows),
        "ok_documents": ok_documents,
        "empty_documents": empty_documents,
        "failed_documents": failed_documents,
        "total_blocks": len(all_blocks),
        "blocks_by_type": dict(sorted(block_counts.items())),
        "errors_sample": errors[:20],
        "outputs": outputs,
    }
    write_json(paths.reports_dir / "S01_normalization_report.json", report)
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

    normalized_path = paths.normalized_dir / "documents_normalized.parquet"
    blocks_path = paths.normalized_dir / "blocks.parquet"
    ingested_path = paths.ingested_dir / "documents.parquet"

    normalized = _read_parquet_for_validation(normalized_path, errors)
    blocks = _read_parquet_for_validation(blocks_path, errors)
    ingested = _read_parquet_for_validation(ingested_path, errors)

    if not ingested_path.exists():
        errors.append(
            {
                "artifact": str(ingested_path),
                "error": "MissingDependency",
                "message": "S01 validation requires S00 documents.parquet",
            }
        )
    if blocks is not None:
        _validate_columns(blocks_path, blocks, S01_BLOCK_COLUMNS, errors)
    if normalized is not None and ingested is not None:
        _validate_normalized_coverage(ingested_path, normalized_path, ingested, normalized, errors)

    _validate_readable(paths.reports_dir / "S01_normalization_report.json", _read_json_file, errors)

    return _validation_result("S01", outputs, missing, errors)


def _validation_result(
    stage: str, outputs: list[Path], missing: list[str], errors: list[dict[str, Any]]
) -> dict[str, Any]:
    return {
        "stage": stage,
        "valid": not missing and not errors,
        "missing": missing,
        "errors": errors,
        "outputs": [str(path) for path in outputs],
    }


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


def _validate_normalized_coverage(
    ingested_path: Path,
    normalized_path: Path,
    ingested: pd.DataFrame,
    normalized: pd.DataFrame,
    errors: list[dict[str, Any]],
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
        errors.append(
            {
                "artifact": str(normalized_path),
                "error": "MissingNormalizedDocuments",
                "message": f"{len(missing_doc_ids)} ingested doc_id values are not normalized",
                "sample": missing_doc_ids[:20],
            }
        )


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
    json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    md_path.write_text(
        normalized.markdown + ("\n" if normalized.markdown else ""), encoding="utf-8"
    )
