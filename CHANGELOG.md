# Changelog

All notable changes to ROPE (`rope-protocol`) are listed here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/); versions follow [Semantic Versioning](https://semver.org/).
The package version is `rope_protocol.__version__`; the wire protocol has its own number (`PROTOCOL_VERSION`, spec
14.5), which changes only on incompatible changes of the wire format.

## [Unreleased]

### Added
- **Formal model of the design** (`docs/model/`, TLA+): one stream from a source to the hub (resume after
  disconnects and crashes, offline media at the same time, final check) and messages with custody (sender, hub,
  recipient over network and media, crashes, delivery reports). TLC checks every reachable state within small bounds:
  bit for bit, nothing acknowledged that is not stored, nothing lost, told at most once, and that the stream and every
  message arrive in the end. 12 mutation checks break one rule each on purpose; all are found. Results in
  `docs/model/RESULTS.md`; `docs/model/check.py` runs everything, also as the workflow `Model`, started by hand
  from time to time and when the behaviour in the spec changes (`AGENTS.md`). No change of the wire format or the
  spec was needed.
- Conformance suite: three scenarios for a **consumer over TCP**: disconnects, restart with `HELLO.have`, block
  repair at the consumer (spec 14.7). Found missing while writing the consumer of rope-rs (#33). 60 scenarios in all.
- Conformance suite: **offline media** (#32). New adapter commands `export_media` and `import_media`; 17 scenarios
  for both roles without any network: streams to the hub and on to a consumer, messages both ways with receipts and
  delivery reports, a second import changes nothing, a bundle for someone else is left alone; a stick too small for
  everything, damaged and cut-off bundles, and block repair by stick from the source to the hub and from the hub to a
  consumer (spec 14.7). 57 scenarios in all.
- Conformance suite: the **hub role** under test (#32). New adapter command `start_hub`; 18 scenarios with reference
  participants: streams with disconnects, restart and block repair, relay to a consumer, messages with delivery
  reports and to the hub itself, rejects, and damaged frames from a scripted participant. 40 scenarios in all.
- `docs/api.md`: the Python API - hub, source, consumer, recipient, messages, offline media, participant list, TLS, status - with a quick start that is run as written.

### Changed
- `SECURITY.md`: what ROPE guarantees (integrity against accidents) and the optional TLS wrapper (spec §14.1).
- Release workflow: a tag with a capital `V` (`V0.1.5`) starts the release as well as `v0.1.5`.

## [0.1.4] - 2026-11-08

Wire format unchanged (`PROTOCOL_VERSION` 1).

### Added
- `Hub.connections()`: which participants have a session right now, with role, session start, seconds since
  anything was last heard from them (monotonic clock, heartbeats included) and peer address. `Hub.last_seen()`:
  when the session of each participant that is not connected any more ended. Both are copies and may be called from
  another thread, for a live status in the hub's application. No change of the wire format (#43).
- Conformance suite: frame-level scenarios against a scripted hub. They cover a valid `HELLO`, the invalid test
  vectors (each answered with `ERROR` and the expected code), unknown core and extension types, and a `REJECT`
  with an announced operation (#32).
- Conformance suite: block repair after bytes changed in place, a new generation for a shorter file, rejects for
  another operation and a wrong role, and five messages each way through a link that breaks. 22 scenarios in total
  (#32).

### Changed
- Specification: normative wording with BCP 14 key words (MUST, SHOULD, MAY) for the wire format (§14), media
  format 1 (§8.6) and the new §14.10 "Required behaviour of peers". No change of behaviour or wire format (#31).

### Fixed
- A participant now answers a bad frame from the hub with `ERROR` before closing the connection (spec 14.2), as
  the hub already did. Before, it only closed. Found by the conformance suite.

## [0.1.3] - 2026-11-07

First release from the `NULLZEIT-net` organisation. Wire format unchanged (`PROTOCOL_VERSION` 1).

### Added
- Announced operation (spec 14.5): `Hub(..., announce_operation=True, operation_name=...)` names its operation in
  the `REJECT` for a participant of another operation (optional keys `operation`, `operation_name`). The
  participant exposes them as `rejected.operation` and `rejected.operation_name` and never switches on its own,
  so an application can ask its user and greet again. Off by default; older peers ignore the keys.
- Test vectors for every core frame type and for damaged frames in `docs/vectors/frames.json` (spec 14.6), for
  other implementations; checked by `tests/test_vectors.py`.
- Conformance suite (`conformance/`, #32, proposed): a harness that tests a participant implementation over TCP
  through a small JSON-lines adapter, against the reference hub and the link simulator. It has 7 scenarios:
  streams bit for bit (also with disconnects and a restart), reject, relay, messages exactly once. The Python
  reference adapter passes; `tests/test_conformance.py` runs it in CI.

## [0.1.2] - 2026-11-04

### Added
- Optional TLS (spec 14.1): `Hub(..., ssl=...)` and every participant (`Source`, `Consumer`, `Recipient`) with
  `ssl=...` and `server_hostname=...` take an `ssl.SSLContext` prepared by the application, e.g. for mutual TLS with
  certificates on both sides. Without it nothing changes. The frames are the same with and without TLS.

### Changed
- Messages to the hub itself are told to the hub application again when `on_message` raised or the hub stopped
  before noting them (every `retell_s`, default 10 s, and after a restart); `Hub.untold()` counts them (spec 8.5).

### Fixed
- A message to the hub that came on an offline medium was told to the hub application twice.
- `Source.add_stream` while the source was reading the file sizes of its streams ended the session with
  "dictionary changed size during iteration"; the source reconnected. Found by `test_stream_added_while_running`
  on Windows CI.

## [0.1.1] - 2026-11-04

First release on PyPI (`pip install rope-protocol`). No change to the code or the wire protocol.

### Added
- Release workflow: build, check and publish with PyPI trusted publishing; TestPyPI first, PyPI only
  after the maintainer's approval.

### Changed
- Package metadata: licence as SPDX expression, development status alpha, links to changelog and issues.
- README: absolute links (the page is also shown on PyPI), installation from PyPI.

## [0.1.0] - 2026-11-02

First release (tag `v0.1.0`), wire protocol version 1. Development started on 2026-10-19.

### Added
- Wire format, default port 47310.
- Resumable streams from a source to the hub: growing files over links that break, no restart after an
  interruption. Data is acknowledged only once it is safely on disk; the final check over the whole file is
  bit-exact. A source can add a stream while it is running (`Source.add_stream`).
- Block repair after a failed final check: only the changed parts are sent again.
- Relay of streams from the hub to consumers; participant list with names and a stream selection per consumer.
- Messages with custody and a delivery report to the sender; messages addressed to the hub reach the hub application
  (`Hub(on_message=...)`).
- Offline media (e.g. a USB stick) as a second path that can be mixed with the network, including block repair.
- Heartbeat and timeout of the hub apply to sending as well as to receiving.
- `stop()` waits for disk writes that are still running.
- Status output for operators (`rope_protocol.status`).
- Specification (`docs/spec.md`) including security considerations: protection (encryption, authentication) is the
  job of the layers around ROPE.
- Test bench: link simulator for lossy and interrupted links, a fault at every step of the procedure, a restart of
  participant or hub at every step, a hard kill of the hub process, and a soak test over many random seeds. It found
  several real defects before the release; each is covered by a test that fails without the fix.

[Unreleased]: https://github.com/NULLZEIT-net/rope/compare/v0.1.4...HEAD
[0.1.4]: https://github.com/NULLZEIT-net/rope/compare/v0.1.3...v0.1.4
[0.1.3]: https://github.com/NULLZEIT-net/rope/compare/v0.1.2...v0.1.3
[0.1.2]: https://github.com/NULLZEIT-net/rope/compare/v0.1.1...v0.1.2
[0.1.1]: https://github.com/NULLZEIT-net/rope/compare/v0.1.0...v0.1.1
[0.1.0]: https://github.com/NULLZEIT-net/rope/releases/tag/v0.1.0
