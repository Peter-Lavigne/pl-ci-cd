import os
import subprocess
from pathlib import Path
from textwrap import dedent

import typer
from pl_mocks_and_fakes import MockInUnitTests, MockReason
from pl_run_program import (
    SimpleProgramError,
    run_simple_program,
)
from pl_tiny_clients.git_push import git_push
from pl_user_io.display import display
from pl_user_io.task import task

from pl_ci_cd._constants import GIT_PROGRAM

MAIN_BRANCH = "main"

REBASE_CONFLICT_PROMPT = dedent("""\
    A rebase conflict occurred in the worktree at {worktree}. Hand the
    following message to the agent working in that worktree:

    ----
    I just rebased this branch onto {main_branch} as part
    of a CD process, and there were conflicts.
    Now, there are conflict markers in one or more files in this worktree.
    Resolve them in place by editing the affected files only. Do NOT run
    any git commands — leave staging, rebasing, and committing to the
    outer process. When you are done, or if you determine the conflict
    is irreconcilable, report back.
    ----
""")


@MockInUnitTests(MockReason.UNMITIGATED_SIDE_EFFECT)
def fix_with_agent(prompt: str) -> None:
    task(prompt)


def ship(worktree: Path | None = None, repo_dir: Path | None = None) -> None:
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

    if worktree is not None:
        _merge(worktree, repo_dir, test_script)
    else:
        _commit_and_test(repo_dir, test_script)

    display("Pushing...")
    git_push()

    display(f"Deploying ({deploy_script})...")
    _run_deploy(deploy_script, repo_dir)

    display("Shipped.")


def _commit_and_test(repo_dir: Path, ci_script: Path) -> None:
    if not _git(repo_dir, "status", "--porcelain").strip():
        msg = f"Repository at {repo_dir} has no changes to ship."
        raise RuntimeError(msg)

    display("Committing changes...")
    _git(repo_dir, "add", "-A")
    _git(repo_dir, "commit", "-m", "Commit")

    display(f"Running CI ({ci_script})...")
    _run_ci(ci_script, repo_dir)


def _merge(worktree: Path, repo_dir: Path, ci_script: Path) -> None:
    if _git(repo_dir, "status", "--porcelain").strip():
        msg = f"Repository at {repo_dir} is dirty. Commit or stash changes first."
        raise RuntimeError(msg)

    display("Committing worktree changes...")
    _git(worktree, "add", "-A")
    _git(worktree, "commit", "-m", "Commit")

    display(f"Rebasing onto {MAIN_BRANCH}...")
    try:
        _git(worktree, "rebase", MAIN_BRANCH)
    except SimpleProgramError:
        _handle_rebase_conflict(worktree)
        _undo_auto_commit(worktree)
        msg = (
            "Rebase conflict was resolved. Review the unstaged changes in "
            f"{worktree} and re-run when satisfied."
        )
        raise RuntimeError(msg) from None

    display(f"Running CI ({ci_script})...")
    _run_ci(ci_script, worktree)

    branch = _git(worktree, "branch", "--show-current").strip()
    display(f"Fast-forward merging {branch} into {MAIN_BRANCH}...")
    _git(repo_dir, "merge", "--ff-only", branch)


def _handle_rebase_conflict(worktree: Path) -> None:
    fix_with_agent(
        REBASE_CONFLICT_PROMPT.format(worktree=worktree, main_branch=MAIN_BRANCH)
    )

    try:
        _git(worktree, "diff", "--check")
    except SimpleProgramError:
        _git(worktree, "rebase", "--abort")
        _undo_auto_commit(worktree)
        msg = "Rebase conflict was irreconcilable; aborted."
        raise RuntimeError(msg) from None

    _git(worktree, "add", "-A")
    # `-c core.editor=/bin/true` skips the commit-message editor that
    # `git rebase --continue` would otherwise pop up. Absolute path so
    # git doesn't need PATH to locate it.
    _git(worktree, "-c", "core.editor=/bin/true", "rebase", "--continue")


def _run_ci(ci_script: Path, worktree: Path) -> None:
    result = subprocess.run(
        [str(ci_script)], cwd=worktree, env=dict(os.environ), check=False
    )
    if result.returncode != 0:
        _undo_auto_commit(worktree)
        msg = f"CI failed with return code {result.returncode}."
        raise RuntimeError(msg)


def _run_deploy(deploy_script: Path, cwd: Path) -> None:
    result = subprocess.run(
        [str(deploy_script)], cwd=cwd, env=dict(os.environ), check=False
    )
    if result.returncode != 0:
        msg = f"Deploy failed with return code {result.returncode}."
        raise RuntimeError(msg)


def _undo_auto_commit(worktree: Path) -> None:
    """Revert ship's own commit so the agent's edits remain in the worktree as unstaged changes."""
    _git(worktree, "reset", "--mixed", "HEAD~1")


def _git(cwd: Path, *args: str) -> str:
    return run_simple_program(GIT_PROGRAM, list(args), cwd=cwd, env=dict(os.environ))


def main() -> None:
    typer.run(ship)  # pragma: no cover
