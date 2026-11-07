"""Conformance harness (#32, conformance/README.md): tests a ROPE participant implementation over TCP.

The implementation under test runs as an adapter process (JSON lines on stdin/stdout). The harness runs the Python
reference hub, the link simulator and, where needed, reference participants, and checks the results: streams bit for
bit, final check "ok", messages told exactly once, plain-language rejects.

    python conformance/harness.py                                   # tests the Python reference adapter
    python conformance/harness.py --adapter "rope-rs-adapter" -k source
"""

import argparse
import asyncio
import json
import os
import shlex
import sys
import tempfile
import time
import traceback

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "src"))

from rope_protocol import frames as F  # noqa: E402
from rope_protocol.channel import now_ms  # noqa: E402
from rope_protocol.frames import Frame, FrameType  # noqa: E402
from rope_protocol.hub import Hub  # noqa: E402
from rope_protocol.linksim import LinkProxy, Profile  # noqa: E402
from rope_protocol.recipient import Recipient  # noqa: E402
from rope_protocol.source import Source  # noqa: E402

DEFAULT_ADAPTER = '"%s" "%s"' % (sys.executable, os.path.join(HERE, "adapter_python.py"))
HUB = dict(heartbeat_s=0.2, timeout_s=1.0)
REF = dict(timeout_s=1.0, backoff=(0.05, 0.3), poll_s=0.05)
OP = "op-1"
VECTORS = os.path.join(HERE, "..", "docs", "vectors", "frames.json")


class Failed(AssertionError):
    pass


def check(cond, text):
    if not cond:
        raise Failed(text)


class Adapter:
    """The implementation under test, driven over JSON lines."""

    def __init__(self, command):
        self.command = command
        self.proc = None

    async def start(self):
        args = shlex.split(self.command, posix=os.name != "nt")
        args = [a.strip('"') for a in args]
        self.proc = await asyncio.create_subprocess_exec(*args, stdin=asyncio.subprocess.PIPE,
                                                         stdout=asyncio.subprocess.PIPE,
                                                         limit=64 * 1024 * 1024)   # status lines carry message bodies
        return self

    async def call(self, cmd, timeout=15, **kw):
        self.proc.stdin.write((json.dumps(dict(kw, cmd=cmd)) + "\n").encode("utf-8"))
        await self.proc.stdin.drain()
        line = await asyncio.wait_for(self.proc.stdout.readline(), timeout)
        if not line:
            raise Failed("adapter ended while answering %r" % cmd)
        answer = json.loads(line)
        if not answer.get("ok"):
            raise Failed("adapter refused %r: %s" % (cmd, answer.get("error")))
        return answer

    async def until(self, cond, text, timeout=30):
        end = time.monotonic() + timeout
        while True:
            st = await self.call("status")
            if cond(st):
                return st
            if time.monotonic() > end:
                raise Failed("%s (last status: %s)" % (text, json.dumps(st)[:300]))
            await asyncio.sleep(0.1)

    async def close(self):
        if self.proc is None:
            return
        try:
            await self.call("quit", timeout=10)
        except Exception:
            pass
        try:
            await asyncio.wait_for(self.proc.wait(), 10)
        except asyncio.TimeoutError:
            self.proc.kill()


class Bench:
    """Reference hub behind the link simulator; the adapter connects through the simulator."""

    def __init__(self, tmp, participants, profile="lan", script=None):
        self.tmp, self.participants, self.profile, self.script = tmp, participants, profile, script

    async def __aenter__(self):
        self.hub = await Hub(os.path.join(self.tmp, "hub"), self.participants, OP, port=0, **HUB).start()
        self.proxy = await LinkProxy(("127.0.0.1", 0), ("127.0.0.1", self.hub.port), self.profile,
                                     script=self.script).start()
        self.address = "127.0.0.1:%d" % self.proxy.port
        return self

    async def __aexit__(self, *exc):
        await self.proxy.stop()
        await self.hub.stop()

    def at_hub(self, participant, stream, gen=1):
        """{participant, stream, gen, committed, complete, verified, path} of a stored stream, or None (read only:
        StreamStore.get would create the stream)."""
        return next((e for e in self.hub.store.entries() if (e["participant"], e["stream"], e["gen"]) ==
                     (participant, stream, gen)), None)

    def committed(self, participant, stream, gen=1):
        e = self.at_hub(participant, stream, gen)
        return e["committed"] if e is not None else 0


