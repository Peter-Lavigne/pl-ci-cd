import contextlib
from pathlib import Path

import pytest
from pl_mocks_and_fakes import mock_for, stub
from pl_tiny_clients.git_add_all import git_add_all
from pl_tiny_clients.git_any_uncommitted_changes import git_any_uncommitted_changes
from pl_tiny_clients.git_commit import git_commit
from pl_tiny_clients.git_push import git_push
from pl_user_io.testing import (
    assert_displayed,
    assert_loading_spinner_displayed,
    stub_str_input,
)

from pl_ci_cd.commit import commit
from pl_ci_cd.testing import set_up_check


def stub_commit(lint_path: Path) -> None:
    _set_up(lint_path)


def assert_commit_called() -> None:
    mock_for(git_commit).assert_called_once()


def _set_up(
    tmp_path: Path,
    has_uncommitted: bool = True,
    manually_entered_message: str = "fixed bug",
) -> None:
    stub(git_any_uncommitted_changes)(has_uncommitted)
    stub_str_input(manually_entered_message, "Enter your commit message:")

    set_up_check(tmp_path)


def test_uses_current_working_directory_if_directory_not_passed(tmp_path: Path) -> None:
    _set_up(tmp_path)
    (tmp_path / "test.py").write_text("x=1+2\n")

    with contextlib.chdir(tmp_path):
        commit()

    assert (tmp_path / "test.py").read_text() == "x = 1 + 2\n"


def test_exits_if_no_changes_to_commit(tmp_path: Path) -> None:
    _set_up(tmp_path, has_uncommitted=False)

    commit(tmp_path)

    assert_displayed("No changes to commit, exiting.")
    # Should not add, commit, or push
    mock_for(git_add_all).assert_not_called()
    mock_for(git_commit).assert_not_called()
    mock_for(git_push).assert_not_called()


def test_runs_checks_at_repo_root_directory_before_commit__pass(
    tmp_path: Path,
) -> None:
    _set_up(tmp_path)
    (tmp_path / "test.py").write_text("print(1 + 2)\n")

    commit(tmp_path)

    assert_loading_spinner_displayed("Linter")


def test_runs_checks_at_repo_root_directory_before_commit__fail(
    tmp_path: Path,
) -> None:
    _set_up(tmp_path)
    (tmp_path / "test.py").write_text("x = undefined_var\n")  # unfixable

    with pytest.raises(
        RuntimeError,
        match=r"(?s)Linting failed, aborting commit. Output:.*undefined_var.*",
    ):
        commit(tmp_path)

    # Should not add, commit, or push
    mock_for(git_add_all).assert_not_called()
    mock_for(git_commit).assert_not_called()
    mock_for(git_push).assert_not_called()


def test_automatically_fixes_fixable_checks(tmp_path: Path) -> None:
    _set_up(tmp_path)
    (tmp_path / "test.py").write_text("x=1+2\n")

    commit(tmp_path)

    assert_loading_spinner_displayed("Formatter")
    assert (tmp_path / "test.py").read_text() == "x = 1 + 2\n"


def test_adds_all_changes_before_commit(tmp_path: Path) -> None:
    _set_up(tmp_path)

    commit(tmp_path)

    mock_for(git_add_all).assert_called_once()


def test_pushes_changes_after_commit(tmp_path: Path) -> None:
    _set_up(tmp_path)

    commit(tmp_path)

    mock_for(git_push).assert_called_once()


def test_prints_pushing_changes_message_with_checkmark(tmp_path: Path) -> None:
    _set_up(tmp_path)

    commit(tmp_path)

    assert_loading_spinner_displayed("Pushing changes")


def test_commits_to_git(tmp_path: Path) -> None:
    _set_up(tmp_path)

    commit(tmp_path)

    mock_for(git_commit).assert_called_once()


def test_uses_generic_commit_message(tmp_path: Path) -> None:
    _set_up(tmp_path)

    commit(tmp_path)

    mock_for(git_commit).assert_called_once_with(message="Commit")
