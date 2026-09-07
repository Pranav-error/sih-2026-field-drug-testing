"""Ledger behaviour, and the adversary matrix from ARCHITECTURE.md §10.

Each adversary test is a live demo: the move, and what catches it.
"""

import hashlib

import pytest

from factory import RAW_FRAME, SimulatedHardwareKeystore, sample_ftr
from ftr.canonical_cbor import dumps, loads
from ftr.chain import Chain
from ftr.record import GENESIS_HASH, SealedRecord, seal
from ftr.signing import SoftwareKeystore
from ftr.verifier import verify_chain, verify_record


@pytest.fixture
def keystore(tmp_path):
    """Simulated StrongBox. See test_software_keys_never_verify_as_evidence for why."""
    return SimulatedHardwareKeystore(tmp_path / "hw.pem")


@pytest.fixture
def chain(tmp_path, keystore):
    c = Chain(tmp_path / "chain")
    for i in range(3):
        c.append(seal(sample_ftr(), c.head(), c.next_sequence(), keystore))
    return c


# --- ordinary behaviour ---------------------------------------------------- #

def test_first_record_chains_to_genesis(tmp_path, keystore):
    c = Chain(tmp_path / "c")
    assert c.head() == GENESIS_HASH
    rec = seal(sample_ftr(), c.head(), 0, keystore)
    c.append(rec)
    assert c.head() == rec.digest and len(c) == 1


def test_each_record_chains_to_the_one_before(chain):
    recs = chain.records()
    for a, b in zip(recs, recs[1:]):
        assert b.prev_record_hash == a.digest
    assert chain.status().intact


def test_envelope_survives_a_round_trip(chain):
    r = chain.records()[0]
    again = SealedRecord.from_envelope(r.to_envelope())
    assert again.digest == r.digest and again.signature_valid()


def test_digest_is_recomputed_not_read_from_the_file(chain):
    """A verifier that trusts a supplied digest is not verifying anything."""
    r = chain.records()[0]
    e = loads(r.to_envelope())
    assert "digest" not in e and "hash" not in e


def test_identical_content_yields_an_identical_digest(tmp_path, keystore):
    f = sample_ftr()
    a = seal(f, GENESIS_HASH, 0, keystore)
    b = seal(f, GENESIS_HASH, 0, keystore)
    assert a.digest == b.digest          # deterministic encoding
    assert a.signature != b.signature    # ECDSA nonce; both verify
    assert a.signature_valid() and b.signature_valid()


# --- adversary matrix ------------------------------------------------------ #

def test_row2_editing_the_image_after_capture_is_caught(chain):
    """§10 row 2 — the raw frame hash is bound into the signed record."""
    blob = chain._paths()[0].read_bytes()
    ok = verify_record(blob, images={"raw_image_sha256": RAW_FRAME})
    assert ok.ok and any("byte-identical" in p for p in ok.proven)

    tampered = verify_record(blob, images={"raw_image_sha256": RAW_FRAME + b" edited"})
    assert not tampered.ok
    assert any("altered since capture" in f for f in tampered.failures)


def test_row3_altering_a_stored_result_breaks_the_signature(chain, tmp_path):
    """§10 row 3 — signature over canonical CBOR."""
    path = chain._paths()[0]
    rec = SealedRecord.from_envelope(path.read_bytes())
    body = rec.body
    body["classification"]["label"] = "negative"
    forged = dumps({"v": 1, "body": dumps(body), "sig": rec.signature,
                    "pub": rec.public_key_der, "att": rec.attestation})
    report = verify_record(forged)
    assert not report.ok
    assert any("does not verify" in f for f in report.failures)


def test_row4_backdating_a_record_forks_the_chain(chain, keystore, tmp_path):
    """§10 row 4 — an inserted record cannot carry the right prev hash."""
    recs = chain.records()
    inserted = seal(sample_ftr(), recs[0].digest, 1, keystore)   # re-chains to #0
    (chain.root / "000001.ftr").write_bytes(inserted.to_envelope())
    st = chain.status()
    assert not st.intact
    assert any(b.kind == "gap" for b in st.breaks)


def test_row5_deleting_a_record_from_the_middle_is_visible(chain):
    """§10 row 5 — removal leaves a gap that replay reports."""
    chain._paths()[1].unlink()
    report = verify_chain(chain.root)
    assert not report.ok
    assert any("chain break" in f for f in report.failures)


