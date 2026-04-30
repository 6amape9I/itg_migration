"""Generate S02A tag candidates with deterministic evidence."""

from __future__ import annotations

import re
from typing import Any

from itg_kb.core.hashing import stable_hash
from itg_kb.schemas.tags import CandidateEvidence, TagCandidate, TopicUnit
from itg_kb.tagging.constants import (
    DEFAULT_TITLE_BLOCK_ID,
    EVIDENCE_HEADING,
    EVIDENCE_HEADING_PATH,
    EVIDENCE_LIST_ITEM,
    EVIDENCE_PATTERN_MATCH,
    EVIDENCE_TABLE,
    EVIDENCE_TITLE,
    UNIT_DOCUMENT_TITLE,
)
from itg_kb.tagging.entity_classifier import EntityClassification, EntityClassifier
from itg_kb.tagging.entity_facet_parser import EntityFacetParser, ParsedSurface
from itg_kb.tagging.role_classifier import assign_candidate_roles
from itg_kb.tagging.scoring import confidence_bucket, minimum_score, score_candidate
from itg_kb.tagging.text import (
    ensure_string_list,
    normalize_spaces,
    normalize_surface,
    safe_int,
    safe_optional_int,
    safe_text,
)

MAX_EVIDENCE_TEXT_LENGTH = 500


def generate_candidates_for_document(
    document: dict[str, Any],
    blocks: list[dict[str, Any]],
    topic_units: list[TopicUnit],
    *,
    parser: EntityFacetParser,
    classifier: EntityClassifier,
    scoring_config: dict[str, Any],
) -> tuple[list[TagCandidate], list[CandidateEvidence]]:
    doc_id = safe_text(document.get("doc_id"))
    ordered_blocks = sorted(
        (dict(block) for block in blocks),
        key=lambda row: safe_int(row.get("order")),
    )
    for block in ordered_blocks:
        block["heading_path"] = ensure_string_list(block.get("heading_path"))

    unit_by_block_id = _unit_by_block_id(topic_units)
    title_unit = next((unit for unit in topic_units if unit.unit_type == UNIT_DOCUMENT_TITLE), None)
    drafts: dict[tuple[str, str, str, tuple[str, ...]], dict[str, Any]] = {}

    title = normalize_spaces(safe_text(document.get("title")))
    if title:
        _upsert_candidate(
            drafts,
            doc_id=doc_id,
            topic_unit=title_unit,
            parsed=parser.parse(title),
            classification=None,
            classifier=classifier,
            sources=["title", "document_title"],
            evidence={
                "block_id": DEFAULT_TITLE_BLOCK_ID,
                "evidence_type": EVIDENCE_TITLE,
                "text": title,
                "heading_path": [],
                "char_start": None,
                "char_end": None,
                "weight": 1.0,
            },
        )

    heading_blocks = [
        block for block in ordered_blocks if safe_text(block.get("type")) == "heading"
    ]
    first_heading_id = safe_text(heading_blocks[0].get("block_id")) if heading_blocks else ""
    for block in heading_blocks:
        sources = ["heading"]
        if safe_text(block.get("block_id")) == first_heading_id:
            sources.append("first_heading")
        topic_unit = unit_by_block_id.get(safe_text(block.get("block_id")))
        _upsert_candidate(
            drafts,
            doc_id=doc_id,
            topic_unit=topic_unit,
            parsed=parser.parse(safe_text(block.get("text"))),
            classification=None,
            classifier=classifier,
            sources=sources,
            evidence=_block_evidence(block, EVIDENCE_HEADING, weight=0.9),
        )

    for unit in topic_units:
        if unit.unit_type == UNIT_DOCUMENT_TITLE or not unit.title:
            continue
        evidence_block = _first_unit_block(unit, ordered_blocks)
        evidence = (
            _block_evidence(evidence_block, EVIDENCE_HEADING_PATH, weight=0.75)
            if evidence_block is not None
            else {
                "block_id": DEFAULT_TITLE_BLOCK_ID,
                "evidence_type": EVIDENCE_HEADING_PATH,
                "text": unit.title,
                "heading_path": unit.heading_path,
                "char_start": None,
                "char_end": None,
                "weight": 0.6,
            }
        )
        _upsert_candidate(
            drafts,
            doc_id=doc_id,
            topic_unit=unit,
            parsed=parser.parse(unit.title),
            classification=None,
            classifier=classifier,
            sources=["heading_path"],
            evidence=evidence,
        )

    for block in ordered_blocks:
        block_type = safe_text(block.get("type"))
        if block_type == "table":
            _add_table_candidates(drafts, doc_id, block, unit_by_block_id, parser, classifier)
        elif block_type == "list_item":
            _add_list_heading_candidate(drafts, doc_id, block, unit_by_block_id, parser, classifier)

    blocks_by_id = {safe_text(block.get("block_id")): block for block in ordered_blocks}
    for unit in topic_units:
        if unit.unit_type == UNIT_DOCUMENT_TITLE:
            continue
        unit_blocks = [
            blocks_by_id[block_id] for block_id in unit.block_ids if block_id in blocks_by_id
        ]
        _add_pattern_candidates(drafts, doc_id, unit, unit_blocks, parser, classifier)

    heading_texts = [safe_text(block.get("text")) for block in heading_blocks]
    finalized: list[dict[str, Any]] = []
    for draft in drafts.values():
        _add_frequency_features(draft, heading_texts)
        candidate_id = _candidate_id(draft)
        draft["candidate_id"] = candidate_id
        score, components = score_candidate(draft, scoring_config)
        if score < minimum_score(scoring_config):
            continue
        draft["score"] = score
        draft["score_components"] = components
        draft["confidence_bucket"] = confidence_bucket(score)
        finalized.append(draft)

    assign_candidate_roles(finalized, scoring_config)
    candidates = [_to_schema_candidate(draft) for draft in finalized]
    evidence = [
        _to_schema_evidence(draft, item) for draft in finalized for item in draft["_evidence"]
    ]
    return candidates, evidence


