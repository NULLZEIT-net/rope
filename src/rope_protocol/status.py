"""Status for operators (spec section 8.7, proposed): what a hub holds, read from its folder - streams with their
committed offsets and whether they are complete and verified, and messages still waiting for recipients.

Read-only: it opens the state files and never writes, so it can run next to a working hub or on a copy of its folder.

Command line::

    python -m rope_protocol.status <hub folder>
"""

import argparse
import json
import os
import sys


def _read(path):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return None


def hub_status(root):
    """{"streams": [...], "messages": {"total", "pending": {participant: count}, "unknown": [...]}} of a hub folder."""
    streams = []
    folder = os.path.join(root, "streams")
    for name in sorted(os.listdir(folder)) if os.path.isdir(folder) else []:
        s = _read(os.path.join(folder, name, "state.json"))
        if isinstance(s, dict) and "participant" in s:
            streams.append(dict(participant=s["participant"], stream=s.get("stream"), gen=s.get("gen"),
                                committed=s.get("committed", 0), complete=bool(s.get("complete")),
                                verified=s.get("verified")))
    streams.sort(key=lambda e: (e["participant"], str(e["stream"]), e["gen"] or 0))
    total, pending, unknown = 0, {}, set()
    folder = os.path.join(root, "messages")
    for name in sorted(os.listdir(folder)) if os.path.isdir(folder) else []:
        if not name.endswith(".json"):
            continue
        rec = _read(os.path.join(folder, name))
        if not isinstance(rec, dict):
            continue
        total += 1
        state = rec.get("state") or {}
        for p in state.get("pending") or []:
            pending[p] = pending.get(p, 0) + 1
        unknown.update(state.get("unknown") or [])
    return {"streams": streams, "messages": {"total": total, "pending": pending, "unknown": sorted(unknown)}}


def _size(n):
    for unit in ("B", "KiB", "MiB", "GiB"):
        if n < 1024 or unit == "GiB":
            return ("%d %s" % (n, unit)) if unit == "B" else ("%.1f %s" % (n, unit))
        n /= 1024.0


def text(status):
    """The status as plain lines."""
    lines = ["Streams: %d" % len(status["streams"])]
    for s in status["streams"]:
        state = "verified" if s["verified"] else "complete, not yet verified" if s["complete"] else "growing"
        lines.append("  %s / %s  gen %s  %s  %s" % (s["participant"], s["stream"], s["gen"], _size(s["committed"]),
                                                     state))
    m = status["messages"]
    lines.append("Messages held: %d" % m["total"])
    for p, n in sorted(m["pending"].items()):
        lines.append("  waiting for %s: %d" % (p, n))
    if m["unknown"]:
        lines.append("  recipients not on the participant list: %s" % ", ".join(m["unknown"]))
    return lines


def main(argv=None):
    ap = argparse.ArgumentParser(prog="python -m rope_protocol.status", description="Status of a ROPE hub folder.")
    ap.add_argument("folder")
    a = ap.parse_args(argv)
    if not os.path.isdir(a.folder):
        print("No such folder: %s" % a.folder)
        return 2
    print("\n".join(text(hub_status(a.folder))))
    return 0


if __name__ == "__main__":
    sys.exit(main())
