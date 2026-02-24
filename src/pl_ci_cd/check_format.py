from pathlib import Path
from types import NoneType

from pl_run_program import run_program, run_simple_program

from pl_ci_cd.constants import UV_PROGRAM


class FormatCheckError(Exception):
    pass


def check_format(directory: Path, fix: bool) -> NoneType:
    args = ["run", "ruff", "format"]
    if not fix:
        args.append("--check")
    args.append(str(directory))
    if fix:
        run_simple_program(UV_PROGRAM, args)
        return
    result = run_program(UV_PROGRAM, args)
    if result.returncode != 0:
        msg = (
            f"Format check failed. stdout: `{result.stdout}` stderr: `{result.stderr}`"
        )
        raise FormatCheckError(msg)
