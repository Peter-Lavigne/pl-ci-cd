import os
import sys
from pathlib import Path
from textwrap import dedent

import pytest
from pl_mocks_and_fakes import mock_for, stub
from pl_run_program import (
    program_at_path,
    run_program,
    run_simple_program,
)
from pl_tiny_clients.git_push import git_push
from pl_user_io.assert_yes import assert_yes
from pl_user_io.testing.user_io_fake import (
    assert_displayed,
    assert_displayed_in_order,
    assert_not_displayed,
)
from verploy._constants import GIT_PROGRAM
from verploy.verploy import git_credentials_present, run_hook, verploy

from tests.constants import PYTEST_MANUAL_MARKER

PYTHON_PROGRAM = program_at_path(Path(sys.executable))

MAIN = "main"
TOUCH = "/usr/bin/touch"
ARBITRARY_FILENAME = "feature.py"
ARBITRARY_TEXT = 'print("hello")\n'


def _git(cwd: Path, *args: str) -> str:
    return run_simple_program(GIT_PROGRAM, list(args), cwd=cwd)


def _commit_sha(cwd: Path) -> str:
    return _git(cwd, "rev-parse", "HEAD")


def _assert_committed(repo_dir: Path, filename: str, text: str) -> None:
    assert _git(repo_dir, "status", "--porcelain") == ""
    assert (repo_dir / filename).read_text() == text
    diff = _git(repo_dir, "diff-tree", "--no-commit-id", "--name-only", "-r", "HEAD")
    assert filename in diff


def _commit_all(cwd: Path, message: str) -> None:
    _git(cwd, "add", "-A")
    _git(cwd, "commit", "-m", message)


def _write_script(path: Path, body: str) -> None:
    path.write_text(f"#!/bin/sh\n{body}\n")
    path.chmod(0o755)


def _create_repo(tmp_path: Path) -> Path:
    repo_dir = tmp_path / "repo"
    repo_dir.mkdir()

    (repo_dir / "items.py").write_text('items = ["a"]\n')

    verploy_dir = repo_dir / ".verploy"
    verploy_dir.mkdir()
    _write_script(verploy_dir / "verify", "")
    _write_script(verploy_dir / "deploy", "")
    _write_script(verploy_dir / "manual", "")

    _git(repo_dir, "init", "-b", MAIN)
    _git(repo_dir, "config", "user.email", "test@example.com")
    _git(repo_dir, "config", "user.name", "Test")
    _commit_all(repo_dir, "initial")

    return repo_dir


@pytest.fixture
def repo_dir(tmp_path: Path) -> Path:
    return _create_repo(tmp_path)


@pytest.fixture
def worktree_dir(tmp_path: Path, repo_dir: Path) -> Path:
    worktree_dir = tmp_path / "worktree"
    _git(repo_dir, "worktree", "add", "-b", "feature", str(worktree_dir))
    return worktree_dir


@pytest.fixture(autouse=True)
def stub_git_credentials() -> None:
    stub(git_credentials_present)(True)


def _commit_deploy_script(repo_dir: Path, body: str) -> None:
    _write_script(repo_dir / ".verploy" / "deploy", body)
    _commit_all(repo_dir, "set deploy script")


def _commit_manual_script(repo_dir: Path, body: str) -> None:
    _write_script(repo_dir / ".verploy" / "manual", body)
    _commit_all(repo_dir, "set manual script")


def test_skips_deploying_if_deploy_script_missing(
    repo_dir: Path, worktree_dir: Path
) -> None:
    (repo_dir / ".verploy" / "deploy").unlink()
    _commit_all(repo_dir, "remove deploy script")
    _git(worktree_dir, "rebase", MAIN)
    (worktree_dir / ARBITRARY_FILENAME).write_text(ARBITRARY_TEXT)
    _commit_all(worktree_dir, "add feature")

    verploy(worktree=worktree_dir, repo_dir=repo_dir)

    assert_displayed("No deploy script found, skipping deploy.")
    assert_not_displayed("Deployed.")


