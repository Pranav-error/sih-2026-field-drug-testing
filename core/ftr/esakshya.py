"""L6 handoff — an envelope for eSakshya / CCTNS-2.0. Not a parallel evidence store.

MHA already runs eSakshya (NCRB) for audio-video recording of search and seizure,
being integrated into CCTNS-2.0. Its offline flow is the same trust model this
system uses: record locally, generate a hash, upload later.

So the correct posture is emphatically **not** to invent a competing evidence
store. Building one would create a new surveillance surface and a new liability
with no benefit, and it is explicitly among the things ARCHITECTURE.md §12 says we
are not building. This module emits an envelope that:

  * carries its own hash in the form the offline flow already expects,
  * references the FIR and seizure memo so it lands in the right locker,
  * treats CCTNS-2.0 as the system of record.

⚠ The field names below are **provisional**. ARCHITECTURE.md §13 open question 2
asks whether eSakshya exposes any documented ingest interface at all; until
somebody answers that, this is a well-formed file with a plausible shape, not an
integration. It is marked as such in the envelope itself so nobody downstream
mistakes it for one.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from .record import SealedRecord

__all__ = ["build_envelope", "write_bundle"]

INTERFACE_STATUS = (
    "PROVISIONAL — field names are not taken from a published eSakshya/CCTNS-2.0 "
    "ingest specification. See docs/ARCHITECTURE.md section 13, open question 2."
)


def build_envelope(rec: SealedRecord, certificate_text: str | None = None) -> dict[str, Any]:
    """Build the handoff envelope for one sealed record."""
    body = rec.body
    ndps = body.get("ndps", {})
    loc = body.get("location_bundle", {})
    cls = body.get("classification", {})
    col = body.get("colorimetry", {})

    envelope: dict[str, Any] = {
        "envelope_version": 1,
        "interface_status": INTERFACE_STATUS,
        "produced_by": "SIH26231 field companion",
        "system_of_record": "CCTNS-2.0",

        "routing": {
            "fir_reference": ndps.get("fir_reference"),
            "seizure_memo_ref": ndps.get("seizure_memo_ref"),
            "sample_ids": ndps.get("sample_ids", []),
        },

        "record": {
            "record_uuid": body.get("record_uuid"),
            "sequence": body.get("sequence"),
            "hash_value": rec.digest.hex(),
            "hash_algorithm": "SHA-256",
            "prev_record_hash": body.get("prev_record_hash", b"").hex(),
            "signature_algorithm": "ECDSA-P256",
            "key_security_level": (rec.attestation or {}).get("security_level"),
        },

        "result": {
            "presumptive": True,
            "confirmatory": False,
            "label": cls.get("label"),
            "prediction_set": cls.get("prediction_set", []),
            "alpha_x1000": cls.get("alpha_x1000"),
            "gate_passed": col.get("gate_passed"),
            "refusals": col.get("refusals", []),
        },

        "location": {
            "lat_x1e7": loc.get("lat_x1e7"),
            "lon_x1e7": loc.get("lon_x1e7"),
            "accuracy_m": loc.get("accuracy_m"),
            "channels_agreeing": loc.get("corroboration_channels_agreeing"),
            "channels_total": loc.get("corroboration_channels_total"),
            # Carried forward deliberately. An envelope that drops the anomalies
            # would hand the receiving system a cleaner story than the record tells.
            "anomalies": loc.get("spoof_indicators", []),
        },

        "caveat": (
            "Presumptive field test. A screening indication only: it does not identify "
            "a substance, does not establish quantity, and does not replace laboratory "
            "analysis under NDPS procedure."
        ),
    }

    if certificate_text is not None:
        envelope["certificate"] = {
            "statute": "Bharatiya Sakshya Adhiniyam 2023, section 63",
            "sha256": hashlib.sha256(certificate_text.encode()).hexdigest(),
            "status": "DRAFT" if "DRAFT" in certificate_text else "READY FOR SIGNATURE",
        }
    return envelope


def write_bundle(rec: SealedRecord, out_dir: Path, certificate_text: str | None = None,
                 raw_frame: bytes | None = None) -> list[Path]:
    """Write a self-contained handoff bundle. Returns the files written.

    The sealed record goes in as raw bytes, not as JSON: the envelope is a
    convenience for the receiving system, and the *record* is the evidence. A
    bundle that carried only a JSON rendering would be unverifiable, because the
    digest is over the canonical CBOR and nothing else.
    """
    out_dir.mkdir(parents=True, exist_ok=True)
    written: list[Path] = []

    seq = rec.body.get("sequence", 0)
    stem = f"{seq:06d}"

    p = out_dir / f"{stem}.ftr"
    p.write_bytes(rec.to_envelope())
    written.append(p)

    p = out_dir / f"{stem}.esakshya.json"
    p.write_text(json.dumps(build_envelope(rec, certificate_text), indent=2) + "\n")
    written.append(p)

    if certificate_text is not None:
        p = out_dir / f"{stem}.bsa63.txt"
        p.write_text(certificate_text + "\n")
        written.append(p)

    if raw_frame is not None:
        p = out_dir / f"{stem}.raw.jpg"
        p.write_bytes(raw_frame)
        written.append(p)

    readme = out_dir / "README.txt"
    readme.write_text(
        "Field Test Record handoff bundle (SIH26231)\n"
        "===========================================\n\n"
        "  *.ftr            the sealed record. THIS is the evidence; everything\n"
        "                   else here is derived from it and can be recomputed.\n"
        "  *.esakshya.json  routing envelope for CCTNS-2.0. Provisional field names.\n"
        "  *.bsa63.txt      certificate under BSA 2023 s.63, Part A pre-populated.\n"
        "  *.raw.jpg        the untouched frame, if included.\n\n"
        "Verify without trusting the app that produced this:\n\n"
        "  python -m ftr.cli record <file>.ftr --image raw_image_sha256=<file>.raw.jpg\n"
        "  dart run ftr_verify:ftrverify record <file>.ftr\n\n"
        "The two verifiers are independent implementations. Run both.\n\n"
        "A presumptive field test is a screening indication. It does not identify a\n"
        "substance and does not replace laboratory analysis.\n"
    )
    written.append(readme)
    return written
