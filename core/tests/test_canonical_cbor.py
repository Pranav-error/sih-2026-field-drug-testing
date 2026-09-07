"""The digest is the legal artefact, so the encoder is the thing most worth testing."""

import pytest

from ftr.canonical_cbor import CborError, dumps, is_canonical, loads


@pytest.mark.parametrize("value,expected", [
    (0, "00"), (1, "01"), (23, "17"), (24, "1818"), (255, "18ff"),
    (256, "190100"), (-1, "20"), (-24, "37"), (-25, "3818"),
    (b"", "40"), (b"\x01\x02", "42 0102".replace(" ", "")),
    ("", "60"), ("a", "6161"), ("IETF", "6449455446"),
    ([], "80"), ([1, 2, 3], "83010203"),
    ({}, "a0"), ({"a": 1}, "a1616101"),
    (True, "f5"), (False, "f4"), (None, "f6"),
])
def test_rfc8949_vectors(value, expected):
    assert dumps(value).hex() == expected


def test_map_keys_sort_bytewise_on_encoded_key():
    # "a" < "b" < "aa" by RFC 8949 core rules: shorter encodings sort first.
    blob = dumps({"aa": 3, "b": 2, "a": 1})
    assert blob.hex() == "a3" "616101" "616202" "62616103"


def test_key_insertion_order_does_not_change_the_digest():
    assert dumps({"z": 1, "a": 2, "m": 3}) == dumps({"a": 2, "m": 3, "z": 1})


def test_integer_keys_sort_before_text_keys():
    assert dumps({"a": 1, 1: 2}).hex() == "a2" "0102" "616101"


def test_floats_are_refused_with_a_useful_message():
    with pytest.raises(CborError, match="scaled integer"):
        dumps({"delta_e": 3.81})


def test_unsupported_types_are_refused():
    with pytest.raises(CborError):
        dumps({"when": object()})
    with pytest.raises(CborError, match="keys must be"):
        dumps({(1, 2): "tuple key"})


def test_roundtrip_of_a_record_shaped_structure():
    v = {
        "schema_version": 1,
        "prev_record_hash": b"\x00" * 32,
        "colorimetry": {"lab_x100": [2840, 1210, -960], "residual_x1000": 1420},
        "omitted": ["kit.lot"],
        "device": {"bootloader_locked": True, "strongbox": None},
    }
    assert loads(dumps(v)) == v
    assert is_canonical(dumps(v))


@pytest.mark.parametrize("blob,why", [
    (bytes.fromhex("1800"), "0 encoded in a longer form than necessary"),
    (bytes.fromhex("190001"), "1 encoded in two bytes"),
    (bytes.fromhex("bf616101ff"), "indefinite-length map"),
    (bytes.fromhex("5f42010243030405ff"), "indefinite-length byte string"),
    (bytes.fromhex("a2616201616101"), "map keys out of order"),
    (bytes.fromhex("a2616101616101"), "duplicate map key"),
    (bytes.fromhex("f97e00"), "half-float"),
    (bytes.fromhex("c11a514b67b0"), "tag"),
    (bytes.fromhex("0101"), "trailing bytes"),
])
def test_non_canonical_input_is_rejected(blob, why):
    assert not is_canonical(blob), why


def test_truncated_input_is_rejected():
    full = dumps({"a": b"12345"})
    assert not is_canonical(full[:-2])
