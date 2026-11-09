# Security

## Scope

ROPE has **no encryption and no authentication** beyond a participant list, by design. It is intended for closed,
physically controlled networks. Reading or spoofing traffic on the same network is therefore expected behaviour, not a
vulnerability. Protecting data in transit is the job of the layers around ROPE (a VPN such as WireGuard, an encrypted
radio channel, a closed network) and of the devices (updates, endpoint protection). See
[Security considerations](docs/spec.md#11-security-considerations).

What ROPE does provide is **integrity against accidents**: a CRC per frame, SHA-256 per stream, resumption from the
last committed offset, and a participant list that prevents mix-ups. When the network is not closed (for example over
the internet), an application can wrap the connection in **TLS**, e.g. with certificates on both sides; the frames
inside are unchanged (spec [§14.1 Transport](docs/spec.md#141-transport)). Offline media are not encrypted either; treat them
like the data on them.

Relevant reports are, for example: crashes or hangs caused by malformed input, unbounded memory or disk use, writing
outside the configured storage directory, or data corruption that passes verification.

## Reporting

Please report vulnerabilities privately via GitHub: **Security → Report a vulnerability** in this repository. Do not
open a public issue for them.
