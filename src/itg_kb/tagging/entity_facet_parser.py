"""Deterministic entity/facet parsing for S02A candidate surfaces."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

from itg_kb.tagging.text import normalize_spaces, normalize_surface, safe_text, strip_list_marker


@dataclass(frozen=True)
class ParsedSurface:
    surface: str
    normalized_surface: str
    core_surface: str | None = None
    normalized_core_surface: str | None = None
    facet_type: str | None = None
    facets: list[str] = field(default_factory=list)
    qualifiers: dict[str, str] = field(default_factory=dict)
    is_generic: bool = False
    is_facet_only: bool = False
    split_confidence: float = 0.0
    matched_pattern: str | None = None


class EntityFacetParser:
    def __init__(
        self,
        *,
        facets: dict[str, list[str]],
        generic_phrases: list[str],
        drug_forms: list[str] | None = None,
        strength_units: list[str] | None = None,
    ) -> None:
        self.facets = {
            facet: [normalize_surface(phrase) for phrase in phrases]
            for facet, phrases in facets.items()
        }
        self.generic_phrases = [normalize_surface(phrase) for phrase in generic_phrases]
        self.drug_forms = [normalize_surface(form) for form in drug_forms or []]
        self.strength_units = [normalize_surface(unit) for unit in strength_units or []]

    @classmethod
    def from_config_dir(cls, config_dir: Path | str) -> "EntityFacetParser":
        config_path = Path(config_dir)
        facet_payload = _read_yaml(config_path / "facet_patterns.yaml")
        generic_payload = _read_yaml(config_path / "generic_blocklist.yaml")
        forms_payload = _read_yaml(config_path / "drug_forms.yaml")
        return cls(
            facets=facet_payload.get("facets", {}),
            generic_phrases=generic_payload.get("generic_phrases", []),
            drug_forms=forms_payload.get("forms", []),
            strength_units=forms_payload.get("strength_units", []),
        )

    def parse(self, value: str) -> ParsedSurface:
        original = strip_list_marker(safe_text(value))
        text = _strip_wrapping_punctuation(original)
        if not text:
            return self._parsed("", is_generic=True, is_facet_only=True, matched_pattern="empty")

        instruction = self._parse_instruction(text)
        if instruction is not None:
            return instruction

        delimited = self._parse_delimited(text)
        if delimited is not None:
            return delimited

        prefixed = self._parse_facet_prefix(text)
        if prefixed is not None:
            return prefixed

        facets = self.match_facets(text)
        is_generic = self.is_generic_phrase(text)
        return self._parsed(
            text,
            facets=facets,
            is_generic=is_generic,
            is_facet_only=is_generic,
            split_confidence=0.35 if facets else 0.0,
            matched_pattern="generic_phrase" if is_generic else None,
        )

    def match_facets(self, value: str) -> list[str]:
        normalized = normalize_surface(value)
        matched: list[str] = []
        for facet, phrases in self.facets.items():
            for phrase in phrases:
                if phrase and _contains_phrase(normalized, phrase):
                    matched.append(facet)
                    break
        return matched

    def is_generic_phrase(self, value: str) -> bool:
        normalized = normalize_surface(value)
        if not normalized:
            return True
        if normalized in self.generic_phrases:
            return True
        return any(_contains_phrase(normalized, phrase) for phrase in self.generic_phrases)

    def _parse_delimited(self, text: str) -> ParsedSurface | None:
        for separator, pattern_name in (
            (":", "entity_colon_facet"),
            (" — ", "entity_dash_facet"),
            (" - ", "entity_dash_facet"),
            (". ", "entity_dot_facet"),
        ):
            if separator not in text:
                continue
            left, right = [part.strip() for part in text.split(separator, 1)]
            if not left or not right:
                continue
            right_facets = self.match_facets(right)
            left_facets = self.match_facets(left)
            left_generic = self.is_generic_phrase(left)
            right_generic = self.is_generic_phrase(right)
            if right_facets or right_generic:
                return self._parsed(
                    left,
                    facets=right_facets,
                    is_generic=self.is_generic_phrase(left),
                    is_facet_only=False,
                    split_confidence=0.92,
                    matched_pattern=pattern_name,
                )
            if left_generic and not right_generic:
                return self._parsed(
                    right,
                    facets=left_facets,
                    is_generic=False,
                    is_facet_only=False,
                    split_confidence=0.82,
                    matched_pattern="facet_left_entity_right",
                )
        return None

    def _parse_facet_prefix(self, text: str) -> ParsedSurface | None:
        normalized = normalize_surface(text)
        candidates = sorted(
            {
                phrase: facet
                for facet, phrases in self.facets.items()
                for phrase in phrases
                if phrase
            }.items(),
            key=lambda item: len(item[0]),
            reverse=True,
        )
        for phrase, facet in candidates:
            if not normalized.startswith(phrase + " "):
                continue
            entity = text[len(_prefix_from_original(text, phrase)) :].strip(" -—:;.")  # noqa: E203
            if entity:
                return self._parsed(
                    entity,
                    facets=[facet],
                    is_generic=False,
                    is_facet_only=False,
                    split_confidence=0.72,
                    matched_pattern="facet_entity_prefix",
                )
        return None

    def _parse_instruction(self, text: str) -> ParsedSurface | None:
        lower = normalize_surface(text)
        if lower.startswith("инструкция по применению "):
            entity = text[len("инструкция по применению ") :].strip(" -—:;.")  # noqa: E203
            return self._parsed(
                entity,
                facets=["instruction"],
                split_confidence=0.80,
                matched_pattern="instruction_entity",
            )
        if lower.startswith("инструкция по использованию "):
            entity = text[len("инструкция по использованию ") :].strip(" -—:;.")  # noqa: E203
            return self._parsed(
                entity,
                facets=["instruction"],
                split_confidence=0.80,
                matched_pattern="instruction_entity",
            )
        match = re.match(
            r"^как\s+(?:правильно\s+)?(?P<verb>надевать|использовать|применять|принимать|"
            r"подготовить|подготовиться)\s+(?P<entity>.+)$",
            lower,
            flags=re.IGNORECASE,
        )
        if match:
            entity_start = match.start("entity")
            entity = text[entity_start:].strip(" -—:;.")
            verb = match.group("verb")
            facets = ["dosage"] if "принимать" in verb else ["instruction"]
            return self._parsed(
                entity,
                facets=facets,
                split_confidence=0.86,
                matched_pattern="how_to_entity",
            )
        if lower.startswith("как "):
            return self._parsed(
                text,
                facets=["instruction"],
                is_generic=True,
                is_facet_only=True,
                split_confidence=0.35,
                matched_pattern="how_to_generic",
            )
        return None

    def _parsed(
        self,
        surface: str,
        *,
        facets: list[str] | None = None,
        is_generic: bool = False,
        is_facet_only: bool = False,
        split_confidence: float = 0.0,
        matched_pattern: str | None = None,
    ) -> ParsedSurface:
        clean_surface = normalize_spaces(surface.strip(" -—:;."))
        normalized = normalize_surface(clean_surface)
        facets = list(dict.fromkeys(facets or self.match_facets(clean_surface)))
        facet_type = facets[0] if facets else None
        core_surface = _guess_core_surface(
            clean_surface,
            drug_forms=self.drug_forms,
            strength_units=self.strength_units,
        )
        normalized_core = normalize_surface(core_surface) if core_surface else None
        generic = is_generic or self.is_generic_phrase(clean_surface)
        return ParsedSurface(
            surface=clean_surface,
            normalized_surface=normalized,
            core_surface=core_surface,
            normalized_core_surface=normalized_core,
            facet_type=facet_type,
            facets=facets,
            is_generic=generic,
            is_facet_only=is_facet_only or (generic and not clean_surface),
            split_confidence=split_confidence,
            matched_pattern=matched_pattern,
        )


def _guess_core_surface(
    surface: str, *, drug_forms: list[str], strength_units: list[str]
) -> str | None:
    clean = normalize_spaces(surface)
    if not clean:
        return None
    normalized = normalize_surface(clean)
    has_drug_signal = any(_contains_phrase(normalized, form) for form in drug_forms) or any(
        re.search(rf"\d+(?:[,.]\d+)?\s*{re.escape(unit)}\b", normalized) for unit in strength_units
    )
    if has_drug_signal:
        tokens = clean.split()
        for index, token in enumerate(tokens):
            if normalize_surface(token.rstrip(",.")) in drug_forms:
                return " ".join(tokens[:index]) or clean
        return clean.split(",", 1)[0].strip() or clean
    return clean


def _strip_wrapping_punctuation(value: str) -> str:
    return normalize_spaces(value.strip(" \t\r\n-—:;."))


def _contains_phrase(normalized: str, phrase: str) -> bool:
    if not phrase:
        return False
    return re.search(rf"(?<!\w){re.escape(phrase)}(?!\w)", normalized) is not None


def _prefix_from_original(original: str, normalized_prefix: str) -> str:
    words = normalized_prefix.split()
    original_words = original.split()
    return " ".join(original_words[: len(words)])


def _read_yaml(path: Path) -> dict[str, Any]:
    return yaml.safe_load(path.read_text(encoding="utf-8")) or {}
