from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

import pytest
from pl_mocks_and_fakes import mock_for
from pl_run_program import run_simple_program
from pl_tiny_clients.git_push import git_push
from pl_user_io.testing.user_io_fake import assert_displayed_in_order

from pl_ci_cd._constants import GIT_PROGRAM
from pl_ci_cd.ship import fix_with_agent, ship

MAIN = "main"
TOUCH = "/usr/bin/touch"


def _git(cwd: Path, *args: str) -> str:
    return run_simple_program(GIT_PROGRAM, list(args), cwd=cwd)


@dataclass
class WorktreeFixture:
    repo_dir: Path
    worktree_dir: Path
    deploy_script: Path

    def run_ship(self) -> None:
        ship(worktree=self.worktree_dir, repo_dir=self.repo_dir)


@dataclass
class MainFixture:
    repo_dir: Path
    deploy_script: Path

    def run_ship(self) -> None:
        ship(repo_dir=self.repo_dir)


def _write_script(path: Path, body: str) -> None:
    path.write_text(f"#!/bin/sh\n{body}\n")
    path.chmod(0o755)


@dataclass
class RepoFixture:
    repo_dir: Path
    deploy_script: Path


def _create_repo(tmp_path: Path) -> RepoFixture:
    repo_dir = tmp_path / "repo"
    repo_dir.mkdir()

    (repo_dir / "items.py").write_text('items = ["a"]\n')

    ship_dir = repo_dir / ".ship"
    ship_dir.mkdir()
    _write_script(ship_dir / "test", "")
    _write_script(ship_dir / "deploy", "")

    _git(repo_dir, "init", "-b", MAIN)
    _git(repo_dir, "config", "user.email", "test@example.com")
    _git(repo_dir, "config", "user.name", "Test")
    _git(repo_dir, "add", "-A")
    _git(repo_dir, "commit", "-m", "initial")

    return RepoFixture(repo_dir=repo_dir, deploy_script=ship_dir / "deploy")


@pytest.fixture
def worktree_fixture(tmp_path: Path) -> WorktreeFixture:
    repo = _create_repo(tmp_path)

    worktree_dir = tmp_path / "worktree"
    _git(repo.repo_dir, "worktree", "add", "-b", "feature", str(worktree_dir))

    return WorktreeFixture(
        repo_dir=repo.repo_dir,
        worktree_dir=worktree_dir,
        deploy_script=repo.deploy_script,
    )


@pytest.fixture
def main_fixture(tmp_path: Path) -> MainFixture:
    repo = _create_repo(tmp_path)
    return MainFixture(repo_dir=repo.repo_dir, deploy_script=repo.deploy_script)


def _create_rebase_conflict(repo_dir: Path, worktree_dir: Path) -> None:
    (repo_dir / "items.py").write_text('items = ["a", "b"]\n')
    _git(repo_dir, "add", "-A")
    _git(repo_dir, "commit", "-m", "add b on main")
    (worktree_dir / "items.py").write_text('items = ["a", "c"]\n')


def _stub_agent(side_effect: Callable[[str], None]) -> None:
    mock_for(fix_with_agent).side_effect = side_effect


def test_errors_if_test_script_missing(worktree_fixture: WorktreeFixture) -> None:
    (worktree_fixture.repo_dir / ".ship" / "test").unlink()
    (worktree_fixture.worktree_dir / "feature.py").write_text('print("hello")\n')

    with pytest.raises(RuntimeError, match=r"\.ship/test"):
        worktree_fixture.run_ship()


def test_errors_if_deploy_script_missing(worktree_fixture: WorktreeFixture) -> None:
    (worktree_fixture.repo_dir / ".ship" / "deploy").unlink()
    (worktree_fixture.worktree_dir / "feature.py").write_text('print("hello")\n')

    with pytest.raises(RuntimeError, match=r"\.ship/deploy"):
        worktree_fixture.run_ship()


def test_worktree_merges_changes_into_main(worktree_fixture: WorktreeFixture) -> None:
    (worktree_fixture.worktree_dir / "feature.py").write_text('print("hello")\n')

    worktree_fixture.run_ship()

    assert (worktree_fixture.repo_dir / "feature.py").read_text() == 'print("hello")\n'
    assert _git(worktree_fixture.repo_dir, "status", "--porcelain") == ""
    assert _git(worktree_fixture.repo_dir, "rev-parse", "HEAD") == _git(
        worktree_fixture.worktree_dir, "rev-parse", "HEAD"
    )


