# Formal model of the protocol (TLA+)

The protocol's design – not its code – written in [TLA+](https://lamport.azurewebsites.net/tla/tla.html) and checked
with the model checker TLC. TLC explores **every reachable state** of a model: every order of frames, sticks,
disconnects and crashes within the model's bounds. Where a test finds an error by chance, the model checker finds it
in any order of events.

Status: **proposed** (2026-11-10). The models describe spec 1.0 as written; a finding goes to the spec first.

**Results: [RESULTS.md](RESULTS.md)** – every check with its numbers, and the mutation checks.

## Models

| Model | What it covers | Checked properties |
|---|---|---|
| `ROPEStream.tla` | One stream from a source to the hub (spec 8.2–8.4, 8.6, 9, 14.5, 14.10): a growing file, segments within a window, store only at the committed offset, acknowledge only what is stored, gaps answered with `RESEND`, resume from `WELCOME.have` after disconnects and crashes of either side, offline media at the same time (bundles from what the hub acknowledged, imported any number of times, receipts back by stick), final check | bit for bit at the hub; the hub never holds more than the source; nothing acknowledged that is not stored; a verified stream is the whole file; nothing stored is lost or changed; **despite breaks, the source learns that the whole file arrived** |
| `ROPEMessages.tla` | Messages with custody (spec 8.5, 8.6, 14.10): sender, hub and recipient over the network **and** offline media at the same time; resend after reconnects, duplicates by id, telling the application, delivery reports; crashes of the recipient and the hub | custody chain (nobody holds or reports what the previous holder did not have); **told at most once**, plus once per crash between telling and storing the flag (the documented case of spec 8.5); nothing in custody is lost; **every message is told and its delivery reported** |

Checked configurations:

| Configuration | Bounds |
|---|---|
| `ROPEStream.cfg` | a file of up to 3 bytes, a window of 2, up to 2 breaks, network and sticks |
| `ROPEMessages.cfg` | one message, network and sticks, up to 3 breaks |
| `ROPEMessagesTwo.cfg` | two messages, network only, up to 2 breaks |

Small bounds are the usual practice: most protocol errors show with two or three items and a few breaks. Larger
bounds were tried and need far more time than a laptop gives a routine check (a file of 4 bytes with 3 breaks, or
two messages with sticks, ran for more than 10 minutes without finishing).

## Mutation checks: does the model see errors?

A model that never fails may simply be too weak. `check.py --mutations` therefore breaks one rule of the design at a
time on purpose – the hub writes at the wrong offset, acknowledges too much, the source resumes from the wrong place,
the recipient forgets what it told, the hub acknowledges without custody, and others – and requires TLC to report each
one. All of them are found (RESULTS.md).

This check already paid off: the first version of `ROPEStream` had no offline media. In it, segments never arrived as
duplicates or beyond a gap, and two mutations – writing without checking the committed offset, and acknowledging a
duplicate as one byte more – were **not** found. With sticks running at the same time as the network, as the spec
allows, both are found.

## What a model does and does not prove

- It proves the **design**: the rules of the specification lead to the stated properties in every order of events
  within the bounds.
- It does not prove the **code** of the Python reference or of rope-rs; tests and the conformance suite connect code
  and specification.
- It abstracts: one byte per segment, one stream, a stick as a set of frames or byte ranges that can be imported at
  any time. The file system is assumed to keep what was flushed (spec 14.10 rule 1).
- Not modelled yet: block repair and new generations (spec 14.7), relay to several consumers, the participant
  list, and the handover of the lead in SONDE Transfer (an application on top of ROPE).

## Run

```
python docs/model/check.py                          # every configuration; exit code 0 if all pass
python docs/model/check.py --mutations              # and every mutation must be found
python docs/model/check.py --mutations --record     # and write RESULTS.md
```

Needs Java 11 or newer and `tla2tools.jar` of TLA+ release v1.7.4 (https://github.com/tlaplus/tlaplus/releases,
SHA-256 in `check.py`), given in the environment variable `TLA2TOOLS` or placed next to `check.py` (it is not part
of the repository).

**When:** not on every change. The models are checked from time to time, in particular when the behaviour described
in the spec changes – locally with the command above, or in CI by starting the workflow `Model` by hand
(`.github/workflows/model.yml`, same command). `RESULTS.md` is then written again.
