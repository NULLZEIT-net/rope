"""A real crash instead of a program stop (spec section 13, test bench): the hub runs in its own process and is killed
hard (no stop(), no finally, no flush of Python buffers) while a stream is being received - twice. After each restart
on the same folder the source continues from the committed offset; the stream ends bit for bit identical."""

import asyncio
import hashlib
import os
import socket
import subprocess
import sys
import time

from rope_protocol.linksim import LinkProxy, Profile
from rope_protocol.source import Source
from rope_protocol.store import StreamStore

SRC_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "src")
HUB = """
import asyncio, sys
sys.path.insert(0, %r)
from rope_protocol.hub import Hub
async def main():
    await Hub(%r, {"source-1": "source"}, "op-1", port=%d, heartbeat_s=0.1, timeout_s=0.6).start()
    await asyncio.Event().wait()
asyncio.run(main())
"""


def _free_port():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _committed(root):
    try:
        return max((e["committed"] for e in StreamStore(root).entries()), default=0)
    except (OSError, ValueError):
        return 0


def _wait_port(port, timeout=10.0):
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        try:
            with socket.create_connection(("127.0.0.1", port), 0.2):
                return
        except OSError:
            time.sleep(0.05)
    raise AssertionError("hub did not start")


def test_hub_killed_twice_during_transfer(tmp_path):
    data = os.urandom(3_000_000)
    path = str(tmp_path / "k.dat")
    with open(path, "wb") as f:
        f.write(data)
    root, port = str(tmp_path / "hub"), _free_port()

    def start_hub():
        p = subprocess.Popen([sys.executable, "-c", HUB % (SRC_DIR, root, port)])
        _wait_port(port)
        return p

    async def run():
        hub = start_hub()
        try:
            async with LinkProxy(("127.0.0.1", 0), ("127.0.0.1", port), Profile("slow", rate=1_000_000)) as proxy:
                src = Source("source-1", "op-1", "127.0.0.1", {"k": path}, str(tmp_path / "src"), hub_port=proxy.port,
                             timeout_s=0.6, backoff=(0.05, 0.2), poll_s=0.05, segment_bytes=64 * 1024).start()
                for level in (500_000, 1_500_000):
                    end = time.monotonic() + 30
                    while _committed(root) < level:                 # read the hub's folder from outside
                        assert time.monotonic() < end, "transfer did not progress"
                        await asyncio.sleep(0.05)
                    hub.kill()                                      # hard: like a power cut of the process
                    hub.wait()
                    await asyncio.sleep(0.2)
                    hub = start_hub()
                src.complete("k")
                assert await src.wait_checked("k", 60) == "ok"
                await src.stop()
        finally:
            hub.kill()
            hub.wait()
        rs = [e for e in StreamStore(root).entries() if e["stream"] == "k"]
        assert len(rs) == 1 and rs[0]["committed"] == len(data)
        with open(rs[0]["path"], "rb") as f:
            assert hashlib.sha256(f.read()).hexdigest() == hashlib.sha256(data).hexdigest()
    asyncio.run(run())