def test_skips_manual_checks_if_manual_script_missing(
    tmp_path: Path, repo_dir: Path, worktree_dir: Path
) -> None:
    marker = tmp_path / "deployed.txt"
    _commit_deploy_script(repo_dir, f"{TOUCH} {marker}")
    (repo_dir / ".verploy" / "manual").unlink()
    _commit_all(repo_dir, "remove manual script")
    _git(worktree_dir, "rebase", MAIN)
    (worktree_dir / ARBITRARY_FILENAME).write_text(ARBITRARY_TEXT)
    _commit_all(worktree_dir, "add feature")

    verploy(worktree=worktree_dir, repo_dir=repo_dir)

    assert_displayed("No manual script found, skipping manual checks.")
    assert marker.exists()


def test_deploy_errors_if_no_git_credentials(
    repo_dir: Path, worktree_dir: Path
) -> None:
    (worktree_dir / ARBITRARY_FILENAME).write_text(ARBITRARY_TEXT)
    _commit_all(worktree_dir, "add feature")
    stub(git_credentials_present)(False)

    with pytest.raises(RuntimeError, match=r"\.git-credentials"):
        verploy(worktree=worktree_dir, repo_dir=repo_dir)


def test_worktree_merges_changes_into_main(repo_dir: Path, worktree_dir: Path) -> None:
    (worktree_dir / ARBITRARY_FILENAME).write_text(ARBITRARY_TEXT)
    _commit_all(worktree_dir, "add feature")

    verploy(worktree=worktree_dir, repo_dir=repo_dir)

    _assert_committed(repo_dir, ARBITRARY_FILENAME, ARBITRARY_TEXT)
    assert _commit_sha(repo_dir) == _commit_sha(worktree_dir)


def test_worktree_errors_if_worktree_is_dirty(
    repo_dir: Path, worktree_dir: Path
) -> None:
    (worktree_dir / ARBITRARY_FILENAME).write_text(ARBITRARY_TEXT)

    with pytest.raises(RuntimeError) as exc:
        verploy(worktree=worktree_dir, repo_dir=repo_dir)
    assert str(exc.value) == (
        f"Repository at {worktree_dir} has uncommitted changes."
        " This project uses Verploy for coding agent CI/CD."
        " Verploy requires all changes to be committed before it can run."
        " Commit all changes now, even partial or work-in-progress ones."
        " If there are unrelated unstaged changes, commit them separately and inform the user."
    )


def test_worktree_errors_if_not_rebased_onto_main(
    repo_dir: Path, worktree_dir: Path
) -> None:
    (repo_dir / "main_change.py").write_text("x = 1\n")
    _commit_all(repo_dir, "main commit")
    (worktree_dir / ARBITRARY_FILENAME).write_text(ARBITRARY_TEXT)
    _commit_all(worktree_dir, "add feature")

    with pytest.raises(RuntimeError, match="not rebased onto main"):
        verploy(worktree=worktree_dir, repo_dir=repo_dir)


def test_worktree_errors_if_repo_dir_is_dirty(
    repo_dir: Path, worktree_dir: Path
) -> None:
    (worktree_dir / ARBITRARY_FILENAME).write_text(ARBITRARY_TEXT)
    _commit_all(worktree_dir, "add feature")
    (repo_dir / "dirty.txt").write_text("uncommitted\n")

    with pytest.raises(RuntimeError) as exc:
        verploy(worktree=worktree_dir, repo_dir=repo_dir)
    assert str(exc.value) == (
        f"Repository at {repo_dir} has uncommitted changes."
        " This project uses Verploy for coding agent CI/CD."
        " Verploy requires all changes to be committed before it can run."
        " Commit all changes now, even partial or work-in-progress ones."
        " If there are unrelated unstaged changes, commit them separately and inform the user."
    )


def test_worktree_displays_progress_for_each_phase(
    repo_dir: Path, worktree_dir: Path
) -> None:
    (worktree_dir / ARBITRARY_FILENAME).write_text(ARBITRARY_TEXT)
    _commit_all(worktree_dir, "add feature")

    verploy(worktree=worktree_dir, repo_dir=repo_dir)

    assert_displayed_in_order(
        f"Fast-forward merging feature into {MAIN}",
        "Pushing",
        "Deploying",
        "Deployed.",
    )


def test_deploy_runs_manual_checks_after_verification(
    repo_dir: Path, worktree_dir: Path
) -> None:
    (worktree_dir / ARBITRARY_FILENAME).write_text(ARBITRARY_TEXT)
    _commit_all(worktree_dir, "add feature")
    manual_script = repo_dir / ".verploy" / "manual"

    verploy(worktree=worktree_dir, repo_dir=repo_dir)

    assert_displayed(
        dedent(f"""\

        Running manual checks ({manual_script})...
    """)
    )


