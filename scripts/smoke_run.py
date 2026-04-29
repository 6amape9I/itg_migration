"""Run S00 and S01 on the synthetic fixture."""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))


def main() -> None:
    from itg_kb.orchestration.stages import run_ingest, run_init_dirs, run_normalize

    fixture = ROOT / "tests" / "fixtures" / "documents_sample.csv"
    with tempfile.TemporaryDirectory(prefix="itg_kb_smoke_") as tmp_dir:
        smoke_root = Path(tmp_dir)
        run_init_dirs(smoke_root)
        ingest_report = run_ingest(fixture, project_root=smoke_root)
        normalize_report = run_normalize(project_root=smoke_root)
    print(f"S00: {ingest_report['status']} rows={ingest_report['total_rows']}")
    print(f"S01: {normalize_report['status']} blocks={normalize_report['total_blocks']}")


if __name__ == "__main__":
    main()
