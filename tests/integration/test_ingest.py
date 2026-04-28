from pathlib import Path

import pandas as pd

from itg_kb.orchestration.stages import run_ingest

FIXTURE = Path(__file__).resolve().parents[1] / "fixtures" / "documents_sample.csv"


def test_ingest_creates_expected_files(tmp_path: Path) -> None:
    report = run_ingest(FIXTURE, project_root=tmp_path)
    assert report["status"] == "ok"
    assert (tmp_path / "data/01_ingested/documents.parquet").exists()
    assert (tmp_path / "data/01_ingested/documents.jsonl").exists()
    assert (tmp_path / "data/01_ingested/manifest.jsonl").exists()
    assert (tmp_path / "data/90_reports/S00_ingest_report.json").exists()


def test_ingest_stable_doc_ids_and_empty_content(tmp_path: Path) -> None:
    run_ingest(FIXTURE, project_root=tmp_path)
    first = pd.read_parquet(tmp_path / "data/01_ingested/documents.parquet")
    run_ingest(FIXTURE, project_root=tmp_path)
    second = pd.read_parquet(tmp_path / "data/01_ingested/documents.parquet")
    assert first["doc_id"].tolist() == second["doc_id"].tolist()
    empty = second[second["ingest_status"] == "empty_content"]
    assert len(empty) == 1
