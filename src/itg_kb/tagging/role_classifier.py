"""Assign deterministic S02A candidate roles."""

from __future__ import annotations

import re
from collections import defaultdict
from typing import Any

from itg_kb.tagging.constants import (
    ROLE_CONDITIONAL_CONTEXT,
    ROLE_CROSS_TOPIC_REFERENCE,
    ROLE_DOCUMENT_PRIMARY,
    ROLE_FACET_ONLY,
    ROLE_NEEDS_REVIEW,
    ROLE_REJECTED_GENERIC,
    ROLE_SECONDARY_TOPIC,
    ROLE_SECTION_TOPIC,
)
from itg_kb.tagging.text import safe_text


def assign_candidate_roles(
    candidates: list[dict[str, Any]], scoring_config: dict[str, Any] | None = None
) -> list[dict[str, Any]]:
    if not candidates:
        return candidates
    config = scoring_config or {}
    primary_min_score = float(config.get("primary_min_score", 0.8))
    section_min_score = float(config.get("section_min_score", 0.45))
    secondary_min_score = float(config.get("secondary_min_score", 0.32))
    needs_review_score = float(config.get("needs_review_score", 0.55))

    eligible = [
        candidate
        for candidate in candidates
        if _is_entity_candidate(candidate)
        and float(candidate.get("score", 0.0)) >= primary_min_score
    ]
    primary_id: str | None = None
    if eligible:
        primary = sorted(eligible, key=lambda row: _sort_key(row), reverse=True)[0]
        primary_id = safe_text(primary.get("candidate_id"))

    best_by_unit: dict[str, str] = {}
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for candidate in candidates:
        topic_unit_id = safe_text(candidate.get("topic_unit_id"))
        if topic_unit_id:
            grouped[topic_unit_id].append(candidate)
    for topic_unit_id, unit_candidates in grouped.items():
        unit_eligible = [
            candidate
            for candidate in unit_candidates
            if _is_entity_candidate(candidate)
            and safe_text(candidate.get("candidate_id")) != primary_id
            and float(candidate.get("score", 0.0)) >= section_min_score
            and "document_title" not in set(candidate.get("sources", []))
        ]
        if unit_eligible:
            best_by_unit[topic_unit_id] = safe_text(
                sorted(unit_eligible, key=lambda row: _sort_key(row), reverse=True)[0].get(
                    "candidate_id"
                )
            )

    for candidate in candidates:
        candidate_id = safe_text(candidate.get("candidate_id"))
        topic_unit_id = safe_text(candidate.get("topic_unit_id"))
        score = float(candidate.get("score", 0.0))
        role = ROLE_NEEDS_REVIEW
        needs_review = False
        review_reason: str | None = None
        warnings = list(candidate.get("warnings", []))

        if candidate.get("is_generic") and candidate.get("facet_type"):
            role = ROLE_FACET_ONLY
        elif candidate.get("is_generic"):
            role = ROLE_REJECTED_GENERIC
            needs_review = True
            review_reason = "generic_phrase_without_entity"
        elif candidate_id == primary_id:
            role = ROLE_DOCUMENT_PRIMARY
        elif _conditional_signal(candidate):
            role = ROLE_CONDITIONAL_CONTEXT
        elif best_by_unit.get(topic_unit_id) == candidate_id:
            role = ROLE_SECTION_TOPIC
        elif _cross_reference_signal(candidate):
            role = ROLE_CROSS_TOPIC_REFERENCE
        elif _is_entity_candidate(candidate) and score >= secondary_min_score:
            role = ROLE_SECONDARY_TOPIC
        else:
            role = ROLE_NEEDS_REVIEW
            needs_review = True
            review_reason = "low_score_or_unknown_entity"

        if safe_text(candidate.get("entity_type")) == "unknown" and role not in {
            ROLE_FACET_ONLY,
            ROLE_REJECTED_GENERIC,
        }:
            needs_review = True
            review_reason = review_reason or "unknown_entity_type"
        if score < needs_review_score and role not in {ROLE_FACET_ONLY, ROLE_REJECTED_GENERIC}:
            needs_review = True
            review_reason = review_reason or "score_below_review_threshold"
        if role == ROLE_NEEDS_REVIEW:
            needs_review = True
            review_reason = review_reason or "needs_manual_review"
        if role in {ROLE_FACET_ONLY, ROLE_REJECTED_GENERIC}:
            warnings.append("generic_facet_not_primary")

        candidate["role"] = role
        candidate["needs_review"] = needs_review
        candidate["review_reason"] = review_reason
        candidate["warnings"] = list(dict.fromkeys(warnings))
    return candidates


def _is_entity_candidate(candidate: dict[str, Any]) -> bool:
    return (
        safe_text(candidate.get("entity_type")) != "unknown"
        and not candidate.get("is_generic")
        and not candidate.get("is_facet_only")
    )


def _conditional_signal(candidate: dict[str, Any]) -> bool:
    entity_type = safe_text(candidate.get("entity_type"))
    if entity_type not in {"symptom", "contraindication", "adverse_effect"}:
        return False
    evidence = " ".join(safe_text(text) for text in candidate.get("evidence_texts", []))
    return bool(
        re.search(
            r"\b(если|при наличии|при отсутствии|только если|отсутствует)\b",
            evidence,
            re.I,
        )
    )


def _cross_reference_signal(candidate: dict[str, Any]) -> bool:
    sources = set(candidate.get("sources", []))
    if "pattern_match" not in sources:
        return False
    return safe_text(candidate.get("entity_type")) in {
        "disease",
        "medical_device",
        "diagnostic_test",
        "procedure",
        "drug_product",
        "drug_brand",
        "drug_substance",
    }


def _sort_key(candidate: dict[str, Any]) -> tuple[float, int, int]:
    sources = set(candidate.get("sources", []))
    source_bonus = 0
    if "title" in sources:
        source_bonus += 3
    if "first_heading" in sources:
        source_bonus += 2
    if "heading" in sources:
        source_bonus += 1
    return (float(candidate.get("score", 0.0)), source_bonus, -int(candidate.get("unit_index", 0)))
