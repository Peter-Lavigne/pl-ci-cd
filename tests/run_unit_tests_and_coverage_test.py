from pathlib import Path
from textwrap import dedent

import pytest
from pl_tiny_clients._initialize_uv_project import initialize_uv_project

from pl_ci_cd._run_unit_tests_and_coverage import (
    CoverageOrTestsError,
    run_unit_tests_and_coverage,
)
from pl_ci_cd.testing._set_up import set_up_run_unit_tests_and_coverage

from .constants import PYTEST_SLOW_MARKER

pytestmark = PYTEST_SLOW_MARKER


def _set_up(tmp_path: Path) -> None:
    uv_project_path = initialize_uv_project(project_path=tmp_path)
    set_up_run_unit_tests_and_coverage(uv_project_path)


def test_run_unit_tests_and_coverage__pass(tmp_path: Path) -> None:
    _set_up(tmp_path)
    (tmp_path / "math_utils.py").write_text(
        dedent("""\
        def add(x: int, y: int) -> int:
            return x + y
    """)
    )
    (tmp_path / "math_utils_test.py").write_text(
        dedent("""\
        from math_utils import add

        def test_add():
            assert add(1, 2) == 3
    """)
    )

    run_unit_tests_and_coverage(tmp_path)


def test_run_unit_tests_and_coverage__fail(tmp_path: Path) -> None:
    """Fail: tests fail."""
    _set_up(tmp_path)
    (tmp_path / "test_ok.py").write_text(
        dedent("""\
        def test_ok(): assert False
    """)
    )

    with pytest.raises(CoverageOrTestsError) as exc_info:
        run_unit_tests_and_coverage(tmp_path)

    assert "Tests or coverage failed" in str(exc_info.value)


def test_run_unit_tests_and_coverage__coverage_fails(tmp_path: Path) -> None:
    _set_up(tmp_path)
    (tmp_path / "math_utils.py").write_text(
        dedent("""\
        def add(x: int, y: int) -> int:
            return x + y

        def subtract(x: int, y: int) -> int:
            return x - y
    """)
    )
    (tmp_path / "math_utils_test.py").write_text(
        dedent("""\
        from math_utils import add

        def test_add():
            assert add(1, 2) == 3
    """)
    )

    with pytest.raises(CoverageOrTestsError) as exc_info:
        run_unit_tests_and_coverage(tmp_path)

    assert "Tests or coverage failed" in str(exc_info.value)


def test_run_unit_tests_and_coverage__coverage_file_written_to_directory(
    tmp_path: Path,
) -> None:
    # coverage.py writes a file in the current working directory. This can cause tests running coverage to fail if they share a working directory, since their coverages might be merged or overwritten.
    _set_up(tmp_path)
    (tmp_path / "passing_test.py").write_text(
        dedent("""\
        def test_ok(): assert True
    """)
    )

    run_unit_tests_and_coverage(tmp_path)

    assert (tmp_path / ".coverage").exists()
