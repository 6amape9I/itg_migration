from pathlib import Path

import pandas as pd

from itg_kb.core.paths import ProjectPaths
from itg_kb.orchestration.stages import run_ingest, run_normalize, validate_stage

FIXTURE = Path(__file__).resolve().parents[1] / "fixtures" / "documents_sample.csv"


def test_validate_stage_s00_success(tmp_path: Path) -> None:
    run_ingest(FIXTURE, project_root=tmp_path)

    result = validate_stage("S00", project_root=tmp_path)

    assert result["valid"] is True
    assert result["missing"] == []
    assert result["errors"] == []


def test_validate_stage_s01_success(tmp_path: Path) -> None:
    run_ingest(FIXTURE, project_root=tmp_path)
    run_normalize(project_root=tmp_path)

    result = validate_stage("S01", project_root=tmp_path)

    assert result["valid"] is True
    assert result["missing"] == []
    assert result["errors"] == []


def test_validate_stage_reports_missing_artifact(tmp_path: Path) -> None:
    run_ingest(FIXTURE, project_root=tmp_path)
    paths = ProjectPaths.from_root(tmp_path)
    (paths.ingested_dir / "manifest.jsonl").unlink()

    result = validate_stage("S00", project_root=tmp_path)

    assert result["valid"] is False
    assert str(paths.ingested_dir / "manifest.jsonl") in result["missing"]


def test_validate_stage_reports_corrupt_artifact(tmp_path: Path) -> None:
    run_ingest(FIXTURE, project_root=tmp_path)
    paths = ProjectPaths.from_root(tmp_path)
    (paths.ingested_dir / "documents.parquet").write_text("not parquet", encoding="utf-8")

    result = validate_stage("S00", project_root=tmp_path)

    assert result["valid"] is False
    assert any(error["error"] == "UnreadableParquet" for error in result["errors"])


def test_validate_stage_reports_missing_required_column(tmp_path: Path) -> None:
    run_ingest(FIXTURE, project_root=tmp_path)
    paths = ProjectPaths.from_root(tmp_path)
    documents_path = paths.ingested_dir / "documents.parquet"
    documents = pd.read_parquet(documents_path).drop(columns=["metadata"])
    documents.to_parquet(documents_path, index=False)

    result = validate_stage("S00", project_root=tmp_path)

    assert result["valid"] is False
    assert any(error["error"] == "MissingColumns" for error in result["errors"])


def test_validate_stage_reports_missing_normalized_doc_id(tmp_path: Path) -> None:
    run_ingest(FIXTURE, project_root=tmp_path)
    run_normalize(project_root=tmp_path)
    paths = ProjectPaths.from_root(tmp_path)
    normalized_path = paths.normalized_dir / "documents_normalized.parquet"
    normalized = pd.read_parquet(normalized_path).iloc[:-1]
    normalized.to_parquet(normalized_path, index=False)

    result = validate_stage("S01", project_root=tmp_path)

    assert result["valid"] is False
    assert any(error["error"] == "MissingNormalizedDocuments" for error in result["errors"])


def test_validate_stage_allows_partial_normalize_with_report_marker(tmp_path: Path) -> None:
    run_ingest(FIXTURE, project_root=tmp_path)
    run_normalize(project_root=tmp_path, limit=2)

    result = validate_stage("S01", project_root=tmp_path)

    assert result["valid"] is True
    assert result["errors"] == []


def test_validate_stage_reports_empty_blocks_for_nonempty_documents(tmp_path: Path) -> None:
    run_ingest(FIXTURE, project_root=tmp_path)
    run_normalize(project_root=tmp_path)
    paths = ProjectPaths.from_root(tmp_path)
    blocks_path = paths.normalized_dir / "blocks.parquet"
    blocks = pd.read_parquet(blocks_path)
    blocks.iloc[0:0].to_parquet(blocks_path, index=False)

    result = validate_stage("S01", project_root=tmp_path)

    assert result["valid"] is False
    assert any(error["error"] == "EmptyBlocksForNonemptyDocuments" for error in result["errors"])


def test_validate_stage_reports_block_count_mismatch(tmp_path: Path) -> None:
    run_ingest(FIXTURE, project_root=tmp_path)
    run_normalize(project_root=tmp_path)
    paths = ProjectPaths.from_root(tmp_path)
    normalized_path = paths.normalized_dir / "documents_normalized.parquet"
    normalized = pd.read_parquet(normalized_path)
    normalized.loc[0, "block_count"] = int(normalized.loc[0, "block_count"]) + 1
    normalized.to_parquet(normalized_path, index=False)

    result = validate_stage("S01", project_root=tmp_path)

    assert result["valid"] is False
    assert any(error["error"] == "BlockCountMismatch" for error in result["errors"])