def _upsert_candidate(
    drafts: dict[tuple[str, str, str, tuple[str, ...]], dict[str, Any]],
    *,
    doc_id: str,
    topic_unit: TopicUnit | None,
    parsed: ParsedSurface,
    classification: EntityClassification | None,
    classifier: EntityClassifier,
    sources: list[str],
    evidence: dict[str, Any],
) -> None:
    if not parsed.surface:
        return
    classification = classification or classifier.classify(parsed.surface)
    key = (
        topic_unit.topic_unit_id if topic_unit else "",
        parsed.normalized_core_surface or parsed.normalized_surface,
        classification.entity_type,
        tuple(parsed.facets),
    )
    draft = drafts.get(key)
    if draft is None:
        draft = {
            "candidate_id": "",
            "doc_id": doc_id,
            "topic_unit_id": topic_unit.topic_unit_id if topic_unit else None,
            "unit_index": topic_unit.unit_index if topic_unit else 999,
            "surface": parsed.surface,
            "normalized_surface": parsed.normalized_surface,
            "core_surface": parsed.core_surface,
            "normalized_core_surface": parsed.normalized_core_surface,
            "entity_type": classification.entity_type,
            "entity_subtype": classification.entity_subtype,
            "facet_type": parsed.facet_type,
            "facets": parsed.facets,
            "qualifiers": parsed.qualifiers,
            "sources": [],
            "evidence_block_ids": [],
            "evidence_texts": [],
            "heading_paths": [],
            "score": 0.0,
            "score_components": {},
            "confidence_bucket": "low",
            "needs_review": False,
            "review_reason": None,
            "warnings": [],
            "metadata": {
                "parser_pattern": parsed.matched_pattern,
                "classifier_pattern": classification.matched_pattern,
                "classifier_confidence": classification.confidence,
            },
            "is_generic": parsed.is_generic,
            "is_facet_only": parsed.is_facet_only,
            "entity_pattern_match": classification.matched_pattern,
            "facet_split_confidence": parsed.split_confidence,
            "_unit_text": topic_unit.text if topic_unit else parsed.surface,
            "_evidence": [],
        }
        drafts[key] = draft

    for source in sources:
        if source not in draft["sources"]:
            draft["sources"].append(source)
    _merge_evidence(draft, evidence)


def _add_table_candidates(
    drafts: dict[tuple[str, str, str, tuple[str, ...]], dict[str, Any]],
    doc_id: str,
    block: dict[str, Any],
    unit_by_block_id: dict[str, TopicUnit],
    parser: EntityFacetParser,
    classifier: EntityClassifier,
) -> None:
    topic_unit = unit_by_block_id.get(safe_text(block.get("block_id")))
    for value in _table_header_values(block):
        parsed = parser.parse(value)
        classification = classifier.classify(parsed.surface)
        if classification.entity_type == "unknown" and not parsed.facets:
            continue
        _upsert_candidate(
            drafts,
            doc_id=doc_id,
            topic_unit=topic_unit,
            parsed=parsed,
            classification=classification,
            classifier=classifier,
            sources=["table"],
            evidence=_block_evidence(block, EVIDENCE_TABLE, weight=0.55),
        )


