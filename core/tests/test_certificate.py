"""L6 — the statutory output, and the promises it must not break."""

import json

import pytest

from factory import SimulatedHardwareKeystore, sample_ftr
from ftr.certcli import main as cert_main
from ftr.certificate import SCHEDULE_PATH, Schedule, build_certificate
from ftr.chain import Chain
from ftr.esakshya import build_envelope, write_bundle
from ftr.record import seal
from ftr.verifier import verify_record


@pytest.fixture
def record(tmp_path):
    ks = SimulatedHardwareKeystore(tmp_path / "hw.pem")
    chain = Chain(tmp_path / "chain")
    f = sample_ftr("opiate_class")
    f.ndps["fir_reference"] = "142/2026 PS Kadugodi"
    f.location_bundle["corroboration_channels_agreeing"] = 2
    f.location_bundle["spoof_indicators"] = ["serving cell conflicts with fix by 310 km"]
    rec = seal(f, chain.head(), 0, ks)
    chain.append(rec)
    return rec


@pytest.fixture
def verified_schedule():
    """The shipped schedule with verified flipped on — what it looks like once
    track E has transcribed the Act."""
    raw = json.loads(SCHEDULE_PATH.read_text())
    raw["verified"] = True
    raw["source"] = "Bharatiya Sakshya Adhiniyam 2023, bare Act"
    raw["transcribed_by"] = "test"
    return Schedule(raw)


# --- the three rules ------------------------------------------------------- #

def test_the_shipped_schedule_is_marked_unverified():
    """If this ever fails without a transcription, someone flipped a flag they
    should not have. The labels are paraphrases until the Act is read."""
    s = Schedule.load()
    assert not s.verified
    assert s.raw["source"] is None
    assert "UNVERIFIED" in " ".join(s.raw["_README"])


def test_an_unverified_schedule_produces_a_draft(record):
    cert = build_certificate(record)
    assert cert.is_draft
    text = cert.text()
    assert "DRAFT — NOT FOR FILING" in text
    assert "transcribe the Schedule" in text
    assert cert.status == "DRAFT — NOT FOR FILING"


def test_a_verified_schedule_drops_the_draft_banner(record, verified_schedule):
    cert = build_certificate(record, verified_schedule)
    assert not cert.is_draft
    assert "DRAFT" not in cert.text()
    assert cert.status == "READY FOR SIGNATURE"


def test_the_app_never_fills_a_field_a_person_must_attest(record, verified_schedule):
    """Rule 1. An auto-filled signature line is a forgery mechanism."""
    cert = build_certificate(record, verified_schedule)
    for part in ("part_a", "part_b"):
        for f in verified_schedule.fields(part):
            if f["filled_by"] == "person":
                assert f["key"] not in cert.values, f"{f['key']} must be left to a human"
                assert f["key"] in cert.blanks


def test_part_b_is_left_entirely_to_the_expert(record, verified_schedule):
    cert = build_certificate(record, verified_schedule)
    for f in verified_schedule.fields("part_b"):
        assert f["key"] not in cert.values
    assert "[ to be completed by hand ]" in cert.text()


def test_nothing_is_asserted_that_the_record_does_not_carry(tmp_path, verified_schedule):
    """Rule 2. A missing operator id must not become an empty string that later
    reads as a positive statement about who held the device."""
    ks = SimulatedHardwareKeystore(tmp_path / "k.pem")
    f = sample_ftr()
    f.operator = {"biometric_unlock_used": False}      # no id at all
    f.captured_at = {"uptime_ms": 1}                    # no device clock
    rec = seal(f, b"\x00" * 32, 0, ks)

    cert = build_certificate(rec, verified_schedule)
    assert "device_operator" not in cert.values
    assert "period_of_use" not in cert.values
    assert "device_operator" in cert.blanks


# --- the statutory requirement --------------------------------------------- #

def test_the_certificate_states_the_hash_and_the_algorithm(record, verified_schedule):
    """The one §63 requirement we are confident of: hash value plus algorithm."""
    cert = build_certificate(record, verified_schedule)
    assert cert.values["hash_value"] == record.digest.hex()
    assert "SHA-256" in cert.values["hash_algorithm"]
    assert record.digest.hex() in cert.text()


