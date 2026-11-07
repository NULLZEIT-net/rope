"""A participant answers a bad frame from the hub with ERROR and closes the connection (spec 14.2), like the hub does
towards participants. Found by the conformance suite (#32): before, the participant only closed."""

import asyncio
import os

import pytest

from rope_protocol import frames as F
from rope_protocol.channel import now_ms
from rope_protocol.frames import Frame, FrameType
from rope_protocol.source import Source

T = 1767225600000


def _welcome():
    return F.encode(Frame(FrameType.WELCOME, dict(version=1, hub="hub", t=now_ms(), t_hello=T, heartbeat_s=0.2,
                                                  timeout_s=1.0, have=[])))


def _bad_crc():
    raw = bytearray(F.encode(Frame(FrameType.HEARTBEAT, dict(t=T))))
    raw[-1] ^= 1
    return bytes(raw)


def _ack_without_committed():
    return F.encode(Frame(FrameType.ACK, dict(stream="x.dat", gen=1)))


def _unknown_core_type():
    return F.encode(Frame(0x7E, dict(t=T)))


@pytest.mark.parametrize("bad,code", [(_bad_crc, "bad_frame"), (_ack_without_committed, "bad_frame"),
                                      (_unknown_core_type, "unknown_type")])
def test_participant_answers_error(tmp_path, bad, code):
    path = os.path.join(str(tmp_path), "x.dat")
    with open(path, "wb") as f:
        f.write(b"x")
    got = []

    async def mock_hub(reader, writer):
        dec = F.FrameDecoder()
        frames = []
        while not frames:
            frames += dec.feed(await reader.read(65536))
        assert frames[0].type == FrameType.HELLO
        writer.write(_welcome() + bad())
        await writer.drain()
        try:
            while True:
                data = await asyncio.wait_for(reader.read(65536), 3)
                if not data:
                    break
                for fr in dec.feed(data):
                    got.append(fr)
        except (ConnectionError, asyncio.TimeoutError, F.FrameError):
            pass
        writer.close()

    async def run():
        server = await asyncio.start_server(mock_hub, "127.0.0.1", 0)
        port = server.sockets[0].getsockname()[1]
        src = Source("source-1", "op-1", "127.0.0.1", {"x.dat": path}, os.path.join(str(tmp_path), "s"),
                     hub_port=port, timeout_s=1.0, backoff=(5, 5), poll_s=0.05).start()
        end = asyncio.get_running_loop().time() + 5
        while not any(f.type == FrameType.ERROR for f in got):
            assert asyncio.get_running_loop().time() < end, [FrameType(f.type).name for f in got]
            await asyncio.sleep(0.05)
        await src.stop()
        server.close()
        err = next(f for f in got if f.type == FrameType.ERROR)
        assert err.meta["code"] == code and err.meta["text"]
    asyncio.run(run())
