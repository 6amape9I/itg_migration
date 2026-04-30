"""Export JSON Schema files from Pydantic models."""

from __future__ import annotations

import json
from pathlib import Path
from typing import TypeAlias

from pydantic import BaseModel

from itg_kb.schemas import (
    ArticleArtifact,
    CandidateEvidence,
    DocTopicSummary,
    DocumentBlock,
    DocumentRecord,
    GraphArtifact,
    NormalizedDocument,
    QuoteRecord,
    TagCandidate,
    TagRecord,
    TopicSnippet,
    TopicUnit,
)

ModelClass: TypeAlias = type[BaseModel]

SCHEMA_MODELS: dict[str, ModelClass] = {
    "document.schema.json": DocumentRecord,
    "normalized_document.schema.json": NormalizedDocument,
    "block.schema.json": DocumentBlock,
    "topic_unit.schema.json": TopicUnit,
    "tag_candidate.schema.json": TagCandidate,
    "candidate_evidence.schema.json": CandidateEvidence,
    "doc_topic_summary.schema.json": DocTopicSummary,
    "tag_catalog.schema.json": TagRecord,
    "topic_snippet.schema.json": TopicSnippet,
    "article.schema.json": ArticleArtifact,
    "quote.schema.json": QuoteRecord,
    "graph.schema.json": GraphArtifact,
}


def write_json_schemas(output_dir: Path | str = "schemas") -> list[Path]:
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)
    written: list[Path] = []
    for filename, model in SCHEMA_MODELS.items():
        target = output_path / filename
        target.write_text(
            json.dumps(model.model_json_schema(), ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        written.append(target)
    return written