def test_pushes_after_verploy(repo_dir: Path, worktree_dir: Path) -> None:
    (worktree_dir / ARBITRARY_FILENAME).write_text(ARBITRARY_TEXT)
    _commit_all(worktree_dir, "add feature")

    verploy(worktree=worktree_dir, repo_dir=repo_dir)

    mock_for(git_push).assert_called_once()


def test_runs_deploy_script(tmp_path: Path, repo_dir: Path, worktree_dir: Path) -> None:
    marker = tmp_path / "deployed.txt"
    _commit_deploy_script(repo_dir, f"{TOUCH} {marker}")
    _git(worktree_dir, "rebase", MAIN)
    (worktree_dir / ARBITRARY_FILENAME).write_text(ARBITRARY_TEXT)
    _commit_all(worktree_dir, "add feature")

    verploy(worktree=worktree_dir, repo_dir=repo_dir)

    assert marker.exists()


def test_deploy_failure_raises_error(repo_dir: Path, worktree_dir: Path) -> None:
    _commit_deploy_script(repo_dir, "exit 1")
    _git(worktree_dir, "rebase", MAIN)
    (worktree_dir / ARBITRARY_FILENAME).write_text(ARBITRARY_TEXT)
    _commit_all(worktree_dir, "add feature")

    with pytest.raises(RuntimeError, match="Deploy failed"):
        verploy(worktree=worktree_dir, repo_dir=repo_dir)


def test_ships_committed_changes_on_main(repo_dir: Path) -> None:
    (repo_dir / ARBITRARY_FILENAME).write_text(ARBITRARY_TEXT)
    _commit_all(repo_dir, "add feature")

    verploy(repo_dir=repo_dir)

    mock_for(git_push).assert_called_once()


def test_errors_if_main_is_dirty(repo_dir: Path) -> None:
    (repo_dir / ARBITRARY_FILENAME).write_text(ARBITRARY_TEXT)

    with pytest.raises(RuntimeError) as exc:
        verploy(repo_dir=repo_dir)
    assert str(exc.value) == (
        f"Repository at {repo_dir} has uncommitted changes."
        " This project uses Verploy for coding agent CI/CD."
        " Verploy requires all changes to be committed before it can run."
        " Commit all changes now, even partial or work-in-progress ones."
        " If there are unrelated unstaged changes, commit them separately and inform the user."
    )


def test_displays_progress_without_rebase_or_merge(
    repo_dir: Path,
) -> None:
    (repo_dir / ARBITRARY_FILENAME).write_text(ARBITRARY_TEXT)
    _commit_all(repo_dir, "add feature")

    verploy(repo_dir=repo_dir)

    assert_displayed_in_order(
        "Pushing",
        "Deploying",
        "Deployed.",
    )


def test_worktree_errors_when_nothing_to_deploy(
    repo_dir: Path, worktree_dir: Path
) -> None:
    with pytest.raises(RuntimeError, match="nothing to deploy"):
        verploy(worktree=worktree_dir, repo_dir=repo_dir)


def test_deploy_rolls_back_if_manual_checks_rejected_on_worktree(
    tmp_path: Path, repo_dir: Path, worktree_dir: Path
) -> None:
    marker = tmp_path / "deployed.txt"
    _commit_deploy_script(repo_dir, f"{TOUCH} {marker}")
    _commit_manual_script(repo_dir, "exit 1")
    main_head = _commit_sha(repo_dir)
    _git(worktree_dir, "rebase", MAIN)
    (worktree_dir / ARBITRARY_FILENAME).write_text(ARBITRARY_TEXT)
    _commit_all(worktree_dir, "add feature")

    with pytest.raises(RuntimeError, match="Manual checks failed"):
        verploy(worktree=worktree_dir, repo_dir=repo_dir)

    assert _commit_sha(repo_dir) == main_head
    mock_for(git_push).assert_not_called()
    assert not marker.exists()


def test_main_errors_when_nothing_to_deploy(tmp_path: Path, repo_dir: Path) -> None:
    _setup_remote(repo_dir, tmp_path)

    with pytest.raises(RuntimeError, match="nothing to deploy"):
        verploy(repo_dir=repo_dir)


