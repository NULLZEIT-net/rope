"""Test vectors of the wire format (docs/vectors/frames.json, spec 14.6): this implementation decodes, validates and
encodes every vector exactly as written, and the committed file matches tests/make_vectors.py."""

import json
import os

import pytest

import make_vectors
from rope_protocol import frames as F
from rope_protocol.frames import Frame, FrameError

PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "docs", "vectors", "frames.json")
DOC = json.load(open(PATH, encoding="utf-8"))


@pytest.mark.parametrize("v", DOC["valid"], ids=lambda v: v["name"])
def test_valid_vector(v):
    raw = bytes.fromhex(v["frame_hex"])
    frame = F.decode(raw)
    assert (frame.type, frame.version, frame.meta, frame.blob.hex()) == (v["type"], v["version"], v["meta"],
                                                                         v["blob_hex"])
    assert F.validate(frame) == v["type"]
    if v["encode_exact"]:
        assert F.encode(Frame(v["type"], v["meta"], bytes.fromhex(v["blob_hex"]), v["version"])).hex() == v["frame_hex"]
    if "raw_data_hex" in v:
        data = F.message_body(frame) if v["type_name"] == "MESSAGE" else F.segment_data(frame)
        assert data.hex() == v["raw_data_hex"]


@pytest.mark.parametrize("v", DOC["invalid"], ids=lambda v: v["name"])
def test_invalid_vector(v):
    with pytest.raises(FrameError) as e:
        for frame in F.FrameDecoder().feed(bytes.fromhex(v["frame_hex"])):
            F.validate(frame)
    assert e.value.code == v["error"]


def test_heartbeat_is_the_example_of_the_spec():
    hb = next(v for v in DOC["valid"] if v["name"] == "heartbeat")
    assert hb["frame_hex"] == ("525001040000001300000000" "7b2274223a313736373232353630303030307d" "45281684")


def test_every_core_type_has_a_vector():
    assert {v["type"] for v in DOC["valid"]} == {int(t) for t in F.REQUIRED}


def test_file_is_up_to_date():
    """Same vectors as the generator writes - except the bytes of zlib blobs, which may differ between zlib builds."""
    def comparable(vs):
        return [{k: x for k, x in v.items() if v.get("encode_exact", True) or k not in ("blob_hex", "frame_hex")}
                for v in vs]
    assert comparable(DOC["valid"]) == comparable(json.loads(json.dumps(make_vectors.frames(), ensure_ascii=False)))
    assert DOC["invalid"] == make_vectors.invalid()
