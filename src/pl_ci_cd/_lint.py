from dataclasses import dataclass
from pathlib import Path

from pl_run_program.run_program import run_program

from ._constants import UV_PROGRAM


@dataclass
class LintResult:
    passed: bool
    output: str


class LintError(Exception):
    pass


def lint(directory: Path, fix: bool = False) -> LintResult:
    args = ["run", "ruff", "check"]
    if fix:
        args.append("--fix")
    args.append(str(directory))
    result = run_program(UV_PROGRAM, args)

    # From https://docs.astral.sh/ruff/linter/#exit-codes:
    # """
    # By default, ruff check exits with the following status codes:
    # 0 if no violations were found, or if all present violations were fixed automatically.
    # 1 if violations were found.
    # 2 if Ruff terminates abnormally due to invalid configuration, invalid CLI options, or an internal error.
    # """

    if result.returncode == 2:
        msg = f"linting failed with an unexpected error. stdout: `{result.stdout}` stderr: `{result.stderr}`"
        raise LintError(msg)

    # As of 2026-01-26, Ruff does not have a separate exit code for warnings or related flag(s).
    warnings_present = "warning" in result.stderr.lower()

    passed = result.returncode == 0 and not warnings_present

    return LintResult(
        passed=passed,
        output="\n".join([f"stdout: {result.stdout}", f"stderr: {result.stderr}"]),
    )
