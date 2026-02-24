import contextlib
from pathlib import Path
from textwrap import dedent

import pytest
from pl_mocks_and_fakes import mock_for
from pl_user_io.testing import assert_displayed, assert_loading_spinner_displayed

from pl_ci_cd._check import check
from pl_ci_cd._check_format import FormatCheckError
from pl_ci_cd._check_types import TypeCheckError, check_types
from pl_ci_cd._run_unit_tests_and_coverage import (
    CoverageOrTestsError,
    run_unit_tests_and_coverage,
)
from pl_ci_cd.testing._set_up import set_up_check


def _set_up(tmp_path: Path) -> None:
    set_up_check(tmp_path)


def test_uses_current_working_directory_if_directory_not_passed(tmp_path: Path) -> None:
    _set_up(tmp_path)
    (tmp_path / "test.py").write_text("x=1+2\n")
    with contextlib.chdir(tmp_path), pytest.raises(FormatCheckError):
        check(fix=False)


def test_raises_error_if_not_in_pyproject(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError, match="Could not find `pyproject.toml`"):
        check(directory=tmp_path)


def test_runs_all_checks_from_pyproject_root(tmp_path: Path) -> None:
    # Create a subdirectory and run `check` from there to verify that it correctly finds the pyproject root and runs checks from there.
    _set_up(tmp_path)
    sub_dir_1 = tmp_path / "sub_dir_1"
    sub_dir_1.mkdir()
    (sub_dir_1 / "test.py").write_text("x=1+2\n")
    sub_dir_2 = sub_dir_1 / "sub_dir_2"
    sub_dir_2.mkdir()

    with pytest.raises(FormatCheckError):
        check(fix=False, directory=sub_dir_2)


def test_formats_code_when_fix_true(tmp_path: Path) -> None:
    _set_up(tmp_path)
    (tmp_path / "test.py").write_text("x=1+2\n")

    check(fix=True, directory=tmp_path)

    assert_loading_spinner_displayed("Formatter")
    assert (tmp_path / "test.py").read_text() == "x = 1 + 2\n"


def test_lints_code_when_fix_true(tmp_path: Path) -> None:
    _set_up(tmp_path)
    (tmp_path / "test.py").write_text("import os\nx = 1\n")  # unused import

    check(fix=True, directory=tmp_path)

    assert_loading_spinner_displayed("Linter")
    assert (tmp_path / "test.py").read_text() == "\nx = 1\n"


def test_checks_format_when_fix_false__pass(tmp_path: Path) -> None:
    _set_up(tmp_path)
    (tmp_path / "test.py").write_text("x = 1 + 2\n")

    check(fix=False, directory=tmp_path)

    assert_loading_spinner_displayed("Formatter")
    assert (tmp_path / "test.py").read_text() == "x = 1 + 2\n"


def test_checks_format_when_fix_false__fail(tmp_path: Path) -> None:
    _set_up(tmp_path)
    (tmp_path / "test.py").write_text("x=1+2\n")

    with pytest.raises(FormatCheckError) as exc_info:
        check(fix=False, directory=tmp_path)

    assert_displayed("✗ Formatter")
    assert "Format check failed" in str(exc_info.value)


def test_checks_linting__pass(tmp_path: Path) -> None:
    _set_up(tmp_path)
    (tmp_path / "test.py").write_text("print(1 + 2)\n")

    check(fix=True, directory=tmp_path)

    assert_loading_spinner_displayed("Linter")


def test_checks_linting__fail(tmp_path: Path) -> None:
    _set_up(tmp_path)
    (tmp_path / "test.py").write_text("x = undefined_var\n")  # unfixable

    with pytest.raises(
        RuntimeError,
        match=r"(?s)Linting failed, aborting commit. Output:.*undefined_var.*",
    ):
        check(fix=True, directory=tmp_path)

    assert_displayed("✗ Linter")


def test_checks_types__pass(tmp_path: Path) -> None:
    _set_up(tmp_path)
    mock_for(check_types).side_effect = None
    (tmp_path / "test.py").write_text("x: int = 1\n")

    check(fix=True, directory=tmp_path)

    assert_loading_spinner_displayed("Type checks")


def test_checks_types__fail(tmp_path: Path) -> None:
    _set_up(tmp_path)
    mock_for(check_types).side_effect = TypeCheckError("Type check failed")
    (tmp_path / "test.py").write_text("x: int = 'string'\n")

    with pytest.raises(TypeCheckError) as exc_info:
        check(fix=True, directory=tmp_path)

    assert_displayed("✗ Type checks")
    assert "Type check failed" in str(exc_info.value)


def test_runs_pytest__pass(tmp_path: Path) -> None:
    _set_up(tmp_path)
    mock_for(run_unit_tests_and_coverage).side_effect = None
    (tmp_path / "test_pass.py").write_text(
        dedent("""\
        def test_pass():
            assert 1 + 2 == 3
    """)
    )

    check(fix=True, directory=tmp_path)

    assert_loading_spinner_displayed("Tests + Coverage")


def test_runs_pytest__fail(tmp_path: Path) -> None:
    _set_up(tmp_path)
    mock_for(run_unit_tests_and_coverage).side_effect = CoverageOrTestsError(
        "Tests failed"
    )
    (tmp_path / "test_fail.py").write_text(
        dedent("""\
        def test_fail():
            assert 1 + 2 == 4
    """)
    )

    with pytest.raises(CoverageOrTestsError):
        check(fix=True, directory=tmp_path)

    assert_displayed("✗ Tests + Coverage")
