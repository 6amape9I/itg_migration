"""Project path contracts."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import yaml

DATA_SUBDIRS = [
    "00_raw",
    "01_ingested",
    "02_normalized",
    "03_tagging",
    "04_tag_normalization",
    "05_topic_corpora",
    "06_articles",
    "07_quotes",
    "08_hierarchy",
    "09_steos_export",
    "10_graph",
    "90_reports",
    "99_cache",
    "99_logs",
]


@dataclass(frozen=True)
class ProjectPaths:
    root: Path
    data_dir: Path
    raw_dir: Path
    ingested_dir: Path
    normalized_dir: Path
    reports_dir: Path
    cache_dir: Path
    logs_dir: Path

    @classmethod
    def from_root(cls, root: Path | str = ".") -> "ProjectPaths":
        root_path = Path(root).resolve()
        config_path = root_path / "configs" / "paths.yaml"
        config: dict[str, str] = {}
        if config_path.exists():
            config = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}

        def resolve(key: str, default: str) -> Path:
            return root_path / config.get(key, default)

        return cls(
            root=root_path,
            data_dir=resolve("data_dir", "data"),
            raw_dir=resolve("raw_dir", "data/00_raw"),
            ingested_dir=resolve("ingested_dir", "data/01_ingested"),
            normalized_dir=resolve("normalized_dir", "data/02_normalized"),
            reports_dir=resolve("reports_dir", "data/90_reports"),
            cache_dir=resolve("cache_dir", "data/99_cache"),
            logs_dir=resolve("logs_dir", "data/99_logs"),
        )

    def ensure_data_dirs(self) -> list[Path]:
        created: list[Path] = []
        self.data_dir.mkdir(parents=True, exist_ok=True)
        keep = self.data_dir / ".gitkeep"
        keep.touch(exist_ok=True)
        for subdir in DATA_SUBDIRS:
            path = self.data_dir / subdir
            path.mkdir(parents=True, exist_ok=True)
            created.append(path)
        (self.normalized_dir / "by_doc").mkdir(parents=True, exist_ok=True)
        return created

    @property
    def s00_outputs(self) -> list[Path]:
        return [
            self.ingested_dir / "documents.parquet",
            self.ingested_dir / "documents.jsonl",
            self.ingested_dir / "manifest.jsonl",
            self.reports_dir / "S00_ingest_report.json",
        ]

    @property
    def s01_outputs(self) -> list[Path]:
        return [
            self.normalized_dir / "documents_normalized.parquet",
            self.normalized_dir / "blocks.parquet",
            self.reports_dir / "S01_normalization_report.json",
        ]


def default_paths() -> ProjectPaths:
    return ProjectPaths.from_root(Path.cwd())
