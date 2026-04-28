"""Run S00 and S01 on the synthetic fixture."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))


def main() -> None:
    from itg_kb.orchestration.stages import run_ingest, run_init_dirs, run_normalize

    run_init_dirs(ROOT)
    fixture = ROOT / "tests" / "fixtures" / "documents_sample.csv"
    ingest_report = run_ingest(fixture, project_root=ROOT)
    normalize_report = run_normalize(project_root=ROOT)
    print(f"S00: {ingest_report['status']} rows={ingest_report['total_rows']}")
    print(f"S01: {normalize_report['status']} blocks={normalize_report['total_blocks']}")


if __name__ == "__main__":
    main()
