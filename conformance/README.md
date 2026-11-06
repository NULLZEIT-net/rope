# Conformance suite

A language-independent check that a ROPE implementation speaks the protocol of `docs/spec.md` (#32). It tests a
**participant** (source, consumer, recipient) against the Python reference hub, over TCP, with the link simulator
in between. The hub stays the Python reference for now (#33).

Status: **proposed**, first scenarios only (2026-11-06). The interface may still change until spec 1.0 (#31).

## Run

```
python conformance/harness.py                                  # the Python reference adapter
python conformance/harness.py --adapter "path/to/your-adapter" # another implementation
python conformance/harness.py -k source                        # only scenarios whose name contains "source"
```

The exit code is 0 only when every scenario passed. `tests/test_conformance.py` runs the suite against the Python
reference in CI.

## The adapter

An implementation provides a small program, the **adapter**:
- It reads one JSON object per line on stdin and answers each with exactly one JSON object per line on stdout.
- It flushes after every line.
- Logging goes to stderr only.
- It runs one participant at a time.
- Every answer has `"ok": true`, or `"ok": false` with an `"error"` text.

| Command | Keys | Effect |
|---|---|---|
| `start_source` | `participant`, `operation`, `hub` (`host:port`), `files` ({stream: path}), `dir` (state folder) | start a source that follows the files as they grow |
| `start_consumer` | `participant`, `operation`, `hub`, `dir` | start a consumer that stores relayed streams below `dir` |
| `start_recipient` | `participant`, `operation`, `hub`, `dir` | start a recipient (messages only) |
| `add_stream` | `stream`, `path` | source: follow one more file |
| `complete` | `stream` | source: declare the stream complete; the result of the final check appears in `status` |
| `send_message` | `to` (list), `kind`, `body_hex` | store a message; answer carries its `id` |
| `status` | – | answer: `running`, `connected`, `rejected` (`{code, operation}` or null), `checked` ({stream: "ok" / "mismatch"}), `told` ({message id: how often the application was told}), `inbox` ([{id, from, kind, body_hex}]), `streams` (consumer: [{stream, gen, committed, verified, path}]) |
| `stop` | – | stop the participant, keep its state on disk (a later `start_*` with the same `dir` continues) |
| `quit` | – | stop and end the process |

Timeouts: the harness's hub uses a heartbeat of 0.2 s and a timeout of 1 s. The adapter takes these from `WELCOME`
like any participant. It should reconnect quickly, with a back-off of at most about 0.3 s, so that the suite stays fast.

## Scenarios

| Name | Checks |
|---|---|
| `source_basic` | A growing file arrives bit for bit; the final check is `ok`; no second generation. |
| `source_disconnects` | The same, through a slow link with two disconnects and a blackout. |
| `source_restart` | The participant is stopped mid-transfer and started again with the same state: it resumes from the committed offset, bit for bit, no new generation. |
| `reject_unknown` | A participant not on the list is rejected with `unknown_participant` and stores nothing. |
| `consumer_relay` | A relayed stream of a reference source arrives bit for bit and verified. |
| `message_to_adapter` | A message is told to the application exactly once, also after a restart. |
| `message_from_adapter` | A message from the adapter reaches a reference recipient exactly once. |

## Planned
- Frame-level checks with the test vectors (`docs/vectors/frames.json`): a mock peer sends damaged or unknown frames.
- Block repair (§14.7), offline media bundles (§8.6), and the hub role under test.
