"""Conformance adapter for the Python reference (conformance/README.md).

Reads one JSON command per line on stdin and writes one JSON answer per line on stdout. Another implementation
provides the same commands in its own language; the harness (conformance/harness.py) then tests it the same way.

    python conformance/adapter_python.py
"""

import asyncio
import json
import os
import sys
import threading

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "src"))

from rope_protocol.consumer import Consumer  # noqa: E402
from rope_protocol.recipient import Recipient  # noqa: E402
from rope_protocol.source import Source  # noqa: E402

FAST = dict(timeout_s=1.0, backoff=(0.05, 0.3))     # the harness uses short timeouts to stay quick


class Adapter:
    def __init__(self):
        self.p = None                       # the one participant this adapter runs
        self.told = {}                      # message id -> how often on_message was called
        self.checked = {}                   # stream -> result of the final check (source)

    def _told(self, meta, body):
        self.told[meta["id"]] = self.told.get(meta["id"], 0) + 1

    def _hub(self, c):
        host, port = c["hub"].rsplit(":", 1)
        return host, int(port)

    async def handle(self, c):
        cmd = c.get("cmd")
        if cmd == "start_source":
            host, port = self._hub(c)
            self.p = Source(c["participant"], c["operation"], host, c["files"], c["dir"], hub_port=port,
                            poll_s=0.05, segment_bytes=64 * 1024, on_message=self._told, **FAST).start()
            return {}
        if cmd == "start_consumer":
            host, port = self._hub(c)
            self.p = Consumer(c["participant"], c["operation"], host, c["dir"], hub_port=port, on_message=self._told,
                              **FAST).start()
            return {}
        if cmd == "start_recipient":
            host, port = self._hub(c)
            self.p = Recipient(c["participant"], c["operation"], host, c["dir"], hub_port=port, poll_s=0.05,
                               on_message=self._told, **FAST).start()
            return {}
        if cmd == "add_stream":
            self.p.add_stream(c["stream"], c["path"])
            return {}
        if cmd == "complete":
            self.p.complete(c["stream"])
            asyncio.ensure_future(self._wait_checked(c["stream"]))
            return {}
        if cmd == "send_message":
            return {"id": self.p.send_message(c["to"], c["kind"], bytes.fromhex(c["body_hex"]))}
        if cmd == "status":
            return self.status()
        if cmd == "stop":
            if self.p is not None:
                await self.p.stop()
                self.p = None
            return {}
        raise ValueError("unknown command %r" % cmd)

    async def _wait_checked(self, stream):
        try:
            self.checked[stream] = await self.p.wait_checked(stream, 60)
        except Exception as e:                       # reported, not raised: the harness reads it from status
            self.checked[stream] = "error: %s" % e

    def status(self):
        p = self.p
        out = {"running": p is not None, "connected": bool(p and p.connected.is_set()), "rejected": None,
               "checked": dict(self.checked), "told": dict(self.told), "inbox": [], "streams": []}
        if p is None:
            return out
        if p.rejected is not None:
            out["rejected"] = {"code": p.rejected.code, "operation": getattr(p.rejected, "operation", None)}
        for m in p.inbox():
            out["inbox"].append({"id": m["id"], "from": m["from"], "kind": m["kind"],
                                 "body_hex": p.message_body(m["id"]).hex()})
        if isinstance(p, Consumer):
            for s in p.streams():
                out["streams"].append({k: s[k] for k in ("stream", "gen", "committed", "verified", "path")})
        return out


def main():
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    adapter = Adapter()
    lines = asyncio.Queue()

    def read():                              # stdin in a thread: works with every event loop on every platform
        for line in sys.stdin:
            loop.call_soon_threadsafe(lines.put_nowait, line)
        loop.call_soon_threadsafe(lines.put_nowait, None)

    threading.Thread(target=read, daemon=True).start()

    async def run():
        while True:
            line = await lines.get()
            if line is None:
                break
            line = line.strip()
            if not line:
                continue
            try:
                c = json.loads(line)
                if c.get("cmd") == "quit":
                    if adapter.p is not None:
                        await adapter.p.stop()
                    print(json.dumps({"ok": True}), flush=True)
                    break
                answer = dict(await adapter.handle(c), ok=True)
            except Exception as e:
                answer = {"ok": False, "error": "%s: %s" % (type(e).__name__, e)}
            print(json.dumps(answer), flush=True)
    loop.run_until_complete(run())


if __name__ == "__main__":
    main()
