from pathlib import Path

import pandas as pd

from itg_kb.core.paths import ProjectPaths
from itg_kb.orchestration.stages import run_ingest, run_normalize

FIXTURE = Path(__file__).resolve().parents[1] / "fixtures" / "documents_sample.csv"


def test_normalize_creates_blocks_and_reports(tmp_path: Path) -> None:
    run_ingest(FIXTURE, project_root=tmp_path)
    report = run_normalize(project_root=tmp_path)
    assert report["status"] == "ok"
    assert report["total_blocks"] > 0
    assert (tmp_path / "data/02_normalized/documents_normalized.parquet").exists()
    assert (tmp_path / "data/02_normalized/blocks.parquet").exists()
    assert (tmp_path / "data/02_normalized/block_metrics.parquet").exists()
    assert (tmp_path / "data/90_reports/S01_normalization_report.json").exists()


def test_normalize_preserves_heading_table_and_broken_html(tmp_path: Path) -> None:
    run_ingest(FIXTURE, project_root=tmp_path)
    run_normalize(project_root=tmp_path)
    blocks = pd.read_parquet(tmp_path / "data/02_normalized/blocks.parquet")
    assert "heading" in set(blocks["type"])
    assert "table" in set(blocks["type"])
    assert blocks["doc_id"].nunique() == 4
    assert {"heading_path", "dom_path", "text_hash"} <= set(blocks.columns)


def test_normalize_limit_marks_partial_run(tmp_path: Path) -> None:
    run_ingest(FIXTURE, project_root=tmp_path)

    report = run_normalize(project_root=tmp_path, limit=2)
    normalized = pd.read_parquet(tmp_path / "data/02_normalized/documents_normalized.parquet")

    assert report["status"] == "partial"
    assert report["partial"] is True
    assert report["total_documents"] == 2
    assert len(normalized) == 2


def test_normalize_doc_id_processes_single_document(tmp_path: Path) -> None:
    run_ingest(FIXTURE, project_root=tmp_path)
    documents = pd.read_parquet(tmp_path / "data/01_ingested/documents.parquet")
    doc_id = str(documents.loc[0, "doc_id"])

    report = run_normalize(project_root=tmp_path, doc_id=doc_id)
    normalized = pd.read_parquet(tmp_path / "data/02_normalized/documents_normalized.parquet")

    assert report["partial"] is True
    assert normalized["doc_id"].tolist() == [doc_id]


def test_normalize_force_overwrites_existing_s01_artifacts(tmp_path: Path) -> None:
    run_ingest(FIXTURE, project_root=tmp_path)
    first = run_normalize(project_root=tmp_path)
    second = run_normalize(project_root=tmp_path)
    third = run_normalize(project_root=tmp_path, limit=1, force=True)

    assert first["status"] == "ok"
    assert second["status"] == "failed"
    assert second["errors_sample"][0]["error"] == "ExistingS01Artifacts"
    assert third["status"] == "partial"
    assert third["total_documents"] == 1


def test_normalize_empty_content_creates_normalized_row_without_blocks(tmp_path: Path) -> None:
    run_ingest(FIXTURE, project_root=tmp_path)
    documents = pd.read_parquet(tmp_path / "data/01_ingested/documents.parquet")
    empty_doc_id = str(
        documents.loc[documents["ingest_status"] == "empty_content", "doc_id"].iloc[0]
    )

    run_normalize(project_root=tmp_path, doc_id=empty_doc_id)
    paths = ProjectPaths.from_root(tmp_path)
    normalized = pd.read_parquet(paths.normalized_dir / "documents_normalized.parquet")
    blocks = pd.read_parquet(paths.normalized_dir / "blocks.parquet")

    assert normalized.loc[0, "normalization_status"] == "empty_content"
    assert normalized.loc[0, "block_count"] == 0
    assert blocks.empty
