from pathlib import Path

import pytest
from pl_tiny_clients.execute_shell_command import CommandError, execute_shell_command

from pl_ci_cd.make_file_executble import make_file_executble

from .constants import PYTEST_INTEGRATION_MARKER

pytestmark = PYTEST_INTEGRATION_MARKER


def test_make_file_executble(tmp_path: Path) -> None:
    file_name = tmp_path / "test_make_file_executble.sh"
    file_name.write_text("#!/bin/bash\necho 'Hello, World!'")

    with pytest.raises(CommandError, match="Permission denied"):
        execute_shell_command(f"/.{file_name}")

    make_file_executble(str(file_name))

    execute_shell_command(f"/.{file_name}")
