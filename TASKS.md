# Tasks – ROPE

Flow: new idea → `docs/ideas.md`; planned → **Backlog**; started → **In progress** (with branch);
finished → **Done** (date, short description; details in `docs/`).

## Ideas inbox
_(see `docs/ideas.md`)_

## Backlog
- [ ] **Heartbeat and timeout for radio links:** configurable at the hub (done 2026-11-02); measure on a real radio
      network before fixing the defaults (spec §9).
- [ ] Resolve the open points listed at the end of `docs/spec.md`.
- [ ] **Spec 1.0** (#31): frozen parts decided 2026-11-07 (§14, media format 1, §14.8, §14.9), MUST/SHOULD
      wording 2026-11-07 (§14.10); still to do: field experience over real radio links, then release.


- [ ] **Offline media:** help for clearing sticks (spec §8.6, open point).
- [ ] **Implementations in other languages** (#33): first #31 spec 1.0 (freeze the wire format) and #32
      language-independent conformance suite; then Rust, Java/Kotlin, Node.js (participant roles first) and an
      Ada/SPARK core with proofs.

## In progress

## Done
- 2026-11-10 Conformance suite: offline media for both roles (#32): in parts, damaged, cut off, block
  repair by stick (source to hub, hub to consumer); 57 scenarios in all.
- 2026-11-10 Conformance suite: the hub role under test (#32), 40 scenarios in all.
- 2026-11-08 Version 0.1.4: `Hub.connections()` and `Hub.last_seen()` (#43); conformance suite with 22
  scenarios (#32); normative wording of the spec (#31); a participant answers a bad frame with `ERROR`.
- 2026-11-07 Version 0.1.3: announced operation (#27), test vectors, conformance suite (#32), spec 1.0 frozen
  parts (#31); first release from the NULLZEIT-net organisation (trusted publishing moved).
- 2026-11-04 Version 0.1.2: optional TLS (spec 14.1, the application passes `ssl.SSLContext` objects); messages to the
  hub told again until the hub application took them (spec 8.5); fixes in `CHANGELOG.md`.
- 2026-11-04 Packaging: `rope-protocol` on PyPI with trusted publishing (`.github/workflows/release.yml`), version 0.1.1, `CHANGELOG.md`.
- 2026-11-02 Version 0.1.0 (first version for an application); `Source.add_stream` adds a stream while running
  (spec §8.2); messages to the hub itself reach the hub application (spec §8.5).
- 2026-11-02 Test bench, rest (spec §13): hub process killed hard twice during a transfer; opt-in soak over many
  seeds of every harsh-link scenario (`ROPE_SOAK_SEEDS=n`).
- 2026-11-02 Status for operators (spec §8.7): `python -m rope_protocol.status <hub folder>`, read-only.
- 2026-11-02 Heartbeat and timeout set by the hub for everyone (spec §9): also used for sending; the timeout must be
  at least twice the heartbeat interval.
- 2026-10-26 Block repair over offline media (#17, spec §8.6): `STREAM_CHECK` + `BLOCK_SUMS` in bundles, repairs
  remembered in `media_repairs.json`.
- 2026-10-26 stop() waits for disk writes (#16, spec §10): writes counted from the hand-over and shielded from
  cancellation.
- 2026-10-26 Restarts at every step (#15, spec §13): participant or hub restarted just before every frame type and
  occurrence.
- 2026-10-26 Test bench: a fault at every step (#14, spec §13): cut, cut mid-frame, duplicate, damage at every frame
  type and occurrence; `ROPE_SOAK=1` for all.
- 2026-10-26 Delivery report (#13, spec §8.5): `DELIVERY` / `DELIVERY_ACK`, over the network and on media.
- 2026-10-26 Participant list (#12, spec §7): names, stream selection per consumer, every participant learns the
  list.
- 2026-10-26 Offline media as a second path (#11, spec §8.6): bundles of wire-format frames on removable media,
  receipts back, mixed with the network.
- 2026-10-26 Messages with custody (#10, spec §8.5): outbox, custody at the hub with state per recipient, inbox with
  "told" flag, recipient role. Open: delivery report to the sender.
- 2026-10-26 Relaying to consumers (#9, spec §7): the hub sends every stored stream on to every consumer, named
  `<source>/<stream>`, with the same sender as the source. Shared building blocks: `sender.py`, `receiver.py`,
  `participant.py`.
- 2026-10-26 Block repair after a mismatch (#8, spec §14.7): `BLOCK_SUMS`, repair segments, new generation only for
  shorter or mostly different files, at most 3 rounds.
- 2026-10-26 Core: streams from one source to the hub (#7): durable store (fsync before ACK, crash cut-back), hub with
  participant list and plain-language REJECT, source following growing files without locks, resume from the
  committed offset, generations, final SHA-256 check; tests over the link simulator.
- 2026-10-26 Wire format draft 1: spec §14 and frame codec `rope_protocol.frames` with test vectors (#5); default
  port 47310 and link simulator `rope_protocol.linksim`, the first part of the test bench (#6).
- 2026-10-19 Repository created: specification draft 0, licence, contribution guidelines, CI (pyflakes + pytest on
  Windows and Linux), package skeleton with a standard-library-only check.
