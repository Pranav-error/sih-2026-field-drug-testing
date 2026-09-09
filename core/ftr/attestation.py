"""Reading Android key attestation — from the certificate, not from the app.

A record that says `verified_boot_state: GREEN` because the app put it there is
worth nothing: the app is exactly the software whose integrity is in question. The
authoritative answer lives in the attestation certificate's Android extension,
signed by the device's secure element and chaining to a Google root.

This module parses that extension. It is a deliberately small ASN.1 reader rather
than a dependency, for the same reason the CBOR encoder is: a challenger must be
able to run the verifier without installing our packages.

Extension OID **1.3.6.1.4.1.11129.2.1.17**, whose structure is:

    KeyDescription ::= SEQUENCE {
        attestationVersion         INTEGER,
        attestationSecurityLevel   ENUMERATED,   -- 0 sw, 1 tee, 2 strongbox
        keymasterVersion           INTEGER,
        keymasterSecurityLevel     ENUMERATED,
        attestationChallenge       OCTET_STRING,
        uniqueId                   OCTET_STRING,
        softwareEnforced           AuthorizationList,
        teeEnforced                AuthorizationList,
    }

with RootOfTrust (tag 704) inside an AuthorizationList carrying the verified boot
key, the device-locked flag and the verified boot state.
"""

from __future__ import annotations

from dataclasses import dataclass

__all__ = ["AttestationInfo", "parse_attestation", "ATTESTATION_OID"]

ATTESTATION_OID = "1.3.6.1.4.1.11129.2.1.17"

_SECURITY_LEVEL = {0: "SOFTWARE", 1: "TEE", 2: "STRONGBOX"}
_BOOT_STATE = {0: "VERIFIED", 1: "SELF_SIGNED", 2: "UNVERIFIED", 3: "FAILED"}

# Android reports GREEN/YELLOW/ORANGE/RED; the enum above is the spec's naming.
_BOOT_COLOUR = {"VERIFIED": "GREEN", "SELF_SIGNED": "YELLOW",
                "UNVERIFIED": "ORANGE", "FAILED": "RED"}


@dataclass(frozen=True)
class AttestationInfo:
    """What the certificate itself says. Nothing here came from the app."""

    attestation_security_level: str
    keymaster_security_level: str
    challenge: bytes
    verified_boot_state: str | None
    device_locked: bool | None
    os_patch_level: int | None

    @property
    def boot_colour(self) -> str:
        return _BOOT_COLOUR.get(self.verified_boot_state or "", "UNKNOWN")


# --------------------------------------------------------------------------- #
# a very small DER reader
# --------------------------------------------------------------------------- #

def _read_tlv(buf: bytes, i: int) -> tuple[int, int, int, int]:
    """Return (tag_number, header_start, content_start, content_end).

    Handles the high-tag-number form, which matters here: RootOfTrust sits at
    context tag [704], encoded as BF 85 40. A reader that took only the first
    byte would treat 0x85 as a length prefix and walk off into the weeds — which
    is exactly what happened before this was fixed.
    """
    start = i
    first = buf[i]
    i += 1
    tag = first & 0x1F
    if tag == 0x1F:                      # high tag number: 7 bits per byte
        tag = 0
        while True:
            b = buf[i]
            i += 1
            tag = (tag << 7) | (b & 0x7F)
            if not (b & 0x80):
                break
    # Keep the class and constructed bits alongside the number so callers can
    # still distinguish a SEQUENCE from a context-specific wrapper.
    tag |= (first & 0xE0) << 8
    if buf[i] & 0x80:
        n = buf[i] & 0x7F
        i += 1
        length = int.from_bytes(buf[i:i + n], "big")
        i += n
    else:
        length = buf[i]
        i += 1
    return tag, start, i, i + length


def _children(buf: bytes, start: int, end: int):
    i = start
    while i < end:
        tag, hs, cs, ce = _read_tlv(buf, i)
        yield tag, cs, ce
        i = ce