def test_row5b_truncation_at_the_head_is_reported_as_unverifiable(chain):
    """§10 row 5, residual risk — truncation is only detectable against an anchor."""
    chain._paths()[-1].unlink()
    report = verify_chain(chain.root)
    assert report.ok, "a truncated chain still replays cleanly — this is the known gap"
    assert any("head" in u and "anchor" in u for u in report.unverifiable)


def test_reordering_records_is_caught(chain):
    a, b = chain._paths()[0], chain._paths()[1]
    ab, bb = a.read_bytes(), b.read_bytes()
    a.write_bytes(bb)
    b.write_bytes(ab)
    assert not chain.status().intact


def test_append_refuses_to_replay_a_record_already_in_the_chain(chain, keystore):
    rec = seal(sample_ftr(), chain.head(), chain.next_sequence(), keystore)
    path = chain.append(rec)
    assert path.exists()
    with pytest.raises(ValueError, match="not the next slot"):
        chain.append(rec)



def test_append_refuses_a_record_that_does_not_chain(chain, keystore):
    stray = seal(sample_ftr(), b"\xaa" * 32, chain.next_sequence(), keystore)
    with pytest.raises(ValueError, match="chains to"):
        chain.append(stray)


def test_sequence_is_inside_the_signed_body(chain, keystore):
    """Relocating a record changes its digest, so it cannot be moved silently."""
    f = sample_ftr()
    a = seal(f, GENESIS_HASH, 0, keystore)
    b = seal(f, GENESIS_HASH, 7, keystore)
    assert a.digest != b.digest


# --- anchoring ------------------------------------------------------------- #

def test_an_unanchored_chain_says_so(chain):
    report = verify_chain(chain.root)
    assert report.ok
    assert any("never been anchored" in a for a in report.asserted)


def test_anchoring_narrows_the_open_window(chain, keystore):
    chain.anchor(1)
    st = chain.status()
    assert st.last_anchor_sequence == 1 and st.unanchored == 1
    report = verify_chain(chain.root)
    assert any("unanchored" in a for a in report.asserted)

    chain.anchor(2)
    assert chain.status().unanchored == 0
    assert any("anchored up to" in p for p in verify_chain(chain.root).proven)


def test_software_keys_never_verify_as_evidence(tmp_path):
    """A development record must fail, loudly, rather than look admissible.

    This is the single most important negative test in the suite: if a software
    key ever verified clean, every demo we run would be indistinguishable from
    real evidence.
    """
    from ftr.signing import SoftwareKeystore

    c = Chain(tmp_path / "dev")
    ks = SoftwareKeystore(tmp_path / "dev.pem")
    c.append(seal(sample_ftr(), c.head(), 0, ks))

    report = verify_record(c._paths()[0].read_bytes())
    assert not report.ok
    assert any("not hardware-backed" in f for f in report.failures)
    assert any("never be presented as evidence" in f for f in report.failures)


def test_tee_is_reported_as_weaker_than_strongbox(tmp_path):
    c = Chain(tmp_path / "tee")
    ks = SimulatedHardwareKeystore(tmp_path / "tee.pem", level="TEE")
    c.append(seal(sample_ftr(), c.head(), 0, ks))
    report = verify_record(c._paths()[0].read_bytes())
    assert report.ok
    assert any("weaker than StrongBox" in p for p in report.proven)


def test_an_unlocked_bootloader_fails_verification(tmp_path):
    """§10 row 7 — a rooted device is detectable years later, without the handset."""
    c = Chain(tmp_path / "rooted")
    ks = SimulatedHardwareKeystore(tmp_path / "r.pem", verified_boot="ORANGE", locked=False)
    c.append(seal(sample_ftr(), c.head(), 0, ks))
    report = verify_record(c._paths()[0].read_bytes())
    assert not report.ok
    assert any("modified device" in f for f in report.failures)


def test_a_location_disagreement_is_recorded_not_suppressed(tmp_path):
    """§5 — the inconsistency must reach the defence as well as the prosecution."""
    c = Chain(tmp_path / "loc")
    ks = SimulatedHardwareKeystore(tmp_path / "l.pem")
    f = sample_ftr()
    f.location_bundle["corroboration_channels_agreeing"] = 2
    f.location_bundle["spoof_indicators"] = ["serving cell conflicts with fix by 310 km"]
    c.append(seal(f, c.head(), 0, ks))

    report = verify_record(c._paths()[0].read_bytes())
    assert report.ok, "a disagreement is recorded, not a verification failure"
    assert any("Only 2 of 4" in a for a in report.asserted)
    assert any("310 km" in a for a in report.asserted)
