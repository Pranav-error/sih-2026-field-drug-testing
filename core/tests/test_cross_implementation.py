"""The Python half of the cross-implementation contract.

The same fixture files the Dart suite reads. Python generated them, so "accepts"
is not news on the day they are written — the value is *regression*: change the
encoder and these committed bytes stop matching, which is exactly the failure that
would otherwise be discovered by a defence expert instead of by CI.

Regenerate deliberately, never to make a test pass:

    python core/tools/gen_vectors.py
"""

import hashlib
import json
from pathlib import Path

import pytest

from ftr.canonical_cbor import dumps, is_canonical, loads
from ftr.verifier import verify_chain, verify_record

VECTORS = Path(__file__).resolve().parents[2] / "dart" / "ftr_verify" / "test" / "vectors"

pytestmark = pytest.mark.skipif(
    not (VECTORS / "encoding.json").exists(),
    reason="vectors not generated; run python core/tools/gen_vectors.py",
)


def _spec():
    return json.loads((VECTORS / "encoding.json").read_text())


def _accept_cases():
    return [(c["name"], c["hex"], c["sha256"]) for c in _spec()["accept"]]


def _reject_cases():
    return [(c["name"], c["hex"], c["why"]) for c in _spec()["reject"]]


@pytest.mark.parametrize("name,hexs,digest", _accept_cases(), ids=lambda v: None)
def test_committed_vectors_still_round_trip(name, hexs, digest):
    blob = bytes.fromhex(hexs)
    assert is_canonical(blob), f"{name}: no longer considered canonical"
    assert dumps(loads(blob)).hex() == hexs, f"{name}: encoder output has changed"
    assert hashlib.sha256(blob).hexdigest() == digest, f"{name}: digest has changed"


@pytest.mark.parametrize("name,hexs,why", _reject_cases(), ids=lambda v: None)
def test_committed_vectors_are_still_rejected(name, hexs, why):
    assert not is_canonical(bytes.fromhex(hexs)), f"{name} must be rejected: {why}"


def test_the_vector_chain_verifies():
    report = verify_chain(VECTORS / "chain")
    assert report.ok, "\n".join(report.failures)
    assert any("no gap and no fork" in p for p in report.proven)


def test_the_vector_chain_reports_its_open_window():
    report = verify_chain(VECTORS / "chain")
    assert any("unanchored" in a for a in report.asserted)


def test_the_vector_chain_surfaces_the_location_disagreement():
    report = verify_record((VECTORS / "chain" / "000002.ftr").read_bytes())
    assert report.ok, "a disagreement is recorded, not a verification failure"
    assert any("Only 2 of 4" in a for a in report.asserted)
    assert any("310 km" in a for a in report.asserted)


@pytest.mark.parametrize("attack", ["rewritten_result", "deleted_middle", "reordered"])
def test_the_tampered_chains_all_fail(attack):
    report = verify_chain(VECTORS / "tampered" / attack)
    assert not report.ok, f"{attack} must not verify"
    assert report.failures


def test_manifest_matches_what_is_on_disk():
    """A stale manifest would let an attack silently stop being tested."""
    manifest = json.loads((VECTORS / "manifest.json").read_text())
    assert len(list((VECTORS / "chain").glob("[0-9]*.ftr"))) == manifest["chain"]["records"]
    on_disk = {p.name for p in (VECTORS / "tampered").iterdir() if p.is_dir()}
    assert on_disk == set(manifest["tampered"]), "manifest and tampered/ have diverged"