def _file(tmp, name, data):
    path = os.path.join(tmp, name)
    with open(path, "wb") as f:
        f.write(data)
    return path


def _append(path, data):
    with open(path, "ab") as f:
        f.write(data)


def _content(path):
    with open(path, "rb") as f:
        return f.read()


async def _source_to_hub(a, tmp, data_parts, profile="lan", script=None, restart_at=None):
    """Adapter as source sends a growing file; the hub must hold it bit for bit and the final check must be ok."""
    path = _file(tmp, "rec-0001.dat", data_parts[0])
    async with Bench(tmp, {"source-1": "source"}, profile, script) as b:
        start = dict(participant="source-1", operation=OP, hub=b.address, files={"rec-0001.dat": path},
                     dir=os.path.join(tmp, "src"))
        await a.call("start_source", **start)
        await a.until(lambda s: s["connected"], "source did not connect")
        for part in data_parts[1:]:
            _append(path, part)
        total = sum(len(p) for p in data_parts)
        if restart_at is not None:
            end = time.monotonic() + 30
            while b.committed("source-1", "rec-0001.dat") < restart_at:
                check(time.monotonic() < end, "nothing committed before the restart")
                await asyncio.sleep(0.05)
            await a.call("stop")
            await a.call("start_source", **start)
        end = time.monotonic() + 60
        while b.committed("source-1", "rec-0001.dat") < total:
            check(time.monotonic() < end, "hub did not receive all %d bytes" % total)
            await asyncio.sleep(0.05)
        await a.call("complete", stream="rec-0001.dat")
        st = await a.until(lambda s: "rec-0001.dat" in s["checked"], "no final check", 60)
        check(st["checked"]["rec-0001.dat"] == "ok", "final check: %s" % st["checked"]["rec-0001.dat"])
        got = b.at_hub("source-1", "rec-0001.dat")
        check(_content(got["path"]) == b"".join(data_parts), "stream at the hub differs from the file")
        check(b.at_hub("source-1", "rec-0001.dat", 2) is None, "a second generation was started")


async def source_basic(a, tmp):
    await _source_to_hub(a, tmp, [os.urandom(300_000), os.urandom(200_000)])


async def source_disconnects(a, tmp):
    slow = Profile("slow", rate=400_000)
    await _source_to_hub(a, tmp, [os.urandom(600_000)], slow,
                         script=[(0.4, "disconnect", 0.2), (1.0, "disconnect", 0.3), (1.3, "blackout", 0.5)])


async def source_restart(a, tmp):
    slow = Profile("slow", rate=300_000)
    await _source_to_hub(a, tmp, [os.urandom(900_000)], slow, restart_at=100_000)


async def reject_unknown(a, tmp):
    path = _file(tmp, "x.dat", b"x")
    async with Bench(tmp, {"source-1": "source"}) as b:
        await a.call("start_source", participant="source-9", operation=OP, hub=b.address, files={"x.dat": path},
                     dir=os.path.join(tmp, "src"))
        st = await a.until(lambda s: s["rejected"] is not None, "no reject reported")
        check(st["rejected"]["code"] == "unknown_participant", "reject code %s" % st["rejected"]["code"])
        check(not st["connected"], "rejected participant counts as connected")
        check(b.hub.store.have("source-9") == [], "hub stored data of a rejected participant")


async def consumer_relay(a, tmp):
    data = os.urandom(400_000)
    path = _file(tmp, "rec-0001.dat", data)
    async with Bench(tmp, {"source-1": "source", "c-1": "consumer"}) as b:
        src = Source("source-1", OP, "127.0.0.1", {"rec-0001.dat": path}, os.path.join(tmp, "ref-src"),
                     hub_port=b.hub.port, **REF).start()
        try:
            await a.call("start_consumer", participant="c-1", operation=OP, hub=b.address, dir=os.path.join(tmp, "c"))
            src.complete("rec-0001.dat")
            st = await a.until(lambda s: any(x["stream"] == "source-1/rec-0001.dat" and x["verified"]
                                              for x in s["streams"]), "relayed stream not verified at the consumer", 60)
            got = next(x for x in st["streams"] if x["stream"] == "source-1/rec-0001.dat")
            check(_content(got["path"]) == data, "relayed stream differs")
        finally:
            await src.stop()


