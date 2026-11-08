"""Live connections of a hub (#43): who has a session right now, how long ago each was last heard, and when the
sessions of the others ended. Read-only copies for the hub's application; no wire change."""

import asyncio
import threading
import time

from test_transfer import FAST, Bench, _file, _until


def test_two_participants_listed_and_heard(tmp_path):
    path = _file(tmp_path, "x.dat", b"x" * 1000)
    out = {}

    async def run():
        async with Bench(str(tmp_path), participants={"source-1": "source", "source-2": "source"}) as b:
            s1 = b.source({"x": path}).start()
            s2 = b.source({"x": path}, participant="source-2").start()
            await _until(lambda: len(b.hub.connections()) == 2, 5)
            await asyncio.sleep(3 * FAST["heartbeat_s"])           # idle: only heartbeats flow
            out["conn"] = b.hub.connections()
            out["seen_before"] = b.hub.last_seen()
            from_thread = []
            t = threading.Thread(target=lambda: from_thread.append(b.hub.connections()))
            t.start()
            t.join()
            out["thread"] = from_thread[0]
            await s1.stop()
            await s2.stop()
    asyncio.run(run())
    conn = out["conn"]
    assert set(conn) == {"source-1", "source-2"}
    for e in conn.values():
        assert e["role"] == "source"
        assert abs(e["since"] / 1000 - time.time()) < 30
        assert 0 <= e["last_heard_s"] < FAST["heartbeat_s"] * 2 + 0.2     # heartbeats keep it fresh
        assert e["address"] and e["address"].startswith("127.0.0.1:")
    assert out["seen_before"] == {}
    assert set(out["thread"]) == {"source-1", "source-2"}


def test_disconnect_moves_to_last_seen_and_back(tmp_path):
    path = _file(tmp_path, "x.dat", b"x" * 1000)
    out = {}

    async def run():
        async with Bench(str(tmp_path)) as b:
            src = b.source({"x": path}).start()
            await _until(lambda: "source-1" in b.hub.connections(), 5)
            await src.stop()
            await _until(lambda: "source-1" not in b.hub.connections(), 5)
            out["seen"] = b.hub.last_seen()
            src = b.source({"x": path}).start()                     # greets again: connected, no "last seen"
            await _until(lambda: "source-1" in b.hub.connections(), 5)
            out["seen_again"] = b.hub.last_seen()
            await src.stop()
    asyncio.run(run())
    assert set(out["seen"]) == {"source-1"} and abs(out["seen"]["source-1"] / 1000 - time.time()) < 30
    assert out["seen_again"] == {}


def test_last_heard_grows_while_silent(tmp_path):
    """No traffic for a while: last_heard_s shows it (simulated by moving the channel's last receive back)."""
    path = _file(tmp_path, "x.dat", b"x")
    out = {}

    async def run():
        async with Bench(str(tmp_path), heartbeat_s=2.0, timeout_s=10.0) as b:
            src = b.source({"x": path}, timeout_s=10.0).start()
            await _until(lambda: "source-1" in b.hub.connections(), 5)
            ch = b.hub._live["source-1"][2]
            ch.last_received -= 5.0
            out["heard"] = b.hub.connections()["source-1"]["last_heard_s"]
            await src.stop()
    asyncio.run(run())
    assert 5.0 <= out["heard"] < 7.0


def test_replaced_session_keeps_one_entry(tmp_path):
    """A new greeting of the same participant (e.g. after a radio dropout) replaces its session: still one entry."""
    path = _file(tmp_path, "x.dat", b"x" * 1000)
    out = {}

    async def run():
        async with Bench(str(tmp_path)) as b:
            first = b.source({"x": path}, backoff=(5.0, 5.0)).start()   # once replaced, it stays away for 5 s
            await _until(lambda: "source-1" in b.hub.connections(), 5)
            started = b.hub.sessions_started
            second = b.source({"x": path}).start()
            await _until(lambda: b.hub.sessions_started > started, 5)
            await asyncio.sleep(0.1)
            out["conn"] = b.hub.connections()
            out["seen"] = b.hub.last_seen()
            await first.stop()
            await second.stop()
    asyncio.run(run())
    assert list(out["conn"]) == ["source-1"] and out["seen"] == {}
