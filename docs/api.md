# ROPE – Python API

How to use the reference implementation (`rope-protocol`, import `rope_protocol`) in an application. The protocol
itself is described in the [specification](spec.md); this page covers the classes, their options and callbacks.

Everything runs in **asyncio**. Participants and the hub are started from inside a running event loop. Callbacks
(`on_written`, `on_checked`, `on_message`, …) are called **in that event loop**: keep them short, hand longer work to a
thread or a task.

## Contents

- [Quick start](#quick-start)
- [Roles](#roles)
- [Hub](#hub)
- [Common to all participants](#common-to-all-participants)
- [Source](#source)
- [Consumer](#consumer)
- [Recipient](#recipient)
- [Messages](#messages)
- [Offline media](#offline-media)
- [Participant list](#participant-list)
- [TLS](#tls)
- [Status for operators](#status-for-operators)
- [What is internal](#what-is-internal)

## Quick start

A hub, a source that sends one file, a consumer that receives it and a recipient that gets a message. This example
is run as written (temporary folders, local address).

```python
import asyncio, os, tempfile

from rope_protocol.consumer import Consumer
from rope_protocol.hub import Hub
from rope_protocol.recipient import Recipient
from rope_protocol.source import Source

OPERATION = "exercise-1"          # all participants of one operation use the same identifier


async def main(base):
    data = os.path.join(base, "recording.bin")
    with open(data, "wb") as f:
        f.write(os.urandom(300_000))

    hub = Hub(os.path.join(base, "hub"), {"01": "source", "50": "consumer", "60": "recipient"},
              OPERATION, host="127.0.0.1", port=47399)
    await hub.start()

    done = asyncio.Event()
    consumer = Consumer("50", OPERATION, "127.0.0.1", os.path.join(base, "consumer"), hub_port=47399,
                        on_checked=lambda stream, gen, result, path: done.set())
    recipient = Recipient("60", OPERATION, "127.0.0.1", os.path.join(base, "recipient"), hub_port=47399,
                          on_message=lambda meta, body: print("message", meta["kind"], body))
    source = Source("01", OPERATION, "127.0.0.1", {"rec-1": data}, os.path.join(base, "source"), hub_port=47399)
    for p in (consumer, recipient, source):
        p.start()

    source.send_message(["60"], "note", b"hello")
    source.complete("rec-1")                          # the file will not grow any more: final check
    print("final check at the source:", await source.wait_checked("rec-1", timeout=30))
    await asyncio.wait_for(done.wait(), 30)
    print(consumer.streams())
    await asyncio.sleep(1)                            # let the message arrive before stopping

    for p in (source, consumer, recipient):
        await p.stop()
    await hub.stop()


with tempfile.TemporaryDirectory() as base:
    asyncio.run(main(base))
```

Output: the message `note b'hello'`, `final check at the source: ok` and the stream `01/rec-1` with
`verified: 'ok'` at the consumer.

## Roles

| Role | Class | Does |
|---|---|---|
| hub | `rope_protocol.hub.Hub` | waits for connections, stores the sources' streams, relays them to consumers, takes custody of messages (spec 7, 8) |
| source | `rope_protocol.source.Source` | sends growing files, resumes after every interruption (spec 8.2, 9, 10) |
| consumer | `rope_protocol.consumer.Consumer` | receives the relayed streams of all sources (or a selection, see [participant list](#participant-list)) |
| recipient | `rope_protocol.recipient.Recipient` | exchanges messages only, receives no streams (spec 8.5) |

Every participant can send and receive [messages](#messages) and use [offline media](#offline-media).

## Hub

```python
Hub(root, participants, operation, hub_id="hub", host="127.0.0.1", port=DEFAULT_PORT, heartbeat_s=2.0,
    timeout_s=10.0, on_stream_checked=None, block_size=BLOCK_SIZE, segment_bytes=256 * 1024, window=8,
    poll_s=0.5, zlib_level=1, hub_name=None, on_message=None, ssl=None, retell_s=10.0,
    announce_operation=False, operation_name=None)
```

| Option | Meaning |
|---|---|
| `root` | Folder for everything the hub stores (streams, messages, state). Survives restarts: a restarted hub continues where it was. |
| `participants` | The [participant list](#participant-list): `{identifier: role}` or `{identifier: {"role", "name", "streams"}}`. `ValueError` with a plain-language reason if invalid. |
| `operation` | Identifier of the operation. Participants with another one are rejected (spec 14.5). |
| `hub_id`, `hub_name` | The hub's identifier (as a message recipient and in bundles) and its name for people. |
| `host`, `port` | Address to listen on. `rope_protocol.DEFAULT_PORT` is 47310 (spec 14.1); applications must allow changing it. Use `"0.0.0.0"` to accept connections from other computers. |
| `heartbeat_s`, `timeout_s` | Heartbeat interval and the time without any frame after which a session is closed (spec 9). |
| `on_stream_checked(participant, stream, gen, result, path)` | After the final check of a source's stream (spec 8.4); `result` is `"ok"` or `"mismatch"`. |
| `on_message(meta, body)` | Once per new message addressed to the hub itself. |
| `block_size`, `segment_bytes`, `window`, `zlib_level`, `poll_s` | Tuning of block repair, segment size, segments in flight, compression and polling (spec 14.8 recommends values). |
| `retell_s` | How often the hub reminds the application of messages it has not taken yet. |
| `ssl` | An `ssl.SSLContext` for the server side, see [TLS](#tls). |
| `announce_operation`, `operation_name` | Off by default. When on, a participant with a wrong operation learns the hub's operation (and its name) in the rejection, so the application can offer to join it (spec 14.5). Turn on only in closed networks or with TLS (spec 11). |

| Method | Returns |
|---|---|
| `await start()`, `await stop()` | Starts listening; stops and waits until everything is written. |
| `connections()` | Participants with a session right now: `{identifier: {"role", "since", "last_heard_s", "address"}}`. `last_heard_s` uses the monotonic clock, so a changed computer clock does not affect it. |
| `last_seen()` | `{identifier: wall-clock ms}` of participants whose session ended since the hub started and who have not come back. |
| `participant_list()` | `[{participant, name, role}]` as every participant learns it, the hub first. |
| `receives(participant, stream)` | Whether a consumer receives the relayed stream `<source>/<stream>`. |
| `message_status(msg_id)` | `{pending, delivered, unknown}` of a message the hub holds, or `None`. |
| `untold()` | Number of messages to the hub the application has not taken yet (for a status display). |
| `await import_media(medium)`, `await export_media(medium, participant, max_bytes=None)` | See [offline media](#offline-media). |

`rope_protocol.hub.relayed_name(source, stream)` builds the name `<source>/<stream>` under which a consumer receives a
source's stream; streams of different sources never mix.

## Common to all participants

Source, consumer and recipient share these options and methods (`rope_protocol.participant.Participant`):

| Option | Meaning |
|---|---|
| `participant` | Own identifier, as in the hub's participant list. |
| `operation` | Identifier of the operation, as at the hub. |
| `hub_host`, `hub_port` | Address of the hub. |
| `timeout_s` | Time without any frame from the hub after which the session is closed and a new one starts. |
| `backoff` | `(first, maximum)` seconds between reconnection attempts. The participant retries forever until `stop()`. |
| `on_message(meta, body)` | Once per new message for this participant. |
| `on_delivery(msg_id, report)` | Once per new delivery report of a message sent from here; `report` is `{delivered, pending, unknown}`. |
| `poll_s` | Polling interval for local changes (new messages to send, growing files). |
| `ssl`, `server_hostname` | Client side of [TLS](#tls). |

| Method / attribute | Meaning |
|---|---|
| `start()` | Starts the connection loop as a task in the running event loop; returns the participant. |
| `await stop()` | Stops and waits until everything is written. |
| `await run()` | The connection loop itself, for applications that manage the task themselves. |
| `connected` | `asyncio.Event`, set while a session with the hub is active. |
| `rejected` | The last `rope_protocol.participant.Rejected` (`code`, `text` in plain language, and with `announce_operation` also `operation`, `operation_name`), or `None`. A rejected participant keeps retrying at the maximum back-off; it never switches the operation on its own. |
| `send_message`, `outbox`, `inbox`, `message_body` | See [messages](#messages). |
| `participant_list()` | `[{participant, name, role}]` of the operation as last learnt from the hub (network or bundle); kept on disk, so it is known after a restart without network. |
| `export_media`, `import_media` | See [offline media](#offline-media). |

## Source

```python
Source(participant, operation, hub_host, streams, state_dir, hub_port=DEFAULT_PORT, segment_bytes=256 * 1024,
       window=8, poll_s=0.5, timeout_s=10.0, backoff=(1.0, 10.0), zlib_level=1, on_message=None,
       on_delivery=None, ssl=None, server_hostname=None)
```

- `streams`: `{stream name: file path}`. Files are only **read** – opened briefly, read, closed, no locks – so the
  program that writes them is never disturbed. A file may grow while it is sent.
- `state_dir`: where the source keeps what the hub has confirmed and its mailbox. Keep it across restarts: the source
  then continues where the hub left off instead of starting again.
- `add_stream(name, path)`: send one more file from now on (e.g. a new recording). Call it in the event loop (from
  another thread: `loop.call_soon_threadsafe`). A known name continues where the hub left off; returns `True` if the
  stream is new.
- `complete(name)`: the application declares the file finished (for example unchanged for a while); the source sends
  the final check.
- `await wait_checked(name, timeout=None)`: result of the final check of the current generation, `"ok"` or
  `"mismatch"`. On a mismatch the source repairs only the differing blocks (spec 14.7).
- If a file becomes shorter or most of its blocks change, a new **generation** starts; the old one is kept at the
  receivers, never overwritten (spec 14.4).

## Consumer

```python
Consumer(participant, operation, hub_host, root, hub_port=DEFAULT_PORT, timeout_s=10.0, backoff=(1.0, 10.0),
         block_size=BLOCK_SIZE, on_written=None, on_checked=None, on_message=None, on_delivery=None, ssl=None,
         server_hostname=None)
```

- `root`: folder for the received streams and the mailbox.
- `on_written(stream, gen, committed)`: after every durable write; bytes up to `committed` may be read now.
- `on_checked(stream, gen, result, path)`: after every final check; with `result == "ok"` the file at `path` is
  complete and verified.
- `streams()`: everything received so far, `[{stream, gen, committed, complete, verified, path}]`.
- `received(stream, gen=1)`: the stored stream (`path`, `committed`, `verified`).
- Stream names are `<source>/<stream>`. Read a growing stream from `path` only up to `committed`.

## Recipient

```python
Recipient(participant, operation, hub_host, root, hub_port=DEFAULT_PORT, timeout_s=10.0, backoff=(1.0, 10.0),
          on_message=None, poll_s=0.5, on_delivery=None, ssl=None, server_hostname=None)
```

`root` is the folder for the mailbox. A recipient receives no streams; everything else is as for every participant.

## Messages

Messages are small (body at most 1 MiB, spec 14), stored durably and delivered **exactly once** to each recipient, also
when the recipient is offline at the time (the hub keeps custody, spec 8.5). ROPE gives no ordering guarantee between
messages.

| Call | Meaning |
|---|---|
| `send_message(to, kind, body)` | Store a message for the identifiers in `to` (a list) and return its id. It leaves with the next connection or the next bundle. `kind` is a short name chosen by the application; `body` is bytes. |
| `outbox()` | `[{id, to, kind, t, at_hub, report}]` of the messages sent from here; `report` is the hub's latest delivery report or `None`. A message has reached everybody when `report["pending"]` is empty. |
| `inbox()` | `[{id, from, to, t, kind}]` of the received messages, oldest first. |
| `message_body(msg_id)` | The body as bytes. |

`on_message(meta, body)` is called once per new message. To send to the hub's own application, address the hub's
identifier (`hub_id`); the hub calls its `on_message`.

## Offline media

When there is no network, the same data travels in **bundles** on a folder – typically a USB stick (spec 8.6). Network
and media may be mixed freely; nothing is stored twice.

| Call | Meaning |
|---|---|
| `await participant.export_media(medium, max_bytes=None)` | Writes a bundle for the hub: messages not yet at the hub, receipts, and what the role adds (a source its streams from what the hub acknowledged, a consumer what it holds). Returns an `ExportReport`. |
| `await participant.import_media(medium)` | Reads every bundle the hub wrote for this participant, oldest first. Returns a list of `ImportReport`. |
| `await hub.import_media(medium)` | Reads every bundle addressed to the hub, as if it had arrived over the network. |
| `await hub.export_media(medium, participant, max_bytes=None)` | Writes a bundle for one participant. |

Importing a bundle again changes nothing. Bundles are addressed by the hub's identifier, which each participant learns
from the hub's greeting.

- `ExportReport` (`rope_protocol.media`): `path`, `bytes`, `segments`, `messages`, `stream_bytes`, `repair_requests`,
  `repair_bytes`, and `complete` – `False` if `max_bytes` stopped it before everything fitted (the rest goes with the
  next bundle).
- `ImportReport`: `path`, `sender`, `created`, `new_bytes`, `written`, `checked`, `messages`, `acks`, and `problems` –
  plain-language sentences for the operator; empty means everything was read and accepted or already there.

Bundles are not encrypted (spec 11); treat the medium like the data on it.

## Participant list

The hub is configured with a list of the participants of the operation (spec 7, `rope_protocol.roster`):

```python
{
    "01": "source",
    "02": {"role": "source", "name": "Boat 2"},
    "50": {"role": "consumer", "name": "Tablet", "streams": ["01/*"]},
    "60": "recipient",
}
```

- `role`: `source`, `consumer` or `recipient`. Only listed identifiers with the right role are accepted.
- `name`: plain language for people (default: the identifier).
- `streams` (consumers only): patterns for the relayed names `<source>/<stream>`; `*` matches any characters
  including `/`, `?` one character, case matters. Default: every stream.

Every participant learns identifiers, names and roles (not the stream selection) and can show them with
`participant_list()`. The list prevents mix-ups, not attacks (spec 11).

## TLS

ROPE has no encryption of its own (spec 11). When the network is not closed, wrap the connection in TLS (spec 14.1):

```python
import ssl

server = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
server.minimum_version = ssl.TLSVersion.TLSv1_2
server.load_cert_chain("hub.pem", "hub.key")
server.load_verify_locations("ca.pem")
server.verify_mode = ssl.CERT_REQUIRED            # participants must present a certificate as well

hub = Hub(root, participants, operation, host="0.0.0.0", ssl=server)

client = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
client.minimum_version = ssl.TLSVersion.TLSv1_2
client.load_cert_chain("source.pem", "source.key")
client.load_verify_locations("ca.pem")

source = Source("01", operation, "hub.example.org", streams, state_dir, ssl=client)
```

`server_hostname` sets the name checked against the hub's certificate (default: `hub_host`). The frames inside are
unchanged; all participants of an operation must use the same setting.

## Status for operators

`rope_protocol.status` reads a hub's folder **without writing** – it can run next to a working hub or on a copy:

```
python -m rope_protocol.status <hub folder>
```

In code: `hub_status(root)` returns `{"streams": [...], "messages": {"total", "pending", "unknown"}}`, `text(status)`
the same as plain lines.

## What is internal

Everything not on this page – the frame codec (`rope_protocol.frames`), the sending and receiving machinery
(`sender`, `receiver`, `channel`, `store`, `messages`, the helper functions in `media`) and `linksim` (the link
simulator for tests, see the README) – may change between versions without notice. Other implementations follow the
[specification](spec.md) and the test vectors, not these modules.
