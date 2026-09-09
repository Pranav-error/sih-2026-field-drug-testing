"""Reading attestation from the certificate rather than from the record.

The single most important property here: **the certificate outranks the app.**
A record that says STRONGBOX while its attestation certificate says SOFTWARE is
not a record with a cosmetic inconsistency; it is a record overstating its own
hardware, and the verifier must fail it.
"""

import pytest

from factory import SimulatedHardwareKeystore, sample_ftr
from ftr.attestation import ATTESTATION_OID, parse_attestation
from ftr.chain import Chain
from ftr.record import seal
from ftr.verifier import verify_record


def _der_len(n: int) -> bytes:
    if n < 0x80:
        return bytes([n])
    b = n.to_bytes((n.bit_length() + 7) // 8, "big")
    return bytes([0x80 | len(b)]) + b


def _tlv(tag: int, payload: bytes) -> bytes:
    return bytes([tag]) + _der_len(len(payload)) + payload


def fake_attestation_cert(level: int, boot_state: int, locked: bool,
                          challenge: bytes = b"chal") -> bytes:
    """A minimal certificate carrying only the Android attestation extension.

    Not a valid X.509 certificate — the parser locates the extension by its OID
    rather than walking the certificate, precisely so that attestation can be
    read from real-world certificates whose surrounding structure varies by
    attestation version.
    """
    root_of_trust = _tlv(0x30,
        _tlv(0x04, b"\x00" * 32) +                 # verifiedBootKey
        _tlv(0x01, b"\xff" if locked else b"\x00") +  # deviceLocked
        _tlv(0x0A, bytes([boot_state])))              # verifiedBootState
    # RootOfTrust sits at context tag [704] inside the AuthorizationList.
    tagged = bytes([0xBF, 0x85, 0x40]) + _der_len(len(root_of_trust)) + root_of_trust
    tee_enforced = _tlv(0x30, tagged)

    key_description = _tlv(0x30,
        _tlv(0x02, b"\x04") +          # attestationVersion
        _tlv(0x0A, bytes([level])) +   # attestationSecurityLevel
        _tlv(0x02, b"\x04") +          # keymasterVersion
        _tlv(0x0A, bytes([level])) +   # keymasterSecurityLevel
        _tlv(0x04, challenge) +        # attestationChallenge
        _tlv(0x04, b"") +              # uniqueId
        _tlv(0x30, b"") +              # softwareEnforced
        tee_enforced)

    oid = bytes([0x06, 0x0A, 0x2B, 0x06, 0x01, 0x04, 0x01, 0xD6, 0x79, 0x02, 0x01, 0x11])
    return b"\x30\x82\x01\x00" + oid + _tlv(0x04, key_description)


# --- the parser ------------------------------------------------------------ #

def test_a_certificate_with_no_extension_is_a_finding_not_a_crash():
    assert parse_attestation(b"\x30\x03\x02\x01\x00") is None


@pytest.mark.parametrize("level,name", [(0, "SOFTWARE"), (1, "TEE"), (2, "STRONGBOX")])
def test_the_security_level_is_read_from_the_certificate(level, name):
    info = parse_attestation(fake_attestation_cert(level, 0, True))
    assert info is not None
    assert info.attestation_security_level == name
    assert info.keymaster_security_level == name


def test_verified_boot_and_lock_state_are_read_from_the_root_of_trust():
    info = parse_attestation(fake_attestation_cert(2, 0, True))
    assert info.verified_boot_state == "VERIFIED"
    assert info.boot_colour == "GREEN"
    assert info.device_locked is True


@pytest.mark.parametrize("state,colour", [
    (0, "GREEN"), (1, "YELLOW"), (2, "ORANGE"), (3, "RED")])
def test_every_boot_state_maps_to_its_colour(state, colour):
    assert parse_attestation(fake_attestation_cert(2, state, True)).boot_colour == colour


def test_the_challenge_survives_the_round_trip():
    """The challenge is what binds a chain to this installation rather than one
    lifted from another handset."""
    info = parse_attestation(fake_attestation_cert(2, 0, True, challenge=b"sih26231"))
    assert info.challenge == b"sih26231"


# --- the verifier ---------------------------------------------------------- #

def _record(tmp_path, chain, claimed_level):
    ks = SimulatedHardwareKeystore(tmp_path / "k.pem", level=claimed_level)
    rec = seal(sample_ftr(), b"\x00" * 32, 0, ks)
    att = dict(rec.attestation)
    att["cert_chain"] = chain
    from ftr.record import SealedRecord
    from ftr.canonical_cbor import dumps
    return SealedRecord.from_envelope(dumps({
        "v": 1, "body": rec.body_cbor, "sig": rec.signature,
        "pub": rec.public_key_der, "att": att,
    }))


def test_the_certificate_outranks_the_record(tmp_path):
    """A record claiming more hardware than its certificate attests to must fail.

    This is the attack the whole attestation path exists to catch: anyone can
    write STRONGBOX into a record; only a secure element can produce a
    certificate that says it.
    """
    cert = fake_attestation_cert(0, 0, True)          # certificate says SOFTWARE
    report = verify_record(_record(tmp_path, [cert], "STRONGBOX").to_envelope())
    assert not report.ok
    assert any("overstates its own hardware" in f for f in report.failures)


def test_a_genuine_strongbox_record_verifies(tmp_path):
    cert = fake_attestation_cert(2, 0, True)
    report = verify_record(_record(tmp_path, [cert], "STRONGBOX").to_envelope())
    assert report.ok, "\n".join(report.failures)
    assert any("read from the certificate, not from the record" in p
               for p in report.proven)
    assert any("Verified boot was GREEN" in p for p in report.proven)


def test_an_unlocked_bootloader_in_the_certificate_fails(tmp_path):
    cert = fake_attestation_cert(2, 2, False)          # ORANGE, unlocked
    report = verify_record(_record(tmp_path, [cert], "STRONGBOX").to_envelope())
    assert not report.ok
    assert any("modified device" in f for f in report.failures)
    assert any("attestation certificate" in f for f in report.failures)


def test_the_unwalked_chain_is_declared(tmp_path):
    """We read the leaf but do not yet chain it to a Google root. Saying so is
    the difference between a limitation and a false claim."""
    cert = fake_attestation_cert(2, 0, True)
    report = verify_record(_record(tmp_path, [cert], "STRONGBOX").to_envelope())
    assert any("does not yet walk the chain to a Google hardware root" in a
               for a in report.asserted)
