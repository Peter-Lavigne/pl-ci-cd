from pathlib import Path

from pl_ci_cd._initialize_uv_project import initialize_uv_project


def test_initialize_uv_project(tmp_path: Path) -> None:
    initialize_uv_project(project_path=tmp_path)

    assert (tmp_path / "pyproject.toml").exists()
