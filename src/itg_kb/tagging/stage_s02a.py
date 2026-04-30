"""S02A deterministic tagging stage writer and audit utilities."""

from __future__ import annotations

import json
import shutil
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

import pandas as pd
import yaml

from itg_kb.core.paths import ProjectPaths
from itg_kb.core.run_context import utc_now_iso
from itg_kb.io.jsonl import write_jsonl
from itg_kb.io.parquet import write_parquet_records
from itg_kb.orchestration.reports import write_json
from itg_kb.schemas.tags import CandidateEvidence, DocTopicSummary, TagCandidate, TopicUnit
from itg_kb.tagging.candidate_generator import generate_candidates_for_document
from itg_kb.tagging.constants import (
    ROLE_CROSS_TOPIC_REFERENCE,
    ROLE_DOCUMENT_PRIMARY,
    ROLE_FACET_ONLY,
    ROLE_REJECTED_GENERIC,
    ROLE_SECTION_TOPIC,
    tagging_config_dir,
)
from itg_kb.tagging.entity_classifier import EntityClassifier
from itg_kb.tagging.entity_facet_parser import EntityFacetParser
from itg_kb.tagging.scoring import load_scoring_config
from itg_kb.tagging.text import decode_json_value, safe_text
from itg_kb.tagging.topic_units import build_topic_units_for_document


