from pl_run_program.run_simple_program import run_simple_program

from ._constants import UV_PROGRAM


def package_version() -> str:
    return run_simple_program(UV_PROGRAM, ["version", "--short"]).strip()
