import contextlib
import tomllib
from pathlib import Path

from pl_tiny_clients.initialize_uv_project import initialize_uv_project

from pl_ci_cd.package_version import package_version


def _set_up(tmp_path: Path) -> None:
    initialize_uv_project(project_path=tmp_path)


def test_package_version_returns_version_from_pyproject(
    tmp_path: Path,
) -> None:
    _set_up(tmp_path)
    with contextlib.chdir(tmp_path):
        version = package_version()

    config = tomllib.loads((tmp_path / "pyproject.toml").read_text())
    assert version == config["project"]["version"]
