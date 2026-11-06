"""Announced operation (spec 14.5): a hub may name its operation when it rejects a participant of another operation,
so that the application can offer to join it. Off by default; never switches the participant on its own."""

import asyncio

import pytest

from rope_protocol import frames as F
from rope_protocol.frames import Frame, FrameType
from rope_protocol.hub import Hub

from test_transfer import Bench, _file, _until


def _rejected(tmp_path, operation, participant="source-1", **hub_kw):
    path = _file(tmp_path, "x.dat", b"x")
    out = {}

    async def run():
        async with Bench(str(tmp_path), operation=operation, **hub_kw) as b:
            src = b.source({"x": path}, participant=participant).start()
            await _until(lambda: src.rejected is not None, 5)
            out["rejected"] = src.rejected
            out["connected"] = src.connected.is_set()
            await src.stop()
    asyncio.run(run())
    return out["rejected"], out["connected"]


def test_not_announced_by_default(tmp_path):
    r, connected = _rejected(tmp_path, "op-2")
    assert r.code == "wrong_operation" and r.operation is None and r.operation_name is None
    assert not connected


def test_announced_with_name(tmp_path):
    r, connected = _rejected(tmp_path, "op-2", announce_operation=True, operation_name="Lake exercise")
    assert r.code == "wrong_operation" and r.operation == "op-1" and r.operation_name == "Lake exercise"
    assert not connected                               # learning the operation is no way in


def test_announced_without_name(tmp_path):
    r, _ = _rejected(tmp_path, "op-2", announce_operation=True)
    assert r.operation == "op-1" and r.operation_name is None


def test_only_for_wrong_operation(tmp_path):
    r, _ = _rejected(tmp_path, "op-1", participant="source-9", announce_operation=True, operation_name="Lake exercise")
    assert r.code == "unknown_participant" and r.operation is None and r.operation_name is None


def test_join_after_the_user_agreed(tmp_path):
    """The application takes the announced operation (after asking its user) and greets again: welcome."""
    path = _file(tmp_path, "x.dat", b"x" * 1000)

    async def run():
        async with Bench(str(tmp_path), operation="op-2", announce_operation=True) as b:
            src = b.source({"x": path}).start()
            await _until(lambda: src.rejected is not None, 5)
            announced = src.rejected.operation
            await src.stop()
            b.operation = announced
            again = b.source({"x": path}).start()
            await _until(again.connected.is_set, 5)
            assert again.rejected is None
            await again.stop()
    asyncio.run(run())


@pytest.mark.parametrize("meta", [
    {"code": "wrong_operation", "text": "t"},                                         # older hubs: no fields
    {"code": "wrong_operation", "text": "t", "operation": "op-1"},
    {"code": "wrong_operation", "text": "t", "operation": "op-1", "operation_name": "Lake exercise"},
])
def test_valid_reject_frames(meta):
    f = Frame(FrameType.REJECT, meta)
    assert F.validate(F.decode(F.encode(f))) == FrameType.REJECT


@pytest.mark.parametrize("extra", [
    {"operation": "bad operation"},
    {"operation": 7},
    {"operation_name": ""},
    {"operation_name": "x" * (F.MAX_OPERATION_NAME + 1)},
    {"operation_name": 7},
])
def test_bad_announced_fields(extra):
    f = Frame(FrameType.REJECT, dict({"code": "wrong_operation", "text": "t"}, **extra))
    with pytest.raises(F.FrameError):
        F.validate(f)


def test_operation_name_is_checked(tmp_path):
    with pytest.raises(ValueError):
        Hub(str(tmp_path), {"source-1": "source"}, "op-1", operation_name="")
