"""Long soak over many seeds of the harsh link profile (opt-in, spec section 13).

Every scenario that runs over harsh links with a fixed seed in the normal test run is repeated here with
``ROPE_SOAK_SEEDS`` different seeds (for example ``ROPE_SOAK_SEEDS=50 python -m pytest tests/test_soak.py``). Without
the variable the tests are skipped. Pass criterion as everywhere: bit-for-bit identical streams, every message and
every report exactly once."""

import os

import pytest

import test_delivery
import test_media
import test_messages
import test_relay
import test_repair

SEEDS = int(os.environ.get("ROPE_SOAK_SEEDS") or 0)
SCENARIOS = {
    "relay": test_relay.test_relay_over_harsh_links_and_hub_restart,
    "messages": test_messages.test_many_messages_over_harsh_links_exactly_once,
    "delivery": test_delivery.test_reports_over_harsh_links_exactly_once,
    "media": test_media.test_harsh_links_and_sticks_at_the_same_time,
    "repair": test_repair.test_repair_over_a_harsh_link,
}


@pytest.mark.skipif(not SEEDS, reason="opt-in: set ROPE_SOAK_SEEDS")
@pytest.mark.parametrize("seed", range(100, 100 + SEEDS))
@pytest.mark.parametrize("scenario", sorted(SCENARIOS))
def test_soak(tmp_path, scenario, seed):
    SCENARIOS[scenario](tmp_path, seed=seed)
