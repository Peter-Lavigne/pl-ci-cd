import os
import subprocess
from pathlib import Path

import typer
from pl_tiny_clients.git_push import git_push
from pl_user_io.display import display

from pl_ci_cd.merge import merge

MAIN_BRANCH = "main"


def ship(worktree: Path, repo_dir: Path | None = None) -> None:
    if repo_dir is None:
        repo_dir = Path.cwd()  # pragma: no cover
    test_script = repo_dir / ".ship" / "test"
    deploy_script = repo_dir / ".ship" / "deploy"
    if not test_script.exists():
        msg = f"Missing {test_script}"
        raise RuntimeError(msg)
    if not deploy_script.exists():
        msg = f"Missing {deploy_script}"
        raise RuntimeError(msg)

    merge(
        worktree=worktree,
        repo_dir=repo_dir,
        main_branch=MAIN_BRANCH,
        ci_script=test_script,
    )

    display("Pushing...")
    git_push()

    display(f"Deploying ({deploy_script})...")
    _run_deploy(deploy_script, repo_dir)

    display("Shipped.")


def _run_deploy(deploy_script: Path, cwd: Path) -> None:
    result = subprocess.run(
        [str(deploy_script)], cwd=cwd, env=dict(os.environ), check=False
    )
    if result.returncode != 0:
        msg = f"Deploy failed with return code {result.returncode}."
        raise RuntimeError(msg)


def main() -> None:
    typer.run(ship)  # pragma: no cover
