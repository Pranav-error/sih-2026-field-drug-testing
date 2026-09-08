"""L6 — the statutory output.

Section 63 of the Bharatiya Sakshya Adhiniyam 2023 replaced section 65B of the
Indian Evidence Act with effect from 1 July 2024. The Schedule to the Act — "[See
section 63(4)(c)]" — sets out a two-part certificate: Part A completed by the
party producing the record, Part B by an expert. **Both parts** must state the
hash value and name the algorithm used, and SHA256 is one of the algorithms the
Schedule names on its face.

The app computed exactly that at the moment of capture, so the machine-knowable
fields can be pre-populated the instant a record is sealed. That is what makes
this layer nearly free once L4 and L5 exist, and it is the part of the system
nobody else builds.

Three rules this module will not bend:

1. **The app never signs for anyone.** Every field a human must attest is emitted
   blank and marked. An auto-filled signature line is a forgery mechanism, and the
   Schedule's declarations ("I do hereby solemnly affirm…") are precisely the
   things no program may assert.
2. **Nothing is asserted that the record does not carry.** A field the FTR cannot
   supply is emitted blank and named in :attr:`Certificate.missing_from_record`.
3. **An unverified Schedule can only produce a DRAFT.** The text in
   ``data/bsa63_schedule.json`` is transcribed from a bare-Act repository, not
   from the official Gazette, so every certificate says so on its face.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .record import SealedRecord

__all__ = ["Schedule", "Certificate", "build_certificate", "SCHEDULE_PATH"]

SCHEDULE_PATH = Path(__file__).parent / "data" / "bsa63_schedule.json"

_BANNERS = {
    "paraphrase": [
        "*** DRAFT — NOT FOR FILING ***",
        "",
        "The statutory field labels below are UNVERIFIED PARAPHRASES. They have not",
        "been transcribed from any source and are very likely wrong.",
    ],
    "secondary": [
        "*** DRAFT — NOT FOR FILING ***",
        "",
        "The field labels below are transcribed from a bare-Act repository, not from",
        "the official Gazette. They read as faithful, but they have not been checked",
        "against the authoritative text.",
        "",
        "To clear this stamp: compare data/bsa63_schedule.json against the eGazette",
        "PDF of the Act, then set verification_level to 'official' and verified to",
        "true. The computed values below are correct either way and come from the",
        "signed record; only the provenance of the LABELS is provisional.",
    ],
}


@dataclass(frozen=True)
class Schedule:
    """The certificate's structure and text, loaded from data."""

    raw: dict[str, Any]

    @classmethod
    def load(cls, path: Path = SCHEDULE_PATH) -> "Schedule":
        return cls(json.loads(path.read_text()))

    @property
    def verified(self) -> bool:
        return bool(self.raw.get("verified"))

    @property
    def verification_level(self) -> str:
        return self.raw.get("verification_level", "paraphrase")

    @property
    def statute(self) -> str:
        return self.raw.get("statute", "unknown statute")

    @property
    def parts(self) -> list[dict[str, Any]]:
        return self.raw["parts"]

    def items(self) -> list[tuple[str, dict[str, Any]]]:
        return [(p["id"], it) for p in self.parts for it in p["items"]]


