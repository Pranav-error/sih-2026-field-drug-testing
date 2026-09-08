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
    """The shipped Schedule with verification flipped to official — what it looks
    like once someone has checked it against the Gazette."""
    raw = json.loads(SCHEDULE_PATH.read_text())
    raw["verified"] = True
    raw["verification_level"] = "official"
    raw["source"] = "eGazette PDF of the Act"
    return Schedule(raw)


# --- the three rules ------------------------------------------------------- #

def test_the_shipped_schedule_is_transcribed_but_not_gazette_verified():
    """The labels are a real transcription now, not paraphrases — but from a
    secondary source. If this ever fails without someone checking the Gazette,
    a flag was flipped that should not have been."""
    s = Schedule.load()
    assert not s.verified
    assert s.verification_level == "secondary"
    assert s.raw["source"], "a transcription must name where it came from"


def test_the_schedule_matches_the_structure_the_act_prescribes():
    """Two parts, Part A by the party and Part B by an expert, and BOTH state the
    hash. Getting the part assignment wrong would put the wrong person's oath on
    the wrong statement."""
    s = Schedule.load()
    parts = s.parts
    assert [p["id"] for p in parts] == ["part_a", "part_b"]
    assert "Party" in parts[0]["subtitle"]
    assert "Expert" in parts[1]["subtitle"]
    for p in parts:
        kinds = [i["kind"] for i in p["items"]]
        assert "hash" in kinds, f"{p['id']} must state the hash value"
        assert "signature" in kinds


def test_sha256_is_an_algorithm_the_schedule_itself_names():
    """One reason the record uses SHA-256 rather than something exotic."""
    s = Schedule.load()
    assert "SHA256" in s.raw["algorithms_named_in_the_schedule"]
    for _, item in s.items():
        if item["kind"] == "hash":
            assert "SHA256" in item["algorithms"]


def test_a_secondary_source_still_produces_a_draft(record):
    cert = build_certificate(record)
    assert cert.is_draft
    text = cert.text()
    assert "DRAFT — NOT FOR FILING" in text
    assert "official Gazette" in text, "the banner must name what is still missing"
    assert cert.status == "DRAFT — NOT FOR FILING"


def test_a_verified_schedule_drops_the_draft_banner(record, verified_schedule):
    cert = build_certificate(record, verified_schedule)
    assert not cert.is_draft
    assert "DRAFT" not in cert.text()
    assert cert.status == "READY FOR SIGNATURE"


def test_the_app_never_fills_a_field_a_person_must_attest(record, verified_schedule):
    """Rule 1. The Schedule's declarations begin "I do hereby solemnly affirm" —
    precisely the things no program may assert on someone's behalf."""
    cert = build_certificate(record, verified_schedule)
    for _, item in verified_schedule.items():
        if item["filled_by"] == "person":
            assert item["key"] not in cert.values, f"{item['key']} must be left to a human"
            assert item["key"] in cert.blanks


def test_no_oath_or_signature_is_ever_machine_filled(record, verified_schedule):
    cert = build_certificate(record, verified_schedule)
    for _, item in verified_schedule.items():
        if item["kind"] in ("signature", "datetimeplace"):
            assert item["key"] not in cert.values
    text = cert.text()
    assert "[ to be signed by hand ]" in text
    assert "solemnly affirm" in text


def test_part_b_is_left_entirely_to_the_expert(record, verified_schedule):
    """Part B is the expert's oath. The app populates none of it — including the
    hash, which the expert must state on their own responsibility."""
    cert = build_certificate(record, verified_schedule)
    for part in verified_schedule.parts:
        if part["id"] != "part_b":
            continue
        for item in part["items"]:
            assert item["key"] not in cert.values, f"{item['key']} is the expert's to state"


def test_statutory_fields_the_record_cannot_supply_are_named(record, verified_schedule):
    """Rule 2, made mechanical.

    Transcribing the real Schedule exposed a gap: the FTR schema was written before
    anyone had read what the certificate actually asks for, and it carries no make,
    model, serial number or IMEI. Rather than leaving that to be discovered by a
    magistrate, the certificate names it.
    """
    cert = build_certificate(record, verified_schedule)
    assert cert.missing_from_record, "the gap must be reported, not silently blank"
    assert any("Make & Model" in m for m in cert.missing_from_record)
    assert any("IMEI" in m for m in cert.missing_from_record)
    text = cert.text()
    assert "Statutory fields the record cannot supply" in text
    assert "record schema extended" in text


def test_a_record_that_carries_device_identity_closes_the_gap(tmp_path, verified_schedule):
    """And when the schema is extended, the gap disappears without a code change."""
    ks = SimulatedHardwareKeystore(tmp_path / "k2.pem")
    f = sample_ftr()
    f.device = {
        **f.device,
        "make_model": "Google Pixel 7a",
        "serial_number": "1A2B3C4D",
        "device_identifier": "IMEI 350000000000001",
    }
    rec = seal(f, b"\x00" * 32, 0, ks)

    cert = build_certificate(rec, verified_schedule)
    assert cert.missing_from_record == []
    assert cert.values["make_model"] == "Google Pixel 7a"
    assert "IMEI 350000000000001" in cert.text()


# --- the statutory requirement --------------------------------------------- #

def test_the_certificate_states_the_hash_and_ticks_the_algorithm(record, verified_schedule):
    """The requirement the Schedule states in both parts."""
    cert = build_certificate(record, verified_schedule)
    assert cert.values["hash_value"] == record.digest.hex()
    assert cert.values["hash_value__algorithm"] == "SHA256"
    text = cert.text()
    assert record.digest.hex() in text
    assert "[X] SHA256" in text, "the algorithm box must actually be ticked"
    assert "Hash report to be enclosed" in text


def test_the_device_type_tick_box_says_mobile(record, verified_schedule):
    text = build_certificate(record, verified_schedule).text()
    assert "[X] Mobile" in text


def test_the_ledger_position_reaches_the_certificate(record, verified_schedule):
    """The record's position in the append-only ledger is what actually bounds
    when it was created, so it goes in the free-text device field."""
    cert = build_certificate(record, verified_schedule)
    assert "append-only ledger" in cert.values["other_device_information"]


def test_the_certificate_says_presumptive_on_its_face(record, verified_schedule):
    text = build_certificate(record, verified_schedule).text()
    assert "PRESUMPTIVE" in text.upper()
    assert "does not replace laboratory analysis" in text


def test_the_security_level_reaches_the_certificate(record, verified_schedule):
    cert = build_certificate(record, verified_schedule)
    assert "STRONGBOX" in cert.values["other_device_information"]


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
