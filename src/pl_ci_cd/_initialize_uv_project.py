import platform
from pathlib import Path

from pl_run_program.run_simple_program import run_simple_program

from pl_ci_cd._constants import UV_PROGRAM

UvProjectPath = Path


def initialize_uv_project(project_path: Path) -> UvProjectPath:
    """Initialize a bare, offline uv project at `project_path` using the configured uv binary."""
    args: list[str] = [
        "init",
        "--offline",
        "--bare",
        str(project_path),
        "--python",
        platform.python_version(),
    ]

    run_simple_program(UV_PROGRAM, args)

    return UvProjectPath(project_path)
