from pathlib import Path

from pl_run_program import program_at_path

UV_PROGRAM = program_at_path(Path.home() / ".local/bin/uv")
