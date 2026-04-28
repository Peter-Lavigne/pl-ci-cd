from dataclasses import dataclass
from pathlib import Path

import pytest
from pl_mocks_and_fakes import mock_for
from pl_run_program import run_simple_program
from pl_tiny_clients.git_push import git_push
from pl_user_io.testing.user_io_fake import assert_displayed_in_order

from pl_ci_cd._constants import GIT_PROGRAM
from pl_ci_cd.ship import ship

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


def test_ci_failure_prevents_push_and_deploy(tmp_path: Path, ship_fixture: ShipFixture) -> None:
    marker = tmp_path / "deployed.txt"
    _write_script(ship_fixture.repo_dir / ".ship" / "test", "exit 1")
    _write_script(ship_fixture.deploy_script, f"touch {marker}")
    _git(ship_fixture.repo_dir, "add", "-A")
    _git(ship_fixture.repo_dir, "commit", "-m", "set scripts")
    (ship_fixture.worktree_dir / "feature.py").write_text('print("hello")\n')

    with pytest.raises(RuntimeError, match="CI failed"):
        ship_fixture.run_ship()

    mock_for(git_push).assert_not_called()
    assert not marker.exists()


def test_displays_progress(ship_fixture: ShipFixture) -> None:
    (ship_fixture.worktree_dir / "feature.py").write_text('print("hello")\n')

    ship_fixture.run_ship()

    assert_displayed_in_order(
        "Pushing",
        "Deploying",
        "Shipped.",
    )
