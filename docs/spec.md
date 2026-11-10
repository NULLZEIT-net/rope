<picture>
  <source media="(prefers-color-scheme: dark)" srcset="images/rope-logo-dark.svg">
  <img alt="ROPE" src="images/rope-logo.svg" height="56">
</picture>

# ROPE – Protocol Specification

**Status: draft 1, on the way to 1.0.** This document describes the goals, model and behaviour of ROPE, and since
draft 1 the wire format ([§14](#14-wire-format)). **Decided 2026-11-07 (#31):** the wire format of §14 and media
format 1 (§8.6) are frozen for spec 1.0 as they stand; values that are a sender's or hub's choice are only
recommended (§14.8); compatibility follows §14.9; the normative wording (MUST/SHOULD) covers §14, §8.6 and the
required behaviour of peers (§14.10). Spec 1.0 is released after field experience; until then only
corrections found there change these parts.

Every statement is marked as one of:

- **decided** – fixed by the maintainer,
- **proposed** – a starting point, may change after measurements or review,
- **assumed** – an estimate that has not been measured yet.

**Conformance language (decided 2026-11-07, #31).** The key words **MUST**, **MUST NOT**, **SHOULD**, **SHOULD
NOT** and **MAY** are to be interpreted as described in BCP 14 ([RFC 2119](https://www.rfc-editor.org/rfc/rfc2119),
[RFC 8174](https://www.rfc-editor.org/rfc/rfc8174)) when, and only when, they appear in all capitals. They are used
in the normative parts only: the wire format (§14), media format 1 (§8.6) and the required behaviour of peers
(§14.10). An implementation conforms when it meets every MUST and MUST NOT there. All other sections explain the
design; where they describe the same behaviour, the normative parts take precedence.

## 1. Purpose

ROPE (*Resumable Offline Protocol for Emergencies*) transfers growing files ("streams") and small messages between a
small, closed group of devices over an unreliable local network – for example radio links or Wi-Fi between a boat,
a command post and a tablet – without any internet access.

The motivating application is the transfer of side-scan sonar recordings while they are being recorded, but the
protocol core knows nothing about sonar (**decided**). An application defines which streams and messages exist.

## 2. Requirements (decided)

1. **Survive interruptions.** If the link drops, e.g. for 0.5 s or for an hour, nothing is lost and nothing restarts
   from zero.
2. **Never block the producer.** The device that records data must never hang or slow down noticeably because of the
   transfer.
3. **Offline.** Works completely without internet; being on the same network does not imply internet access.
4. **More than two devices.** Several participants (e.g. a data source, a hub, a display device) – but always a
   closed, pre-selected group.
5. **No encryption,** as simple as possible (see [Security considerations](#11-security-considerations)).
6. **Built for the future.** Multiple participants, a protocol version and an application-agnostic core are part of
   the design from the start, even if the first deployment has only two participants.

## 3. Why not plain TCP or UDP?

| Problem | TCP alone | UDP alone |
|---|---|---|
| Longer outage | Connection breaks; afterwards TCP does not know where it was. Without extra logic the transfer starts over. | Packets sent during the outage are gone; gaps appear. |
| Acknowledgement | Means "arrived in the network buffer", not "safely on disk". If the receiver crashes, data counted as delivered is missing. | Does not exist. |
| Order, completeness | Guaranteed, but only within one connection. | Not guaranteed. |
| Files and growing files | Unknown – TCP only carries a byte stream. | Same. |
| End-to-end check of a whole file | None. | None. |
| Several devices, store-and-forward | Always exactly two endpoints; nothing waits for a participant that is currently away. | Same. |
| Congestion | Built-in rate control. | None – can saturate a radio link. |
| Hanging | A program waiting on the network stalls unless built otherwise. | Same. |

**Conclusion:** TCP is the better foundation – ordering, retransmission and rate control already exist. ROPE adds what
is missing on top. A UDP-based design would have to rebuild retransmission, ordering and congestion control, which only
pays off with very long round-trip times (space links).

## 4. Prior art

The ideas – not the code or the formats – come from space communication, where links are interrupted routinely:
CCSDS File Delivery Protocol (CFDP) class 2 (acknowledged mode: the receiver reports missing parts, which are resent
selectively) and Delay/Disruption Tolerant Networking (DTN, custody transfer). ESA's Euclid mission, for example,
delivers its files with CFDP class 2 over a K-band link.

Not adopted: the standards themselves. They target dedicated hardware, radio frames and round-trip times of seconds to
minutes. ROPE stays small and manageable and is therefore **not compatible** with CFDP or DTN software (**decided**).

## 5. Design decisions

| Topic | Decision | Reason |
|---|---|---|
| Transport | TCP (**decided**) | Short round-trip times on local radio networks (**assumed**). TCP bridges short dropouts by itself. |
| Own protocol | Yes, as a separate package (**decided**) | TCP cannot resume across connections and does not acknowledge persistence. Existing solutions are too large or need internet. |
| Standards | Adopt ideas, not standards (**decided**) | Small and controllable. |
| Topology | Star with a hub (**decided**) | Simple responsibilities and troubleshooting; every device has exactly one peer. |
| Participants | Only from a list prepared in advance (**decided**) | Prevents mix-ups on the network. Without encryption no protection against intent. |
| Encryption | None (**decided**) | As simple as possible in the field. |
| Dependencies | Python standard library only (**decided**) | Offline installation, small programs, runs on old hardware. |
| Network file shares (SMB etc.) | Not used (**decided**) | Programs hang on file access when the link is unstable. |
| Who connects | Every participant connects to the hub (**decided**) | The hub has a known address; participants may come and go. |
| Licence | Apache-2.0 (**decided**) | Permissive; proprietary applications may use the core. |

## 6. Architecture and terms

Two layers (**decided:** separate package; **proposed:** this split):

```
+--------------------------------------------+
| Application  (defines streams + messages)  |
+--------------------------------------------+
| ROPE core    (resume, custody, delivery)   |
+--------------------------------------------+
| TCP                                        |
+--------------------------------------------+
```

The core does not rebuild what TCP provides. It adds what TCP lacks: resuming across connections, acknowledgement only
after persistence, end-to-end verification, and delivery to participants that are currently unreachable.

**Terms**

- **Participant** – a device of the group with a unique identifier.
- **Hub** – the participant all others connect to; relays streams and messages.
- **Stream** – a sequence of bytes that only grows at the end (an append-only file).
- **Segment** – a piece of a stream with offset, length, checksum and timestamp. The application may choose segment
  boundaries (e.g. at record boundaries).
- **Committed offset** – up to which byte a receiver has stored a stream durably.
- **Message** – a small, self-contained item with a unique identifier (e.g. a task or a note).
- **Custody** – a participant takes over data or a message only once it is stored durably on disk; only then does it
  acknowledge.

## 7. Star topology

All participants connect only to the hub (**decided**). Data and messages between two participants always travel via
the hub.

- **Participant list (proposed):** identifier, name, role and what the participant receives. Anyone not on the list is
  rejected during the greeting with a plain-language reason.
- **Roles (proposed):**
  - *source* – provides streams,
  - *consumer* – receives streams and may send messages,
  - *recipient* – exchanges messages only, receives no streams.
- **Need-to-know:** raw streams only to consumers; messages also to recipients.
- **Several consumers:** a second consumer receives the same streams via the hub.
- **Relaying (proposed, first implementation 2026-10-26):**
  - To a consumer, the hub is a sender exactly as a source is to the hub: same window, resume from the consumer's
    committed offset, final check and block repair (§8.2–8.4, §14.7).
  - A consumer receives every stream of every source of the operation, while the stream still grows.
  - A relayed stream is named `<source>/<stream>`, so that streams of different sources never mix.
  - The hub sends the final check to a consumer only after its own copy passed the check.
  - The hub keeps no delivery state per consumer. The consumer reports what it holds when it greets (`HELLO.have`,
    §14.5), so a restart of the hub or of the consumer loses nothing.
  - Order: streams in name order, each from its committed offset (see open point "catch-up order").
- **Participant list (proposed, first implementation 2026-10-26):**
  - Per participant: identifier, role, a **name** in plain language for the operator (default: the identifier) and,
    for a consumer, a **selection** of streams. Anything else in the list is refused when the hub starts, with a
    plain-language reason.
  - **Selection:** patterns over the relayed names `<source>/<stream>`, e.g. `source-1/*` (all streams of one source)
    or `*/rec-*`. `*` matches any characters including `/`, `?` exactly one; upper and lower case are different on
    every system. Without a selection a consumer receives every stream (as before); an empty selection means none.
    Only consumers have a selection: sources and recipients receive no streams.
  - The selection applies to the network and to media in the same way. The hub checks it whenever it looks for
    streams to send, so a changed list takes effect when the hub restarts with it. A consumer keeps what it already
    holds when its selection becomes narrower; nothing is deleted.
  - **Every participant learns the list** – identifier, name and role of everybody, the hub first with role
    `hub` – in `WELCOME` (`participants`, §14.3) and in every bundle the hub writes (§8.6). An application can thus
    show names and address messages also offline. The participant keeps the newest list it has seen (by the hub's
    time), so an older stick never replaces a newer greeting. The selections stay at the hub: a participant does not
    need to know what others receive.
- **Group size:** a few devices, no open membership (**decided**).
- **Hub down:** all participants keep collecting and send as soon as the hub is back. A standby hub is an open point.

## 8. Procedures

All numbers are **proposed** starting values until measured.

### 8.1 Connect and greet

1. The participant connects to the hub. The address comes from the prepared configuration, optionally discovered by
   broadcast on the local network.
2. It sends its identifier, role, protocol version and an operation identifier (separates independent operations).
3. The hub checks the participant list and the version. On mismatch it replies with a plain-language reason and closes.
4. The hub reports, per stream, its committed offset and, per message, what it already holds. The connection is then
   active.
5. A participant has at most one session. A new greeting from the same participant replaces the old session
   (**decided** with the first implementation). After a radio dropout, the hub often still holds the old, dead
   connection; it must not block the new one.

### 8.2 Sending a stream

- The source sends each stream starting at the reported committed offset.
- Segments hold roughly one second of data, at most 256 KiB (**assumed** suitable), and are compressed individually.
- Every segment carries stream id, offset, raw and compressed length, checksum and timestamp.
- The source keeps only a bounded number of unacknowledged segments in flight, e.g. 8. This bounds memory and backlog.
- The application can add a stream while the source runs (**decided**, `Source.add_stream`): a recording program
  starts new files during an operation. The new stream is sent like the others from the next round on; a name known
  from an earlier run of the source continues where the hub left off.

### 8.3 Acknowledging

- The receiver verifies the checksum, writes the segment at its offset and makes it durable (flush + fsync).
- Only then does it acknowledge with the new committed offset. Duplicate or already present segments are acknowledged
  without writing.
- Gaps cannot arise because sending always starts at the committed offset. If a segment arrives damaged, the receiver
  requests exactly that range again.

### 8.4 Completing a stream

- When the stream is complete (application decides, e.g. file unchanged for 10 s), the source sends a checksum of the
  whole stream. The final size is never smaller than what the source has already sent.
- The receiver compares. On mismatch both sides exchange per-block checksums and only differing blocks are resent
  (§14.7). Bytes the source changed in place, e.g. a header updated at the end of a recording, are fixed this way
  without a full retransfer.
- The stream is then marked complete and verified.

### 8.5 Messages

- Every message has a unique id, sender, recipient(s) and timestamp.
- The sender stores it durably in its outbox. The hub takes custody and acknowledges, then delivers it to each recipient
  individually.
- Each recipient acknowledges after storing it. The hub tracks "delivered" or "pending" per recipient.
- Messages take priority over stream segments.
- A message may be addressed to the **hub itself** (its identifier as recipient, **decided**): it is for the
  application running the hub (`Hub(on_message=...)`); for the delivery report it counts as delivered to the hub.
  Example: a source tells the hub application which device it is.
  **Decided (2026-11-04):** the hub tells its application one message after the other (in its event loop), also with
  many participants. A message counts as told only when `on_message` returns; if it raises, or the hub stops first,
  the message is told again later (every `retell_s`, default 10 s) and after a restart. A restart between telling and
  noting may tell a message twice, so the application treats messages by their id (at least once). `Hub.untold()`
  counts the messages not taken yet. A message from an offline medium is told once (before, twice).
- Duplicates are detected by id and shown only once.

**First implementation (2026-10-26, proposed):**

- **Who:** every role may send and receive messages. A *recipient* differs from the others only in that it
  receives no streams.
- **Sender check:** the hub accepts a message only if `from` is the participant on that connection. Otherwise it
  answers `ERROR` `bad_frame`.
- **Unknown recipients:** recipients not on the participant list are recorded as "unknown" and logged. The
  message is delivered to the known ones.
- **Custody at every step:** a holder writes the body, then the meta, both durably. Only then does it send
  `MESSAGE_ACK`.
  - Until it is acknowledged, a message is sent again after every reconnect.
  - At most 16 unacknowledged messages are in flight per connection.
  - The sender's outbox shows "at the hub" once the hub has taken custody.
- **Delivery report to the sender (proposed, 2026-10-26):**
  - The hub sends the sender a `DELIVERY` frame with the lists `delivered`, `pending` and `unknown`
    (§14.3) whenever another recipient has acknowledged the message.
  - It also sends one at once if there is nobody to wait for: all recipients unknown, or only the sender itself.
    With unknown recipients next to known ones, a first report goes out at once as well, so the sender learns early
    that some recipients do not exist.
  - The sender stores the report durably, then answers `DELIVERY_ACK` with the number of recipients it now knows as
    delivered. The hub keeps that number per message (`reported`) and sends again, after every reconnect, until a
    report with all delivered recipients is acknowledged. A report that is older than the stored one (e.g. from
    an old stick) is acknowledged but not stored.
  - The application is told once per new report (`on_delivery`), with the same "told" flag as for received
    messages: a report stored but not yet told is told when the next session starts. The outbox always holds the
    latest report; the message reached everybody when `pending` is empty.
  - The report is about custody at each recipient, not about a person reading the message.
- **Telling the application:** the inbox records whether the application was told about a message. If the
  connection breaks between storing and telling, a resent copy is a duplicate and would not tell it again. So every
  untold message is told after each received message and when a session starts. The application is told at least
  once; in practice exactly once (it is told twice only if the program stops between telling and recording that).
  Within one run of the program the participant also notes in memory, without a pause after telling, what it told:
  a session that ends while the flag is being written does not lead the next session to tell again (found by the
  test bench, §13).
- **Priority:** messages travel in their own task on the same connection. A message waits behind at most the
  segment being written, not behind the stream backlog. The test bench checks this on a simulated 1 MB/s link
  with a 3 MB file in progress: the message must arrive within 2 s, while the file is still on its way.

### 8.6 Offline media as a second path

Removable media (e.g. a USB stick) can carry the same segments and messages. Import follows the same rules: check the
committed offset, ignore duplicates, report damaged items. Network and media may be mixed.

**Media format 1 (decided for spec 1.0, 2026-11-07, #31):** the bundle layout and content below are normative.
An implementation that supports offline media MUST read and write this format; `bundle.json` carries the format
number, and a reader MUST NOT import a bundle whose `format` it does not know. First implemented 2026-10-26:

- **Bundle:** one export writes one bundle. It holds the frames the exporter would send over the network, in the
  wire format of §14:
  - `SEGMENT`, `STREAM_END` and `MESSAGE`,
  - plus receipts for what it holds from the other side: `ACK` (committed offsets) and `MESSAGE_ACK`.
  - The core decides nothing new for media; only the way the frames travel is different.
- **Who exchanges with whom:** as on the network, always a participant and the hub (star, §7).
  - A participant exports for the hub and imports what the hub exported for it.
  - The hub imports bundles from all participants and exports one bundle per participant.
- **Layout on the medium:** `rope/<operation>/<from>-to-<to>-<created ms>-<random>/`, with the frames in
  `frames-0001.rope`, … and a manifest `bundle.json` (`format`, `operation`, `from`, `to`, `created`, `files`,
  `frames`, `complete`; a bundle from the hub also carries `participants`, §7).
  - A writer SHOULD keep each frames file at most 1 GiB, because many sticks use FAT32 (limit 4 GiB per file).
    A reader MUST accept frames files of any size.
  - A writer MUST write a bundle under a name ending in `.partial` and MUST rename it only when it is complete and
    durable. A reader MUST skip directories ending in `.partial`. A medium pulled out during the export therefore
    never holds a half bundle under a valid name.
  - The protocol implementation MUST NOT delete a bundle from a medium on its own. The application decides when a
    stick is cleared.
- **What a bundle carries:**

  | Direction | Content |
  |---|---|
  | source → hub | streams not yet verified at the hub, from the offset the hub last acknowledged (over the network or by a receipt on a medium; from 0 after a restart of the source); `STREAM_END` once the stream is complete and fully in the bundle |
  | consumer → hub | its committed offsets as `ACK` |
  | hub → source | the hub's committed offsets of that source's streams as `ACK`, so that the next bundle of the source is smaller |
  | hub → consumer | the relayed streams (§7), from the offsets the consumer last reported in a bundle (from 0 if it never did); `STREAM_END` only for streams verified at the hub |
  | everybody, both ways | messages for the addressee not yet in custody there, and `MESSAGE_ACK` for messages received from the addressee |
  | hub → participant | `DELIVERY` reports for the participant's messages it has not acknowledged yet (§8.5) |
  | participant → hub | `DELIVERY_ACK` for every report it holds |

  Order inside a bundle: receipts, then messages, then streams (SHOULD; a reader MUST accept any order). If the
  medium is too small (`max_bytes`), the export MUST stop at a frame boundary and set `complete: false`; the rest
  goes with the next bundle.
- **Import:**
  - Bundles SHOULD be imported oldest first. Importing a bundle again MUST change nothing.
  - Segments MUST be stored as from the network (§14.10): durably, duplicates not written. A segment beyond the
    committed offset is a gap: the rest of that stream in the bundle MUST be skipped and SHOULD be reported; the
    bytes must come first from an earlier bundle or the network.
  - Frames are read one at a time. A frame with a wrong CRC MUST be skipped and SHOULD be reported; its length is
    known, so reading goes on (later segments of that stream then usually meet a gap). A damaged frame header ends
    the reading of its file, because the position of the next frame is lost. A cut-off file SHOULD be reported.
  - A bundle whose manifest cannot be read is reported by every participant that looks at the medium: nobody can
    tell for whom it was.
  - The hub MUST accept only bundles from participants on its list, and only messages written by the bundle's
    sender (§8.5).
  - A received message is told to the application once, also if the same message arrives by medium and by network
    at the same time.
- **Block repair over media (proposed, 2026-10-26):** the same frames as on the network (§14.7), one trip of the
  medium per step.
  1. A receiver whose final check failed (the hub for a source's stream, a consumer for a relayed stream) puts
     `STREAM_CHECK` `mismatch` and the `BLOCK_SUMS` of what it holds into every bundle for the sender, as long as
     the check fails.
  2. The sender keeps a complete request durably (`media_repairs.json`). A request whose block sums arrived only in
     part, e.g. from a damaged bundle, is dropped; the receiver asks again with its next bundle.
  3. The sender's next bundle carries only the differing blocks as `SEGMENT` `repair` and then `STREAM_END` again;
     afterwards it forgets the request. If that bundle is lost, the receiver still fails its check and asks again.
  4. As on the network, a source starts a new generation instead if more than half of the blocks differ. The hub
     repairs a consumer only from its own verified copy.
  - Counting the trips: a header changed after the data left takes three trips to the hub (final check, request,
    repair) and three more to a consumer.
  - A verified stream ignores repair segments, so an old bundle imported again never changes it.
- **Limits of the first implementation:**
  - A `STREAM_END` from a medium never overrides a stream that is already verified: the bundle may be older than a
    repair over the network.
  - A participant's message counts as "at the hub" only after a receipt from the hub (network or medium). Until then
    every export carries it again; the hub ignores the duplicates.
  - The hub keeps what a consumer last reported in a bundle (`media_have.json`). That is state per consumer, but for
    media only. On the network the consumer still reports in `HELLO` (§7).

### 8.7 Status for operators (proposed)

`python -m rope_protocol.status <hub folder>` (`rope_protocol.status.hub_status`) shows what a hub holds, read from
its folder: every stream with participant, name, generation, committed size and whether it is growing, complete or
verified; the number of messages held, how many wait for each recipient, and recipients that are not on the
participant list. It only reads the state files and never writes, so it can run next to a working hub or on a copy.
Not part of the wire format; applications may show the same in their own user interface.

**Live connections (proposed, #43).** A running hub tells its application which participants have a session right
now (`Hub.connections()`: role, session start, seconds since the participant was last heard, peer address) and when
the sessions of the others ended (`Hub.last_seen()`). "Last heard" counts every frame, heartbeats included (§9), and
uses the monotonic clock, so setting the computer's clock does not change it. On a healthy link it stays below
`heartbeat_s`; during a dropout it grows until the session ends at `timeout_s`. No frames are added: the status comes
from traffic that flows anyway. Not part of the wire format.

## 9. Interruptions and resumption

Core idea: the data lives on the source's disk and the receiver knows its committed offset. An interruption costs time,
never data.

Connection states (**proposed**): *disconnected* → *connecting* → *greeting* → *active* → back to *disconnected* on
any failure. Reconnect back-off grows from 1 s to at most 10 s and never gives up. This includes unexpected errors
(bugs): they are logged with their details and end only the current session, never the connection loop
(**decided** 2026-10-26 after the test bench found a case where the loop ended silently).

| Outage | What happens |
|---|---|
| Up to a few seconds, e.g. 0.5 s | TCP retransmits; the connection stays up. The core notices nothing. |
| No sign of life for about 10 s | Connection considered lost (heartbeat every 2 s, **assumed** suitable – **may be too short for radio links**, see note below). Reconnect, greet, continue from the committed offset; unacknowledged segments are resent. |
| Minutes to hours | The source keeps recording; nothing piles up in memory. After reconnecting the backlog is transferred. |
| Device restart | Committed offsets and outbox are on disk; work continues from the last acknowledged point. |

**Note on heartbeat and timeout (open, must not get lost):** The values above (2 s heartbeat, ~10 s until a connection
counts as lost) are assumptions. On directional radio links, longer dropouts are normal – shadowing, movement of a
vessel or vehicle, antenna alignment. A timeout that is too short turns every such dropout into a disconnect with an
unnecessary reconnect and greeting. Therefore heartbeat interval and timeout **must be configurable** and are to be
**measured on real radio links** before defaults are fixed. Losing the TCP connection is harmless for data (resume from
the committed offset), but frequent reconnects cost time and bandwidth.

**Configuration (decided):** the hub is configured with both values and sends them in `WELCOME`; every participant
uses them for its own heartbeat, for receiving **and for sending** (a send that cannot drain within the timeout ends
the session, like silence). The timeout MUST be at least twice the heartbeat interval, so that one lost heartbeat is
never a disconnect; the hub refuses other values at start. The defaults (2 s / 10 s) stay **assumed** until measured.

**Catch-up order (proposed, open):** messages first, then the tail of the currently growing stream (so the consumer is
up to date), then the backlog in order.

## 10. Never block

The producer must never hang because of the transfer (**decided**). Measures (**proposed**):

- **Separate process,** independent of the recording software and of any UI. If it crashes, recording continues; it
  restarts itself (service or scheduled task).
- **Low priority** for CPU and disk I/O.
- **Read-only, no locks:** open files briefly and close them; watch growing files by size every 0.5–1 s.
- **Network never in the read path:** reading, packing and sending are decoupled; all network calls have timeouts. If
  the network hangs, only sending waits.
- **Hard limits** for unacknowledged segments, memory and bandwidth, configurable.
- **Fast compression,** e.g. zlib at a low level (**assumed**; to be measured on target hardware).
- **No in-memory buffer for outages:** the file on disk is the buffer.
- **Receiver likewise:** writing and syncing are decoupled from display and processing.
- **A clean stop (decided 2026-10-26):** writes run in worker threads, and a worker thread goes on after the session
  that started it was cancelled. `stop()` of the hub and of every participant therefore waits until no disk write is
  running any more (at most 5 s, then it reports it). Afterwards a new instance on the same folders - e.g. a hub
  restarted inside the same program with a changed participant list - finds the final state.
- **A write once started always completes:** a cancelled session does not drop a write that is still waiting for a
  worker thread. Otherwise e.g. the "told" flag of a message could get lost and the next session would tell the
  application again.

## 11. Security considerations

ROPE deliberately has **no encryption and no authentication** beyond the participant list (**decided**). It is meant
for closed, physically controlled networks. Anyone on the same network can read the traffic and could impersonate a
participant. Do not use ROPE over the internet or on shared networks without an additional protection layer (e.g. a
VPN). The participant list prevents accidental mix-ups, not attacks.

**No encryption in ROPE does not mean no protection is needed.** Protecting data in transit and the devices themselves
is the job of the layers below and around ROPE (**decided**: ROPE stays simple; these layers are chosen per deployment):

- **Network layer:** a VPN on operating-system level (for example WireGuard) between the participants, or a radio
  system that encrypts its channel. ROPE runs unchanged on top of either; it only needs a TCP connection.
- **Access to the network:** a closed network with its own key (for example WPA2/WPA3 with a strong passphrase), no
  open or shared networks, no port forwarding to the internet.
- **Devices:** current operating system updates, endpoint protection (virus scanner), user accounts without
  administrator rights for daily work, disk encryption where devices can be lost.
- **Announced operation (§14.5):** a hub configured to announce its operation tells its identifier to anyone who
  reaches it with a wrong one. The identifier alone grants nothing (the participant list still decides), but it is
  off by default; turn it on only in closed networks or with TLS (§14.1).
- **Offline media (§8.6):** bundles on removable media are not encrypted either. Treat the media like the data on them
  (keep them with the team, wipe or encrypt them according to the deployment's rules).

What ROPE itself guarantees is **integrity against accidents**, not against attacks: every frame carries a CRC, every
stream is checked with SHA-256 at the end (§14), and only participants from the list are accepted. An attacker on the
same network can still read, replay or forge traffic; that is exactly what the layers above prevent.

## 12. Failure cases

| Case | Detection | Reaction |
|---|---|---|
| Short dropout | none needed | TCP bridges it |
| Dead connection | no heartbeat for about 10 s | disconnect, reconnect, continue from committed offset |
| Damaged segment | checksum mismatch | request that range again, keep the rest |
| Duplicate segment | offset already stored | acknowledge, do not write |
| Whole stream differs | final checksum | compare per-block checksums, resend only differing blocks |
| Source changed bytes in place | final checksum | resend only the differing blocks (§14.7) |
| Source file shortened or replaced | file shorter than before, or most blocks differ at the final check | never overwrite; report in plain language; keep as a new version |
| Unknown participant | not on the list | reject with a plain-language reason |
| Different protocol version | greeting | reject or operate on the common subset, with a plain-language reason |
| Wrong operation | operation identifier | store separately, never mix |
| Receiver disk full | write fails | do not acknowledge, report; source waits |
| Recipient offline | no acknowledgement | hub keeps custody and delivers later |
| Hub offline | no connection | participants keep collecting; offline media as fallback (§8.6) |
| Damaged or cut-off medium | frame CRC, frame count | keep everything before the damage, report the rest |
| Bundle without its predecessor | segment beyond the committed offset | skip that stream in the bundle, report the gap |
| Final check fails after an import | final checksum | the next bundle asks for the differing blocks; the answer brings only those (§8.6) |

## 13. Test bench (proposed)

**Conformance suite (proposed, 2026-11-06):** `conformance/` tests any participant implementation over TCP through
a small adapter (JSON lines on stdin/stdout), against the reference hub and the link simulator. Since 2026-11-10 it
also tests a hub implementation, against reference participants, and offline media (8.6) for both roles. See
`conformance/README.md` for the adapter commands and the scenarios.

**Formal model (proposed, 2026-11-10):** `docs/model/` holds TLA+ models of the design – one stream with resume,
offline media and the final check, and messages with custody over network and media – checked with TLC in every
reachable state within small bounds, plus mutation checks that each broken rule is found. Results:
`docs/model/RESULTS.md`. The models check the design, not the code.

A custom protocol brings custom bugs, so faults are produced in tests rather than discovered in the field. The test
bench runs on Windows and Linux in CI (**decided**):

- drop the connection at every point of the procedure, including mid-segment and mid-greeting,
- delay, throttled bandwidth, packet loss,
- restart of source or hub during a transfer,
- duplicate, damaged and reordered segments,
- offline media and network at the same time.

**Pass criterion of every test:** at the end the stream at the receiver is bit-for-bit identical to the original, and
every message has arrived exactly once.

**Faults at every step** (`tests/framefault.py`, `tests/test_faults.py`, implemented 2026-10-26). A frame-aware
proxy injects exactly one fault at a chosen frame: connection cut before it, cut in the middle of it, the frame sent
twice, the frame damaged, or a restart of the participant on that link or of the hub just before the frame. The scenario uses every part of the protocol – greeting, segments, a header changed in
place (final check, block sums, repair), relaying to a consumer, messages both ways and the delivery report – on the
link of the source and on the link of a consumer.

- A *step* is every occurrence of every frame type in a clean run, in both directions (heartbeats: the first two;
  their number depends on timing). Targeting by type rather than by position makes sure that rare frames such as
  `STREAM_CHECK` are hit.
- The normal test run cuts the connection at every step and tries the other faults at a few steps. Setting
  `ROPE_SOAK=1` runs every fault at every step (several minutes); it belongs before every release.
- A restart stops the program part the way a program ends (tasks cancelled, nothing more written) and starts a new
  one on the same folders.
- **Killed process** (`tests/test_kill.py`, implemented 2026-11-02): the hub runs in its own process and is killed
  hard twice while it receives a stream (no stop, no clean-up, Python buffers lost), then started again on the same
  folder. A power cut of the whole machine, which can also lose what the operating system had not written to disk yet,
  is still not simulated; the store only counts what was flushed and fsynced before the acknowledgement (§8.3).
- **Soak over many seeds** (`tests/test_soak.py`, opt-in): `ROPE_SOAK_SEEDS=n` repeats every scenario over harsh
  links (relay with hub restart, messages, delivery reports, media and network at the same time, repair) with `n`
  different seeds. Like `ROPE_SOAK=1` it belongs before every release.
- A duplicated frame inside one TCP connection does not happen on a real network (TCP removes duplicates). It is
  still tested because it shows how a participant reacts to a frame it did not expect.

**Link simulator** (`rope_protocol.linksim`, implemented). It is a TCP proxy between two participants and behaves like
an unreliable link, per direction:
- bandwidth limit, latency and jitter
- **blackouts:** no data flows, but the connections stay open, as with shadowing on a directional radio link
- **disconnects:** all connections are aborted, followed by an outage

Faults follow a random schedule from a profile (reproducible with a seed) or an exact script for tests. It can also
be run by hand: `python -m rope_protocol.linksim --listen 127.0.0.1:47311 --target 127.0.0.1:47310 --profile radio`.

The profiles are **assumed** and must be replaced by measurements on real links:

| Profile | Bandwidth | Latency | Blackouts | Disconnects |
|---|---|---|---|---|
| `lan` | unlimited | – | – | – |
| `wifi` | 2.5 MB/s | 5 ms + up to 10 ms | every ~2 min, 0.2–2 s | – |
| `radio` | 500 kB/s (~4 Mbit/s) | 10 ms + up to 20 ms | every ~1 min, 0.5–20 s | every ~15 min, down 5–60 s |
| `radio-bad` | 125 kB/s (~1 Mbit/s) | 30 ms + up to 50 ms | every ~20 s, 1–60 s | every ~3 min, down 10–300 s |

Limits of the simulation:
- It acts on the byte stream, not on radio packets. Packet loss and retransmissions inside TCP appear only as delay.
- During an outage, a new connection is accepted by the proxy and waits. On a real link the connection attempt itself
  would wait or fail.

## 14. Wire format

**Decided for spec 1.0 (2026-11-07, #31):** the frame layout, frame types, keys, values, greeting and the frames of
the final check and block repair below. Values marked as recommended in §14.8 are not part of the wire format.
This section is normative (conformance language at the top of this document).

### 14.1 Transport

- ROPE runs over one TCP connection per participant (§5).
- **Default port 47310** (TCP). An implementation MUST let the application choose another port. At the time of choosing
  (2026-10-26) the port was not assigned in the IANA registry, no known software used it, and it lies below the dynamic
  range that operating systems use for outgoing connections (49152 and up). It is not registered with IANA. If the hub
  cannot listen on the port, it SHOULD report this in plain language and name the port; it MUST NOT silently pick
  another one.
- An application MAY wrap the connection in TLS, e.g. with certificates on both sides, when the network is not closed
  (§11). The frames inside are unchanged; the core does not know whether TLS is in use.
  **Decided (2026-11-04):** the hub and every participant take an optional `ssl` argument, an `ssl.SSLContext` the
  application prepares (certificates, trust, verification, minimum version); participants also take
  `server_hostname` for the name checked against the hub's certificate (default: the hub's host). The TLS handshake
  has the same time limit as the connection (`timeout_s`). A failed handshake counts as a lost connection: the
  participant retries with back-off (§9), the hub starts no session. ROPE itself creates no keys or certificates.
- All integers are unsigned and big-endian (network byte order).

### 14.2 Frames

Everything on the connection is a sequence of frames:

| Offset | Size | Field |
|---|---|---|
| 0 | 2 | magic `0x52 0x50` (`RP`) |
| 2 | 1 | protocol version |
| 3 | 1 | frame type |
| 4 | 4 | meta length *M* |
| 8 | 4 | blob length *B* |
| 12 | *M* | **meta:** a JSON object, UTF-8 |
| 12 + *M* | *B* | **blob:** raw bytes (segment data, message body), may be empty |
| 12 + *M* + *B* | 4 | CRC-32 (as in zlib/ISO-HDLC) over all preceding bytes of the frame |

- **Limits:** *M* ≤ 64 KiB and *B* ≤ 1 MiB. A receiver MUST check both lengths **before** reading the rest.
- **Bad frames:** a frame that is too long, has a wrong magic or a wrong CRC, whose meta is not a JSON object, or that
  breaks §14.3 or §14.4 is a bad frame. The receiver MUST send `ERROR` (code as in the test vectors, §14.6) and then
  MUST close the connection; if sending the `ERROR` fails, it MUST close anyway. It MUST NOT act on the bad frame.
  Nothing is acknowledged, so nothing is lost: after reconnecting, the transfer continues from the committed offset
  (§9). The same applies wherever this document says a frame is answered with `ERROR`.
- **Why JSON for meta:** readable in network captures, part of every standard library, and extendable. Receivers MUST
  ignore unknown keys, so a newer participant can add keys without breaking older ones. The cost is about 100–200 bytes
  per segment of up to 256 KiB, below 0.1 %.
- **Meta encoding:** senders SHOULD encode compact (no spaces), with keys sorted and non-ASCII characters as UTF-8.
  Receivers MUST accept any valid JSON object; the rule only makes frames reproducible for test vectors.
- **Why a CRC per frame:** the TCP checksum is weak; the CRC catches damage between the network stack and the
  application. It protects the transfer; stored data is protected separately (segment CRC, stream SHA-256).

### 14.3 Frame types

Types `0x00`–`0x7F` belong to the core. A receiver that does not know a core type MUST treat the frame as a bad
frame (`ERROR` `unknown_type`, §14.2). Types `0x80`–`0xFF` are extensions: a receiver that does not know one MUST
ignore it. A core frame without one of its required keys, or with a value outside §14.4, is a bad frame.

| Type | Name | Direction | Meta (required keys) | Blob |
|---|---|---|---|---|
| `0x01` | `HELLO` | participant → hub | `participant`, `operation`, `role`, `versions`, `t`, `have` | – |
| `0x02` | `WELCOME` | hub → participant | `version`, `hub`, `t`, `t_hello`, `heartbeat_s`, `timeout_s`, `have` | – |
| `0x03` | `REJECT` | hub → participant | `code`, `text` | – |
| `0x04` | `HEARTBEAT` | both | `t` | – |
| `0x05` | `BYE` | both | `reason` | – |
| `0x06` | `ERROR` | both | `code`, `text` | – |
| `0x10` | `SEGMENT` | sender → receiver | `stream`, `gen`, `off`, `len`, `crc`, `t`, `enc` | encoded data |
| `0x11` | `ACK` | receiver → sender | `stream`, `gen`, `committed` | – |
| `0x12` | `RESEND` | receiver → sender | `stream`, `gen`, `off`, `len` | – |
| `0x13` | `STREAM_END` | sender → receiver | `stream`, `gen`, `size`, `sha256` | – |
| `0x14` | `STREAM_CHECK` | receiver → sender | `stream`, `gen`, `result`, `size` | – |
| `0x15` | `BLOCK_SUMS` | receiver → sender | `stream`, `gen`, `block_size`, `first`, `sums` | – |
| `0x20` | `MESSAGE` | both | `id`, `from`, `to`, `t`, `kind`, `len`, `crc`, `enc` | encoded body |
| `0x21` | `MESSAGE_ACK` | both | `id` | – |
| `0x22` | `DELIVERY` | hub → sender of a message | `id`, `delivered`, `pending`, `unknown` | – |
| `0x23` | `DELIVERY_ACK` | sender of a message → hub | `id`, `delivered` | – |

"Sender" and "receiver" are roles per stream: a source sends to the hub, and the hub sends to consumers.

Optional keys:

- `SEGMENT` MAY carry `repair` (`true` or `false`, default `false`, §14.7).
- `WELCOME` MAY carry `participants`: the participant list as every participant may know it,
  `[{"participant": …, "name": …, "role": …}]`, the hub first with role `hub` (§7). Added 2026-10-26; a participant
  that does not know the key ignores it.

### 14.4 Values

- **Times** (`t`, `t_hello`): integer milliseconds since 1970-01-01 UTC, from the clock of the frame's sender.
- **Identifiers** (`participant`, `hub`, `operation`, `from`, entries of `to`): 1–64 characters from `A–Z a–z 0–9 . _ -`.
- **Stream name** (`stream`): chosen by the application, 1–255 bytes UTF-8, e.g. `rec-0005.dat`. A receiver
  MUST NOT use it directly as a file path; it maps names to its own storage. The hub relays a stream as
  `<source>/<stream>` (§7). That name must also fit in 255 bytes; otherwise the hub MUST refuse the stream with
  `ERROR` `bad_frame` and a plain-language reason.
- **Generation** (`gen`): integer ≥ 1. The sender starts a new generation when a stream is not a continuation of the
  previous one: the file became shorter, or the final check finds more than half of its blocks changed (§14.7).
  Receivers MUST keep every generation separately and MUST NOT overwrite one with another. Bytes changed in place within
  a generation (e.g. a header updated at the end of a recording) are not a new generation; the block repair fixes them.
- **Offsets and lengths** (`off`, `len`, `size`, `committed`): bytes of the raw (decoded) stream.
- **Checksums:** `crc` is the CRC-32 of the raw segment data or message body after decoding; `sha256` and `sums` are
  SHA-256 digests in lower-case hex.
- **Message length** (`len`): bytes of the raw body, at most 1 MiB. Added on 2026-10-26: without it, a receiver could
  not bound the decompression of a `zlib` body (the same rule as for segments, see Encoding).
- **Encoding** (`enc`): `none` or `zlib` (§10: low level). The sender SHOULD use `zlib` only when it makes the blob
  smaller. A `zlib` blob MUST be exactly one complete zlib stream. The receiver MUST decode at most `len` + 1 bytes
  and MUST reject anything that is not exactly `len` bytes (bad frame), so a small blob can never expand into a large
  amount of memory. The data MUST match `crc` after decoding.
- **Message id** (`id`): 32 lower-case hex characters chosen by the original sender, e.g. a random UUID. It MUST
  stay the same across retries and relays.
- **Message kind** (`kind`): chosen by the application, 1–64 characters, same alphabet as identifiers. The core does
  not interpret it.
- **Delivery report:** in `DELIVERY`, `delivered`, `pending` and `unknown` are lists of participant identifiers
  (possibly empty). In `DELIVERY_ACK`, `delivered` is the number of recipients in the report the sender holds.
  Added 2026-10-26.
- **Role** (`role`): `source`, `consumer` or `recipient` (§7).
- **Reject and error codes** (`code`): `unknown_participant`, `wrong_operation`, `version`, `role`, `busy`,
  `bad_frame`, `too_large`, `unknown_type`, `storage`, `internal`. Receivers MUST accept other codes as plain
  strings (§14.9). `text` is plain language for the operator.

### 14.5 Greeting and version

1. The participant sends `HELLO`. `versions` lists the protocol versions it supports. `have` lists what it already
   holds as a receiver: `[{"stream": …, "gen": …, "committed": …}]` (empty for a pure source).
2. The hub MUST pick the highest common version and answer `WELCOME` with `version`. `have` lists what the hub
   holds from this participant. Otherwise it MUST answer `REJECT` and close the connection.
   **Announced operation (decided, added 2026-11-06):** with code `wrong_operation` a hub that is configured to do so
   adds `operation` (its operation identifier) and optionally `operation_name` (a name for people, 1-100
   characters) to `REJECT`. Both keys are optional; older participants ignore them. A participant MUST NOT switch
   to the announced operation on its own: the application MAY offer it to its user and greet again. Announcing
   SHOULD be off by default, because anyone who reaches the hub learns the identifier (§11).
3. Every later frame MUST carry the chosen version in byte 2. The 12-byte header and the frames `HELLO`, `WELCOME`
   and `REJECT` keep their layout in all versions, so that version 1 can always reject a newer participant with a
   readable reason.
4. **Clock offset:** `WELCOME` echoes the participant's `HELLO.t` as `t_hello`. The participant receives `WELCOME` at
   its own time *r* and estimates the hub clock offset as `t − (t_hello + r) / 2`, with an uncertainty of ± half the
   round trip. The core reports the estimate to the application and MUST NOT change the system clock.
5. `heartbeat_s` and `timeout_s` from the hub's configuration apply to both sides (§9: configurable, to be measured).
   A participant MUST use the values as sent; the hub is responsible for them (§14.10).

### 14.6 Example (test vector)

A `HEARTBEAT` at `t = 1767225600000` (2026-01-01 00:00 UTC) in version 1, meta `{"t":1767225600000}` (19 bytes),
empty blob:

```
52 50 01 04 00 00 00 13 00 00 00 00
7b 22 74 22 3a 31 37 36 37 32 32 35 36 30 30 30 30 30 7d
45 28 16 84
```

The last four bytes are the CRC-32 of the 31 bytes before them. `tests/test_frames.py` checks this vector.

**All vectors (added 2026-11-06):** `docs/vectors/frames.json` holds at least one complete frame of every core
type, with its meta, blob and – for encoded data – the raw bytes, plus damaged or illegal frames with the error
code a receiver answers. It is meant for other implementations. Frames with a `zlib` blob are marked
`encode_exact: false`: another zlib may compress differently, decoding must give the same raw bytes.
`tests/test_vectors.py` checks the file against this implementation; `tests/make_vectors.py` writes it.

### 14.7 Final check and block repair

Why: a recording program may change bytes it has already written, typically a header with counters at the end of a
recording. Resending the whole file for that would cost the full transfer again over a slow link.

1. When the application declares the stream complete, the sender sends `STREAM_END` with the final `size` and the
   `sha256` of that many bytes of its file. It MUST NOT send it before everything up to `size` is acknowledged.
2. The receiver MUST compare with what it holds and answer `STREAM_CHECK` (`ok` or `mismatch`, `size` = its committed
   offset). On `mismatch` it then MUST send `BLOCK_SUMS`: the SHA-256 of every block of `block_size` bytes of its data
   (the last block may be shorter), in index order, several frames if needed; `first` is the index of the frame's first
   block. The block size is the receiver's choice (recommended 1 MiB, §14.8); a frame SHOULD carry at most 512 sums
   (about 34 KiB of meta) and MUST stay within the meta limit.
3. The sender has all sums when it holds ⌈`size` / `block_size`⌉ of them. It compares each block with its file:
   - If **more than half** of the blocks differ, the file was replaced rather than edited: the sender starts a new
     generation, and the receiver MUST keep the old one unchanged.
   - Otherwise it resends exactly the differing blocks as `SEGMENT` with `repair: true` and then sends `STREAM_END`
     again. The receiver overwrites those bytes below its committed offset and MUST make them durable before it
     acknowledges as usual (the committed offset does not change).
4. After **3** repairs that reached the receiver and still end in `mismatch`, the sender stops and reports the
   mismatch to the application in plain language. The receiver keeps all bytes. A repair counts as reached when the
   answer to the `STREAM_END` after it arrives on the same connection (frames keep their order); a repair cut off by
   a disconnect does not count.
5. A disconnect at any point is harmless. After reconnecting, the sender sends `STREAM_END` again, and the check and
   repair start over from what the receiver holds.

Without `repair`, a segment below the committed offset is a duplicate and MUST NOT be written (§8.3), so a late
duplicate never changes stored data. A verified stream MUST ignore repair segments. A `STREAM_CHECK` that does not
answer an open `STREAM_END` of the same session MUST be ignored (and SHOULD be logged), and so MUST `BLOCK_SUMS` that
nobody waits for: a stray answer never restarts a repair. Streams are kept per participant, so only a stream's own
sender can repair it.

Status: the frames and their keys are **decided** for 1.0. Block size, the half rule and the 3 rounds are a
sender's choice (recommended values, §14.8), assumptions until measured.

### 14.8 Recommended values (not part of the wire format)

**Decided 2026-11-07 (#31):** the following are choices of the sender or the hub. A peer MUST work with any value
within the limits of §14.2–14.4. The values given are recommended starting points, **assumed** until measured.

| What | Recommended | Where it matters |
|---|---|---|
| Heartbeat / timeout | 2 s / 10 s (may be too short for radio, §9) | the hub decides and sends both in `WELCOME`; participants follow |
| Segment size | about 1 s of data, at most 256 KiB | sender; receivers accept any segment up to the blob limit |
| Compression | zlib at a low level, only if smaller | sender; receivers decode any valid zlib stream (§14.4) |
| Block size for repair | 1 MiB | carried in `BLOCK_SUMS`; the receiver chooses |
| New generation instead of repair | more than half of the blocks differ | sender |
| Repair rounds | stop after 3 | sender |
| Catch-up order | streams in name order, each from its committed offset | sender; receivers accept any order |
| Reconnect back-off | 1 s doubling up to 10 s, with jitter | participant |

### 14.9 Compatibility (decided 2026-11-07)

- **Within 1.x** (no new `PROTOCOL_VERSION`): new optional meta keys, new reject and error codes, new extension
  frame types (`0x80`–`0xFF`), new recommended values. Receivers ignore unknown keys and extension types and
  accept unknown codes as strings, so older and newer peers keep working together.
- **Needs a new protocol version:** a changed meaning or layout of an existing key or frame, a new core frame type
  (`0x00`–`0x7F`), new required keys, changed limits. The greeting (§14.5) then picks the highest common version.
- **Media format:** the same rules apply to `bundle.json` and its `format` number.
- Every change is listed in `CHANGELOG.md`; test vectors (`docs/vectors/frames.json`) are extended, never changed
  silently.

### 14.10 Required behaviour of peers (decided 2026-11-07)

The rules from §7–§12 that another implementation must follow so that peers work together and nothing is lost. The
explanations stay in those sections.

**Durability and acknowledgement**

1. A receiver MUST NOT send `ACK`, `MESSAGE_ACK` or `DELIVERY_ACK` before what it acknowledges is stored durably
   (written and flushed to stable storage). If storing fails, e.g. the disk is full, it MUST NOT acknowledge.
2. A segment or message that is already stored MUST be acknowledged again without writing it a second time.
   Messages are recognised by `id`.
3. A sender MUST continue a stream from the committed offset the receiver reported (`have` in `WELCOME` or
   `HELLO`, or the latest `ACK`). It MUST keep unacknowledged segments and messages and send them again after a
   reconnect.

**Sessions and timing**

4. A participant has at most one session at the hub. A new greeting from the same participant MUST replace the old
   session; the hub MUST NOT refuse it because an old connection still looks alive.
5. Each side MUST send a frame at least every `heartbeat_s` (a `HEARTBEAT` if nothing else is due). Each side MUST
   end the session when nothing arrives for `timeout_s`, and when a send cannot complete within `timeout_s`.
6. The hub MUST NOT run with a `timeout_s` below twice its `heartbeat_s`.
7. After a lost session a participant SHOULD reconnect with back-off and SHOULD NOT give up (§9, §14.8).

**Participants, operations and messages**

8. The hub MUST answer `REJECT` to a participant that is not on its list (`unknown_participant`), greets with
   another operation (`wrong_operation`), a role that does not match the list (`role`) or no common version
   (`version`).
9. Data of different operations and of different participants MUST be kept apart and never mixed.
10. The hub MUST accept a `MESSAGE` only if `from` is the participant of that connection; otherwise it is a bad frame
    (`bad_frame`).
11. The hub MUST deliver a message to every recipient on its list, and MUST report recipients that are not on the
    list as `unknown` in `DELIVERY`. It MUST send `DELIVERY` again after reconnects until a report with all
    delivered recipients is acknowledged.
12. A receiver MUST accept streams and messages in any order (catch-up order is the sender's choice, §14.8).

## Open points

- [x] Wire format: framing, encoding of control messages, checksum algorithm, version negotiation (draft 1, §14,
      proposed).
- [x] Default TCP port: 47310, overridable (§14.1).
- [x] Message body size above 1 MiB: **forbidden in 1.0** (decided 2026-11-07): a message body is at most 1 MiB;
      larger content is split by the application. A later 1.x may add multi-frame bodies as an extension.
- [ ] Network: fixed hub address or discovery; other users on the same network.
- [ ] Bandwidth and typical outages of the radio links (how often, how long).
- [ ] Catch-up order: current stream first, or strictly in order. First implementation: streams in name order,
      each from its committed offset.
- [x] Delivery report to the sender of a message: `DELIVERY` / `DELIVERY_ACK` (§8.5, proposed).
- [x] Which consumer receives which streams: a selection per consumer in the participant list (§7, proposed).
- [ ] Hub failure: standby hub or offline media only.
- [x] Offline media: block repair over media (§8.6, proposed).
- [ ] Offline media: whether the core should help the application decide when a bundle on a stick can be deleted.

**To measure**

- [ ] Data rate of typical streams.
- [ ] Compression ratio and CPU time on target hardware.
- [ ] Heartbeat and timeout on a real radio network, so that short dropouts do not count as disconnects. The current
      assumption (2 s / ~10 s) may be too short for radio links – see the note in §9. Configurable at the hub
      (decided, §9); only the defaults are still to be measured.
