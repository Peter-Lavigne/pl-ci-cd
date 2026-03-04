import contextlib
from pathlib import Path

from pl_tiny_clients.initialize_uv_project import initialize_uv_project

from pl_ci_cd.bump_package_version_patch import bump_package_version_patch
from pl_ci_cd.package_version import package_version


def _set_up(tmp_path: Path) -> None:
    initialize_uv_project(project_path=tmp_path)


def test_bump_package_version_patch_bumps_version(tmp_path: Path) -> None:
    _set_up(tmp_path)
    with contextlib.chdir(tmp_path):
        assert package_version() == "0.1.0"

        bump_package_version_patch()

        assert package_version() == "0.1.1"