def test_deploy_stops_if_manual_checks_rejected_on_main(
    tmp_path: Path, repo_dir: Path
) -> None:
    marker = tmp_path / "deployed.txt"
    _commit_deploy_script(repo_dir, f"{TOUCH} {marker}")
    _commit_manual_script(repo_dir, "exit 1")

    with pytest.raises(RuntimeError, match="Manual checks failed"):
        verploy(repo_dir=repo_dir)

    mock_for(git_push).assert_not_called()
    assert not marker.exists()


VERPLOY_ARGS = ["-c", "from verploy.verploy import main; main()"]


def _setup_remote(repo_dir: Path, tmp_path: Path) -> Path:
    remote_dir = tmp_path / "remote.git"
    remote_dir.mkdir()
    _git(remote_dir, "init", "--bare")
    _git(repo_dir, "remote", "add", "origin", str(remote_dir))
    _git(repo_dir, "config", "push.autoSetupRemote", "true")
    _git(repo_dir, "push", "-u", "origin", "main")
    return remote_dir


def _e2e_env(tmp_path: Path) -> dict[str, str]:
    fake_home = tmp_path / "fake_home"
    fake_home.mkdir(exist_ok=True)
    (fake_home / ".git-credentials").write_text("")
    real_local = Path.home() / ".local"
    if real_local.exists():
        (fake_home / ".local").symlink_to(real_local)
    return {**os.environ, "HOME": str(fake_home)}


def _run_verploy_e2e(command: str, *, cwd: Path, env: dict[str, str]) -> None:
    args = command.split()
    assert args[0] == "verploy"
    result = run_program(PYTHON_PROGRAM, [*VERPLOY_ARGS, *args[1:]], cwd=cwd, env=env)
    assert result.returncode == 0, result.stderr


def test_e2e_defaults_repo_dir_to_cwd(tmp_path: Path, repo_dir: Path) -> None:
    remote_dir = _setup_remote(repo_dir, tmp_path)
    (repo_dir / ARBITRARY_FILENAME).write_text(ARBITRARY_TEXT)
    _commit_all(repo_dir, "add feature")
    local_head = _commit_sha(repo_dir)

    _run_verploy_e2e("verploy", cwd=repo_dir, env=_e2e_env(tmp_path))

    remote_head = _git(remote_dir, "rev-parse", "main")
    assert remote_head == local_head


def test_e2e_detects_worktree_from_cwd(
    tmp_path: Path, repo_dir: Path, worktree_dir: Path
) -> None:
    _setup_remote(repo_dir, tmp_path)
    (worktree_dir / ARBITRARY_FILENAME).write_text(ARBITRARY_TEXT)
    _commit_all(worktree_dir, "add feature")

    _run_verploy_e2e("verploy", cwd=worktree_dir, env=_e2e_env(tmp_path))

    _assert_committed(repo_dir, ARBITRARY_FILENAME, ARBITRARY_TEXT)


def test_resolves_worktree_by_local_path(tmp_path: Path, repo_dir: Path) -> None:
    worktree_dir = tmp_path / "nested" / "dir" / "my-worktree"
    _git(repo_dir, "worktree", "add", "-b", "feature", str(worktree_dir))
    (worktree_dir / ARBITRARY_FILENAME).write_text(ARBITRARY_TEXT)
    _commit_all(worktree_dir, "add feature")

    verploy(worktree=worktree_dir, repo_dir=repo_dir)

    _assert_committed(repo_dir, ARBITRARY_FILENAME, ARBITRARY_TEXT)


def test_resolves_worktree_by_basename(tmp_path: Path, repo_dir: Path) -> None:
    worktree_dir = tmp_path / "nested" / "dir" / "my-worktree"
    _git(repo_dir, "worktree", "add", "-b", "feature", str(worktree_dir))
    (worktree_dir / ARBITRARY_FILENAME).write_text(ARBITRARY_TEXT)
    _commit_all(worktree_dir, "add feature")

    verploy(worktree="my-worktree", repo_dir=repo_dir)

    _assert_committed(repo_dir, ARBITRARY_FILENAME, ARBITRARY_TEXT)