def _add_list_heading_candidate(
    drafts: dict[tuple[str, str, str, tuple[str, ...]], dict[str, Any]],
    doc_id: str,
    block: dict[str, Any],
    unit_by_block_id: dict[str, TopicUnit],
    parser: EntityFacetParser,
    classifier: EntityClassifier,
) -> None:
    text = safe_text(block.get("text"))
    if ":" not in text:
        return
    prefix = text.split(":", 1)[0].strip()
    if not prefix or len(prefix) > 90:
        return
    topic_unit = unit_by_block_id.get(safe_text(block.get("block_id")))
    _upsert_candidate(
        drafts,
        doc_id=doc_id,
        topic_unit=topic_unit,
        parsed=parser.parse(prefix),
        classification=None,
        classifier=classifier,
        sources=["list_item"],
        evidence=_block_evidence(block, EVIDENCE_LIST_ITEM, weight=0.55),
    )


def _add_pattern_candidates(
    drafts: dict[tuple[str, str, str, tuple[str, ...]], dict[str, Any]],
    doc_id: str,
    unit: TopicUnit,
    unit_blocks: list[dict[str, Any]],
    parser: EntityFacetParser,
    classifier: EntityClassifier,
) -> None:
    for mention in classifier.extract_entity_mentions(unit.text):
        evidence_block = _block_for_surface(unit_blocks, mention.surface) or _first_block(
            unit_blocks
        )
        if evidence_block is None:
            continue
        parsed = parser.parse(mention.surface)
        classification = EntityClassification(
            entity_type=mention.entity_type,
            matched_pattern=mention.matched_pattern,
            confidence=0.76,
        )
        _upsert_candidate(
            drafts,
            doc_id=doc_id,
            topic_unit=unit,
            parsed=parsed,
            classification=classification,
            classifier=classifier,
            sources=["pattern_match"],
            evidence=_block_evidence(evidence_block, EVIDENCE_PATTERN_MATCH, weight=0.45),
        )

    for match in re.finditer(r"\bлеч\w+\b", unit.text, flags=re.IGNORECASE):
        evidence_block = _block_for_surface(unit_blocks, match.group(0)) or _first_block(
            unit_blocks
        )
        if evidence_block is None:
            continue
        _upsert_candidate(
            drafts,
            doc_id=doc_id,
            topic_unit=unit,
            parsed=parser.parse("лечение"),
            classification=EntityClassification(
                entity_type="treatment",
                matched_pattern="facet_verb:леч",
                confidence=0.65,
            ),
            classifier=classifier,
            sources=["pattern_match"],
            evidence=_block_evidence(evidence_block, EVIDENCE_PATTERN_MATCH, weight=0.35),
        )


def _merge_evidence(draft: dict[str, Any], evidence: dict[str, Any]) -> None:
    block_id = safe_text(evidence.get("block_id"))
    text = _trim_evidence_text(safe_text(evidence.get("text")))
    heading_path = list(evidence.get("heading_path", []))
    if block_id and block_id not in draft["evidence_block_ids"]:
        draft["evidence_block_ids"].append(block_id)
    if text and text not in draft["evidence_texts"]:
        draft["evidence_texts"].append(text)
    if heading_path and heading_path not in draft["heading_paths"]:
        draft["heading_paths"].append(heading_path)
    evidence_key = (block_id, safe_text(evidence.get("evidence_type")), text)
    existing = {
        (
            safe_text(item.get("block_id")),
            safe_text(item.get("evidence_type")),
            safe_text(item.get("text")),
        )
        for item in draft["_evidence"]
    }
    if evidence_key not in existing:
        merged = dict(evidence)
        merged["text"] = text
        draft["_evidence"].append(merged)


def _add_frequency_features(draft: dict[str, Any], heading_texts: list[str]) -> None:
    needle = safe_text(draft.get("core_surface") or draft.get("surface"))
    normalized_needle = normalize_surface(needle)
    if not normalized_needle:
        draft["heading_hits"] = 0
        draft["unit_frequency"] = 0
        return
    draft["heading_hits"] = sum(
        1 for text in heading_texts if normalized_needle in normalize_surface(text)
    )
    draft["unit_frequency"] = normalize_surface(safe_text(draft.get("_unit_text"))).count(
        normalized_needle
    )


def _to_schema_candidate(draft: dict[str, Any]) -> TagCandidate:
    metadata = dict(draft.get("metadata", {}))
    metadata["is_generic"] = bool(draft.get("is_generic"))
    metadata["is_facet_only"] = bool(draft.get("is_facet_only"))
    return TagCandidate(
        candidate_id=safe_text(draft.get("candidate_id")),
        doc_id=safe_text(draft.get("doc_id")),
        topic_unit_id=draft.get("topic_unit_id"),
        role=safe_text(draft.get("role")),
        surface=safe_text(draft.get("surface")),
        normalized_surface=safe_text(draft.get("normalized_surface")),
        core_surface=draft.get("core_surface"),
        normalized_core_surface=draft.get("normalized_core_surface"),
        entity_type=safe_text(draft.get("entity_type")),
        entity_subtype=draft.get("entity_subtype"),
        facet_type=draft.get("facet_type"),
        facets=list(draft.get("facets", [])),
        qualifiers=dict(draft.get("qualifiers", {})),
        sources=list(draft.get("sources", [])),
        evidence_block_ids=list(draft.get("evidence_block_ids", [])),
        evidence_texts=list(draft.get("evidence_texts", [])),
        heading_paths=list(draft.get("heading_paths", [])),
        score=float(draft.get("score", 0.0)),
        score_components=dict(draft.get("score_components", {})),
        confidence_bucket=safe_text(draft.get("confidence_bucket")),
        needs_review=bool(draft.get("needs_review")),
        review_reason=draft.get("review_reason"),
        warnings=list(draft.get("warnings", [])),
        metadata=metadata,
    )


