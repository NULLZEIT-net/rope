<h1>
  <picture>
    <source media="(prefers-color-scheme: dark)" srcset="https://raw.githubusercontent.com/NULLZEIT-net/rope/main/docs/images/rope-logo-dark.svg">
    <img alt="ROPE" src="https://raw.githubusercontent.com/NULLZEIT-net/rope/main/docs/images/rope-logo.svg" height="72">
  </picture>
</h1>

**Resumable Offline Protocol for Emergencies**

[![Tests](https://github.com/NULLZEIT-net/rope/actions/workflows/tests.yml/badge.svg)](https://github.com/NULLZEIT-net/rope/actions/workflows/tests.yml)
[![PyPI](https://img.shields.io/pypi/v/rope-protocol.svg)](https://pypi.org/project/rope-protocol/)
[![License: Apache-2.0](https://img.shields.io/badge/License-Apache_2.0-blue.svg)](https://github.com/NULLZEIT-net/rope/blob/main/LICENSE)
![Python 3.11+](https://img.shields.io/badge/Python-3.11%2B-blue.svg)
![Status: early development](https://img.shields.io/badge/status-early_development-orange.svg)

ROPE transfers growing files and small messages between a small, closed group of devices over unreliable local
networks – radio links, Wi-Fi, no internet. Like a rescue line it holds the connection even when it is pulled:
an interruption costs time, never data.

> **Status:** early development, version 0.1.4. The wire format and media format 1 of the
> [specification](https://github.com/NULLZEIT-net/rope/blob/main/docs/spec.md) are frozen for spec 1.0 (decided
> 2026-11-07); spec 1.0 is released after field experience. Streams from sources via the hub to consumers work,
> including resume after disconnects and restarts and block repair, and so do messages with custody and offline media
> (e.g. a USB stick) as a second path. The Python interfaces may still change.

## Why

Field teams record large files (for example sonar recordings) on one device and want to evaluate them somewhere else
while they are still being recorded. The link in between drops out regularly, and there is no internet. Plain TCP does
not resume across connections and acknowledges data before it is safely stored; UDP loses data during outages. ROPE
adds the missing pieces on top of TCP, borrowing ideas – not code – from space communication (CFDP class 2, DTN custody
transfer).

## Key properties

- **Resumable** – after any interruption, transfer continues from the last durably stored byte, never from zero.
- **Custody** – a receiver acknowledges only after the data is on disk (flush + fsync). The sender of a message
  learns which recipients have it.
- **End-to-end verified** – checksums per segment and per complete file; bit-for-bit identical results. If bytes
  changed after they were sent (e.g. a header updated at the end of a recording), only the differing blocks travel
  again.
- **Never blocks the producer** – separate process, read-only file access without locks, bounded memory.
- **Offline** – no internet, no cloud, no external services.
- **Small groups** – star topology with a hub and a closed participant list: source, consumer and recipient roles,
  names for the operator, and per consumer a choice of which streams it receives.
- **Application-agnostic core** – the core knows nothing about the data; applications define streams and messages.
- **Standard library only** – no third-party runtime dependencies.
- **Two paths** – the same segments and messages can also travel on removable media and mix with the network.

ROPE has **no encryption of its own** and is meant for closed networks. Where a link is not closed, the application
can wrap every connection in **TLS** by passing an `ssl.SSLContext` to the hub and the participants – see
[Security considerations](https://github.com/NULLZEIT-net/rope/blob/main/docs/spec.md#11-security-considerations).

## How it works (in short)

```
 source ──TCP──▶ hub ──TCP──▶ consumer(s)
                  │
                  └──TCP──▶ recipient(s)   (messages only)
```

1. Every participant connects to the hub and greets it (identifier, role, protocol version). The hub checks its
   participant list and tells everybody the names and roles of the group.
2. The hub reports how far it has stored each stream (*committed offset*).
3. The source sends segments from there; the hub writes, syncs, then acknowledges.
4. When a stream is complete, a final checksum confirms the whole file; on a difference, only the differing blocks
   are resent.
5. On any disconnect: reconnect, greet, continue from the committed offset.
6. Without a network, a participant and the hub exchange the same frames as bundles on removable media
   (`export_media`, `import_media`); network and media mix freely.

Details: [docs/spec.md](https://github.com/NULLZEIT-net/rope/blob/main/docs/spec.md).

## Requirements

- Python 3.11 or newer, on Windows or Linux
- Nothing else at runtime

## Installation

```
python -m pip install rope-protocol
```

The package is named `rope-protocol` (import `rope_protocol`), because the name `rope` on PyPI belongs to a
well-known refactoring library. Versions and changes: [CHANGELOG.md](https://github.com/NULLZEIT-net/rope/blob/main/CHANGELOG.md). While ROPE is in early
development, pin the version you tested with (e.g. `rope-protocol==0.1.4`).

Using it in a program: [docs/api.md](https://github.com/NULLZEIT-net/rope/blob/main/docs/api.md) - hub, source,
consumer, recipient, messages, offline media, TLS, with a quick start.

For development:

```
git clone https://github.com/NULLZEIT-net/rope.git
cd rope
python -m pip install pytest pyflakes
python -m pytest
```

### Simulating an unreliable link

No radio link at hand? The link simulator sits between two programs and adds bandwidth limits, latency, blackouts
and disconnects:

```
python -m rope_protocol.linksim --listen 127.0.0.1:47311 --target 127.0.0.1:47310 --profile radio
```

Profiles are `lan`, `wifi`, `radio` and `radio-bad`; `--seed` makes the fault schedule reproducible. All profile
values are assumptions until measured on real links (see spec §13).

ROPE's default port is **47310**; applications can override it.

### Status for operators

- `python -m rope_protocol.status <hub folder>` shows what a hub holds (streams, messages waiting per recipient),
  read from its folder.
- A running hub tells its application who is connected and how fresh each link is: `Hub.connections()` (role,
  session start, seconds since the participant was last heard, peer address) and `Hub.last_seen()` (when the others
  were last connected). Both are copies and may be called from another thread; no extra traffic is sent.

## Repository layout

| Path | Content |
|---|---|
| `docs/spec.md` | Protocol specification (wire format and media format 1 frozen for 1.0) |
| `docs/api.md` | Python API of the reference implementation |
| `docs/decisions.md` | Decisions with date and reason |
| `docs/ideas.md` | Ideas not yet planned |
| `docs/images/` | Logo and symbol (SVG; light and dark variant) |
| `TASKS.md` | Task board |
| `CHANGELOG.md` | Changes per version |
| `src/rope_protocol/` | Package: frame codec (`frames.py`), link simulator (`linksim.py`), durable store (`store.py`), sending and receiving side of streams (`sender.py`, `receiver.py`), messages (`messages.py`), offline media (`media.py`), participant list (`roster.py`), participants (`hub.py`, `source.py`, `consumer.py`, `recipient.py`, base `participant.py`) |
| `tests/` | Unit tests and the fault-injection test bench (`framefault.py`, `test_faults.py`) |
| `docs/vectors/` | Test vectors for every core frame type (valid and invalid frames) |
| `conformance/` | Conformance suite for implementations in other languages: 40 scenarios for the participant and the hub roles, a scripted hub and participant (`harness.py`) and the adapter for this package (`adapter_python.py`) |
| `AGENTS.md` | Guidelines for contributors and coding agents |

## Testing

Every change runs `pyflakes` and `pytest` on Windows and Linux (Python 3.11–3.13). The test bench injects faults – a
simulated radio link with blackouts and disconnects, restarts, and one fault at every step of the procedure (connection
cut before or in the middle of a frame, frame duplicated or damaged, participant or hub restarted) – and checks that every file arrives bit-for-bit
identical and every message exactly once. The full set of faults at every step runs with:

```
ROPE_SOAK=1 python -m pytest tests/test_faults.py
```

The conformance suite (`python conformance/harness.py`, also part of `pytest`) checks an implementation against the
frozen wire format with the same scenarios that this package passes.

## Limitations

- Early development: streams, messages and offline media work. The Python interfaces may still change; the wire
  format is frozen for 1.0 and changes only for corrections found in the field.
- Not a general file synchronisation tool. Over the internet only inside TLS.
- No encryption of its own and no authentication beyond the participant list (and the certificates, when TLS is
  used).
- Not compatible with CFDP or DTN software; only the ideas are borrowed.

## Contributing

Contributions are welcome – please read [CONTRIBUTING.md](https://github.com/NULLZEIT-net/rope/blob/main/CONTRIBUTING.md). Questions and ideas: open an issue.

## License

Copyright 2026 Daniel Fankhauser. Licensed under the [Apache License, Version 2.0](https://github.com/NULLZEIT-net/rope/blob/main/LICENSE); see also [NOTICE](https://github.com/NULLZEIT-net/rope/blob/main/NOTICE).
The name "ROPE" in connection with this protocol is not covered by the licence (Apache-2.0, section 6).
