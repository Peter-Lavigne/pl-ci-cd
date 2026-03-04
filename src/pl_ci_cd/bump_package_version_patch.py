from pl_run_program.run_program import run_program

from ._constants import UV_PROGRAM


def bump_package_version_patch() -> None:
    run_program(UV_PROGRAM, ["version", "--bump", "patch"])
