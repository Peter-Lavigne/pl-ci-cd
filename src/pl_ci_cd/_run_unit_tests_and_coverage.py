from pathlib import Path
from types import NoneType

from pl_mocks_and_fakes import MockInUnitTests, MockReason
from pl_run_program.run_program import run_program

from ._constants import UV_PROGRAM


class CoverageOrTestsError(Exception):
    pass


@MockInUnitTests(MockReason.SLOW)
def run_unit_tests_and_coverage(directory: Path) -> NoneType:
    """
    Run pytest with coverage in one command. Raises if tests fail or coverage is below 100%.

    Tests and coverage are combined to save time during CI.
    """
    args = ["run", "pytest", "--cov", "--cov-fail-under=100", "-q", str(directory)]
    result = run_program(UV_PROGRAM, args, cwd=directory)

    if result.returncode == 0:
        return

    msg = (
        f"Tests or coverage failed. stdout: `{result.stdout}` stderr: `{result.stderr}`"
    )
    raise CoverageOrTestsError(msg)