async def message_to_adapter(a, tmp):
    """A message for the adapter is told exactly once, also across a restart of the adapter's participant."""
    body = "Grüße – ✓".encode("utf-8")
    async with Bench(tmp, {"source-1": "source", "r-1": "recipient"}) as b:
        src = Source("source-1", OP, "127.0.0.1", {}, os.path.join(tmp, "ref-src"), hub_port=b.hub.port, **REF).start()
        try:
            start = dict(participant="r-1", operation=OP, hub=b.address, dir=os.path.join(tmp, "r"))
            await a.call("start_recipient", **start)
            msg_id = src.send_message(["r-1"], "note", body)
            st = await a.until(lambda s: s["told"].get(msg_id), "message not told")
            got = next(m for m in st["inbox"] if m["id"] == msg_id)
            check(bytes.fromhex(got["body_hex"]) == body and got["from"] == "source-1", "message content differs")
            await a.call("stop")
            await a.call("start_recipient", **start)
            await a.until(lambda s: s["connected"], "recipient did not reconnect")
            await asyncio.sleep(1.0)
            st = await a.call("status")
            check(st["told"].get(msg_id) == 1, "message told %s times" % st["told"].get(msg_id))
        finally:
            await src.stop()


async def message_from_adapter(a, tmp):
    """A message from the adapter reaches a reference recipient exactly once."""
    told = []
    async with Bench(tmp, {"r-1": "recipient", "r-2": "recipient"}) as b:
        ref = Recipient("r-2", OP, "127.0.0.1", os.path.join(tmp, "ref-r"), hub_port=b.hub.port,
                        on_message=lambda meta, body: told.append((meta, body)), **REF).start()
        try:
            await a.call("start_recipient", participant="r-1", operation=OP, hub=b.address, dir=os.path.join(tmp, "r"))
            ans = await a.call("send_message", to=["r-2"], kind="note", body_hex=b"hello".hex())
            end = time.monotonic() + 30
            while not told:
                check(time.monotonic() < end, "message from the adapter did not arrive")
                await asyncio.sleep(0.05)
            await asyncio.sleep(1.0)
            check(len(told) == 1 and told[0][0]["id"] == ans["id"] and told[0][1] == b"hello",
                  "message arrived %d times or differs" % len(told))
        finally:
            await ref.stop()


async def _wait_committed(b, participant, stream, total, gen=1, timeout=60):
    end = time.monotonic() + timeout
    while b.committed(participant, stream, gen) < total:
        check(time.monotonic() < end, "hub did not receive all %d bytes of generation %d" % (total, gen))
        await asyncio.sleep(0.05)


async def source_repair(a, tmp):
    """Bytes changed in place after they were sent (a header updated at the end of a recording) are fixed by the
    block repair: final check ok, the hub holds the changed file, no new generation (spec 14.7)."""
    data = bytearray(os.urandom(3_000_000))             # three blocks of the recommended 1 MiB
    path = _file(tmp, "rec-0001.dat", bytes(data))
    async with Bench(tmp, {"source-1": "source"}) as b:
        await a.call("start_source", participant="source-1", operation=OP, hub=b.address,
                     files={"rec-0001.dat": path}, dir=os.path.join(tmp, "src"))
        await _wait_committed(b, "source-1", "rec-0001.dat", len(data))
        data[0:64] = os.urandom(64)                     # the header, rewritten in place
        with open(path, "r+b") as f:
            f.write(bytes(data[0:64]))
        await a.call("complete", stream="rec-0001.dat")
        st = await a.until(lambda s: "rec-0001.dat" in s["checked"], "no final check", 60)
        check(st["checked"]["rec-0001.dat"] == "ok", "final check after repair: %s" % st["checked"]["rec-0001.dat"])
        check(_content(b.at_hub("source-1", "rec-0001.dat")["path"]) == bytes(data),
              "stream at the hub differs from the changed file")
        check(b.at_hub("source-1", "rec-0001.dat", 2) is None, "a new generation instead of a block repair")


