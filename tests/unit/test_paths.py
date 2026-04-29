from pathlib import Path

from itg_kb.core.paths import DATA_SUBDIRS, ProjectPaths


def test_external_data_dir_derives_stage_paths(tmp_path: Path) -> None:
    project_root = tmp_path / "project"
    external_data_dir = tmp_path / "external_data"
    config_dir = project_root / "configs"
    config_dir.mkdir(parents=True)
    (config_dir / "paths.yaml").write_text(
        f"data_dir: {external_data_dir}\n",
        encoding="utf-8",
    )

    paths = ProjectPaths.from_root(project_root)

    assert paths.data_dir == external_data_dir
    assert paths.raw_dir == external_data_dir / "00_raw"
    assert paths.ingested_dir == external_data_dir / "01_ingested"
    assert paths.normalized_dir == external_data_dir / "02_normalized"
    assert paths.reports_dir == external_data_dir / "90_reports"
    assert paths.cache_dir == external_data_dir / "99_cache"
    assert paths.logs_dir == external_data_dir / "99_logs"

    paths.ensure_data_dirs()

    for subdir in DATA_SUBDIRS:
        assert (external_data_dir / subdir).is_dir()
    assert not (external_data_dir / ".gitkeep").exists()


def test_local_repo_data_dir_keeps_gitkeep(tmp_path: Path) -> None:
    project_root = tmp_path / "project"
    project_root.mkdir()

    paths = ProjectPaths.from_root(project_root)
    paths.ensure_data_dirs()

    assert paths.data_dir == project_root / "data"
    assert (project_root / "data" / ".gitkeep").exists()


def test_explicit_absolute_stage_path_overrides_data_dir(tmp_path: Path) -> None:
    project_root = tmp_path / "project"
    external_data_dir = tmp_path / "external_data"
    explicit_raw_dir = tmp_path / "raw_override"
    config_dir = project_root / "configs"
    config_dir.mkdir(parents=True)
    (config_dir / "paths.yaml").write_text(
        f"data_dir: {external_data_dir}\nraw_dir: {explicit_raw_dir}\n",
        encoding="utf-8",
    )

    paths = ProjectPaths.from_root(project_root)

    assert paths.raw_dir == explicit_raw_dir
    assert paths.ingested_dir == external_data_dir / "01_ingested"
