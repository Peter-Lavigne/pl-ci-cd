from pathlib import Path
from types import NoneType

from pl_mocks_and_fakes import MockInUnitTests, MockReason
from pl_run_program.run_program import run_program

from pl_ci_cd._constants import UV_PROGRAM


class TypeCheckError(Exception):
    pass


@MockInUnitTests(MockReason.SLOW)
def check_types(directory: Path) -> NoneType:
    args = ["run", "pyright", str(directory)]
    result = run_program(UV_PROGRAM, args)

    if result.returncode == 0:
        return

    msg = f"Type check failed. stdout: `{result.stdout}` stderr: `{result.stderr}`"
    raise TypeCheckError(msg)
