import os
import subprocess
import sys
from pathlib import Path
from textwrap import dedent
from typing import Annotated

import typer
from pl_mocks_and_fakes import MockInUnitTests, MockReason
from pl_run_program import SimpleProgramError, run_simple_program
from pl_tiny_clients.git_push import git_push
from pl_user_io.display import display

from verploy._constants import GIT_PROGRAM

MAIN_BRANCH = "main"
GIT_CREDENTIALS = Path.home() / ".git-credentials"

app = typer.Typer()


@MockInUnitTests(MockReason.UNMITIGATED_SIDE_EFFECT)
def git_credentials_present() -> bool:
    return GIT_CREDENTIALS.exists()  # pragma: no cover


def _detect_worktree(cwd: Path) -> tuple[Path | None, Path]:  # pragma: no cover
    git_dir = (cwd / _git(cwd, "rev-parse", "--git-dir").strip()).resolve()
    git_common_dir = (
        cwd / _git(cwd, "rev-parse", "--git-common-dir").strip()
    ).resolve()
    if git_dir != git_common_dir:
        worktree = Path(_git(cwd, "rev-parse", "--show-toplevel").strip())
        repo_dir = git_common_dir.parent
        return worktree, repo_dir
    return None, cwd


@app.callback(invoke_without_command=True)
def verploy_cmd(  # pragma: no cover
    worktree: Annotated[Path | None, typer.Option("--worktree", "-w")] = None,
    repo_dir: Annotated[Path | None, typer.Option()] = None,
) -> None:
    if worktree is None and repo_dir is None:
        worktree, repo_dir = _detect_worktree(Path.cwd())
    elif repo_dir is None:
        repo_dir = Path.cwd()
    verploy(repo_dir, worktree)


def _validate_verploy_dir(
    repo_dir: Path,
) -> tuple[Path | None, Path | None]:
    deploy_script = repo_dir / ".verploy" / "deploy"
    manual_file = repo_dir / ".verploy" / "manual"
    if not deploy_script.exists():
        display("No deploy script found, skipping deploy.")
        deploy_script = None
    if not manual_file.exists():
        display("No manual script found, skipping manual checks.")
        manual_file = None
    return deploy_script, manual_file


def _resolve_worktree(worktree: Path | str | None, repo_dir: Path) -> Path | None:
    if worktree is None:
        return None
    name = str(worktree)
    output = _git(repo_dir, "worktree", "list", "--porcelain")
    for line in output.splitlines():
        if line.startswith("worktree "):
            path = Path(line.removeprefix("worktree "))
            if path.name == name:
                return path
    worktree_path = Path(worktree)
    if worktree_path.exists():
        return worktree_path
    msg = f"No worktree found matching '{name}'"
    raise RuntimeError(msg)


def verploy(
    repo_dir: Path,
    worktree: Path | str | None = None,
) -> None:
    worktree = _resolve_worktree(worktree, repo_dir)
    if not git_credentials_present():
        msg = f"Missing {GIT_CREDENTIALS}"
        raise RuntimeError(msg)
    deploy_script, manual_script = _validate_verploy_dir(repo_dir)

    if worktree is not None:
        wt_manual = worktree / ".verploy" / "manual"
        if wt_manual.exists():
            manual_script = wt_manual
        _verploy_worktree(worktree, repo_dir, manual_script)
    else:
        _verploy_main(repo_dir, manual_script)

    if deploy_script is not None:
        display(f"Deploying ({deploy_script})...")
        _run_deploy(deploy_script, repo_dir)
        display("Deployed.")

    display("Pushing...")
    git_push()


def _verploy_main(
    repo_dir: Path,
    manual_script: Path | None,
) -> None:
    _require_clean(repo_dir)

    try:
        unpushed = _git(repo_dir, "rev-list", "@{u}..HEAD").strip()
    except SimpleProgramError:
        pass
    else:
        if not unpushed:
            msg = f"{MAIN_BRANCH} has nothing to deploy: no unpushed commits."
            raise RuntimeError(msg)

    if manual_script is not None:
        _run_manual_checks(manual_script, repo_dir)


def _require_clean(cwd: Path) -> None:
    if _git(cwd, "status", "--porcelain").strip():
        msg = (
            f"Repository at {cwd} has uncommitted changes."
            " This project uses Verploy for coding agent CI/CD."
            " Verploy requires all changes to be committed before it can run."
            " Commit all changes now, even partial or work-in-progress ones."
            " If there are unrelated unstaged changes, commit them separately and inform the user."
        )
        raise RuntimeError(msg)


def _require_rebased(worktree: Path) -> None:
    try:
        _git(worktree, "merge-base", "--is-ancestor", MAIN_BRANCH, "HEAD")
    except SimpleProgramError:
        branch = _git(worktree, "branch", "--show-current").strip()
        msg = f"Branch {branch} is not rebased onto main. Run: git rebase main"
        raise RuntimeError(msg) from None


def _verploy_worktree(
    worktree: Path,
    repo_dir: Path,
    manual_script: Path | None,
) -> None:
    _require_clean(worktree)
    _require_clean(repo_dir)
    _require_rebased(worktree)

    branch = _git(worktree, "branch", "--show-current").strip()
    new_commits = _git(worktree, "rev-list", f"{MAIN_BRANCH}..HEAD").strip()
    if not new_commits:
        msg = f"Branch {branch} has nothing to deploy: no commits beyond {MAIN_BRANCH}."
        raise RuntimeError(msg)

    if manual_script is not None:
        _run_manual_checks(manual_script, worktree)

    display(f"Fast-forward merging {branch} into {MAIN_BRANCH}...")
    _git(repo_dir, "merge", "--ff-only", branch)


def _run_manual_checks(manual_script: Path, cwd: Path) -> None:
    display(
        dedent(f"""\

        Running manual checks ({manual_script})...
    """)
    )
    result = subprocess.run(
        [str(manual_script)], cwd=cwd, env=dict(os.environ), check=False
    )
    if result.returncode != 0:
        msg = "Manual checks failed."
        raise RuntimeError(msg)


def _run_deploy(deploy_script: Path, cwd: Path) -> None:
    result = subprocess.run(
        [str(deploy_script)], cwd=cwd, env=dict(os.environ), check=False
    )
    if result.returncode != 0:
        msg = f"Deploy failed with return code {result.returncode}."
        raise RuntimeError(msg)


def _git(cwd: Path, *args: str) -> str:
    return run_simple_program(GIT_PROGRAM, list(args), cwd=cwd, env=dict(os.environ))


def _run_verify(verify_script: Path, cwd: Path) -> None:
    result = subprocess.run(
        [str(verify_script)], cwd=cwd, env=dict(os.environ), check=False
    )
    if result.returncode != 0:
        msg = f"Verification failed with return code {result.returncode}."
        raise RuntimeError(msg)


def run_hook(cwd: Path) -> None:
    _require_clean(cwd)
    git_dir = (cwd / _git(cwd, "rev-parse", "--git-dir").strip()).resolve()
    git_common_dir = (
        cwd / _git(cwd, "rev-parse", "--git-common-dir").strip()
    ).resolve()
    if git_dir != git_common_dir:
        _require_rebased(cwd)
    verify_script = cwd / ".verploy" / "verify"
    if verify_script.exists():
        _run_verify(verify_script, cwd)
    _require_clean(cwd)


def hook() -> None:  # pragma: no cover
    sys.stdin.read()
    try:
        run_hook(Path.cwd())
    except RuntimeError as e:
        print(str(e), file=sys.stderr)
        sys.exit(2)


def main() -> None:
    app()  # pragma: no cover