@dataclass(frozen=True)
class Certificate:
    """A populated certificate. Never final, never signed, by construction."""

    schedule: Schedule
    values: dict[str, Any]
    blanks: list[str]
    missing_from_record: list[str] = field(default_factory=list)
    record_digest: str = ""
    is_draft: bool = True

    @property
    def status(self) -> str:
        return "DRAFT — NOT FOR FILING" if self.is_draft else "READY FOR SIGNATURE"

    # -- rendering ---------------------------------------------------------- #

    def _render_item(self, item: dict[str, Any], out: list[str], width: int) -> None:
        kind, key = item["kind"], item["key"]
        value = self.values.get(key)

        if kind == "prose":
            for line in _wrap(item["text"], width - 2):
                out.append(f"  {line}")
            out.append("")

        elif kind == "checkboxes":
            ticked = value if isinstance(value, str) else None
            boxes = [f"[{'X' if o == ticked else ' '}] {o}" for o in item["options"]]
            for line in _wrap("   ".join(boxes), width - 2):
                out.append(f"  {line}")
            if item.get("suffix"):
                out.append(f"  {item['suffix']}")
            out.append("")

        elif kind == "field":
            shown = value if value else "______"
            out.append(f"  {item['label']}: {shown}")
            if not value:
                out.append("      ^ blank")
            out.append("")

        elif kind == "hash":
            for line in _wrap(item["text"], width - 2):
                out.append(f"  {line}")
            if value:
                out.append("")
                out.append(f"      {value}")
            algo = self.values.get(f"{key}__algorithm")
            boxes = [f"[{'X' if a == algo else ' '}] {a}" for a in item["algorithms"]]
            out.append(f"      {'  '.join(boxes)}")
            out.append(f"      {item['note']}")
            out.append("")

        elif kind == "signature":
            out.append(f"  {item['label']}")
            out.append("      ______________________   [ to be signed by hand ]")
            out.append("")

        elif kind == "datetimeplace":
            for line in _wrap(item["label"], width - 2):
                out.append(f"  {line}")
            out.append("      [ to be completed by hand ]")
            out.append("")

    def text(self, width: int = 78) -> str:
        out: list[str] = []
        if self.is_draft:
            out += _BANNERS.get(self.schedule.verification_level, _BANNERS["paraphrase"])
            out += ["", "=" * width, ""]

        out.append(f"THE SCHEDULE — {self.schedule.raw.get('title', 'CERTIFICATE')}")
        out.append(self.schedule.raw.get("reference", ""))
        out.append(f"({self.schedule.statute})")
        out.append("=" * width)
        out.append("")

        for part in self.schedule.parts:
            out.append(f"{part['title']}  {part['subtitle']}")
            out.append("-" * width)
            out.append("")
            for item in part["items"]:
                self._render_item(item, out, width)

        out.append("-" * width)
        out.append(f"Status: {self.status}")
        out.append(f"Fields awaiting a human: {len(self.blanks)}")
        if self.missing_from_record:
            out.append("")
            out.append("Statutory fields the record cannot supply:")
            for m in self.missing_from_record:
                out.append(f"  - {m}")
            out.append("  These must be completed by hand, or the record schema extended.")
        out.append("")
        out.append("This certificate accompanies a PRESUMPTIVE field test. A presumptive")
        out.append("test is a screening indication only. It does not identify a substance")
        out.append("and does not replace laboratory analysis.")
        return "\n".join(out)


def _wrap(s: str, w: int) -> list[str]:
    words, line, out = s.split(), "", []
    for word in words:
        if line and len(line) + 1 + len(word) > w:
            out.append(line)
            line = word
        else:
            line = f"{line} {word}".strip()
    if line:
        out.append(line)
    return out or [""]


# --------------------------------------------------------------------------- #

def build_certificate(rec: SealedRecord, schedule: Schedule | None = None) -> Certificate:
    """Populate what the record knows. Everything else stays blank and named."""
    schedule = schedule or Schedule.load()
    body = rec.body
    device = body.get("device", {})
    att = rec.attestation or {}

    values: dict[str, Any] = {
        # The Schedule's own tick-list. A phone is "Mobile".
        "device_type": "Mobile",
        # Both parts require the hash and the algorithm. SHA256 is named in the
        # Schedule itself, which is one reason the record uses it.
        "hash_value": rec.digest.hex(),
        "hash_value__algorithm": "SHA256",
    }

    # Device identity, as far as the record carries it.
    if device.get("make_model"):
        values["make_model"] = str(device["make_model"])
    if device.get("serial_number"):
        values["serial_number"] = str(device["serial_number"])
    if device.get("device_identifier"):
        values["device_identifier"] = str(device["device_identifier"])

    context = [
        f"Field Test Record {body.get('record_uuid', 'unknown')}",
        f"sequence {body.get('sequence', '?')} on this device's append-only ledger",
        f"verified boot {device.get('verified_boot_state', 'UNKNOWN')}",
        f"bootloader {device.get('bootloader_state', 'UNKNOWN')}",
        f"OS patch level {device.get('os_patch_level', 'unknown')}",
        f"signing key security level {att.get('security_level', 'UNKNOWN')}",
    ]
    values["other_device_information"] = "; ".join(context)

    # Rule 2, made mechanical: statutory fields the record is expected to supply
    # but cannot. Transcribing the real Schedule is what surfaced these — the FTR
    # schema was written before anyone had read what the certificate asks for.
    expected_from_record = {
        "make_model": "Make & Model of the device",
        "serial_number": "Serial Number of the device",
        "device_identifier": "IMEI/UIN/UID/MAC/Cloud ID",
    }
    missing = [label for key, label in expected_from_record.items() if key not in values]

    blanks = [it["key"] for _, it in schedule.items() if it["key"] not in values]

    return Certificate(
        schedule=schedule,
        values=values,
        blanks=blanks,
        missing_from_record=missing,
        record_digest=rec.digest.hex(),
        is_draft=not schedule.verified,
    )