def run_tag_candidates_s02a(
    project_root: Path | str = ".",
    *,
    stage: str = "S02A",
    limit: int | None = None,
    doc_id: str | None = None,
    force: bool = False,
) -> dict[str, Any]:
    normalized_stage = stage.upper()
    paths = ProjectPaths.from_root(project_root)
    paths.ensure_data_dirs()
    started_at = utc_now_iso()
    partial = limit is not None or doc_id is not None
    if normalized_stage != "S02A":
        return _failed_report(
            paths,
            started_at,
            partial=partial,
            limit=limit,
            doc_id=doc_id,
            force=force,
            errors=[
                {"error": "UnsupportedStage", "message": f"Unsupported tagging stage: {stage}"}
            ],
        )
    if _has_s02a_artifacts(paths) and not force:
        return _failed_report(
            paths,
            started_at,
            partial=partial,
            limit=limit,
            doc_id=doc_id,
            force=force,
            errors=[
                {
                    "error": "ExistingS02AArtifacts",
                    "message": "Use --force to overwrite S02A artifacts.",
                }
            ],
        )
    if force:
        _clear_s02a_artifacts(paths)
        paths.ensure_data_dirs()

    documents_path = paths.normalized_dir / "documents_normalized.parquet"
    blocks_path = paths.normalized_dir / "blocks.parquet"
    block_metrics_path = paths.normalized_dir / "block_metrics.parquet"
    missing_inputs = [
        str(path) for path in [documents_path, blocks_path, block_metrics_path] if not path.exists()
    ]
    if missing_inputs:
        return _failed_report(
            paths,
            started_at,
            partial=partial,
            limit=limit,
            doc_id=doc_id,
            force=force,
            errors=[{"error": "MissingInput", "message": ", ".join(missing_inputs)}],
        )

    all_documents = _decode_dataframe(pd.read_parquet(documents_path), ["metadata"])
    blocks = _decode_dataframe(
        pd.read_parquet(blocks_path), ["metadata", "parent_path", "heading_path"]
    )
    selected_documents = all_documents
    if doc_id is not None:
        selected_documents = selected_documents[
            selected_documents.get("doc_id", pd.Series(dtype=str)).astype(str) == doc_id
        ]
        if selected_documents.empty:
            return _failed_report(
                paths,
                started_at,
                partial=True,
                limit=limit,
                doc_id=doc_id,
                force=force,
                errors=[{"error": "DocIdNotFound", "message": f"doc_id not found: {doc_id}"}],
            )
    if limit is not None:
        selected_documents = selected_documents.head(max(0, limit))

    skipped_no_blocks = selected_documents[
        selected_documents.get("normalization_status", pd.Series(dtype=str)).astype(str)
        == "no_blocks"
    ].copy()
    ok_documents = selected_documents[
        selected_documents.get("normalization_status", pd.Series(dtype=str)).astype(str) == "ok"
    ].copy()
    selected_doc_ids = set(ok_documents.get("doc_id", pd.Series(dtype=str)).astype(str))
    selected_blocks = blocks[
        blocks.get("doc_id", pd.Series(dtype=str)).astype(str).isin(selected_doc_ids)
    ]
    blocks_by_doc: dict[str, list[dict[str, Any]]] = {}
    for row in selected_blocks.to_dict(orient="records"):
        blocks_by_doc.setdefault(safe_text(row.get("doc_id")), []).append(row)

    config_dir = tagging_config_dir(paths.root)
    parser = EntityFacetParser.from_config_dir(config_dir)
    classifier = EntityClassifier.from_config_dir(config_dir)
    scoring_config = load_scoring_config(config_dir)
    review_config = _read_yaml(config_dir / "review.yaml")
    review_top_k = int(review_config.get("review_top_k_per_doc", 10))

    all_topic_units: list[TopicUnit] = []
    all_candidates: list[TagCandidate] = []
    all_evidence: list[CandidateEvidence] = []
    doc_summaries: list[DocTopicSummary] = []
    doc_jsonl_records: list[dict[str, Any]] = []
    ambiguity_records: list[dict[str, Any]] = []
    documents_with_many_candidates: list[str] = []

    by_doc_dir = paths.tagging_dir / "by_doc"
    by_doc_dir.mkdir(parents=True, exist_ok=True)

    for document in ok_documents.to_dict(orient="records"):
        current_doc_id = safe_text(document.get("doc_id"))
        doc_blocks = blocks_by_doc.get(current_doc_id, [])
        topic_units = build_topic_units_for_document(document, doc_blocks)
        candidates, evidence = generate_candidates_for_document(
            document,
            doc_blocks,
            topic_units,
            parser=parser,
            classifier=classifier,
            scoring_config=scoring_config,
        )
        warnings = _document_warnings(
            topic_unit_count=len(topic_units),
            candidate_count=len(candidates),
            review_config=review_config,
        )
        if "many_candidates_in_document" in warnings:
            documents_with_many_candidates.append(current_doc_id)
        candidate_ids_by_role = _candidate_ids_by_role(candidates)
        top_candidate_ids = [
            candidate.candidate_id
            for candidate in sorted(candidates, key=lambda item: item.score, reverse=True)[
                :review_top_k
            ]
        ]
        needs_review, review_reason = _doc_review_state(candidates, warnings)
        if not candidates:
            needs_review = True
            review_reason = "document_without_candidates"
            ambiguity_records.append(
                {
                    "doc_id": current_doc_id,
                    "title": safe_text(document.get("title")),
                    "reason": "document_without_candidates",
                    "topic_unit_count": len(topic_units),
                }
            )
        elif needs_review:
            ambiguity_records.append(
                {
                    "doc_id": current_doc_id,
                    "title": safe_text(document.get("title")),
                    "reason": review_reason,
                    "topic_unit_count": len(topic_units),
                    "candidate_count_total": len(candidates),
                    "needs_review_candidate_ids": [
                        candidate.candidate_id for candidate in candidates if candidate.needs_review
                    ][:20],
                }
            )

        summary = DocTopicSummary(
            doc_id=current_doc_id,
            title=safe_text(document.get("title")),
            normalization_status=safe_text(document.get("normalization_status")),
            topic_unit_count=len(topic_units),
            candidate_count_total=len(candidates),
            primary_candidate_ids=candidate_ids_by_role[ROLE_DOCUMENT_PRIMARY],
            top_candidate_ids_for_review=top_candidate_ids,
            facet_only_count=len(candidate_ids_by_role[ROLE_FACET_ONLY]),
            cross_topic_reference_count=len(candidate_ids_by_role[ROLE_CROSS_TOPIC_REFERENCE]),
            needs_review=needs_review,
            review_reason=review_reason,
            warnings=warnings,
        )
        doc_summaries.append(summary)
        all_topic_units.extend(topic_units)
        all_candidates.extend(candidates)
        all_evidence.extend(evidence)

        by_doc_payload = {
            "doc_id": current_doc_id,
            "title": summary.title,
            "summary": summary.model_dump(mode="json"),
            "topic_units": [unit.model_dump(mode="json") for unit in topic_units],
            "candidates": [candidate.model_dump(mode="json") for candidate in candidates],
            "evidence": [item.model_dump(mode="json") for item in evidence],
        }
        (by_doc_dir / f"{current_doc_id}.tag_candidates.json").write_text(
            json.dumps(by_doc_payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        doc_jsonl_records.append(
            {
                "doc_id": current_doc_id,
                "title": summary.title,
                "topic_unit_count": summary.topic_unit_count,
                "candidate_count_total": summary.candidate_count_total,
                "candidate_ids": [candidate.candidate_id for candidate in candidates],
                "top_candidate_ids_for_review": summary.top_candidate_ids_for_review,
                "warnings": summary.warnings,
            }
        )

    _write_stage_artifacts(
        paths,
        topic_units=all_topic_units,
        candidates=all_candidates,
        evidence=all_evidence,
        doc_summaries=doc_summaries,
        doc_jsonl_records=doc_jsonl_records,
        ambiguity_records=ambiguity_records,
        skipped_no_blocks=skipped_no_blocks,
    )
    _write_review_outputs(
        paths,
        doc_summaries=doc_summaries,
        candidates=all_candidates,
        topic_units=all_topic_units,
        sample_size=int(review_config.get("review_sample_size", 300)),
        review_top_k=review_top_k,
    )
    report = _build_report(
        paths,
        started_at=started_at,
        total_documents=len(all_documents),
        processed_documents=len(ok_documents),
        skipped_no_blocks=len(skipped_no_blocks),
        topic_units=all_topic_units,
        candidates=all_candidates,
        doc_summaries=doc_summaries,
        documents_with_many_candidates=documents_with_many_candidates,
        partial=partial,
        limit=limit,
        doc_id=doc_id,
        force=force,
    )
    write_json(paths.reports_dir / "S02A_tagging_report.json", report)
    (paths.reports_dir / "S02A_tagging_report.md").write_text(
        _render_report_markdown(report), encoding="utf-8"
    )
    return report


def audit_tag_candidates_s02a(
    project_root: Path | str = ".", *, sample_size: int = 300
) -> dict[str, Any]:
    paths = ProjectPaths.from_root(project_root)
    errors: list[dict[str, Any]] = []
    candidates = _read_s02a_parquet(paths.tagging_dir / "tag_candidates.parquet", errors)
    topic_units = _read_s02a_parquet(paths.tagging_dir / "topic_units.parquet", errors)
    doc_topics = _read_s02a_parquet(paths.tagging_dir / "doc_topics.parquet", errors)
    if errors or candidates is None or topic_units is None or doc_topics is None:
        return {
            "stage": "S02A",
            "status": "failed",
            "sample_size_requested": sample_size,
            "sample_size_actual": 0,
            "errors_sample": errors[:20],
        }
    config_dir = tagging_config_dir(paths.root)
    review_config = _read_yaml(config_dir / "review.yaml")
    review_top_k = int(review_config.get("review_top_k_per_doc", 10))
    candidate_models = [
        TagCandidate(**_json_ready(row)) for row in candidates.to_dict(orient="records")
    ]
    topic_unit_models = [
        TopicUnit(**_json_ready(row)) for row in topic_units.to_dict(orient="records")
    ]
    doc_summary_models = [
        DocTopicSummary(**_json_ready(row)) for row in doc_topics.to_dict(orient="records")
    ]
    review_rows, distribution_rows = _write_review_outputs(
        paths,
        doc_summaries=doc_summary_models,
        candidates=candidate_models,
        topic_units=topic_unit_models,
        sample_size=sample_size,
        review_top_k=review_top_k,
    )
    return {
        "stage": "S02A",
        "status": "ok",
        "sample_size_requested": sample_size,
        "sample_size_actual": len(review_rows),
        "distribution_rows": len(distribution_rows),
        "outputs": [
            str(paths.reports_dir / "S02A_review_sample.csv"),
            str(paths.reports_dir / "S02A_candidate_distribution.csv"),
        ],
        "errors_sample": [],
    }


def has_s02a_artifacts(paths: ProjectPaths) -> bool:
    return _has_s02a_artifacts(paths)


def clear_s02a_artifacts(paths: ProjectPaths) -> None:
    _clear_s02a_artifacts(paths)


def _write_stage_artifacts(
    paths: ProjectPaths,
    *,
    topic_units: list[TopicUnit],
    candidates: list[TagCandidate],
    evidence: list[CandidateEvidence],
    doc_summaries: list[DocTopicSummary],
    doc_jsonl_records: list[dict[str, Any]],
    ambiguity_records: list[dict[str, Any]],
    skipped_no_blocks: pd.DataFrame,
) -> None:
    write_parquet_records(
        paths.tagging_dir / "topic_units.parquet",
        [unit.model_dump(mode="json") for unit in topic_units],
        columns=list(TopicUnit.model_fields),
    )
    write_parquet_records(
        paths.tagging_dir / "tag_candidates.parquet",
        [candidate.model_dump(mode="json") for candidate in candidates],
        columns=list(TagCandidate.model_fields),
    )
    write_parquet_records(
        paths.tagging_dir / "candidate_evidence.parquet",
        [item.model_dump(mode="json") for item in evidence],
        columns=list(CandidateEvidence.model_fields),
    )
    write_parquet_records(
        paths.tagging_dir / "doc_topics.parquet",
        [summary.model_dump(mode="json") for summary in doc_summaries],
        columns=list(DocTopicSummary.model_fields),
    )
    write_jsonl(paths.tagging_dir / "doc_tag_candidates.jsonl", doc_jsonl_records)
    write_jsonl(paths.tagging_dir / "ambiguity_queue.jsonl", ambiguity_records)
    skipped_columns = [
        "doc_id",
        "title",
        "normalization_status",
        "block_count",
        "error",
        "raw_length",
    ]
    skipped = skipped_no_blocks.reindex(columns=skipped_columns)
    skipped.to_csv(paths.reports_dir / "S02A_no_blocks_skipped.csv", index=False)


def _write_review_outputs(
    paths: ProjectPaths,
    *,
    doc_summaries: list[DocTopicSummary],
    candidates: list[TagCandidate],
    topic_units: list[TopicUnit],
    sample_size: int,
    review_top_k: int,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    title_by_doc = {summary.doc_id: summary.title for summary in doc_summaries}
    unit_by_id = {unit.topic_unit_id: unit for unit in topic_units}
    candidates_by_doc: dict[str, list[TagCandidate]] = {}
    for candidate in candidates:
        candidates_by_doc.setdefault(candidate.doc_id, []).append(candidate)

    review_pool: list[TagCandidate] = []
    for doc_candidates in candidates_by_doc.values():
        sorted_candidates = sorted(
            doc_candidates,
            key=lambda item: (item.needs_review, item.score),
            reverse=True,
        )
        review_pool.extend(sorted_candidates[:review_top_k])
    review_pool = sorted(
        review_pool, key=lambda item: (item.needs_review, item.score), reverse=True
    )
    if sample_size >= 0:
        review_pool = review_pool[:sample_size]
    review_rows = [
        _review_row(candidate, title_by_doc=title_by_doc, unit_by_id=unit_by_id)
        for candidate in review_pool
    ]
    review_columns = [
        "doc_id",
        "title",
        "topic_unit_id",
        "heading_path",
        "candidate_id",
        "surface",
        "core_surface",
        "entity_type",
        "role",
        "facet_type",
        "facets",
        "score",
        "confidence_bucket",
        "evidence_text",
        "warnings",
        "needs_review",
        "review_reason",
    ]
    pd.DataFrame(review_rows, columns=review_columns).to_csv(
        paths.reports_dir / "S02A_review_sample.csv", index=False
    )

    distribution_rows = [
        _distribution_row(summary, candidates_by_doc.get(summary.doc_id, []))
        for summary in doc_summaries
    ]
    distribution_columns = [
        "doc_id",
        "title",
        "topic_unit_count",
        "candidate_count_total",
        "primary_candidate_count",
        "section_candidate_count",
        "cross_reference_count",
        "facet_only_count",
        "needs_review_count",
        "warnings",
    ]
    pd.DataFrame(distribution_rows, columns=distribution_columns).to_csv(
        paths.reports_dir / "S02A_candidate_distribution.csv", index=False
    )
    return review_rows, distribution_rows


def _build_report(
    paths: ProjectPaths,
    *,
    started_at: str,
    total_documents: int,
    processed_documents: int,
    skipped_no_blocks: int,
    topic_units: list[TopicUnit],
    candidates: list[TagCandidate],
    doc_summaries: list[DocTopicSummary],
    documents_with_many_candidates: list[str],
    partial: bool,
    limit: int | None,
    doc_id: str | None,
    force: bool,
) -> dict[str, Any]:
    role_counts = Counter(candidate.role for candidate in candidates)
    entity_counts = Counter(candidate.entity_type for candidate in candidates)
    confidence_counts = Counter(candidate.confidence_bucket for candidate in candidates)
    rejected_generic = Counter(
        candidate.normalized_surface
        for candidate in candidates
        if candidate.role == ROLE_REJECTED_GENERIC
    )
    facets = Counter(facet for candidate in candidates for facet in candidate.facets)
    documents_without_candidates = [
        summary.doc_id for summary in doc_summaries if summary.candidate_count_total == 0
    ]
    documents_needing_review = [summary.doc_id for summary in doc_summaries if summary.needs_review]
    return {
        "stage": "S02A",
        "status": "partial" if partial else "ok",
        "started_at": started_at,
        "finished_at": utc_now_iso(),
        "total_documents": total_documents,
        "processed_documents": processed_documents,
        "skipped_no_blocks": skipped_no_blocks,
        "total_topic_units": len(topic_units),
        "total_candidates": len(candidates),
        "candidates_by_role": dict(sorted(role_counts.items())),
        "candidates_by_entity_type": dict(sorted(entity_counts.items())),
        "candidates_by_confidence_bucket": dict(sorted(confidence_counts.items())),
        "documents_without_candidates": documents_without_candidates,
        "documents_needing_review": documents_needing_review,
        "documents_with_many_candidates": documents_with_many_candidates,
        "top_generic_rejected_phrases": rejected_generic.most_common(20),
        "top_facets": facets.most_common(20),
        "partial": partial,
        "limit": limit,
        "doc_id": doc_id,
        "force": force,
        "outputs": [str(path) for path in paths.s02a_outputs],
        "errors_sample": [],
    }


def _failed_report(
    paths: ProjectPaths,
    started_at: str,
    *,
    partial: bool,
    limit: int | None,
    doc_id: str | None,
    force: bool,
    errors: list[dict[str, Any]],
) -> dict[str, Any]:
    report = {
        "stage": "S02A",
        "status": "failed",
        "started_at": started_at,
        "finished_at": utc_now_iso(),
        "total_documents": 0,
        "processed_documents": 0,
        "skipped_no_blocks": 0,
        "total_topic_units": 0,
        "total_candidates": 0,
        "candidates_by_role": {},
        "candidates_by_entity_type": {},
        "candidates_by_confidence_bucket": {},
        "documents_without_candidates": [],
        "documents_needing_review": [],
        "documents_with_many_candidates": [],
        "top_generic_rejected_phrases": [],
        "top_facets": [],
        "partial": partial,
        "limit": limit,
        "doc_id": doc_id,
        "force": force,
        "outputs": [],
        "errors_sample": errors[:20],
    }
    write_json(paths.reports_dir / "S02A_tagging_report.json", report)
    return report


def _render_report_markdown(report: dict[str, Any]) -> str:
    lines = [
        "# S02A tagging report",
        "",
        "## Summary",
        "",
        f"- Status: {report['status']}",
        f"- Total documents: {report['total_documents']}",
        f"- Processed documents: {report['processed_documents']}",
        f"- Skipped no-block documents: {report['skipped_no_blocks']}",
        f"- Topic units: {report['total_topic_units']}",
        f"- Candidates: {report['total_candidates']}",
        f"- Documents without candidates: {len(report['documents_without_candidates'])}",
        f"- Documents needing review: {len(report['documents_needing_review'])}",
        f"- Documents with many candidates: {len(report['documents_with_many_candidates'])}",
        "",
        "## Candidates By Role",
        "",
    ]
    lines.extend(_counter_lines(report.get("candidates_by_role", {})))
    lines.extend(["", "## Candidates By Entity Type", ""])
    lines.extend(_counter_lines(report.get("candidates_by_entity_type", {})))
    lines.extend(["", "## Confidence Buckets", ""])
    lines.extend(_counter_lines(report.get("candidates_by_confidence_bucket", {})))
    lines.extend(["", "## Top Facets", ""])
    lines.extend(_pair_lines(report.get("top_facets", [])))
    lines.extend(["", "## Top Generic Rejected Phrases", ""])
    lines.extend(_pair_lines(report.get("top_generic_rejected_phrases", [])))
    lines.extend(["", "## Outputs", ""])
    lines.extend(f"- {path}" for path in report.get("outputs", []))
    return "\n".join(lines).rstrip() + "\n"


def _document_warnings(
    *, topic_unit_count: int, candidate_count: int, review_config: dict[str, Any]
) -> list[str]:
    warnings: list[str] = []
    if topic_unit_count > int(review_config.get("large_doc_topic_unit_warning_threshold", 50)):
        warnings.append("long_document_many_topic_units")
    if candidate_count > int(review_config.get("many_candidates_warning_threshold", 50)):
        warnings.append("many_candidates_in_document")
    if candidate_count > int(review_config.get("candidate_explosion_warning_threshold", 200)):
        warnings.append("candidate_explosion_risk")
    return warnings


def _doc_review_state(
    candidates: list[TagCandidate], warnings: list[str]
) -> tuple[bool, str | None]:
    if warnings:
        return True, ",".join(warnings)
    if any(candidate.needs_review for candidate in candidates):
        return True, "candidate_needs_review"
    if candidates and not any(candidate.role == ROLE_DOCUMENT_PRIMARY for candidate in candidates):
        return True, "no_document_primary_candidate"
    return False, None


def _candidate_ids_by_role(candidates: list[TagCandidate]) -> dict[str, list[str]]:
    grouped: dict[str, list[str]] = {}
    for candidate in candidates:
        grouped.setdefault(candidate.role, []).append(candidate.candidate_id)
    return defaultdict(list, grouped)


def _review_row(
    candidate: TagCandidate,
    *,
    title_by_doc: dict[str, str],
    unit_by_id: dict[str, TopicUnit],
) -> dict[str, Any]:
    unit = unit_by_id.get(candidate.topic_unit_id or "")
    heading_path = unit.heading_path if unit else []
    return {
        "doc_id": candidate.doc_id,
        "title": title_by_doc.get(candidate.doc_id, ""),
        "topic_unit_id": candidate.topic_unit_id,
        "heading_path": " > ".join(heading_path),
        "candidate_id": candidate.candidate_id,
        "surface": candidate.surface,
        "core_surface": candidate.core_surface,
        "entity_type": candidate.entity_type,
        "role": candidate.role,
        "facet_type": candidate.facet_type,
        "facets": ";".join(candidate.facets),
        "score": candidate.score,
        "confidence_bucket": candidate.confidence_bucket,
        "evidence_text": candidate.evidence_texts[0] if candidate.evidence_texts else "",
        "warnings": ";".join(candidate.warnings),
        "needs_review": candidate.needs_review,
        "review_reason": candidate.review_reason,
    }


def _distribution_row(summary: DocTopicSummary, candidates: list[TagCandidate]) -> dict[str, Any]:
    role_counts = Counter(candidate.role for candidate in candidates)
    return {
        "doc_id": summary.doc_id,
        "title": summary.title,
        "topic_unit_count": summary.topic_unit_count,
        "candidate_count_total": summary.candidate_count_total,
        "primary_candidate_count": role_counts.get(ROLE_DOCUMENT_PRIMARY, 0),
        "section_candidate_count": role_counts.get(ROLE_SECTION_TOPIC, 0),
        "cross_reference_count": role_counts.get(ROLE_CROSS_TOPIC_REFERENCE, 0),
        "facet_only_count": role_counts.get(ROLE_FACET_ONLY, 0),
        "needs_review_count": sum(1 for candidate in candidates if candidate.needs_review),
        "warnings": ";".join(summary.warnings),
    }


def _read_s02a_parquet(path: Path, errors: list[dict[str, Any]]) -> pd.DataFrame | None:
    if not path.exists():
        errors.append({"artifact": str(path), "error": "MissingArtifact", "message": str(path)})
        return None
    try:
        return _decode_dataframe(pd.read_parquet(path), list(_json_columns_for_path(path)))
    except Exception as exc:
        errors.append({"artifact": str(path), "error": "UnreadableParquet", "message": str(exc)})
        return None


def _decode_dataframe(dataframe: pd.DataFrame, columns: list[str]) -> pd.DataFrame:
    decoded = dataframe.copy()
    for column in columns:
        if column in decoded.columns:
            decoded[column] = decoded[column].map(decode_json_value)
    return decoded


def _json_columns_for_path(path: Path) -> set[str]:
    if path.name == "tag_candidates.parquet":
        return {
            "facets",
            "qualifiers",
            "sources",
            "evidence_block_ids",
            "evidence_texts",
            "heading_paths",
            "score_components",
            "warnings",
            "metadata",
        }
    if path.name == "topic_units.parquet":
        return {"heading_path", "block_ids", "source_block_types", "metadata", "warnings"}
    if path.name == "doc_topics.parquet":
        return {
            "primary_candidate_ids",
            "top_candidate_ids_for_review",
            "warnings",
        }
    return set()


def _has_s02a_artifacts(paths: ProjectPaths) -> bool:
    if any(path.exists() for path in paths.s02a_outputs):
        return True
    by_doc_dir = paths.tagging_dir / "by_doc"
    return by_doc_dir.exists() and any(by_doc_dir.iterdir())


def _clear_s02a_artifacts(paths: ProjectPaths) -> None:
    for path in paths.s02a_outputs:
        if path.exists():
            path.unlink()
    by_doc_dir = paths.tagging_dir / "by_doc"
    if by_doc_dir.exists():
        shutil.rmtree(by_doc_dir)


def _read_yaml(path: Path) -> dict[str, Any]:
    return yaml.safe_load(path.read_text(encoding="utf-8")) or {}


def _counter_lines(values: dict[str, Any]) -> list[str]:
    if not values:
        return ["- none"]
    return [f"- {key}: {value}" for key, value in values.items()]


def _pair_lines(values: list[list[Any]] | list[tuple[Any, Any]]) -> list[str]:
    if not values:
        return ["- none"]
    return [f"- {key}: {value}" for key, value in values]


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
