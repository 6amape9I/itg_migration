"""Deterministic YAML-pattern entity classification for S02A."""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

from itg_kb.tagging.constants import ENTITY_TYPES
from itg_kb.tagging.text import normalize_surface, safe_text


@dataclass(frozen=True)
class EntityClassification:
    entity_type: str
    entity_subtype: str | None = None
    matched_pattern: str | None = None
    confidence: float = 0.0


@dataclass(frozen=True)
class EntityMention:
    surface: str
    entity_type: str
    matched_pattern: str
    start: int
    end: int


class EntityClassifier:
    def __init__(
        self,
        *,
        entity_patterns: dict[str, dict[str, list[str]]],
        drug_forms: list[str],
        strength_units: list[str],
    ) -> None:
        self.entity_patterns = entity_patterns
        self.drug_forms = [normalize_surface(form) for form in drug_forms]
        self.strength_units = [normalize_surface(unit) for unit in strength_units]

    @classmethod
    def from_config_dir(cls, config_dir: Path | str) -> "EntityClassifier":
        config_path = Path(config_dir)
        entity_payload = _read_yaml(config_path / "entity_patterns.yaml")
        forms_payload = _read_yaml(config_path / "drug_forms.yaml")
        return cls(
            entity_patterns=entity_payload.get("entity_types", {}),
            drug_forms=forms_payload.get("forms", []),
            strength_units=forms_payload.get("strength_units", []),
        )

    def classify(self, value: str) -> EntityClassification:
        surface = safe_text(value).strip()
        normalized = normalize_surface(surface)
        if not normalized:
            return EntityClassification("unknown", confidence=0.0)

        drug_match = self._drug_product_match(normalized)
        if drug_match is not None:
            return drug_match

        for entity_type, rules in self.entity_patterns.items():
            if entity_type not in ENTITY_TYPES or entity_type == "drug_product":
                continue
            keyword = self._keyword_match(normalized, rules.get("keywords", []))
            if keyword:
                return EntityClassification(
                    entity_type=entity_type,
                    matched_pattern=f"keyword:{keyword}",
                    confidence=0.78,
                )
            pattern = self._regex_match(normalized, rules.get("regex", []))
            if pattern:
                return EntityClassification(
                    entity_type=entity_type,
                    matched_pattern=f"regex:{pattern}",
                    confidence=0.66,
                )
        return EntityClassification("unknown", confidence=0.25)

    def extract_entity_mentions(self, text: str) -> list[EntityMention]:
        value = safe_text(text)
        mentions: list[EntityMention] = []
        for entity_type, rules in self.entity_patterns.items():
            for keyword in rules.get("keywords", []):
                if not keyword or len(keyword) < 4:
                    continue
                for match in re.finditer(rf"(?<!\w){re.escape(keyword)}(?!\w)", value, re.I):
                    mentions.append(
                        EntityMention(
                            surface=match.group(0),
                            entity_type=entity_type,
                            matched_pattern=f"keyword:{keyword}",
                            start=match.start(),
                            end=match.end(),
                        )
                    )
            if entity_type in {"drug_product", "symptom", "medical_device"}:
                for pattern in rules.get("regex", []):
                    for match in re.finditer(pattern, value, re.I):
                        mentions.append(
                            EntityMention(
                                surface=match.group(0),
                                entity_type=entity_type,
                                matched_pattern=f"regex:{pattern}",
                                start=match.start(),
                                end=match.end(),
                            )
                        )
        mentions.sort(key=lambda item: (item.start, -(item.end - item.start)))
        return _dedupe_overlapping_mentions(mentions)

    def _drug_product_match(self, normalized: str) -> EntityClassification | None:
        form_present = any(_contains_phrase(normalized, form) for form in self.drug_forms)
        strength_present = any(
            re.search(rf"\d+(?:[,.]\d+)?\s*{re.escape(unit)}\b", normalized)
            for unit in self.strength_units
        )
        if form_present and strength_present:
            return EntityClassification(
                entity_type="drug_product",
                matched_pattern="drug_form_strength",
                confidence=0.92,
            )
        rules = self.entity_patterns.get("drug_product", {})
        pattern = self._regex_match(normalized, rules.get("regex", []))
        if pattern:
            return EntityClassification(
                entity_type="drug_product",
                matched_pattern=f"regex:{pattern}",
                confidence=0.88,
            )
        return None

    @staticmethod
    def _keyword_match(normalized: str, keywords: list[str]) -> str | None:
        for keyword in keywords:
            normalized_keyword = normalize_surface(keyword)
            if normalized_keyword and _contains_phrase(normalized, normalized_keyword):
                return keyword
        return None

    @staticmethod
    def _regex_match(normalized: str, patterns: list[str]) -> str | None:
        for pattern in patterns:
            if re.search(pattern, normalized, flags=re.IGNORECASE):
                return pattern
        return None


def _dedupe_overlapping_mentions(mentions: list[EntityMention]) -> list[EntityMention]:
    selected: list[EntityMention] = []
    occupied: list[tuple[int, int]] = []
    for mention in mentions:
        if any(not (mention.end <= start or mention.start >= end) for start, end in occupied):
            continue
        selected.append(mention)
        occupied.append((mention.start, mention.end))
    return selected


def _contains_phrase(normalized: str, phrase: str) -> bool:
    return re.search(rf"(?<!\w){re.escape(phrase)}(?!\w)", normalized) is not None


def _read_yaml(path: Path) -> dict[str, Any]:
    return yaml.safe_load(path.read_text(encoding="utf-8")) or {}
