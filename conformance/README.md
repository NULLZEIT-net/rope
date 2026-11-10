# Conformance suite

A language-independent check that a ROPE implementation speaks the protocol of `docs/spec.md` (#32), over TCP, with
the link simulator in between. It tests both roles:
- a **participant** (source, consumer, recipient) against the Python reference hub;
- a **hub** against Python reference participants (since 2026-11-10).

Status: **proposed**, first scenarios only (2026-11-06). The interface may still change until spec 1.0 (#31).

## Run

```
python conformance/harness.py                                  # the Python reference adapter
python conformance/harness.py --adapter "path/to/your-adapter" # another implementation
python conformance/harness.py -k source                        # only scenarios whose name contains "source"
python conformance/harness.py -k hub_                          # only the hub role
```

The exit code is 0 only when every scenario passed. `tests/test_conformance.py` runs the suite against the Python
reference in CI.

## The adapter

An implementation provides a small program, the **adapter**:
- It reads one JSON object per line on stdin and answers each with exactly one JSON object per line on stdout.
- It flushes after every line.
- Logging goes to stderr only.
- It runs one participant or one hub at a time.
- An implementation that offers only one role answers the commands of the other role with `"ok": false`; those
  scenarios then fail, and the report shows which role is covered.
- Every answer has `"ok": true`, or `"ok": false` with an `"error"` text.

| Command | Keys | Effect |
|---|---|---|
| `start_source` | `participant`, `operation`, `hub` (`host:port`), `files` ({stream: path}), `dir` (state folder) | start a source that follows the files as they grow |
| `start_consumer` | `participant`, `operation`, `hub`, `dir` | start a consumer that stores relayed streams below `dir` |
| `start_recipient` | `participant`, `operation`, `hub`, `dir` | start a recipient (messages only) |
| `start_hub` | `operation`, `participants` ({identifier: role}), `dir` (state folder), `port` (0 = any free port), `heartbeat_s`, `timeout_s` | start a hub on 127.0.0.1; the answer carries the `port`. Messages to the hub (`to` contains `hub`) are told to its application. A later `start_hub` with the same `dir` and `port` continues |
| `add_stream` | `stream`, `path` | source: follow one more file |
| `complete` | `stream` | source: declare the stream complete; the result of the final check appears in `status` |
| `send_message` | `to` (list), `kind`, `body_hex` | store a message; answer carries its `id` |
| `status` | – | answer: `running`, `connected`, `rejected` (`{code, operation}` or null), `checked` ({stream: "ok" / "mismatch"}), `told` ({message id: how often the application was told}), `inbox` ([{id, from, kind, body_hex}]), `streams` (consumer: [{stream, gen, committed, verified, path}]) |
| `status` of a hub | – | answer: `running`, `connected` (any session), `sessions` ([identifier]), `checked` ({"source/stream": result of the final check}), `told`, `inbox` (messages told to the hub), `streams` ([{participant, stream, gen, committed, complete, verified, path}], `path`: the stored bytes) |
| `stop` | – | stop the participant or hub, keep its state on disk (a later `start_*` with the same `dir` continues) |
| `quit` | – | stop and end the process |

The harness reads answers of up to 64 MiB per line, because `status` carries the message bodies.

Timeouts: the harness's hub uses a heartbeat of 0.2 s and a timeout of 1 s. The adapter takes these from `WELCOME`
like any participant. It should reconnect quickly, with a back-off of at most about 0.3 s, so that the suite stays fast.

## Scenarios

| Name | Checks |
|---|---|
| `source_basic` | A growing file arrives bit for bit; the final check is `ok`; no second generation. |
| `source_disconnects` | The same, through a slow link with two disconnects and a blackout. |
| `source_restart` | The participant is stopped mid-transfer and started again with the same state: it resumes from the committed offset, bit for bit, no new generation. |
| `source_repair` | Bytes changed in place after sending (a header at the end of a recording) are fixed by the block repair: final check `ok`, the hub holds the changed file, no new generation (spec 14.7). |
| `source_new_generation` | A file that became shorter is sent as generation 2; generation 1 at the hub stays unchanged (spec 14.4). |
| `reject_unknown` | A participant not on the list is rejected with `unknown_participant` and stores nothing. |
| `reject_wrong_operation`, `reject_role` | The same for another operation (`wrong_operation`) and a role that does not match the list (`role`), spec 14.10. |
| `consumer_relay` | A relayed stream of a reference source arrives bit for bit and verified. |
| `message_to_adapter` | A message is told to the application exactly once, also after a restart. |
| `message_from_adapter` | A message from the adapter reaches a reference recipient exactly once. |
| `messages_to_adapter_disconnects`, `messages_from_adapter_disconnects` | Five messages each way through a slow link with two disconnects and a blackout: each told exactly once, content unchanged. |
| `frame_hello` | The greeting is a valid `HELLO` that offers protocol version 1 (frame-level, scripted hub). |
| `frame_bad_*` | One per invalid test vector (`docs/vectors/frames.json`): the participant answers `ERROR` with the expected code and closes the connection (spec 14.2). |
| `frame_unknown_core_type` | An unknown core type is answered with `ERROR unknown_type`. |
| `frame_extension_ignored` | An unknown extension frame (0x80+) is ignored; the session goes on. |
| `frame_reject_announced` | A `REJECT` with the announced operation (spec 14.5) reaches the application. |

The `frame_*` scenarios run against a **scripted hub** in the harness, which sends exact bytes, so they also test
how an implementation handles frames the reference hub would never send.

### Hub role

| Name | Checks |
|---|---|
| `hub_from_source` | A growing file of a reference source arrives at the hub bit for bit; final check `ok` at the source and reported to the hub's application; no second generation. |
| `hub_from_source_disconnects` | The same, through a slow link with two disconnects and a blackout. |
| `hub_restart` | The hub is stopped mid-transfer and started again on the same state: the source resumes, bit for bit, no new generation. |
| `hub_repair` | Bytes changed in place at the source after sending are fixed by the block repair at the hub (spec 14.7). |
| `hub_relay` | The stream of a reference source reaches a reference consumer through the hub, verified (spec 8.3). |
| `hub_messages` | Five messages between two reference recipients through a breaking link: each told exactly once, and the sender's delivery report names the recipient (spec 8.5). |
| `hub_message_to_hub` | A message addressed to the hub is told to its application exactly once, also across a hub restart. |
| `hub_reject_unknown`, `hub_reject_wrong_operation`, `hub_reject_role` | Greetings that do not match the participant list are rejected with the right code; nothing is stored (spec 14.10). |
| `hub_frame_first_not_hello` | A connection that starts with another frame than `HELLO` is answered with `ERROR bad_frame` and closed. |
| `hub_frame_bad_*` | One per invalid test vector, sent after the `WELCOME`: `ERROR` with the expected code, connection closed. |
| `hub_frame_unknown_core_type`, `hub_frame_extension_ignored` | As for the participant: unknown core type means `ERROR unknown_type`, an extension frame is ignored. |

The `hub_frame_*` scenarios use a **scripted participant** that connects to the hub directly, without the link
simulator.

## Planned
- Offline media bundles (§8.6): new adapter commands to export and import a bundle, for both roles.
