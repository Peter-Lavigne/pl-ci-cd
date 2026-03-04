from pl_mocks_and_fakes import THIRD_PARTY_API_MOCK_REASONS, MockInUnitTests
from pl_run_program.run_program import run_program

from ._constants import UV_PROGRAM


@MockInUnitTests(*THIRD_PARTY_API_MOCK_REASONS)
def publish_to_pypi() -> None:
    run_program(UV_PROGRAM, ["publish"])
