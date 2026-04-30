"""Deterministic candidate scoring for S02A."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from itg_kb.tagging.text import normalize_surface, safe_int, safe_text


def load_scoring_config(config_dir: Path | str) -> dict[str, Any]:
    return yaml.safe_load((Path(config_dir) / "scoring.yaml").read_text(encoding="utf-8")) or {}


def score_candidate(
    candidate: dict[str, Any], scoring_config: dict[str, Any] | None = None
) -> tuple[float, dict[str, float]]:
    config = scoring_config or {}
    weights = config.get("components", {})
    sources = set(candidate.get("sources", []))
    entity_type = safe_text(candidate.get("entity_type"))
    normalized = normalize_surface(safe_text(candidate.get("surface")))
    normalized_core = normalize_surface(safe_text(candidate.get("core_surface")))
    is_generic = bool(candidate.get("is_generic"))
    facets = list(candidate.get("facets", []))
    unit_index = safe_int(candidate.get("unit_index"), default=999)

    components: dict[str, float] = {}
    if entity_type != "unknown" and not is_generic:
        components["base_entity"] = _weight(weights, "base_entity")
    elif facets:
        components["base_generic_facet"] = _weight(weights, "base_generic_facet")

    if "title" in sources:
        components["title_entity_match"] = _weight(weights, "title_entity_match")
    if "first_heading" in sources or "heading" in sources:
        components["heading_entity_match"] = _weight(weights, "heading_entity_match")
    if "heading_path" in sources:
        components["heading_path_match"] = _weight(weights, "heading_path_match")
    if "pattern_match" in sources:
        components["cross_reference_signal"] = _weight(weights, "cross_reference_signal")

    if unit_index <= 1:
        components["topic_unit_position"] = _weight(weights, "topic_unit_position")
    elif unit_index <= 5:
        components["topic_unit_position"] = round(_weight(weights, "topic_unit_position") * 0.5, 4)

    if candidate.get("entity_pattern_match"):
        components["entity_pattern_match"] = _weight(weights, "entity_pattern_match")
    if candidate.get("facet_split_confidence"):
        components["facet_split_confidence"] = round(
            _weight(weights, "facet_split_confidence")
            * float(candidate.get("facet_split_confidence", 0.0)),
            4,
        )
    heading_hits = safe_int(candidate.get("heading_hits"), default=0)
    if heading_hits:
        components["frequency_in_headings"] = round(
            min(_weight(weights, "frequency_in_headings"), heading_hits * 0.025),
            4,
        )
    unit_frequency = safe_int(candidate.get("unit_frequency"), default=0)
    if unit_frequency > 1:
        components["frequency_in_unit_text"] = round(
            min(_weight(weights, "frequency_in_unit_text"), (unit_frequency - 1) * 0.02),
            4,
        )

    if is_generic:
        components["generic_penalty"] = _weight(weights, "generic_penalty")
    if candidate.get("facet_type") == "dosage" and entity_type == "unknown":
        components["dosage_only_penalty"] = _weight(weights, "dosage_only_penalty")
    if len(normalized_core or normalized) <= 2:
        components["too_short_penalty"] = _weight(weights, "too_short_penalty")

    score = max(0.0, min(1.0, sum(components.values())))
    return round(score, 4), components


def confidence_bucket(score: float) -> str:
    if score >= 0.80:
        return "high"
    if score >= 0.55:
        return "medium"
    return "low"


def minimum_score(scoring_config: dict[str, Any] | None = None) -> float:
    return float((scoring_config or {}).get("minimum_score", 0.12))


def _weight(weights: dict[str, Any], name: str) -> float:
    return float(weights.get(name, 0.0))
