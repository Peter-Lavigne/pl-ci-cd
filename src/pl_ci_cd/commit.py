from pathlib import Path

import typer
from pl_tiny_clients.git_add_all import git_add_all
from pl_tiny_clients.git_any_uncommitted_changes import git_any_uncommitted_changes
from pl_tiny_clients.git_commit import git_commit
from pl_tiny_clients.git_push import git_push
from pl_user_io.display import display
from pl_user_io.loading_spinner import loading_spinner

from pl_ci_cd import check


def commit(directory: Path | None = None) -> None:
    if directory is None:
        directory = Path.cwd()

    if not git_any_uncommitted_changes():
        display("No changes to commit, exiting.")
        return

    check(fix=True, directory=directory)

    git_add_all()

    git_commit(message="Commit")

    with loading_spinner("Pushing changes"):
        git_push()


def main() -> None:
    typer.run(commit)  # pragma: no cover
