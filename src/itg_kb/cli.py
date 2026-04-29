"""Command line interface for the pipeline."""

from __future__ import annotations

import json
from pathlib import Path

import typer
from rich.console import Console
from rich.table import Table

from itg_kb.core.paths import ProjectPaths
from itg_kb.orchestration.stages import (
    pipeline_status,
    run_audit_normalized,
    run_ingest,
    run_init_dirs,
    run_normalize,
    validate_stage,
)

app = typer.Typer(no_args_is_help=True)
console = Console()


@app.command("init-dirs")
def init_dirs() -> None:
    created = run_init_dirs()
    console.print(f"Initialized {len(created)} data directories.")


@app.command("ingest")
def ingest(
    input_path: Path | None = typer.Option(
        None,
        "--input",
        "-i",
        help="Path to source documents.csv. Defaults to configured raw_dir/documents.csv.",
    ),
) -> None:
    if input_path is None:
        input_path = ProjectPaths.from_root(".").raw_dir / "documents.csv"
    report = run_ingest(input_path)
    console.print_json(json.dumps(report, ensure_ascii=False))
    if report["status"] == "failed":
        raise typer.Exit(code=1)


@app.command("normalize")
def normalize(
    limit: int | None = typer.Option(None, "--limit", min=1, help="Process first N documents."),
    doc_id: str | None = typer.Option(None, "--doc-id", help="Process a single doc_id."),
    force: bool = typer.Option(False, "--force", help="Overwrite existing S01 artifacts."),
) -> None:
    report = run_normalize(limit=limit, doc_id=doc_id, force=force)
    console.print_json(json.dumps(report, ensure_ascii=False))
    if report["status"] == "failed":
        raise typer.Exit(code=1)


@app.command("audit-normalized")
def audit_normalized(
    sample_size: int = typer.Option(
        100, "--sample-size", min=0, help="Number of documents to sample for review."
    ),
) -> None:
    report = run_audit_normalized(sample_size=sample_size)
    console.print_json(json.dumps(report, ensure_ascii=False))
    if report["status"] == "failed":
        raise typer.Exit(code=1)


@app.command("status")
def status() -> None:
    rows = pipeline_status()
    table = Table(title="Pipeline Status")
    table.add_column("Stage")
    table.add_column("Artifact")
    table.add_column("Exists")
    for row in rows:
        for artifact, exists in row["outputs"].items():
            table.add_row(row["stage"], artifact, "yes" if exists else "no")
    console.print(table)


@app.command("validate-stage")
def validate_stage_command(stage: str) -> None:
    result = validate_stage(stage)
    console.print_json(json.dumps(result, ensure_ascii=False))
    if not result["valid"]:
        raise typer.Exit(code=1)


def main() -> None:
    app()


if __name__ == "__main__":
    main()
