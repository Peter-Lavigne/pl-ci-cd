from pathlib import Path
from textwrap import dedent

import pytest
from pl_tiny_clients.initialize_uv_project import initialize_uv_project

from pl_ci_cd._lint import LintError, lint
from pl_ci_cd.testing._set_up import set_up_lint


def _set_up(tmp_path: Path) -> None:
    uv_project_path = initialize_uv_project(
        project_path=tmp_path,
    )
    set_up_lint(uv_project_path)


def test_lint_passes_for_valid_code(tmp_path: Path) -> None:
    _set_up(tmp_path)
    valid_code = "x = 1 + 2\n"
    (tmp_path / "test.py").write_text(valid_code)

    result = lint(tmp_path)

    assert result.passed
    assert "All checks passed!" in result.output


def test_lint_fails_for_invalid_code(tmp_path: Path) -> None:
    _set_up(tmp_path)
    invalid_code = "import os\nx = 1\n"  # unused import
    (tmp_path / "test.py").write_text(invalid_code)

    result = lint(tmp_path)

    assert not result.passed
    assert "unused" in result.output


def test_lint_fails_for_warnings(tmp_path: Path) -> None:
    _set_up(tmp_path)
    valid_code = "x = 1 + 2\n"
    (tmp_path / "test.py").write_text(valid_code)
    # Select a preview rule without enabling preview mode to trigger a warning.
    (tmp_path / "pyproject.toml").write_text(
        dedent("""\
        [tool.ruff.lint]
        select = ["PLW0244"]
    """)
    )

    result = lint(tmp_path)

    assert not result.passed
    assert "warning" in result.output


def test_lint_fix_fixes_fixable_violations(tmp_path: Path) -> None:
    _set_up(tmp_path)
    (tmp_path / "test.py").write_text("import os\nx = 1\n")  # unused import

    result = lint(tmp_path, fix=True)

    assert result.passed
    assert (tmp_path / "test.py").read_text() == "x = 1\n"


def test_lint_fix_fails_when_violations_unfixable(tmp_path: Path) -> None:
    _set_up(tmp_path)
    (tmp_path / "test.py").write_text("x = undefined_var\n")  # undefined name

    result = lint(tmp_path, fix=True)

    assert not result.passed
    assert "undefined_var" in result.output


def test_lint_raises_on_ruff_exit_code_2(tmp_path: Path) -> None:
    _set_up(tmp_path)
    (tmp_path / "test.py").write_text("x = 1\n")
    (tmp_path / "pyproject.toml").write_text(
        dedent("""\
        [tool.ruff.lint]
        select = ["INVALID_RULE_XYZ123"]
    """)
    )

    with pytest.raises(LintError) as exc_info:
        lint(tmp_path)

    assert "linting failed with an unexpected error" in str(exc_info.value)
    assert "stdout" in str(exc_info.value)
    assert "stderr" in str(exc_info.value)
