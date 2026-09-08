"""The other direction: records sealed by Dart, verified by Python.

`test_cross_implementation.py` runs Python→Dart. This runs Dart→Python, which is
the direction that actually matters in deployment: **the app seals in Dart.** A
format only one implementation can write is not a format, and a verifier that has
only ever read its own output has not been tested.

The fixture is deterministic (fixed keystore seed), so it can be committed and a
diff means something. Regenerate deliberately:

    cd dart/ftr_verify && dart run bin/gen_dart_chain.dart ../../core/tests/vectors/dart_sealed
"""

from pathlib import Path

import pytest

from ftr.canonical_cbor import dumps, is_canonical, loads
from ftr.record import SealedRecord
from ftr.verifier import verify_chain, verify_record

CHAIN = Path(__file__).parent / "vectors" / "dart_sealed"

pytestmark = pytest.mark.skipif(
    not CHAIN.is_dir() or not list(CHAIN.glob("*.ftr")),
    reason="dart-sealed fixture missing; run gen_dart_chain.dart",
)


def _records():
    return [SealedRecord.from_envelope(p.read_bytes()) for p in sorted(CHAIN.glob("*.ftr"))]


def test_dart_writes_canonical_cbor_python_agrees_with():
    """The encoder agreement, tested in the write direction."""
    for rec in _records():
        assert is_canonical(rec.body_cbor)
        assert dumps(loads(rec.body_cbor)) == rec.body_cbor, (
            "Python re-encodes Dart's bytes differently — the two encoders have diverged"
        )


def test_openssl_accepts_a_pointycastle_signature():
    """Different language, different bignum implementation, same curve.

    If this ever fails, a record sealed on a handset cannot be verified by the
    reference verifier, which would make the whole scheme worthless.
    """
    for rec in _records():
        report = verify_record(rec.to_envelope())
        assert any("signature verifies" in p for p in report.proven), (
            "\n".join(report.failures)
        )


def test_the_dart_sealed_chain_replays_in_python():
    report = verify_chain(CHAIN)
    assert any("no gap and no fork" in p for p in report.proven), "\n".join(report.failures)


def test_a_dart_sealed_software_record_still_fails_verification():
    """The policy holds regardless of which implementation sealed it.

    A development key is a development key. If Dart could seal something Python
    accepted as evidence, every demo we run would be indistinguishable from the
    real thing.
    """
    report = verify_chain(CHAIN)
    assert not report.ok
    assert all("not hardware-backed" in f for f in report.failures)


def test_the_sequence_is_inside_the_body_dart_wrote():
    recs = _records()
    assert [r.sequence for r in recs] == list(range(len(recs)))
    for a, b in zip(recs, recs[1:]):
        assert b.prev_record_hash == a.digest


def test_dart_carried_the_location_disagreement_into_the_record():
    """The rule survives the port: anomalies are recorded, not dropped."""
    report = verify_record((CHAIN / "000002.ftr").read_bytes())
    assert any("Only 2 of 4" in a for a in report.asserted)
    assert any("310 km" in a for a in report.asserted)


def test_dart_recorded_an_abstention_as_a_first_class_result():
    body = SealedRecord.from_envelope((CHAIN / "000002.ftr").read_bytes()).body
    cls = body["classification"]
    assert cls["label"] is None
    assert cls["prediction_set"] == ["opiate_class", "amphetamine_class"]


def test_the_envelope_dart_writes_carries_no_digest():
    """Same rule, enforced on the writer: a supplied digest is not evidence."""
    e = loads((CHAIN / "000000.ftr").read_bytes())
    assert set(e) == {"v", "body", "sig", "pub", "att"}
