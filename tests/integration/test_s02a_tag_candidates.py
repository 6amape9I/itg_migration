import csv
from pathlib import Path

import pandas as pd

from itg_kb.core.paths import ProjectPaths
from itg_kb.orchestration.stages import (
    run_audit_tag_candidates,
    run_ingest,
    run_normalize,
    run_tag_candidates,
    validate_stage,
)


def test_s02a_smoke_creates_required_artifacts_and_audit_outputs(tmp_path: Path) -> None:
    fixture = _write_s02a_fixture(tmp_path)
    run_ingest(fixture, project_root=tmp_path)
    run_normalize(project_root=tmp_path)

    report = run_tag_candidates(project_root=tmp_path, stage="S02A", limit=2, force=True)
    validate = validate_stage("S02A", project_root=tmp_path)
    audit = run_audit_tag_candidates(project_root=tmp_path, sample_size=2)
    paths = ProjectPaths.from_root(tmp_path)

    assert report["status"] == "partial"
    assert report["processed_documents"] == 2
    assert report["total_topic_units"] > 0
    assert report["total_candidates"] > 0
    assert validate["valid"] is True
    assert audit["status"] == "ok"
    for path in paths.s02a_outputs:
        assert path.exists()
    assert pd.read_parquet(paths.tagging_dir / "tag_candidates.parquet").shape[0] > 0


def test_s02a_doc_id_and_force_behaviour(tmp_path: Path) -> None:
    fixture = _write_s02a_fixture(tmp_path)
    run_ingest(fixture, project_root=tmp_path)
    run_normalize(project_root=tmp_path)
    paths = ProjectPaths.from_root(tmp_path)
    normalized = pd.read_parquet(paths.normalized_dir / "documents_normalized.parquet")
    doc_id = str(normalized.loc[0, "doc_id"])

    first = run_tag_candidates(project_root=tmp_path, stage="S02A", doc_id=doc_id, force=True)
    second = run_tag_candidates(project_root=tmp_path, stage="S02A")
    third = run_tag_candidates(project_root=tmp_path, stage="S02A", limit=1, force=True)
    doc_topics = pd.read_parquet(paths.tagging_dir / "doc_topics.parquet")

    assert first["status"] == "partial"
    assert second["status"] == "failed"
    assert second["errors_sample"][0]["error"] == "ExistingS02AArtifacts"
    assert third["status"] == "partial"
    assert len(doc_topics) == 1


def test_validate_s02a_reports_missing_column_and_artifact(tmp_path: Path) -> None:
    fixture = _write_s02a_fixture(tmp_path)
    run_ingest(fixture, project_root=tmp_path)
    run_normalize(project_root=tmp_path)
    run_tag_candidates(project_root=tmp_path, stage="S02A", limit=2, force=True)
    paths = ProjectPaths.from_root(tmp_path)

    candidates_path = paths.tagging_dir / "tag_candidates.parquet"
    candidates = pd.read_parquet(candidates_path).drop(columns=["metadata"])
    candidates.to_parquet(candidates_path, index=False)
    missing_column = validate_stage("S02A", project_root=tmp_path)

    (paths.tagging_dir / "topic_units.parquet").unlink()
    missing_artifact = validate_stage("S02A", project_root=tmp_path)

    assert missing_column["valid"] is False
    assert any(error["error"] == "MissingColumns" for error in missing_column["errors"])
    assert missing_artifact["valid"] is False
    assert str(paths.tagging_dir / "topic_units.parquet") in missing_artifact["missing"]


def _write_s02a_fixture(tmp_path: Path) -> Path:
    fixture = tmp_path / "s02a_documents.csv"
    rows = [
        {
            "source_id": "s02a-1",
            "name": "Зиннат таблетки 125 мг: Способы и дозировка",
            "description": "drug",
            "content": "<h1>Режим дозирования</h1><p>Зиннат принимают внутрь.</p>",
        },
        {
            "source_id": "s02a-2",
            "name": "Гастрит: симптомы и лечение",
            "description": "disease",
            "content": "<h1>Гастрит</h1><p>Симптомы включают боль и тошноту.</p>",
        },
        {
            "source_id": "s02a-3",
            "name": "Как правильно надевать медицинские перчатки",
            "description": "device",
            "content": "<p>Медицинские перчатки используют по инструкции.</p>",
        },
    ]
    with fixture.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=["source_id", "name", "description", "content"])
        writer.writeheader()
        writer.writerows(rows)
    return fixture