def test_worktree_errors_if_repo_dir_is_dirty(
    worktree_fixture: WorktreeFixture,
) -> None:
    (worktree_fixture.repo_dir / "dirty.txt").write_text("uncommitted\n")
    (worktree_fixture.worktree_dir / "feature.py").write_text('print("hello")\n')

    with pytest.raises(RuntimeError, match="Commit or stash changes first"):
        worktree_fixture.run_ship()


def test_worktree_displays_progress_for_each_phase(
    worktree_fixture: WorktreeFixture,
) -> None:
    (worktree_fixture.worktree_dir / "feature.py").write_text('print("hello")\n')

    worktree_fixture.run_ship()

    assert_displayed_in_order(
        "Committing worktree changes",
        f"Rebasing onto {MAIN}",
        "Running CI",
        f"Fast-forward merging feature into {MAIN}",
        "Pushing",
        "Deploying",
        "Shipped.",
    )


def test_worktree_ci_failure_unstages_changes_without_modifying_main(
    tmp_path: Path, worktree_fixture: WorktreeFixture
) -> None:
    marker = tmp_path / "deployed.txt"
    _write_script(worktree_fixture.repo_dir / ".ship" / "test", "exit 1")
    _write_script(worktree_fixture.deploy_script, f"{TOUCH} {marker}")
    _git(worktree_fixture.repo_dir, "add", "-A")
    _git(worktree_fixture.repo_dir, "commit", "-m", "set scripts")
    main_head = _git(worktree_fixture.repo_dir, "rev-parse", "HEAD")
    (worktree_fixture.worktree_dir / "feature.py").write_text('print("hello")\n')

    with pytest.raises(RuntimeError, match="CI failed"):
        worktree_fixture.run_ship()

    assert _git(worktree_fixture.repo_dir, "rev-parse", "HEAD") == main_head
    assert "feature.py" in _git(worktree_fixture.worktree_dir, "status", "--porcelain")
    mock_for(git_push).assert_not_called()
    assert not marker.exists()


def test_worktree_rebase_conflict_resolved_pauses_for_review(
    worktree_fixture: WorktreeFixture,
) -> None:
    _create_rebase_conflict(worktree_fixture.repo_dir, worktree_fixture.worktree_dir)
    main_head = _git(worktree_fixture.repo_dir, "rev-parse", "HEAD")

    def _agent_keeps_both(_prompt: str) -> None:
        (worktree_fixture.worktree_dir / "items.py").write_text(
            'items = ["a", "b", "c"]\n'
        )

    _stub_agent(_agent_keeps_both)

    with pytest.raises(RuntimeError, match="[Rr]eview"):
        worktree_fixture.run_ship()

    assert _git(worktree_fixture.repo_dir, "rev-parse", "HEAD") == main_head
    assert (worktree_fixture.worktree_dir / "items.py").read_text() == (
        'items = ["a", "b", "c"]\n'
    )
    assert "items.py" in _git(worktree_fixture.worktree_dir, "status", "--porcelain")


def test_worktree_irreconcilable_conflict_aborts_without_modifying_main(
    worktree_fixture: WorktreeFixture,
) -> None:
    _create_rebase_conflict(worktree_fixture.repo_dir, worktree_fixture.worktree_dir)
    main_head = _git(worktree_fixture.repo_dir, "rev-parse", "HEAD")

    def _agent_leaves_as_is(_prompt: str) -> None:
        return

    _stub_agent(_agent_leaves_as_is)

    with pytest.raises(RuntimeError, match="irreconcilable"):
        worktree_fixture.run_ship()

    assert _git(worktree_fixture.repo_dir, "rev-parse", "HEAD") == main_head
    assert (worktree_fixture.repo_dir / "items.py").read_text() == (
        'items = ["a", "b"]\n'
    )
    assert "items.py" in _git(worktree_fixture.worktree_dir, "status", "--porcelain")


def test_pushes_after_ship(worktree_fixture: WorktreeFixture) -> None:
    (worktree_fixture.worktree_dir / "feature.py").write_text('print("hello")\n')

    worktree_fixture.run_ship()

    mock_for(git_push).assert_called_once()


def test_runs_deploy_script(tmp_path: Path, worktree_fixture: WorktreeFixture) -> None:
    marker = tmp_path / "deployed.txt"
    _write_script(worktree_fixture.deploy_script, f"{TOUCH} {marker}")
    _git(worktree_fixture.repo_dir, "add", "-A")
    _git(worktree_fixture.repo_dir, "commit", "-m", "set deploy script")
    (worktree_fixture.worktree_dir / "feature.py").write_text('print("hello")\n')

    worktree_fixture.run_ship()

    assert marker.exists()


