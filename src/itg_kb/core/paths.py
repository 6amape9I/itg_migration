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
    tagging_dir: Path
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

        def resolve_value(value: str | Path) -> Path:
            configured = Path(value)
            return configured if configured.is_absolute() else root_path / configured

        data_dir = resolve_value(config.get("data_dir", "data"))

        def resolve_stage(key: str, subdir: str) -> Path:
            if key in config and config[key] not in (None, ""):
                return resolve_value(config[key])
            return data_dir / subdir

        return cls(
            root=root_path,
            data_dir=data_dir,
            raw_dir=resolve_stage("raw_dir", "00_raw"),
            ingested_dir=resolve_stage("ingested_dir", "01_ingested"),
            normalized_dir=resolve_stage("normalized_dir", "02_normalized"),
            tagging_dir=resolve_stage("tagging_dir", "03_tagging"),
            reports_dir=resolve_stage("reports_dir", "90_reports"),
            cache_dir=resolve_stage("cache_dir", "99_cache"),
            logs_dir=resolve_stage("logs_dir", "99_logs"),
        )

    def ensure_data_dirs(self) -> list[Path]:
        created: list[Path] = []
        self.data_dir.mkdir(parents=True, exist_ok=True)
        if self.data_dir == self.root / "data":
            keep = self.data_dir / ".gitkeep"
            keep.touch(exist_ok=True)
        configured_dirs = {
            self.raw_dir,
            self.ingested_dir,
            self.normalized_dir,
            self.tagging_dir,
            self.reports_dir,
            self.cache_dir,
            self.logs_dir,
        }
        stage_dirs = configured_dirs | {self.data_dir / subdir for subdir in DATA_SUBDIRS}
        for path in sorted(stage_dirs):
            path.mkdir(parents=True, exist_ok=True)
            created.append(path)
        (self.normalized_dir / "by_doc").mkdir(parents=True, exist_ok=True)
        (self.tagging_dir / "by_doc").mkdir(parents=True, exist_ok=True)
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
            self.normalized_dir / "block_metrics.parquet",
            self.reports_dir / "S01_normalization_report.json",
        ]

    @property
    def s02a_outputs(self) -> list[Path]:
        return [
            self.tagging_dir / "topic_units.parquet",
            self.tagging_dir / "tag_candidates.parquet",
            self.tagging_dir / "candidate_evidence.parquet",
            self.tagging_dir / "doc_topics.parquet",
            self.tagging_dir / "doc_tag_candidates.jsonl",
            self.tagging_dir / "ambiguity_queue.jsonl",
            self.reports_dir / "S02A_tagging_report.json",
            self.reports_dir / "S02A_tagging_report.md",
            self.reports_dir / "S02A_review_sample.csv",
            self.reports_dir / "S02A_candidate_distribution.csv",
            self.reports_dir / "S02A_no_blocks_skipped.csv",
        ]


def default_paths() -> ProjectPaths:
    return ProjectPaths.from_root(Path.cwd())
