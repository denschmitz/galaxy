import os

import pytest


@pytest.mark.skipif(os.environ.get("GALAXY_RUN_LIVE_TESTS") != "1", reason="live archive test is opt-in")
def test_public_integration_placeholder() -> None:
    assert True
