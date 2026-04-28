"""Pydantic schemas for pipeline artifacts."""

from itg_kb.schemas.articles import ArticleArtifact
from itg_kb.schemas.blocks import DocumentBlock
from itg_kb.schemas.documents import DocumentRecord, NormalizedDocument
from itg_kb.schemas.graph import GraphArtifact, GraphEdge, GraphNode
from itg_kb.schemas.quotes import QuoteRecord
from itg_kb.schemas.reports import StageReport
from itg_kb.schemas.tags import TagCandidate, TagDocLink, TagRecord
from itg_kb.schemas.topic_snippets import TopicSnippet

__all__ = [
    "ArticleArtifact",
    "DocumentBlock",
    "DocumentRecord",
    "GraphEdge",
    "GraphArtifact",
    "GraphNode",
    "NormalizedDocument",
    "QuoteRecord",
    "StageReport",
    "TagCandidate",
    "TagDocLink",
    "TagRecord",
    "TopicSnippet",
]