def _to_schema_evidence(draft: dict[str, Any], evidence: dict[str, Any]) -> CandidateEvidence:
    candidate_id = safe_text(draft.get("candidate_id"))
    evidence_id = "ev_" + stable_hash(
        {
            "candidate_id": candidate_id,
            "block_id": evidence.get("block_id"),
            "evidence_type": evidence.get("evidence_type"),
            "text": evidence.get("text"),
        },
        length=20,
    )
    return CandidateEvidence(
        evidence_id=evidence_id,
        candidate_id=candidate_id,
        doc_id=safe_text(draft.get("doc_id")),
        topic_unit_id=draft.get("topic_unit_id"),
        block_id=safe_text(evidence.get("block_id")),
        evidence_type=safe_text(evidence.get("evidence_type")),
        text=safe_text(evidence.get("text")),
        heading_path=list(evidence.get("heading_path", [])),
        char_start=evidence.get("char_start"),
        char_end=evidence.get("char_end"),
        weight=float(evidence.get("weight", 0.0)),
    )


def _candidate_id(draft: dict[str, Any]) -> str:
    return "cand_" + stable_hash(
        {
            "doc_id": draft.get("doc_id"),
            "topic_unit_id": draft.get("topic_unit_id"),
            "surface": draft.get("normalized_surface"),
            "core": draft.get("normalized_core_surface"),
            "entity_type": draft.get("entity_type"),
            "facets": draft.get("facets", []),
        },
        length=20,
    )


def _unit_by_block_id(topic_units: list[TopicUnit]) -> dict[str, TopicUnit]:
    by_block: dict[str, TopicUnit] = {}
    for unit in topic_units:
        for block_id in unit.block_ids:
            if block_id not in by_block or unit.unit_type != UNIT_DOCUMENT_TITLE:
                by_block[block_id] = unit
    return by_block


def _block_evidence(block: dict[str, Any], evidence_type: str, *, weight: float) -> dict[str, Any]:
    return {
        "block_id": safe_text(block.get("block_id")),
        "evidence_type": evidence_type,
        "text": safe_text(block.get("text")),
        "heading_path": ensure_string_list(block.get("heading_path")),
        "char_start": safe_optional_int(block.get("char_start")),
        "char_end": safe_optional_int(block.get("char_end")),
        "weight": weight,
    }


def _first_unit_block(unit: TopicUnit, blocks: list[dict[str, Any]]) -> dict[str, Any] | None:
    block_by_id = {safe_text(block.get("block_id")): block for block in blocks}
    for block_id in unit.block_ids:
        if block_id in block_by_id:
            return block_by_id[block_id]
    return None


def _first_block(blocks: list[dict[str, Any]]) -> dict[str, Any] | None:
    return blocks[0] if blocks else None


def _block_for_surface(blocks: list[dict[str, Any]], surface: str) -> dict[str, Any] | None:
    normalized = normalize_surface(surface)
    for block in blocks:
        if normalized and normalized in normalize_surface(safe_text(block.get("text"))):
            return block
    return None


def _table_header_values(block: dict[str, Any]) -> list[str]:
    metadata = block.get("metadata")
    if isinstance(metadata, str):
        metadata = {}
    rows = metadata.get("rows") if isinstance(metadata, dict) else None
    if isinstance(rows, list) and rows:
        first_row = rows[0]
        if isinstance(first_row, list):
            return [safe_text(value) for value in first_row if safe_text(value)]
    first_line = safe_text(block.get("text")).splitlines()[0:1]
    if not first_line:
        return []
    return [
        normalize_spaces(value)
        for value in re.split(r"\s*\|\s*|\t", first_line[0])
        if normalize_spaces(value)
    ]


def _trim_evidence_text(text: str) -> str:
    clean = normalize_spaces(text)
    if len(clean) <= MAX_EVIDENCE_TEXT_LENGTH:
        return clean
    return clean[:MAX_EVIDENCE_TEXT_LENGTH].rstrip() + "..."
