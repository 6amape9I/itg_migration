from pathlib import Path

from itg_kb.orchestration.stages import run_audit_normalized, run_ingest, run_normalize

FIXTURE = Path(__file__).resolve().parents[1] / "fixtures" / "documents_sample.csv"


def test_audit_normalized_creates_quality_reports_and_samples(tmp_path: Path) -> None:
    run_ingest(FIXTURE, project_root=tmp_path)
    run_normalize(project_root=tmp_path)

    report = run_audit_normalized(project_root=tmp_path, sample_size=3)

    assert report["status"] == "ok"
    assert report["total_documents"] == 5
    assert (tmp_path / "data/90_reports/S01_quality_report.json").exists()
    assert (tmp_path / "data/90_reports/S01_quality_report.md").exists()
    assert (tmp_path / "data/90_reports/S01_sample_index.md").exists()
    assert len(list((tmp_path / "data/90_reports/samples").glob("*.json"))) > 0
