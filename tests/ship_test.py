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


def _git(cwd: Path, *args: str) -> str:
    return run_simple_program(GIT_PROGRAM, list(args), cwd=cwd)


@dataclass
class ShipFixture:
    repo_dir: Path
    worktree_dir: Path
    deploy_script: Path

    def run_ship(self) -> None:
        ship(worktree=self.worktree_dir, repo_dir=self.repo_dir)


def _write_script(path: Path, body: str) -> None:
    path.write_text(f"#!/bin/sh\n{body}\n")
    path.chmod(0o755)


@pytest.fixture
def ship_fixture(tmp_path: Path) -> ShipFixture:
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

    worktree_dir = tmp_path / "worktree"
    _git(repo_dir, "worktree", "add", "-b", "feature", str(worktree_dir))

    return ShipFixture(
        repo_dir=repo_dir, worktree_dir=worktree_dir, deploy_script=ship_dir / "deploy"
    )


def _create_rebase_conflict(repo_dir: Path, worktree_dir: Path) -> None:
    (repo_dir / "items.py").write_text('items = ["a", "b"]\n')
    _git(repo_dir, "add", "-A")
    _git(repo_dir, "commit", "-m", "add b on main")
    (worktree_dir / "items.py").write_text('items = ["a", "c"]\n')


def _stub_agent(side_effect: Callable[[str], None]) -> None:
    mock_for(fix_with_agent).side_effect = side_effect


def test_errors_if_test_script_missing(ship_fixture: ShipFixture) -> None:
    (ship_fixture.repo_dir / ".ship" / "test").unlink()
    (ship_fixture.worktree_dir / "feature.py").write_text('print("hello")\n')

    with pytest.raises(RuntimeError, match=r"\.ship/test"):
        ship_fixture.run_ship()


def test_errors_if_deploy_script_missing(ship_fixture: ShipFixture) -> None:
    (ship_fixture.repo_dir / ".ship" / "deploy").unlink()
    (ship_fixture.worktree_dir / "feature.py").write_text('print("hello")\n')

    with pytest.raises(RuntimeError, match=r"\.ship/deploy"):
        ship_fixture.run_ship()


def test_merges_worktree_changes_into_main(ship_fixture: ShipFixture) -> None:
    (ship_fixture.worktree_dir / "feature.py").write_text('print("hello")\n')

    ship_fixture.run_ship()

    assert (ship_fixture.repo_dir / "feature.py").read_text() == 'print("hello")\n'
    assert _git(ship_fixture.repo_dir, "status", "--porcelain") == ""
    assert _git(ship_fixture.repo_dir, "rev-parse", "HEAD") == _git(
        ship_fixture.worktree_dir, "rev-parse", "HEAD"
    )


def test_errors_if_repo_dir_is_dirty(ship_fixture: ShipFixture) -> None:
    (ship_fixture.repo_dir / "dirty.txt").write_text("uncommitted\n")
    (ship_fixture.worktree_dir / "feature.py").write_text('print("hello")\n')

    with pytest.raises(RuntimeError, match="Commit or stash changes first"):
        ship_fixture.run_ship()


def test_displays_progress_for_each_phase(ship_fixture: ShipFixture) -> None:
    (ship_fixture.worktree_dir / "feature.py").write_text('print("hello")\n')

    ship_fixture.run_ship()

    assert_displayed_in_order(
        "Committing worktree changes",
        f"Rebasing onto {MAIN}",
        "Running CI",
        f"Fast-forward merging feature into {MAIN}",
        "Pushing",
        "Deploying",
        "Shipped.",
    )


def test_ci_failure_unstages_changes_without_modifying_main(
    tmp_path: Path, ship_fixture: ShipFixture
) -> None:
    marker = tmp_path / "deployed.txt"
    _write_script(ship_fixture.repo_dir / ".ship" / "test", "exit 1")
    _write_script(ship_fixture.deploy_script, f"touch {marker}")
    _git(ship_fixture.repo_dir, "add", "-A")
    _git(ship_fixture.repo_dir, "commit", "-m", "set scripts")
    main_head = _git(ship_fixture.repo_dir, "rev-parse", "HEAD")
    (ship_fixture.worktree_dir / "feature.py").write_text('print("hello")\n')

    with pytest.raises(RuntimeError, match="CI failed"):
        ship_fixture.run_ship()

    assert _git(ship_fixture.repo_dir, "rev-parse", "HEAD") == main_head
    assert "feature.py" in _git(ship_fixture.worktree_dir, "status", "--porcelain")
    mock_for(git_push).assert_not_called()
    assert not marker.exists()


def test_rebase_conflict_resolved_pauses_for_review(
    ship_fixture: ShipFixture,
) -> None:
    _create_rebase_conflict(ship_fixture.repo_dir, ship_fixture.worktree_dir)
    main_head = _git(ship_fixture.repo_dir, "rev-parse", "HEAD")

    def _agent_keeps_both(_prompt: str) -> None:
        (ship_fixture.worktree_dir / "items.py").write_text(
            'items = ["a", "b", "c"]\n'
        )

    _stub_agent(_agent_keeps_both)

    with pytest.raises(RuntimeError, match="[Rr]eview"):
        ship_fixture.run_ship()

    assert _git(ship_fixture.repo_dir, "rev-parse", "HEAD") == main_head
    assert (ship_fixture.worktree_dir / "items.py").read_text() == (
        'items = ["a", "b", "c"]\n'
    )
    assert "items.py" in _git(ship_fixture.worktree_dir, "status", "--porcelain")


def test_irreconcilable_conflict_aborts_without_modifying_main(
    ship_fixture: ShipFixture,
) -> None:
    _create_rebase_conflict(ship_fixture.repo_dir, ship_fixture.worktree_dir)
    main_head = _git(ship_fixture.repo_dir, "rev-parse", "HEAD")

    def _agent_leaves_as_is(_prompt: str) -> None:
        return

    _stub_agent(_agent_leaves_as_is)

    with pytest.raises(RuntimeError, match="irreconcilable"):
        ship_fixture.run_ship()

    assert _git(ship_fixture.repo_dir, "rev-parse", "HEAD") == main_head
    assert (ship_fixture.repo_dir / "items.py").read_text() == ('items = ["a", "b"]\n')
    assert "items.py" in _git(ship_fixture.worktree_dir, "status", "--porcelain")


def test_pushes_after_merge(ship_fixture: ShipFixture) -> None:
    (ship_fixture.worktree_dir / "feature.py").write_text('print("hello")\n')

    ship_fixture.run_ship()

    mock_for(git_push).assert_called_once()


def test_runs_deploy_script(tmp_path: Path, ship_fixture: ShipFixture) -> None:
    marker = tmp_path / "deployed.txt"
    _write_script(ship_fixture.deploy_script, f"touch {marker}")
    _git(ship_fixture.repo_dir, "add", "-A")
    _git(ship_fixture.repo_dir, "commit", "-m", "set deploy script")
    (ship_fixture.worktree_dir / "feature.py").write_text('print("hello")\n')

    ship_fixture.run_ship()

    assert marker.exists()


def test_deploy_failure_raises_error(ship_fixture: ShipFixture) -> None:
    _write_script(ship_fixture.deploy_script, "exit 1")
    _git(ship_fixture.repo_dir, "add", "-A")
    _git(ship_fixture.repo_dir, "commit", "-m", "set deploy script")
    (ship_fixture.worktree_dir / "feature.py").write_text('print("hello")\n')

    with pytest.raises(RuntimeError, match="Deploy failed"):
        ship_fixture.run_ship()