async def source_new_generation(a, tmp):
    """A file that became shorter is a new generation; the hub keeps the old one unchanged (spec 14.4)."""
    old, new = os.urandom(400_000), os.urandom(150_000)
    path = _file(tmp, "rec-0001.dat", old)
    async with Bench(tmp, {"source-1": "source"}) as b:
        await a.call("start_source", participant="source-1", operation=OP, hub=b.address,
                     files={"rec-0001.dat": path}, dir=os.path.join(tmp, "src"))
        await _wait_committed(b, "source-1", "rec-0001.dat", len(old))
        _file(tmp, "rec-0001.dat", new)                 # replaced by a shorter file
        await _wait_committed(b, "source-1", "rec-0001.dat", len(new), gen=2)
        await a.call("complete", stream="rec-0001.dat")
        st = await a.until(lambda s: "rec-0001.dat" in s["checked"], "no final check", 60)
        check(st["checked"]["rec-0001.dat"] == "ok", "final check: %s" % st["checked"]["rec-0001.dat"])
        check(_content(b.at_hub("source-1", "rec-0001.dat", 2)["path"]) == new, "generation 2 differs")
        check(_content(b.at_hub("source-1", "rec-0001.dat", 1)["path"]) == old, "generation 1 was changed")


def _reject_scenario(name, participants, operation, code):
    async def scenario(a, tmp):
        path = _file(tmp, "x.dat", b"x")
        async with Bench(tmp, participants) as b:
            await a.call("start_source", participant="source-1", operation=operation, hub=b.address,
                         files={"x.dat": path}, dir=os.path.join(tmp, "src"))
            st = await a.until(lambda s: s["rejected"] is not None, "no reject reported")
            check(st["rejected"]["code"] == code, "reject code %s, expected %s" % (st["rejected"]["code"], code))
            check(not st["connected"], "rejected participant counts as connected")
            check(b.hub.store.have("source-1") == [], "hub stored data of a rejected participant")
    scenario.__name__ = name
    return scenario


reject_wrong_operation = _reject_scenario("reject_wrong_operation", {"source-1": "source"}, "op-2", "wrong_operation")
reject_role = _reject_scenario("reject_role", {"source-1": "consumer"}, OP, "role")

FLAKY = dict(profile=Profile("slow", rate=60_000),
             script=[(0.3, "disconnect", 0.2), (0.9, "disconnect", 0.3), (1.6, "blackout", 0.6)])


async def messages_to_adapter_disconnects(a, tmp):
    """Several messages through a link that breaks: each is told exactly once (spec 8.5, 14.10)."""
    bodies = [os.urandom(30_000) for _ in range(5)]
    async with Bench(tmp, {"source-1": "source", "r-1": "recipient"}, **FLAKY) as b:
        src = Source("source-1", OP, "127.0.0.1", {}, os.path.join(tmp, "ref-src"), hub_port=b.hub.port, **REF).start()
        try:
            await a.call("start_recipient", participant="r-1", operation=OP, hub=b.address, dir=os.path.join(tmp, "r"))
            ids = [src.send_message(["r-1"], "note", body) for body in bodies]
            await a.until(lambda s: all(s["told"].get(i) for i in ids), "not every message told", 60)
            await asyncio.sleep(1.5)
            st = await a.call("status")
            check(all(st["told"].get(i) == 1 for i in ids), "told counts %s" % [st["told"].get(i) for i in ids])
            inbox = {m["id"]: bytes.fromhex(m["body_hex"]) for m in st["inbox"]}
            check(all(inbox.get(i) == body for i, body in zip(ids, bodies)), "message content differs")
        finally:
            await src.stop()


