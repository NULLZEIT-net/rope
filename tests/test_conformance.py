"""The conformance suite (conformance/, #32) passes against the Python reference adapter - so the suite itself keeps
working while the reference changes."""

import asyncio
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "conformance"))

import harness  # noqa: E402


def test_reference_passes_every_scenario():
    results = asyncio.run(harness.run(harness.DEFAULT_ADAPTER, out=lambda *a: None))
    assert len(results) == len(harness.SCENARIOS)
    assert [r for r in results if r[1] != "PASS"] == []
