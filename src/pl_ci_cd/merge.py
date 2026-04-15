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
from pl_user_io.display import display
from pl_user_io.task import task

from pl_ci_cd._constants import GIT_PROGRAM

REBASE_CONFLICT_PROMPT = dedent("""\
    A rebase conflict occurred in the worktree at {worktree}. Hand the
    following message to the agent working in that worktree:

    ----
    There are conflict markers in one or more files in this worktree.
    Resolve them in place by editing the affected files only. Do NOT run
    any git commands — leave staging, rebasing, and committing to the
    outer process. When you are done, or if you determine the conflict
    is irreconcilable, report back.
    ----
""")


@MockInUnitTests(MockReason.UNMITIGATED_SIDE_EFFECT)
def fix_with_agent(prompt: str) -> None:
    task(prompt)


def merge(worktree: Path, repo_dir: Path, main_branch: str, ci_script: Path) -> None:
    display("Committing worktree changes...")
    _git(worktree, "add", "-A")
    _git(worktree, "commit", "-m", "Commit")

    display(f"Rebasing onto {main_branch}...")
    try:
        _git(worktree, "rebase", main_branch)
    except SimpleProgramError:
        _handle_rebase_conflict(worktree)

    display(f"Running CI ({ci_script})...")
    _run_ci(ci_script, worktree)

    branch = _git(worktree, "branch", "--show-current").strip()
    display(f"Fast-forward merging {branch} into {main_branch}...")
    _git(repo_dir, "merge", "--ff-only", branch)
    display("Done.")


def _handle_rebase_conflict(worktree: Path) -> None:
    fix_with_agent(REBASE_CONFLICT_PROMPT.format(worktree=worktree))

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
    # Inherit stdout/stderr so CI output streams live to the user's terminal.
    result = subprocess.run(
        [str(ci_script)], cwd=worktree, env=dict(os.environ), check=False
    )
    if result.returncode != 0:
        _undo_auto_commit(worktree)
        msg = f"CI failed with return code {result.returncode}."
        raise RuntimeError(msg)


def _undo_auto_commit(worktree: Path) -> None:
    """Revert merge's own commit so the agent's edits remain in the worktree as unstaged changes."""
    _git(worktree, "reset", "--mixed", "HEAD~1")


def _git(cwd: Path, *args: str) -> str:
    return run_simple_program(GIT_PROGRAM, list(args), cwd=cwd, env=dict(os.environ))


def main() -> None:
    typer.run(merge)  # pragma: no cover
