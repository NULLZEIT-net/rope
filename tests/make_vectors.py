"""Write the test vectors of the wire format (spec 14.6) to docs/vectors/frames.json.

    python tests/make_vectors.py

The file is meant for other implementations: every vector is a complete frame in hex together with what it means.
`tests/test_vectors.py` checks the committed file against this implementation, so a change of the wire format shows
up as a failing test. Regenerate only on purpose (and say so in CHANGELOG.md)."""

import hashlib
import json
import os
import struct
import sys
import zlib

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "src"))

from rope_protocol import frames as F  # noqa: E402
from rope_protocol.frames import Frame, FrameType  # noqa: E402

OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "docs", "vectors", "frames.json")

T = 1767225600000                                   # 2026-01-01 00:00 UTC
ID = "0123456789abcdef0123456789abcdef"
SHA_EMPTY = hashlib.sha256(b"").hexdigest()
DATA = b"ROPE test vector segment data. " * 8        # 248 bytes, compresses well
BODY = "Grüße – ✓".encode("utf-8")


def valid(name, frame, note="", raw_data=None, encode_exact=True):
    v = {"name": name, "type": frame.type, "type_name": FrameType(frame.type).name, "version": frame.version,
         "meta": frame.meta, "blob_hex": frame.blob.hex(), "frame_hex": F.encode(frame).hex(),
         "encode_exact": encode_exact}
    if raw_data is not None:
        v["raw_data_hex"] = raw_data.hex()
    if note:
        v["note"] = note
    return v


def frames():
    out = [
        valid("hello", Frame(FrameType.HELLO, dict(participant="source-1", operation="op-1", role="source",
                                                   versions=[1], t=T, have=[]))),
        valid("hello-consumer-have", Frame(FrameType.HELLO, dict(
            participant="c-1", operation="op-1", role="consumer", versions=[1], t=T,
            have=[dict(stream="source-1/rec-0001.dat", gen=1, committed=4096)]))),
        valid("welcome", Frame(FrameType.WELCOME, dict(
            version=1, hub="hub", t=T + 5, t_hello=T, heartbeat_s=2, timeout_s=10, have=[],
            participants=[dict(participant="hub", name="Command post", role="hub"),
                          dict(participant="source-1", name="Survey boat", role="source")])),
              note="participants is optional"),
        valid("reject", Frame(FrameType.REJECT, dict(code="unknown_participant",
                                                     text="source-9 is not on the participant list of this hub"))),
        valid("reject-announced-operation", Frame(FrameType.REJECT, dict(
            code="wrong_operation", text="source-1 belongs to operation op-2, this hub serves op-1",
            operation="op-1", operation_name="Lake exercise")),
              note="operation and operation_name are optional (spec 14.5)"),
        valid("heartbeat", Frame(FrameType.HEARTBEAT, dict(t=T)), note="the example of spec 14.6"),
        valid("bye", Frame(FrameType.BYE, dict(reason="shutdown"))),
        valid("error", Frame(FrameType.ERROR, dict(code="bad_frame", text="CRC mismatch"))),
        valid("segment-none", F.segment("rec-0001.dat", 1, 0, b"\x00\x01\x02\x03 raw", T),
              note="enc none: too short to gain from compression", raw_data=b"\x00\x01\x02\x03 raw"),
        valid("segment-zlib", F.segment("rec-0001.dat", 1, 7, DATA, T), raw_data=DATA, encode_exact=False,
              note="enc zlib: another zlib may produce other compressed bytes; decoding must give raw_data"),
        valid("segment-repair", F.segment("rec-0001.dat", 1, 0, b"HDR1", T, repair=True), raw_data=b"HDR1",
              note="repair is optional, default false (spec 14.7)"),
        valid("ack", Frame(FrameType.ACK, dict(stream="rec-0001.dat", gen=1, committed=255))),
        valid("resend", Frame(FrameType.RESEND, dict(stream="rec-0001.dat", gen=1, off=7, len=248))),
        valid("stream-end", Frame(FrameType.STREAM_END, dict(stream="rec-0001.dat", gen=1, size=0,
                                                             sha256=SHA_EMPTY))),
        valid("stream-check", Frame(FrameType.STREAM_CHECK, dict(stream="rec-0001.dat", gen=1, result="mismatch",
                                                                 size=0))),
        valid("block-sums", Frame(FrameType.BLOCK_SUMS, dict(stream="rec-0001.dat", gen=1, block_size=1 << 20,
                                                             first=0, sums=[SHA_EMPTY]))),
        valid("message", F.message(ID, "source-1", ["hub", "tablet"], T, "note", BODY), raw_data=BODY,
              note="body as UTF-8 text; enc none because zlib would not make it smaller"),
        valid("message-ack", Frame(FrameType.MESSAGE_ACK, dict(id=ID))),
        valid("delivery", Frame(FrameType.DELIVERY, dict(id=ID, delivered=["tablet"], pending=["c-1"], unknown=[]))),
        valid("delivery-ack", Frame(FrameType.DELIVERY_ACK, dict(id=ID, delivered=1))),
    ]
    return out


def invalid():
    """Damaged or illegal frames with the error code a receiver answers (spec 14.2, 14.4)."""
    good = bytearray(F.encode(Frame(FrameType.HEARTBEAT, dict(t=T))))
    bad_crc = bytearray(good)
    bad_crc[-1] ^= 0x01
    bad_magic = bytearray(good)
    bad_magic[0] = 0x00
    too_long = struct.pack(">2sBBII", b"RP", 1, FrameType.SEGMENT, 64 * 1024 + 1, 0)
    not_object = F.HEADER.pack(F.MAGIC, 1, FrameType.HEARTBEAT, 2, 0) + b"[]"
    not_object += F.TRAILER.pack(zlib.crc32(not_object))
    missing = F.encode(Frame(FrameType.ACK, dict(stream="rec-0001.dat", gen=1)))
    return [
        {"name": "wrong-crc", "frame_hex": bytes(bad_crc).hex(), "error": "bad_frame"},
        {"name": "wrong-magic", "frame_hex": bytes(bad_magic).hex(), "error": "bad_frame",
         "note": "detected at the first byte"},
        {"name": "meta-too-long", "frame_hex": too_long.hex(), "error": "too_large",
         "note": "header only: the meta length is checked before reading the rest"},
        {"name": "meta-not-an-object", "frame_hex": not_object.hex(), "error": "bad_frame"},
        {"name": "ack-without-committed", "frame_hex": missing.hex(), "error": "bad_frame",
         "note": "decodes, but fails validation: a required key is missing"},
    ]


def main():
    doc = {"about": "Test vectors of the ROPE wire format (spec 14). Generated by tests/make_vectors.py; "
                    "checked by tests/test_vectors.py.",
           "rules": ["frame_hex is the complete frame: 12-byte header, meta, blob, CRC-32.",
                     "meta is compact, key-sorted UTF-8 JSON; receivers must accept any valid JSON object.",
                     "encode_exact false: encoding may produce other bytes (zlib); decoding must give the same "
                     "meaning and raw_data.",
                     "invalid: a receiver answers ERROR with the given code and closes the connection."],
           "valid": frames(), "invalid": invalid()}
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, "w", encoding="utf-8", newline="\n") as f:
        json.dump(doc, f, ensure_ascii=False, indent=1)
        f.write("\n")
    print("written:", os.path.normpath(OUT), len(doc["valid"]), "valid,", len(doc["invalid"]), "invalid")


if __name__ == "__main__":
    main()
