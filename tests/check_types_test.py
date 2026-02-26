from pathlib import Path

import pytest
from pl_tiny_clients.initialize_uv_project import initialize_uv_project

from pl_ci_cd._check_types import TypeCheckError, check_types
from pl_ci_cd.testing._set_up import set_up_type_check

from .constants import PYTEST_SLOW_MARKER

pytestmark = PYTEST_SLOW_MARKER


def _set_up(tmp_path: Path) -> None:
    uv_project_path = initialize_uv_project(
        project_path=tmp_path,
    )
    set_up_type_check(uv_project_path)


def test_check_types_passes_for_valid_code(tmp_path: Path) -> None:
    _set_up(tmp_path)
    valid_code = "x: int = 1 + 2\n"
    (tmp_path / "test.py").write_text(valid_code)

    check_types(tmp_path)


def test_check_types_fails_for_invalid_types(tmp_path: Path) -> None:
    _set_up(tmp_path)
    invalid_code = "x: int = 'string'\n"
    (tmp_path / "test.py").write_text(invalid_code)

    with pytest.raises(TypeCheckError) as exc_info:
        check_types(tmp_path)

    assert "Type check failed" in str(exc_info.value)
