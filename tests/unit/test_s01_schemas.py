from itg_kb.schemas.blocks import DocumentBlock
from itg_kb.schemas.documents import NormalizedDocument


def test_document_block_schema_has_v1_fields() -> None:
    schema_fields = set(DocumentBlock.model_fields)

    assert {"heading_path", "dom_path", "text_hash"} <= schema_fields


def test_normalized_document_schema_has_quality_metrics() -> None:
    schema_fields = set(NormalizedDocument.model_fields)

    assert {
        "raw_length",
        "plain_text_length",
        "markdown_length",
        "text_preservation_ratio",
        "source_format",
        "raw_format_detected",
        "useful_text_length",
        "useful_text_ratio",
        "heading_count",
        "paragraph_count",
        "list_item_count",
        "table_count",
        "unknown_count",
        "has_tables",
        "has_headings",
        "has_warnings",
    } <= schema_fields
