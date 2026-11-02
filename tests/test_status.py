"""Status for operators (spec 8.7): read from a hub folder - after a real transfer and with messages waiting."""

import asyncio
import json
import os

from rope_protocol import status
from test_transfer import Bench, _file


def test_status_after_a_transfer(tmp_path):
    data = os.urandom(300_000)
    path = _file(tmp_path, "rec1.dat", data)

    async def run():
        async with Bench(str(tmp_path)) as b:
            src = b.source({"rec1": path}).start()
            src.complete("rec1")
            assert await src.wait_checked("rec1", 30) == "ok"
            await src.stop()
    asyncio.run(run())
    hub = os.path.join(str(tmp_path), "hub")
    msgs = os.path.join(hub, "messages")
    os.makedirs(msgs, exist_ok=True)
    with open(os.path.join(msgs, "m1.json"), "w", encoding="utf-8") as f:
        json.dump({"meta": {"id": "m1", "from": "source-1", "to": ["tablet", "nobody"], "t": 1},
                   "state": {"pending": ["tablet"], "delivered": [], "unknown": ["nobody"]}}, f)
    st = status.hub_status(hub)
    assert st["streams"] == [dict(participant="source-1", stream="rec1", gen=1, committed=300_000, complete=True,
                                  verified=st["streams"][0]["verified"])]
    assert st["streams"][0]["verified"]
    assert st["messages"] == {"total": 1, "pending": {"tablet": 1}, "unknown": ["nobody"]}
    lines = status.text(st)
    assert "source-1 / rec1" in lines[1] and "verified" in lines[1]
    assert "  waiting for tablet: 1" in lines and any("nobody" in line for line in lines)


def test_empty_or_missing_folder(tmp_path, capsys):
    assert status.hub_status(str(tmp_path)) == {"streams": [], "messages": {"total": 0, "pending": {}, "unknown": []}}
    assert status.main([str(tmp_path / "missing")]) == 2
    assert status.main([str(tmp_path)]) == 0
    assert "Streams: 0" in capsys.readouterr().out
