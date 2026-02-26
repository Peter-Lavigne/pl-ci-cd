import importlib.metadata
from pathlib import Path

import ruff  # pyright: ignore[reportMissingTypeStubs]
from pl_mocks_and_fakes import mock_for
from pl_run_program import run_simple_program
from pl_tiny_clients._initialize_uv_project import UvProjectPath, initialize_uv_project

from pl_ci_cd._check_types import check_types
from pl_ci_cd._constants import UV_PROGRAM
from pl_ci_cd._run_unit_tests_and_coverage import run_unit_tests_and_coverage


def set_up_formatter(uv_project_path: UvProjectPath) -> None:
    """All subsequent calls to `format_code` should use `tmp_path` as the working directory."""
    ruff_version = importlib.metadata.version(ruff.__name__)
    run_simple_program(
        UV_PROGRAM,
        ["add", "--offline", f"ruff=={ruff_version}"],
        cwd=uv_project_path,
    )


def set_up_type_check(uv_project_path: UvProjectPath) -> None:
    pyright_version = importlib.metadata.version("pyright")
    run_simple_program(
        UV_PROGRAM,
        ["add", "--offline", f"pyright=={pyright_version}"],
        cwd=uv_project_path,
    )


def set_up_lint(uv_project_path: UvProjectPath) -> None:
    """All subsequent calls to `lint` should use `lint_path` as the working directory."""
    ruff_version = importlib.metadata.version(ruff.__name__)
    run_simple_program(
        UV_PROGRAM,
        ["add", "--offline", f"ruff=={ruff_version}"],
        cwd=uv_project_path,
    )
    (uv_project_path / "__init__.py").write_text("")


def set_up_run_unit_tests_and_coverage(uv_project_path: UvProjectPath) -> None:
    pytest_version = importlib.metadata.version("pytest")
    pytest_cov_version = importlib.metadata.version("pytest-cov")
    run_simple_program(
        UV_PROGRAM,
        [
            "add",
            "--offline",
            f"pytest=={pytest_version}",
            f"pytest-cov=={pytest_cov_version}",
        ],
        cwd=uv_project_path,
    )


def set_up_check(tmp_path: Path) -> None:
    uv_project_path = initialize_uv_project(tmp_path)
    set_up_lint(uv_project_path)
    set_up_formatter(uv_project_path)

    mock_for(check_types).side_effect = None
    # To be used if I unmock run_unit_tests_and_coverage:
    # set_up_type_check(uv_project_path)

    mock_for(run_unit_tests_and_coverage).side_effect = None
    # To be used if I unmock run_unit_tests_and_coverage:
    # set_up_run_unit_tests_and_coverage(uv_project_path)
    # # pytest fails when there are no tests, so add a passing test.
    # (tmp_path / "basic_test.py").write_text(
    #     dedent("""\
    #     def test_pass():
    #         assert 1 + 1 == 2
    # """)
    # )