def _int(buf: bytes, cs: int, ce: int) -> int:
    return int.from_bytes(buf[cs:ce], "big", signed=False)


# Tag constants after the class/constructed bits are folded in by _read_tlv.
_SEQUENCE = 0x2000 | 0x10
_OCTET_STRING = 0x00 | 0x04
_BOOLEAN = 0x00 | 0x01
_ENUMERATED = 0x00 | 0x0A
_INTEGER = 0x00 | 0x02
_ROOT_OF_TRUST = 0xA000 | 704


def _find_extension(cert_der: bytes) -> bytes | None:
    """Locate the Android attestation extension's OCTET STRING payload.

    Scans for the encoded OID rather than walking the whole certificate: the
    structure around it varies by attestation version, and the OID does not.
    """
    # DER encoding of 1.3.6.1.4.1.11129.2.1.17
    oid = bytes([0x06, 0x0A, 0x2B, 0x06, 0x01, 0x04, 0x01, 0xD6, 0x79, 0x02, 0x01, 0x11])
    at = cert_der.find(oid)
    if at < 0:
        return None
    i = at + len(oid)
    # Optional BOOLEAN critical flag, then the OCTET STRING wrapper.
    if i < len(cert_der) and cert_der[i] == 0x01:
        _, _, cs, ce = _read_tlv(cert_der, i)
        i = ce
    if i >= len(cert_der) or cert_der[i] != 0x04:
        return None
    _, _, cs, ce = _read_tlv(cert_der, i)
    return cert_der[cs:ce]


def _root_of_trust(buf: bytes, start: int, end: int) -> tuple[str | None, bool | None]:
    """Pull verified boot state and the device-locked flag out of an
    AuthorizationList, if it carries a RootOfTrust (context tag 704)."""
    for tag, cs, ce in _children(buf, start, end):
        if tag != _ROOT_OF_TRUST:
            continue
        for t2, c2s, c2e in _children(buf, cs, ce):
            if t2 != _SEQUENCE:          # RootOfTrust is a SEQUENCE
                continue
            locked = state = None
            for t3, s3, e3 in _children(buf, c2s, c2e):
                if t3 == _BOOLEAN and e3 - s3 == 1:
                    locked = buf[s3] != 0
                elif t3 == _ENUMERATED:
                    state = _BOOT_STATE.get(_int(buf, s3, e3))
            if locked is not None or state is not None:
                return state, locked
    return None, None


def parse_attestation(cert_der: bytes) -> AttestationInfo | None:
    """Parse the leaf certificate of an attestation chain.

    Returns None when the certificate carries no attestation extension, which is
    itself a finding: a key with no attestation proves nothing about the hardware
    that holds it.
    """
    payload = _find_extension(cert_der)
    if payload is None:
        return None

    tag, _, cs, ce = _read_tlv(payload, 0)
    if tag != _SEQUENCE:
        return None
    fields = list(_children(payload, cs, ce))
    if len(fields) < 8:
        return None

    att_level = _SECURITY_LEVEL.get(_int(payload, *fields[1][1:]), "UNKNOWN")
    km_level = _SECURITY_LEVEL.get(_int(payload, *fields[3][1:]), "UNKNOWN")
    challenge = payload[fields[4][1]:fields[4][2]]

    # The TEE-enforced list is the one that matters; software-enforced values are
    # asserted by the OS and carry no hardware guarantee.
    boot_state, locked = _root_of_trust(payload, fields[7][1], fields[7][2])
    if boot_state is None:
        boot_state, locked = _root_of_trust(payload, fields[6][1], fields[6][2])

    return AttestationInfo(
        attestation_security_level=att_level,
        keymaster_security_level=km_level,
        challenge=challenge,
        verified_boot_state=boot_state,
        device_locked=locked,
        os_patch_level=None,
    )