def test_the_certificate_never_claims_a_period_of_regular_use_it_cannot_evidence(record, verified_schedule):
    """One record is one moment. Claiming an unevidenced period would be the kind
    of boilerplate that gets a certificate thrown out."""
    cert = build_certificate(record, verified_schedule)
    period = cert.values["period_of_use"]
    assert "not independently corroborated" in period
    assert "ledger bounds when it was created" in period


def test_the_certificate_says_presumptive_on_its_face(record, verified_schedule):
    text = build_certificate(record, verified_schedule).text()
    assert "PRESUMPTIVE" in text.upper()
    assert "does not replace laboratory analysis" in text


def test_the_security_level_reaches_the_certificate(record, verified_schedule):
    cert = build_certificate(record, verified_schedule)
    assert "STRONGBOX" in cert.values["device_particulars"]


# --- the eSakshya envelope ------------------------------------------------- #

def test_the_envelope_routes_by_fir_and_memo(record):
    env = build_envelope(record)
    assert env["routing"]["fir_reference"] == "142/2026 PS Kadugodi"
    assert env["routing"]["seizure_memo_ref"] == "SM-2026-0913-07"
    assert env["system_of_record"] == "CCTNS-2.0"


def test_the_envelope_is_marked_provisional(record):
    """We have no published ingest spec. Saying so stops a downstream reader
    mistaking a plausible file for an integration."""
    env = build_envelope(record)
    assert "PROVISIONAL" in env["interface_status"]
    assert "open question 2" in env["interface_status"]


def test_the_envelope_carries_the_anomalies_forward(record):
    """An envelope that dropped these would hand the receiving system a cleaner
    story than the record tells."""
    env = build_envelope(record)
    assert env["location"]["channels_agreeing"] == 2
    assert env["location"]["anomalies"] == ["serving cell conflicts with fix by 310 km"]


def test_the_envelope_never_claims_to_be_confirmatory(record):
    env = build_envelope(record)
    assert env["result"]["presumptive"] is True
    assert env["result"]["confirmatory"] is False
    assert "does not identify a substance" in env["caveat"]


# --- the bundle ------------------------------------------------------------ #

def test_the_bundle_carries_the_record_as_bytes_not_as_json(record, tmp_path):
    """The digest is over canonical CBOR. A JSON rendering is unverifiable."""
    out = tmp_path / "bundle"
    written = write_bundle(record, out, certificate_text="cert", raw_frame=b"frame")
    ftr_files = [p for p in written if p.suffix == ".ftr"]
    assert len(ftr_files) == 1

    report = verify_record(ftr_files[0].read_bytes())
    assert report.ok, "\n".join(report.failures)


def test_the_bundle_tells_the_reader_how_to_distrust_us(record, tmp_path):
    out = tmp_path / "bundle"
    write_bundle(record, out, certificate_text="cert")
    readme = (out / "README.txt").read_text()
    assert "without trusting the app" in readme
    assert "ftr.cli record" in readme and "ftrverify record" in readme
    assert "Run both" in readme
    assert "presumptive" in readme.lower()


def test_the_bundle_records_the_certificate_status(record, tmp_path):
    cert = build_certificate(record)
    written = write_bundle(record, tmp_path / "b", certificate_text=cert.text())
    env = json.loads([p for p in written if p.name.endswith(".esakshya.json")][0].read_text())
    assert env["certificate"]["status"] == "DRAFT"


# --- the CLI --------------------------------------------------------------- #

def test_the_cli_exits_nonzero_while_the_schedule_is_unverified(record, tmp_path, capsys):
    """A script piping this into a filing system must stop until the Act is read."""
    path = tmp_path / "chain" / "000000.ftr"
    code = cert_main([str(path)])
    assert code == 3
    assert "DRAFT" in capsys.readouterr().out


def test_the_cli_reports_a_missing_record(tmp_path, capsys):
    assert cert_main([str(tmp_path / "nope.ftr")]) == 2
    assert "no such record" in capsys.readouterr().out
