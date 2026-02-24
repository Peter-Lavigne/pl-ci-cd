import importlib.metadata
from pathlib import Path

import pytest
import ruff  # pyright: ignore[reportMissingTypeStubs]
from pl_run_program import run_simple_program

from pl_ci_cd.check_format import FormatCheckError, check_format
from pl_ci_cd.constants import UV_PROGRAM
from pl_ci_cd.initialize_uv_project import UvProjectPath, initialize_uv_project


def set_up_formatter(uv_project_path: UvProjectPath) -> None:
    """All subsequent calls to `format_code` should use `tmp_path` as the working directory."""
    ruff_version = importlib.metadata.version(ruff.__name__)
    run_simple_program(
        UV_PROGRAM,
        ["add", "--offline", f"ruff=={ruff_version}"],
        cwd=uv_project_path,
    )


def _set_up(tmp_path: Path) -> None:
    uv_project_path = initialize_uv_project(
        project_path=tmp_path,
    )
    set_up_formatter(uv_project_path)


def test_check_format_formats_file(tmp_path: Path) -> None:
    _set_up(tmp_path)
    unformatted_code = "x=1+2"
    (tmp_path / "test.py").write_text(unformatted_code)

    check_format(tmp_path, True)

    formatted_code = (tmp_path / "test.py").read_text()
    assert formatted_code != unformatted_code
    assert "x = 1 + 2" in formatted_code


def test_check_format_check_passes_for_formatted_code(tmp_path: Path) -> None:
    _set_up(tmp_path)
    formatted_code = "x = 1 + 2\n"
    (tmp_path / "test.py").write_text(formatted_code)

    check_format(tmp_path, False)


def test_check_format_check_fails_for_unformatted_code(tmp_path: Path) -> None:
    _set_up(tmp_path)
    unformatted_code = "x=1+2"
    (tmp_path / "test.py").write_text(unformatted_code)

    with pytest.raises(FormatCheckError) as exc_info:
        check_format(tmp_path, False)

    assert "Format check failed" in str(exc_info.value)
