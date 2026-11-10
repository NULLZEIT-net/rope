# Results of the model checks

Written by `python docs/model/check.py --mutations --record`. Run it yourself to reproduce; the numbers
of states are the same on every machine, the times are not.

| | |
|---|---|
| Date | 2026-11-10 |
| TLA+ tools | v1.7.4 (`tla2tools.jar`, SHA-256 `936a262061c914694dfd669a543be24573c45d5aa0ff20a8b96b23d01e050e88`) |
| Java | openjdk version "11.0.22" 2024-01-16 |
| Machine | Windows 10.0.26200, 12 logical processors |

## Model checks

Every reachable state of each configuration was explored. **PASS** means TLC found no violation of any
invariant or property listed in the configuration.

| Model | Configuration | Covers | Distinct states | States generated | Depth | Time | Result |
|---|---|---|---:|---:|---:|---:|---|
| `ROPEStream` | `ROPEStream.cfg` | one stream, a file of up to 3 bytes, window 2, network and sticks, up to 2 breaks | 339,944 | 1,691,309 | 32 | 33 s | PASS |
| `ROPEMessages` | `ROPEMessages.cfg` | one message, network and sticks, up to 3 breaks | 223,034 | 2,728,960 | 30 | 13 s | PASS |
| `ROPEMessages` | `ROPEMessagesTwo.cfg` | two messages, network only, up to 2 breaks | 256,748 | 1,084,943 | 35 | 23 s | PASS |

## Mutation checks

Each mutation breaks one rule of the design on purpose. **Found** means TLC reported the violation
named; a mutation that is not found would show that the model is too weak to see that error.

| Model | Configuration | Broken on purpose | Result | Reported by TLC |
|---|---|---|---|---|
| `ROPEStream` | `ROPEStream.cfg` | the hub writes a segment at the offset it names, without checking its committed offset | Found | Invariant StoredCorrectly is violated. |
| `ROPEStream` | `ROPEStream.cfg` | the hub acknowledges a duplicate segment as one byte more than it stores | Found | Invariant AckedIsStored is violated. |
| `ROPEStream` | `ROPEStream.cfg` | the source resumes from what it sent, not from WELCOME.have | Found | Temporal properties were violated. |
| `ROPEStream` | `ROPEStream.cfg` | the source sends STREAM_END before everything is acknowledged | Found | Invariant NeverMismatch is violated. |
| `ROPEMessages` | `ROPEMessages.cfg` | the recipient forgets which messages it told in this run | Found | Invariant ToldAtMostOnce is violated. |
| `ROPEMessages` | `ROPEMessages.cfg` | the hub acknowledges a message without taking custody | Found | Invariant CustodyChain is violated. |
| `ROPEMessages` | `ROPEMessages.cfg` | the sender does not send again after a reconnect | Found | Temporal properties were violated. |
| `ROPEMessages` | `ROPEMessages.cfg` | the hub counts a message as delivered when it sends it, not on the recipient's receipt | Found | Invariant CustodyChain is violated. |
| `ROPEMessages` | `ROPEMessagesTwo.cfg` | the recipient forgets which messages it told in this run | Found | Invariant ToldAtMostOnce is violated. |
| `ROPEMessages` | `ROPEMessagesTwo.cfg` | the hub acknowledges a message without taking custody | Found | Invariant CustodyChain is violated. |
| `ROPEMessages` | `ROPEMessagesTwo.cfg` | the sender does not send again after a reconnect | Found | Deadlock reached. |
| `ROPEMessages` | `ROPEMessagesTwo.cfg` | the hub counts a message as delivered when it sends it, not on the recipient's receipt | Found | Invariant CustodyChain is violated. |
