from pathlib import Path
from types import NoneType

from pl_mocks_and_fakes import MockInUnitTests, MockReason


@MockInUnitTests(MockReason.UNINVESTIGATED)
def make_file_executble(file_name: str) -> NoneType:
    path = Path(file_name)
    current_permissions = path.stat().st_mode
    path.chmod(current_permissions | 0o100)
    return None
