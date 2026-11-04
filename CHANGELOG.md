# Changelog

All notable changes to ROPE (`rope-protocol`) are listed here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/); versions follow [Semantic Versioning](https://semver.org/).
The package version is `rope_protocol.__version__`; the wire protocol has its own number (`PROTOCOL_VERSION`, spec
14.5), which changes only on incompatible changes of the wire format.

## [Unreleased]

### Added
- Optional TLS (spec 14.1): `Hub(..., ssl=...)` and every participant (`Source`, `Consumer`, `Recipient`) with
  `ssl=...` and `server_hostname=...` take an `ssl.SSLContext` prepared by the application, e.g. for mutual TLS with
  certificates on both sides. Without it nothing changes. The frames are the same with and without TLS.

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

[Unreleased]: https://github.com/d-fankhauser/rope/compare/v0.1.1...HEAD
[0.1.1]: https://github.com/d-fankhauser/rope/compare/v0.1.0...v0.1.1
[0.1.0]: https://github.com/d-fankhauser/rope/releases/tag/v0.1.0
