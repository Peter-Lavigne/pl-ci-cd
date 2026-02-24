import pytest
from pl_mocks_and_fakes import create_fakes, initialize_mocks
from pl_user_io.testing import UserIOFake

from tests.constants import PYTEST_INTEGRATION_TEST_MARKERS


def pytest_runtest_setup(item: pytest.Item) -> None:
    def _is_integration_test() -> bool:
        return any(
            marker.name in [m.name for m in PYTEST_INTEGRATION_TEST_MARKERS]
            for marker in item.iter_markers()
        )

    def _mock_code_for_unit_tests() -> None:
        if not _is_integration_test():
            initialize_mocks()
            create_fakes(UserIOFake)

    _mock_code_for_unit_tests()