async def messages_from_adapter_disconnects(a, tmp):
    """Several messages from the adapter through a link that breaks reach a reference recipient exactly once."""
    told = []
    async with Bench(tmp, {"r-1": "recipient", "r-2": "recipient"}, **FLAKY) as b:
        ref = Recipient("r-2", OP, "127.0.0.1", os.path.join(tmp, "ref-r"), hub_port=b.hub.port,
                        on_message=lambda meta, body: told.append((meta["id"], body)), **REF).start()
        try:
            await a.call("start_recipient", participant="r-1", operation=OP, hub=b.address, dir=os.path.join(tmp, "r"))
            sent = {}
            for _ in range(5):
                body = os.urandom(30_000)
                sent[(await a.call("send_message", to=["r-2"], kind="note", body_hex=body.hex()))["id"]] = body
            end = time.monotonic() + 60
            while len({i for i, _ in told}) < len(sent):
                check(time.monotonic() < end, "%d of %d messages arrived" % (len({i for i, _ in told}), len(sent)))
                await asyncio.sleep(0.05)
            await asyncio.sleep(1.5)
            check(len(told) == len(sent), "%d messages told for %d sent" % (len(told), len(sent)))
            check(all(sent.get(i) == body for i, body in told), "message content differs")
        finally:
            await ref.stop()


class MockHub:
    """A scripted hub for frame-level checks: takes the greeting of the adapter's source and answers with ``reply``
    (bytes, sent at once), then records every frame until the adapter closes the connection."""

    def __init__(self, reply, listen_s=3.0):
        self.reply = reply
        self.listen_s = listen_s
        self.hello = None
        self.frames = []
        self.closed = False
        self.done = asyncio.Event()

    async def start(self):
        self.server = await asyncio.start_server(self._conn, "127.0.0.1", 0)
        self.address = "127.0.0.1:%d" % self.server.sockets[0].getsockname()[1]
        return self

    async def stop(self):
        self.server.close()

    async def _conn(self, reader, writer):
        if self.done.is_set():                      # only the first connection counts
            writer.close()
            return
        dec = F.FrameDecoder()
        try:
            while self.hello is None:
                data = await asyncio.wait_for(reader.read(65536), 5)
                if not data:
                    return
                got = dec.feed(data)
                if got:
                    self.hello = got[0]
                    self.frames += got[1:]
            writer.write(self.reply(self.hello))
            await writer.drain()
            end = time.monotonic() + self.listen_s
            while time.monotonic() < end:
                try:
                    data = await asyncio.wait_for(reader.read(65536), 0.15)
                except asyncio.TimeoutError:
                    data = None
                if data is not None and not data:
                    self.closed = True
                    break
                if data:
                    self.frames += dec.feed(data)
                # stay alive like a hub: heartbeats, so that silence never ends the session (spec 9)
                writer.write(F.encode(Frame(FrameType.HEARTBEAT, dict(t=now_ms()))))
                await writer.drain()
        except (ConnectionError, F.FrameError):
            self.closed = True
        finally:
            self.done.set()
            writer.close()


def _welcome(hello):
    return F.encode(Frame(FrameType.WELCOME, dict(version=1, hub="hub", t=now_ms(), t_hello=hello.meta.get("t", 0),
                                                  heartbeat_s=0.2, timeout_s=1.0, have=[])))


async def _mock(a, tmp, reply, listen_s=3.0):
    path = _file(tmp, "x.dat", b"x" * 1000)
    hub = await MockHub(reply, listen_s).start()
    try:
        await a.call("start_source", participant="source-1", operation=OP, hub=hub.address, files={"x.dat": path},
                     dir=os.path.join(tmp, "src"))
        await asyncio.wait_for(hub.done.wait(), listen_s + 15)
        hub.status = await a.call("status")         # before stopping: what the adapter's participant reports
        return hub
    finally:
        await a.call("stop")
        await hub.stop()


def _errors(hub):
    return [f for f in hub.frames if f.type == FrameType.ERROR]


async def frame_hello(a, tmp):
    """The greeting is a valid HELLO (spec 14.5)."""
    hub = await _mock(a, tmp, _welcome, listen_s=0.5)
    h = hub.hello
    check(h is not None and h.type == FrameType.HELLO, "first frame is not HELLO")
    F.validate(h)
    check(h.meta["participant"] == "source-1" and h.meta["operation"] == OP and h.meta["role"] == "source",
          "HELLO names %s / %s / %s" % (h.meta["participant"], h.meta["operation"], h.meta["role"]))
    check(1 in h.meta["versions"], "HELLO does not offer protocol version 1")


