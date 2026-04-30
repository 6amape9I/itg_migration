"""Shared deterministic S02A tagging constants."""

from __future__ import annotations

from pathlib import Path

from itg_kb.core.paths import ProjectPaths

ROLE_DOCUMENT_PRIMARY = "document_primary_candidate"
ROLE_SECTION_TOPIC = "section_topic_candidate"
ROLE_SECONDARY_TOPIC = "secondary_topic_candidate"
ROLE_CROSS_TOPIC_REFERENCE = "cross_topic_reference"
ROLE_CONDITIONAL_CONTEXT = "conditional_context"
ROLE_FACET_ONLY = "facet_only"
ROLE_REJECTED_GENERIC = "rejected_generic"
ROLE_NEEDS_REVIEW = "needs_review"

CANDIDATE_ROLES = {
    ROLE_DOCUMENT_PRIMARY,
    ROLE_SECTION_TOPIC,
    ROLE_SECONDARY_TOPIC,
    ROLE_CROSS_TOPIC_REFERENCE,
    ROLE_CONDITIONAL_CONTEXT,
    ROLE_FACET_ONLY,
    ROLE_REJECTED_GENERIC,
    ROLE_NEEDS_REVIEW,
}

UNIT_DOCUMENT_TITLE = "document_title"
UNIT_HEADING_SECTION = "heading_section"
UNIT_TABLE = "table_unit"
UNIT_LIST = "list_unit"
UNIT_PARAGRAPH_WINDOW = "paragraph_window"
UNIT_FALLBACK_DOCUMENT = "fallback_document"

TOPIC_UNIT_TYPES = {
    UNIT_DOCUMENT_TITLE,
    UNIT_HEADING_SECTION,
    UNIT_TABLE,
    UNIT_LIST,
    UNIT_PARAGRAPH_WINDOW,
    UNIT_FALLBACK_DOCUMENT,
}

EVIDENCE_TITLE = "title"
EVIDENCE_HEADING = "heading"
EVIDENCE_HEADING_PATH = "heading_path"
EVIDENCE_PARAGRAPH = "paragraph"
EVIDENCE_LIST_ITEM = "list_item"
EVIDENCE_TABLE = "table"
EVIDENCE_PATTERN_MATCH = "pattern_match"

EVIDENCE_TYPES = {
    EVIDENCE_TITLE,
    EVIDENCE_HEADING,
    EVIDENCE_HEADING_PATH,
    EVIDENCE_PARAGRAPH,
    EVIDENCE_LIST_ITEM,
    EVIDENCE_TABLE,
    EVIDENCE_PATTERN_MATCH,
}

ENTITY_TYPES = {
    "disease",
    "symptom",
    "drug_brand",
    "drug_substance",
    "drug_product",
    "medical_device",
    "procedure",
    "treatment",
    "diagnostic_test",
    "anatomy",
    "contraindication",
    "adverse_effect",
    "document_type",
    "medical_instruction",
    "healthcare_process",
    "lifestyle_prevention",
    "organization_process",
    "other_core_topic",
    "unknown",
}

DEFAULT_TITLE_BLOCK_ID = "__document_title__"


def tagging_config_dir(project_root: Path | str = ".") -> Path:
    configured = ProjectPaths.from_root(project_root).root / "configs" / "tagging"
    if configured.exists():
        return configured
    cwd_config = Path.cwd().resolve() / "configs" / "tagging"
    if cwd_config.exists():
        return cwd_config
    return configured
