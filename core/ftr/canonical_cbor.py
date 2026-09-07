"""Canonical CBOR — deterministic encoding, RFC 8949 §4.2.1 core rules.

The digest is the legal artefact, so serialisation must be byte-identical for
identical content on every implementation, forever. That rules out most of CBOR:

  * definite lengths only — no streaming forms
  * shortest-form integer and length encoding
  * map keys sorted bytewise-lexicographically by their *encoded* bytes
  * no floats, no tags, no duplicate keys

Floats are rejected outright rather than canonicalised. IEEE-754 rounding is not
worth defending under cross-examination; every measured quantity in an FTR is
stored as a scaled integer with its scale named in the field (``delta_e_x1000``).

This module has no third-party dependencies on purpose: the verifier must be
runnable by someone who does not trust us and will not install our packages.
"""

from __future__ import annotations

from typing import Any

__all__ = ["dumps", "loads", "is_canonical", "CborError"]


class CborError(ValueError):
    """Raised for input this profile refuses to encode or decode."""


# --------------------------------------------------------------------------- #
# encoding
# --------------------------------------------------------------------------- #

def _head(major: int, n: int) -> bytes:
    """Type byte plus shortest-form argument for ``n``."""
    m = major << 5
    if n < 24:
        return bytes([m | n])
    if n < 0x100:
        return bytes([m | 24, n])
    if n < 0x10000:
        return bytes([m | 25]) + n.to_bytes(2, "big")
    if n < 0x100000000:
        return bytes([m | 26]) + n.to_bytes(4, "big")
    if n < 0x10000000000000000:
        return bytes([m | 27]) + n.to_bytes(8, "big")
    raise CborError(f"integer too large for CBOR: {n}")


def _encode(v: Any) -> bytes:
    # bool before int: bool is an int subclass in Python and would encode as 0/1.
    if v is True:
        return b"\xf5"
    if v is False:
        return b"\xf4"
    if v is None:
        return b"\xf6"
    if isinstance(v, int):
        return _head(0, v) if v >= 0 else _head(1, -v - 1)
    if isinstance(v, float):
        raise CborError(
            "floats are not encodable in an FTR — store a scaled integer and "
            "name the scale in the field (e.g. delta_e_x1000)"
        )
    if isinstance(v, bytes):
        return _head(2, len(v)) + v
    if isinstance(v, str):
        b = v.encode("utf-8")
        return _head(3, len(b)) + b
    if isinstance(v, (list, tuple)):
        return _head(4, len(v)) + b"".join(_encode(x) for x in v)
    if isinstance(v, dict):
        items = []
        for k, val in v.items():
            if not isinstance(k, (str, int)) or isinstance(k, bool):
                raise CborError(f"map keys must be str or int, got {type(k).__name__}")
            items.append((_encode(k), _encode(val)))
        keys = [k for k, _ in items]
        if len(set(keys)) != len(keys):
            raise CborError("duplicate map key after encoding")
        items.sort(key=lambda kv: kv[0])  # bytewise lexicographic on encoded keys
        return _head(5, len(items)) + b"".join(k + val for k, val in items)
    raise CborError(f"type not encodable in an FTR: {type(v).__name__}")


def dumps(value: Any) -> bytes:
    """Encode ``value`` canonically."""
    return _encode(value)


# --------------------------------------------------------------------------- #
# decoding
# --------------------------------------------------------------------------- #

def _read_head(buf: bytes, i: int) -> tuple[int, int, int]:
    if i >= len(buf):
        raise CborError("truncated: expected a type byte")
    ib = buf[i]
    major, minor = ib >> 5, ib & 0x1F
    i += 1
    if minor < 24:
        return major, minor, i
    if minor == 31:
        raise CborError("indefinite-length item is not canonical")
    if minor > 27:
        raise CborError(f"reserved additional-information value {minor}")
    width = 1 << (minor - 24)
    if i + width > len(buf):
        raise CborError("truncated: argument runs past end of buffer")
    n = int.from_bytes(buf[i:i + width], "big")
    # shortest-form check — a longer encoding of a small value is not canonical
    limits = {1: 24, 2: 0x100, 4: 0x10000, 8: 0x100000000}
    if n < limits[width]:
        raise CborError(f"non-canonical: {n} encoded in {width} byte(s), shorter form exists")
    return major, n, i + width


def _decode(buf: bytes, i: int) -> tuple[Any, int]:
    major, n, i = _read_head(buf, i)
    if major == 0:
        return n, i
    if major == 1:
        return -1 - n, i
    if major == 2:
        if i + n > len(buf):
            raise CborError("truncated byte string")
        return buf[i:i + n], i + n
    if major == 3:
        if i + n > len(buf):
            raise CborError("truncated text string")
        try:
            return buf[i:i + n].decode("utf-8"), i + n
        except UnicodeDecodeError as e:
            raise CborError("invalid UTF-8 in text string") from e
    if major == 4:
        out = []
        for _ in range(n):
            v, i = _decode(buf, i)
            out.append(v)
        return out, i
    if major == 5:
        out: dict[Any, Any] = {}
        prev: bytes | None = None
        for _ in range(n):
            start = i
            k, i = _decode(buf, i)
            enc = buf[start:i]
            if prev is not None and enc <= prev:
                raise CborError("non-canonical: map keys out of order or duplicated")
            prev = enc
            v, i = _decode(buf, i)
            out[k] = v
        return out, i
    if major == 7:
        if n == 20:
            return False, i
        if n == 21:
            return True, i
        if n == 22:
            return None, i
        raise CborError(f"simple/float value {n} is not permitted in an FTR")
    raise CborError(f"unsupported major type {major}")


def loads(buf: bytes) -> Any:
    """Decode ``buf``, rejecting anything a canonical encoder could not have produced."""
    if not isinstance(buf, (bytes, bytearray)):
        raise CborError("loads expects bytes")
    v, i = _decode(bytes(buf), 0)
    if i != len(buf):
        raise CborError(f"{len(buf) - i} trailing byte(s) after the top-level item")
    return v


def is_canonical(buf: bytes) -> bool:
    """True if ``buf`` decodes and re-encodes to itself, byte for byte."""
    try:
        return dumps(loads(buf)) == bytes(buf)
    except CborError:
        return False
