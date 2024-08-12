import json
import os
from unittest.mock import patch

import bittensor as bt
import pytest

from template.mock import MockDendrite, MockMetagraph, MockSubtensor

# @pytest.fixture(autouse=True)
# def mock_env_var(monkeypatch):
#     monkeypatch.setenv("DOJO_API_BASE_URL", "http://example.com")

#     with patch("subprocess.check_output") as mock_check_output:
#         mock_check_output.return_value = b"v1.0.0\n"
#         yield monkeypatch

#     # Test that the monkey patch for get_latest_git_tag works
#     from template import __version__

#     assert __version__ == "1.0.0"


@pytest.fixture
def mock_evalplus_leaderboard_results():
    fixture_path = os.path.join(
        os.path.dirname(__file__), "..", "fixtures", "evalplus_leaderboard_results.json"
    )
    with open(fixture_path) as f:
        mock_data = json.load(f)

    expected_keys = [
        "claude-2 (Mar 2024)",
        "claude-3-haiku (Mar 2024)",
        "claude-3-opus (Mar 2024)",
        "claude-3-sonnet (Mar 2024)",
    ]
    assert all(
        key in mock_data for key in expected_keys
    ), f"Missing one or more expected keys in the fixture data. Expected keys: {expected_keys}"

    return mock_data


@pytest.fixture
def mock_initialise() -> (
    tuple[patch, bt.MockWallet, MockSubtensor, MockMetagraph, MockDendrite]
):
    """Fixture to initialise mock components for testing."""
    netuid = 1

    bt.MockSubtensor.reset()
    mock_wallet = bt.MockWallet()
    mock_subtensor = MockSubtensor(netuid=netuid, wallet=mock_wallet)
    mock_metagraph = MockMetagraph(netuid=netuid, subtensor=mock_subtensor)
    mock_dendrite = MockDendrite(wallet=mock_wallet)

    with patch("commons.utils.initialise") as mock_initialise:
        mock_initialise.return_value = (
            mock_wallet,
            mock_subtensor,
            mock_metagraph,
            mock_dendrite,
        )
        yield (
            mock_initialise,
            mock_wallet,
            mock_subtensor,
            mock_metagraph,
            mock_dendrite,
        )
