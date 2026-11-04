"""Messages addressed to the hub itself (spec 8.5): the hub's application takes them one after the other, also from many
participants; one it could not take (on_message raised, or the hub stopped first) is told again later and after a
restart; a message from an offline medium is told once, not twice."""

import asyncio
import os
import threading

from rope_protocol.hub import Hub
from rope_protocol.source import Source
from test_transfer import FAST, SRC, _until

SOURCES = {"source-%d" % i: "source" for i in range(1, 4)}


def _src(tmp, name, port):
    return Source(name, "op-1", "127.0.0.1", {}, os.path.join(tmp, "src-" + name), hub_port=port, **SRC)


def test_many_participants_are_told_one_after_the_other(tmp_path):
    tmp, told, busy, overlap = str(tmp_path), [], threading.Lock(), []

    def on_message(meta, body):
        if not busy.acquire(blocking=False):
            overlap.append(meta["id"])                  # two at the same time: must never happen
            return
        try:
            told.append((meta["from"], body))
        finally:
            busy.release()

    async def run():
        hub = await Hub(os.path.join(tmp, "hub"), SOURCES, "op-1", port=0, on_message=on_message, **FAST).start()
        srcs = [_src(tmp, n, hub.port).start() for n in SOURCES]
        try:
            for i in range(20):
                for s in srcs:
                    s.send_message([hub.hub_id], "reply", b"%s %d" % (s.participant.encode(), i))
            await _until(lambda: len(told) == 60)
            await asyncio.sleep(0.3)
            assert len(told) == 60 and not overlap
            for s in srcs:                              # per participant in the order sent
                mine = [b for who, b in told if who == s.participant]
                assert mine == [b"%s %d" % (s.participant.encode(), i) for i in range(20)]
        finally:
            for s in srcs:
                await s.stop()
            await hub.stop()
    asyncio.run(run())


def test_message_the_application_could_not_take_is_told_again(tmp_path):
    tmp, told, fail = str(tmp_path), [], [2]

    def on_message(meta, body):
        if fail[0]:
            fail[0] -= 1
            raise OSError("file held by a virus scanner")
        told.append(body)

    async def run():
        hub = await Hub(os.path.join(tmp, "hub"), SOURCES, "op-1", port=0, on_message=on_message, retell_s=0.1,
                        **FAST).start()
        src = _src(tmp, "source-1", hub.port).start()
        try:
            src.send_message([hub.hub_id], "reply", b"reached")
            await _until(lambda: told)
            await asyncio.sleep(0.4)
            assert told == [b"reached"] and hub.untold() == 0          # once, after two failures
        finally:
            await src.stop()
            await hub.stop()
    asyncio.run(run())


def test_untold_message_is_told_after_a_restart(tmp_path):
    tmp, told = str(tmp_path), []

    def broken(meta, body):
        raise RuntimeError("application not ready")

    async def run():
        root = os.path.join(tmp, "hub")
        hub = await Hub(root, SOURCES, "op-1", port=0, on_message=broken, retell_s=60, **FAST).start()
        src = _src(tmp, "source-1", hub.port).start()
        src.send_message([hub.hub_id], "x", b"1")
        await _until(lambda: src.outbox()[0]["at_hub"])
        await src.stop()
        assert hub.untold() == 1
        await hub.stop()
        again = await Hub(root, SOURCES, "op-1", port=0, on_message=lambda m, b: told.append(b), **FAST).start()
        try:
            await _until(lambda: told)
            assert told == [b"1"]
            await asyncio.sleep(0.2)
            await again.stop()
            third = await Hub(root, SOURCES, "op-1", port=0, on_message=lambda m, b: told.append(b), **FAST).start()
            await asyncio.sleep(0.3)
            await third.stop()
            assert told == [b"1"]                                       # noted as told: not again
        finally:
            await again.stop()
    asyncio.run(run())


def test_message_to_the_hub_from_a_medium_is_told_once(tmp_path):
    """Before 2026-11-04 the hub told such a message twice (once while importing, once afterwards)."""
    tmp, told = str(tmp_path), []
    stick = os.path.join(tmp, "stick")

    async def run():
        src = _src(tmp, "source-1", 1)
        src.send_message(["hub"], "reply", b"by stick")
        await src.export_media(stick)
        hub = Hub(os.path.join(tmp, "hub"), SOURCES, "op-1", on_message=lambda m, b: told.append(b))
        await hub.import_media(stick)
        await hub.import_media(stick)                                   # again: nothing new
        await asyncio.sleep(0.2)
        assert told == [b"by stick"]
    asyncio.run(run())