def test_prefers_worktree_basename_over_local_path(
    tmp_path: Path, repo_dir: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    worktree_dir = tmp_path / "nested" / "dir" / "wt"
    _git(repo_dir, "worktree", "add", "-b", "feature", str(worktree_dir))
    (worktree_dir / ARBITRARY_FILENAME).write_text(ARBITRARY_TEXT)
    _commit_all(worktree_dir, "add feature")
    decoy_dir = repo_dir / "wt"
    decoy_dir.mkdir()
    monkeypatch.chdir(repo_dir)

    verploy(worktree="wt", repo_dir=repo_dir)

    _assert_committed(repo_dir, ARBITRARY_FILENAME, ARBITRARY_TEXT)


def test_errors_when_worktree_name_not_found(
    repo_dir: Path,
) -> None:
    with pytest.raises(RuntimeError, match="no-such-worktree"):
        verploy(worktree="no-such-worktree", repo_dir=repo_dir)


HOOK_ARGS = ["-c", "from verploy.verploy import hook; hook()"]


def _run_hook(cwd: Path) -> tuple[int, str]:
    result = run_program(
        PYTHON_PROGRAM, HOOK_ARGS, cwd=cwd, stdin="", env=dict(os.environ)
    )
    return result.returncode, result.stderr


def test_hook_passes_when_verification_passes(repo_dir: Path) -> None:
    _write_script(repo_dir / ".verploy" / "verify", "true")
    _commit_all(repo_dir, "set passing verify")

    run_hook(repo_dir)


def test_hook_errors_when_dirty(repo_dir: Path) -> None:
    (repo_dir / ARBITRARY_FILENAME).write_text(ARBITRARY_TEXT)

    with pytest.raises(RuntimeError) as exc:
        run_hook(repo_dir)
    assert str(exc.value) == (
        f"Repository at {repo_dir} has uncommitted changes."
        " This project uses Verploy for coding agent CI/CD."
        " Verploy requires all changes to be committed before it can run."
        " Commit all changes now, even partial or work-in-progress ones."
        " If there are unrelated unstaged changes, commit them separately and inform the user."
    )


def test_hook_errors_when_not_rebased(repo_dir: Path, worktree_dir: Path) -> None:
    (repo_dir / "main_change.py").write_text("x = 1\n")
    _commit_all(repo_dir, "main commit")
    (worktree_dir / ARBITRARY_FILENAME).write_text(ARBITRARY_TEXT)
    _commit_all(worktree_dir, "add feature")

    with pytest.raises(RuntimeError, match="not rebased onto main"):
        run_hook(worktree_dir)


def test_hook_errors_when_verify_fails(repo_dir: Path) -> None:
    _write_script(repo_dir / ".verploy" / "verify", "exit 1")
    _commit_all(repo_dir, "set failing verify")

    with pytest.raises(RuntimeError, match="Verification failed"):
        run_hook(repo_dir)


def test_hook_errors_when_verify_dirties_repo(repo_dir: Path) -> None:
    _write_script(repo_dir / ".verploy" / "verify", "echo dirty > untracked.txt")
    _commit_all(repo_dir, "set dirtying verify")

    with pytest.raises(RuntimeError) as exc:
        run_hook(repo_dir)
    assert str(exc.value) == (
        f"Repository at {repo_dir} has uncommitted changes."
        " This project uses Verploy for coding agent CI/CD."
        " Verploy requires all changes to be committed before it can run."
        " Commit all changes now, even partial or work-in-progress ones."
        " If there are unrelated unstaged changes, commit them separately and inform the user."
    )


def test_hook_passes_when_no_verify_script(repo_dir: Path) -> None:
    (repo_dir / ".verploy" / "verify").unlink()
    _commit_all(repo_dir, "remove verify script")

    run_hook(repo_dir)


def test_hook_e2e_exits_0_on_success(repo_dir: Path) -> None:
    returncode, _ = _run_hook(repo_dir)

    assert returncode == 0


def test_hook_e2e_exits_2_on_failure(repo_dir: Path) -> None:
    (repo_dir / ARBITRARY_FILENAME).write_text(ARBITRARY_TEXT)

    returncode, stderr = _run_hook(repo_dir)

    assert returncode == 2
    assert "uncommitted changes" in stderr


@PYTEST_MANUAL_MARKER
def test_manual_script_prompts_user(repo_dir: Path) -> None:
    _commit_manual_script(
        repo_dir,
        'read -p "Say no to this prompt (y/n): " answer\n[ "$answer" = "y" ]',
    )
    (repo_dir / ARBITRARY_FILENAME).write_text(ARBITRARY_TEXT)

    with pytest.raises(RuntimeError, match="Manual checks failed"):
        verploy(repo_dir=repo_dir)

    assert_yes("Were you prompted to say no to a prompt?")