def _bad_vector_scenario(v):
    async def scenario(a, tmp):
        raw = bytes.fromhex(v["frame_hex"])
        hub = await _mock(a, tmp, lambda hello: _welcome(hello) + raw)
        errs = _errors(hub)
        check(errs, "no ERROR after the damaged frame %r (got %s)" % (v["name"],
                                                                    [FrameType(f.type).name for f in hub.frames]))
        check(errs[0].meta["code"] == v["error"], "ERROR code %s, expected %s" % (errs[0].meta["code"], v["error"]))
        check(hub.closed, "connection not closed after ERROR")
    scenario.__name__ = "frame_bad_" + v["name"].replace("-", "_")
    return scenario


async def frame_unknown_core_type(a, tmp):
    hub = await _mock(a, tmp, lambda hello: _welcome(hello) + F.encode(Frame(0x7E, dict(t=now_ms()))))
    errs = _errors(hub)
    check(errs and errs[0].meta["code"] == "unknown_type", "unknown core type not answered with ERROR unknown_type")
    check(hub.closed, "connection not closed after ERROR")


async def frame_extension_ignored(a, tmp):
    """An unknown extension frame (0x80-0xFF) is ignored: no ERROR, the session goes on (heartbeats keep coming)."""
    hub = await _mock(a, tmp, lambda hello: _welcome(hello) + F.encode(Frame(0x90, dict(x=1))), listen_s=2.0)
    check(not _errors(hub), "extension frame answered with ERROR %s" % [f.meta for f in _errors(hub)])
    check(not hub.closed, "connection closed after an extension frame")
    check(any(f.type in (FrameType.HEARTBEAT, FrameType.SEGMENT) for f in hub.frames), "session did not go on")


async def frame_reject_announced(a, tmp):
    """A REJECT with the optional announced operation reaches the application (spec 14.5)."""
    rej = F.encode(Frame(FrameType.REJECT, dict(code="wrong_operation", text="this hub serves op-9",
                                                operation="op-9", operation_name="Lake exercise")))
    hub = await _mock(a, tmp, lambda hello: rej, listen_s=1.0)
    check(hub.hello is not None, "no greeting")
    st = hub.status
    check(st["rejected"] and st["rejected"]["code"] == "wrong_operation", "reject not reported: %s" % st["rejected"])
    check(st["rejected"].get("operation") == "op-9", "announced operation not reported: %s" % st["rejected"])


with open(VECTORS, encoding="utf-8") as _f:
    BAD_VECTORS = [_bad_vector_scenario(v) for v in json.load(_f)["invalid"]]


SCENARIOS = [source_basic, source_disconnects, source_restart, source_repair, source_new_generation, reject_unknown,
             reject_wrong_operation, reject_role, consumer_relay, message_to_adapter, message_from_adapter,
             messages_to_adapter_disconnects, messages_from_adapter_disconnects, frame_hello] + BAD_VECTORS + [frame_unknown_core_type, frame_extension_ignored,
                                                                 frame_reject_announced]


async def run(adapter_cmd, only=None, out=print):
    results = []
    for sc in SCENARIOS:
        if only and only not in sc.__name__:
            continue
        a = Adapter(adapter_cmd)
        t0 = time.monotonic()
        with tempfile.TemporaryDirectory(prefix="rope-conf-") as tmp:
            try:
                await a.start()
                await sc(a, tmp)
                res = ("PASS", "")
            except Failed as e:
                res = ("FAIL", str(e))
            except Exception:
                res = ("ERROR", traceback.format_exc(limit=3))
            finally:
                await a.close()
        results.append((sc.__name__, res[0], round(time.monotonic() - t0, 1), res[1]))
        out("%-34s %-5s %5.1f s  %s" % results[-1])
    return results


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--adapter", default=DEFAULT_ADAPTER, help="command that starts the adapter under test")
    ap.add_argument("-k", dest="only", help="run only scenarios whose name contains this")
    args = ap.parse_args()
    results = asyncio.run(run(args.adapter, args.only))
    bad = [r for r in results if r[1] != "PASS"]
    print("%d of %d scenarios passed" % (len(results) - len(bad), len(results)))
    sys.exit(1 if bad else 0)


if __name__ == "__main__":
    main()
