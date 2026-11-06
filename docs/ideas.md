# Ideas

Ideas that are not planned yet. Planned work goes to `TASKS.md`; rejected ideas stay here with the reason, so they
are not proposed again.

## Open
- Discovery of the hub by broadcast on the local network (spec 8.1, optional).
- Standby hub that takes over when the primary hub fails.
- Bandwidth limit per participant, configurable in the participant list.
- **Implementations in other languages** (2026-11-06, maintainer): Rust, Java/Kotlin, Node.js and Ada, once ROPE has
  reached a stable state. Two independent implementations that interoperate are the real test of the spec.
  - Prerequisites:
    1. Spec 1.0, with nothing "proposed" left in the wire format.
    2. A **language-independent conformance suite**: a harness that tests any implementation over TCP, as hub and as
       participant, using the test vectors (14.6) and the link simulator for faults.
    3. Field experience.
  - Suggested scope: participant roles first, while the hub stays the Python reference.
  - Suggested order: Rust, then Java/Kotlin (Android), then Node.js.
  - Ada/SPARK: the core only (frames, checksums, resume logic) with formal proofs that no data is lost or duplicated.
  - Each port needs its own dependency rule (e.g. zlib is not in every standard library).
  - Repositories next to `rope` in the same organisation.

## Rejected
_(none yet)_
