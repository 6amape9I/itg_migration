import csv
import json
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


def test_audit_normalized_reports_editorjs_and_omits_raw_json_samples(tmp_path: Path) -> None:
    fixture = _write_editorjs_fixture(tmp_path)
    run_ingest(fixture, project_root=tmp_path)
    run_normalize(project_root=tmp_path)

    report = run_audit_normalized(project_root=tmp_path, sample_size=1)
    sample_json = next((tmp_path / "data/90_reports/samples").glob("*.json"))
    sample_md = next((tmp_path / "data/90_reports/samples").glob("*.md"))
    sample_html = next((tmp_path / "data/90_reports/samples").glob("*.html"))
    sample_payload = sample_json.read_text(encoding="utf-8")

    assert report["documents_by_source_format"] == {"editorjs": 1}
    assert report["editorjs_documents"] == 1
    assert report["top_documents_with_json_markers"] == []
    assert "raw_content" not in sample_payload
    assert '"api"' not in sample_payload
    assert '"styles"' not in sample_payload
    assert '"toolbar"' not in sample_payload
    assert '"version"' not in sample_payload
    assert '"api"' not in sample_md.read_text(encoding="utf-8")
    assert '"api"' not in sample_html.read_text(encoding="utf-8")
    assert "Normalized Markdown" in sample_html.read_text(encoding="utf-8")


def _write_editorjs_fixture(tmp_path: Path) -> Path:
    content = json.dumps(
        {
            "blocks": [
                {"id": "h1", "type": "header", "data": {"text": "Заголовок", "level": 3}},
                {
                    "id": "p1",
                    "type": "paragraph",
                    "data": {
                        "api": {"blocks": {}, "styles": {}, "toolbar": {}},
                        "element": {},
                        "text": "Режим дозирования<br><br>Внутрь.",
                    },
                },
            ],
            "version": "2.24.3",
        },
        ensure_ascii=False,
    )
    fixture = tmp_path / "editorjs_documents.csv"
    with fixture.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=["source_id", "name", "description", "content"])
        writer.writeheader()
        writer.writerow(
            {
                "source_id": "editorjs-1",
                "name": "Editor.js документ",
                "description": "fixture",
                "content": content,
            }
        )
    return fixture
