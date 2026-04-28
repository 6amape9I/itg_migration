from pathlib import Path

import pandas as pd

from itg_kb.orchestration.stages import run_ingest, run_normalize

FIXTURE = Path(__file__).resolve().parents[1] / "fixtures" / "documents_sample.csv"


def test_normalize_creates_blocks_and_reports(tmp_path: Path) -> None:
    run_ingest(FIXTURE, project_root=tmp_path)
    report = run_normalize(project_root=tmp_path)
    assert report["status"] == "ok"
    assert report["total_blocks"] > 0
    assert (tmp_path / "data/02_normalized/documents_normalized.parquet").exists()
    assert (tmp_path / "data/02_normalized/blocks.parquet").exists()
    assert (tmp_path / "data/90_reports/S01_normalization_report.json").exists()


def test_normalize_preserves_heading_table_and_broken_html(tmp_path: Path) -> None:
    run_ingest(FIXTURE, project_root=tmp_path)
    run_normalize(project_root=tmp_path)
    blocks = pd.read_parquet(tmp_path / "data/02_normalized/blocks.parquet")
    assert "heading" in set(blocks["type"])
    assert "table" in set(blocks["type"])
    assert blocks["doc_id"].nunique() == 4
