import contextlib
from pathlib import Path

import typer
from pl_user_io.loading_spinner import loading_spinner

from pl_ci_cd._check_format import check_format
from pl_ci_cd._check_types import check_types
from pl_ci_cd._lint import lint
from pl_ci_cd._run_unit_tests_and_coverage import run_unit_tests_and_coverage


def check(directory: Path | None = None, fix: bool = False) -> None:
    if directory is None:
        directory = Path.cwd()

    pyproject_root = directory
    while not (pyproject_root / "pyproject.toml").exists():
        if pyproject_root.parent == pyproject_root:
            msg = f"Could not find `pyproject.toml` in {directory} or any parent directories."
            raise FileNotFoundError(msg)
        pyproject_root = pyproject_root.parent

    with contextlib.chdir(pyproject_root):
        with loading_spinner("Formatter"):
            check_format(pyproject_root, fix)

        with loading_spinner("Linter"):
            lint_result = lint(pyproject_root, fix=fix)
            if not lint_result.passed:
                msg = f"Linting failed, aborting commit. Output:\n{lint_result.output}"
                raise RuntimeError(msg)

        with loading_spinner("Type checks"):
            check_types(pyproject_root)

        with loading_spinner("Tests + Coverage"):
            run_unit_tests_and_coverage(pyproject_root)


def main() -> None:
    typer.run(check)  # pragma: no cover