def test_deploy_failure_raises_error(worktree_fixture: WorktreeFixture) -> None:
    _write_script(worktree_fixture.deploy_script, "exit 1")
    _git(worktree_fixture.repo_dir, "add", "-A")
    _git(worktree_fixture.repo_dir, "commit", "-m", "set deploy script")
    (worktree_fixture.worktree_dir / "feature.py").write_text('print("hello")\n')

    with pytest.raises(RuntimeError, match="Deploy failed"):
        worktree_fixture.run_ship()


def test_ships_uncommitted_changes_on_main(main_fixture: MainFixture) -> None:
    (main_fixture.repo_dir / "feature.py").write_text('print("hello")\n')

    main_fixture.run_ship()

    assert (main_fixture.repo_dir / "feature.py").read_text() == 'print("hello")\n'
    assert _git(main_fixture.repo_dir, "status", "--porcelain") == ""
    mock_for(git_push).assert_called_once()


def test_errors_if_main_has_no_changes(main_fixture: MainFixture) -> None:
    with pytest.raises(RuntimeError, match="no changes to ship"):
        main_fixture.run_ship()


def test_ci_failure_undoes_commit_on_main(
    tmp_path: Path, main_fixture: MainFixture
) -> None:
    marker = tmp_path / "deployed.txt"
    _write_script(main_fixture.repo_dir / ".ship" / "test", "exit 1")
    _write_script(main_fixture.deploy_script, f"{TOUCH} {marker}")
    _git(main_fixture.repo_dir, "add", "-A")
    _git(main_fixture.repo_dir, "commit", "-m", "set scripts")
    main_head = _git(main_fixture.repo_dir, "rev-parse", "HEAD")
    (main_fixture.repo_dir / "feature.py").write_text('print("hello")\n')

    with pytest.raises(RuntimeError, match="CI failed"):
        main_fixture.run_ship()

    assert _git(main_fixture.repo_dir, "rev-parse", "HEAD") == main_head
    assert "feature.py" in _git(main_fixture.repo_dir, "status", "--porcelain")
    mock_for(git_push).assert_not_called()
    assert not marker.exists()


def test_ci_auto_fixes_are_included_in_commit_on_main(
    main_fixture: MainFixture,
) -> None:
    _write_script(main_fixture.repo_dir / ".ship" / "test", "ruff format .")
    _git(main_fixture.repo_dir, "add", "-A")
    _git(main_fixture.repo_dir, "commit", "-m", "set test script")
    head_before = _git(main_fixture.repo_dir, "rev-parse", "HEAD").strip()
    (main_fixture.repo_dir / "messy.py").write_text("x=1+2\n")

    main_fixture.run_ship()

    assert (main_fixture.repo_dir / "messy.py").read_text() == "x = 1 + 2\n"
    assert _git(main_fixture.repo_dir, "status", "--porcelain") == ""
    commit_count = int(
        _git(
            main_fixture.repo_dir, "rev-list", "--count", f"{head_before}..HEAD"
        ).strip()
    )
    assert commit_count == 1


def test_ci_auto_fixes_are_included_in_commit_on_worktree(
    worktree_fixture: WorktreeFixture,
) -> None:
    _write_script(worktree_fixture.repo_dir / ".ship" / "test", "ruff format .")
    _git(worktree_fixture.repo_dir, "add", "-A")
    _git(worktree_fixture.repo_dir, "commit", "-m", "set test script")
    head_before = _git(worktree_fixture.repo_dir, "rev-parse", "HEAD").strip()
    (worktree_fixture.worktree_dir / "messy.py").write_text("x=1+2\n")

    worktree_fixture.run_ship()

    assert (worktree_fixture.repo_dir / "messy.py").read_text() == "x = 1 + 2\n"
    assert _git(worktree_fixture.repo_dir, "status", "--porcelain") == ""
    commit_count = int(
        _git(
            worktree_fixture.repo_dir, "rev-list", "--count", f"{head_before}..HEAD"
        ).strip()
    )
    assert commit_count == 1


def test_displays_progress_without_rebase_or_merge(
    main_fixture: MainFixture,
) -> None:
    (main_fixture.repo_dir / "feature.py").write_text('print("hello")\n')

    main_fixture.run_ship()

    assert_displayed_in_order(
        "Running CI",
        "Committing changes",
        "Pushing",
        "Deploying",
        "Shipped.",
    )
