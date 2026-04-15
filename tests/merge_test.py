import importlib.metadata
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

import pytest
import ruff  # pyright: ignore[reportMissingTypeStubs]
from pl_mocks_and_fakes import mock_for
from pl_run_program import run_simple_program
from pl_tiny_clients.initialize_uv_project import initialize_uv_project
from pl_user_io.testing.user_io_fake import assert_displayed_in_order

from pl_ci_cd._constants import GIT_PROGRAM, UV_PROGRAM
from pl_ci_cd.merge import fix_with_agent, merge

MAIN = "main"


def _git(cwd: Path, *args: str) -> str:
    return run_simple_program(GIT_PROGRAM, list(args), cwd=cwd)


@dataclass
class MergeFixture:
    repo_dir: Path
    worktree_dir: Path
    ci_script: Path

    def run_merge(self) -> None:
        merge(
            worktree=self.worktree_dir,
            repo_dir=self.repo_dir,
            main_branch=MAIN,
            ci_script=self.ci_script,
        )


@pytest.fixture
def merge_fixture(tmp_path: Path) -> MergeFixture:
    repo_dir = tmp_path / "repo"
    repo_dir.mkdir()

    initialize_uv_project(repo_dir)
    ruff_version = importlib.metadata.version(ruff.__name__)
    run_simple_program(
        UV_PROGRAM,
        ["add", "--offline", f"ruff=={ruff_version}"],
        cwd=repo_dir,
    )

    (repo_dir / "items.py").write_text('items = ["a"]\n')

    _git(repo_dir, "init", "-b", MAIN)
    _git(repo_dir, "config", "user.email", "test@example.com")
    _git(repo_dir, "config", "user.name", "Test")
    _git(repo_dir, "add", "-A")
    _git(repo_dir, "commit", "-m", "initial")

    worktree_dir = tmp_path / "worktree"
    _git(repo_dir, "worktree", "add", "-b", "feature", str(worktree_dir))

    ci_script = tmp_path / "ci.sh"
    ci_script.write_text("#!/bin/sh\nexec ruff format --check .\n")
    ci_script.chmod(0o755)

    return MergeFixture(
        repo_dir=repo_dir, worktree_dir=worktree_dir, ci_script=ci_script
    )


def _create_rebase_conflict(repo_dir: Path, worktree_dir: Path) -> None:
    (repo_dir / "items.py").write_text('items = ["a", "b"]\n')
    _git(repo_dir, "add", "-A")
    _git(repo_dir, "commit", "-m", "add b on main")
    (worktree_dir / "items.py").write_text('items = ["a", "c"]\n')


def _stub_agent(side_effect: Callable[[str], None]) -> None:
    mock_for(fix_with_agent).side_effect = side_effect


def test_merges_worktree_changes_into_main(merge_fixture: MergeFixture) -> None:
    (merge_fixture.worktree_dir / "feature.py").write_text('print("hello")\n')

    merge_fixture.run_merge()

    assert (merge_fixture.repo_dir / "feature.py").read_text() == 'print("hello")\n'
    assert _git(merge_fixture.repo_dir, "status", "--porcelain") == ""
    assert _git(merge_fixture.repo_dir, "rev-parse", "HEAD") == _git(
        merge_fixture.worktree_dir, "rev-parse", "HEAD"
    )


def test_displays_progress_for_each_phase(merge_fixture: MergeFixture) -> None:
    (merge_fixture.worktree_dir / "feature.py").write_text('print("hello")\n')

    merge_fixture.run_merge()

    assert_displayed_in_order(
        "Committing worktree changes",
        f"Rebasing onto {MAIN}",
        "Running CI",
        f"Fast-forward merging feature into {MAIN}",
        "Done.",
    )


def test_ci_failure_unstages_changes_without_modifying_main(
    merge_fixture: MergeFixture,
) -> None:
    main_head = _git(merge_fixture.repo_dir, "rev-parse", "HEAD")
    (merge_fixture.worktree_dir / "feature.py").write_text("x=1+2\n")

    with pytest.raises(RuntimeError, match="CI failed"):
        merge_fixture.run_merge()

    assert _git(merge_fixture.repo_dir, "rev-parse", "HEAD") == main_head
    assert "feature.py" in _git(merge_fixture.worktree_dir, "status", "--porcelain")


def test_rebase_conflict_resolved_by_agent_completes_merge(
    merge_fixture: MergeFixture,
) -> None:
    _create_rebase_conflict(merge_fixture.repo_dir, merge_fixture.worktree_dir)

    def _agent_keeps_both(_prompt: str) -> None:
        (merge_fixture.worktree_dir / "items.py").write_text(
            'items = ["a", "b", "c"]\n'
        )

    _stub_agent(_agent_keeps_both)

    merge_fixture.run_merge()

    assert (merge_fixture.repo_dir / "items.py").read_text() == (
        'items = ["a", "b", "c"]\n'
    )
    assert _git(merge_fixture.repo_dir, "rev-parse", "HEAD") == _git(
        merge_fixture.worktree_dir, "rev-parse", "HEAD"
    )


def test_irreconcilable_conflict_aborts_without_modifying_main(
    merge_fixture: MergeFixture,
) -> None:
    _create_rebase_conflict(merge_fixture.repo_dir, merge_fixture.worktree_dir)
    main_head = _git(merge_fixture.repo_dir, "rev-parse", "HEAD")

    def _agent_leaves_as_is(_prompt: str) -> None:
        return

    _stub_agent(_agent_leaves_as_is)

    with pytest.raises(RuntimeError, match="irreconcilable"):
        merge_fixture.run_merge()

    assert _git(merge_fixture.repo_dir, "rev-parse", "HEAD") == main_head
    assert (merge_fixture.repo_dir / "items.py").read_text() == ('items = ["a", "b"]\n')
    assert "items.py" in _git(merge_fixture.worktree_dir, "status", "--porcelain")
