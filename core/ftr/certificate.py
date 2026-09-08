"""L6 — the statutory output.

Section 63 of the Bharatiya Sakshya Adhiniyam 2023 replaced section 65B of the
Indian Evidence Act with effect from 1 July 2024. Its certificate comes in two
parts — one completed by the person in charge of the device, one by an expert —
and it must state **the hash value of the record and the algorithm used**.

The app computed exactly that at the moment of capture. So Part A can be
pre-populated the instant a record is sealed, which is what makes this layer
nearly free once L4 and L5 exist, and is the part of the system nobody else
builds.

Three rules this module will not bend:

1. **The app never signs for anyone.** Every field a human must attest is emitted
   empty and marked. An auto-filled signature line is a forgery mechanism.
2. **Nothing is asserted that the record does not carry.** If a field has no
   value, it is emitted as absent rather than guessed.
3. **Unverified statutory labels produce a DRAFT.** The field labels in
   ``data/bsa63_schedule.json`` are paraphrases until somebody transcribes the
   Schedule from the bare Act. Until then every certificate says on its face that
   it must not be filed.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .record import SealedRecord

__all__ = ["Schedule", "Certificate", "build_certificate", "SCHEDULE_PATH"]

SCHEDULE_PATH = Path(__file__).parent / "data" / "bsa63_schedule.json"

DRAFT_BANNER = [
    "*** DRAFT — NOT FOR FILING ***",
    "",
    "The statutory field labels below are UNVERIFIED PARAPHRASES. They have not",
    "been transcribed from the bare Act and are very likely wrong in wording, and",
    "possibly in numbering and part assignment.",
    "",
    "Before any certificate is filed, transcribe the Schedule to section 63 from",
    "the Act itself into ftr/data/bsa63_schedule.json and set verified = true.",
    "The computed values below (hash, algorithm, device, period) are correct and",
    "come from the signed record; only the LABELS are provisional.",
]


@dataclass(frozen=True)
class Schedule:
    """The certificate's field structure, loaded from data."""

    raw: dict[str, Any]

    @classmethod
    def load(cls, path: Path = SCHEDULE_PATH) -> "Schedule":
        return cls(json.loads(path.read_text()))

    @property
    def verified(self) -> bool:
        return bool(self.raw.get("verified"))

    @property
    def statute(self) -> str:
        return self.raw.get("statute", "unknown statute")

    def part(self, name: str) -> dict[str, Any]:
        return self.raw[name]

    def fields(self, part: str) -> list[dict[str, str]]:
        return self.part(part)["fields"]


@dataclass(frozen=True)
class Certificate:
    """A populated certificate. Never final, never signed, by construction."""

    schedule: Schedule
    values: dict[str, str]              # machine-filled values, by field key
    blanks: list[str]                   # field keys a human must complete
    record_digest: str
    is_draft: bool

    @property
    def status(self) -> str:
        return "DRAFT — NOT FOR FILING" if self.is_draft else "READY FOR SIGNATURE"

    def text(self, width: int = 78) -> str:
        out: list[str] = []
        if self.is_draft:
            out += DRAFT_BANNER + ["", "=" * width, ""]

        out.append(f"CERTIFICATE UNDER {self.schedule.statute.upper()}")
        out.append("=" * width)
        out.append("")

        for part in ("part_a", "part_b"):
            meta = self.schedule.part(part)
            title = part.replace("_", " ").upper()
            out.append(f"{title} — {meta['signatory_role']}")
            out.append("-" * width)
            for f in self.schedule.fields(part):
                key, label = f["key"], f["label"]
                if key in self.values:
                    value = self.values[key]
                    out.append(f"  {label}:")
                    for line in _wrap(value, width - 6):
                        out.append(f"      {line}")
                else:
                    marker = "[ to be completed by hand ]"
                    out.append(f"  {label}:")
                    out.append(f"      {marker}")
            out.append("")

        out.append("-" * width)
        out.append(f"Status: {self.status}")
        out.append(f"Fields awaiting a human signatory: {len(self.blanks)}")
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


def build_certificate(rec: SealedRecord, schedule: Schedule | None = None) -> Certificate:
    """Populate Part A from a sealed record. Part B is left entirely to the expert."""
    schedule = schedule or Schedule.load()
    body = rec.body

    device = body.get("device", {})
    operator = body.get("operator", {})
    captured = body.get("captured_at", {})
    att = rec.attestation or {}

    device_bits = [
        f"Android device, verified boot {device.get('verified_boot_state', 'UNKNOWN')}",
        f"bootloader {device.get('bootloader_state', 'UNKNOWN')}",
        f"OS patch level {device.get('os_patch_level', 'unknown')}",
        f"signing key security level {att.get('security_level', 'UNKNOWN')}",
    ]

    values: dict[str, str] = {
        "device_particulars": "; ".join(device_bits),
        "record_produced": f"Field Test Record {body.get('record_uuid', 'unknown')}, "
                           f"sequence {body.get('sequence', '?')} on this device's ledger",
        "hash_value": rec.digest.hex(),
        "hash_algorithm": "SHA-256 over the canonical CBOR encoding of the record",
    }

    if operator.get("id"):
        values["device_operator"] = str(operator["id"])
    if captured.get("device_clock"):
        # One record, one moment. Claiming a "period of regular use" the record does
        # not evidence would be asserting something the device never observed.
        values["period_of_use"] = (
            f"This record was created at {captured['device_clock']} (device clock). "
            f"The device clock is not independently corroborated; the record's position "
            f"in the append-only ledger bounds when it was created."
        )

    blanks = [f["key"] for part in ("part_a", "part_b")
              for f in schedule.fields(part) if f["key"] not in values]

    return Certificate(
        schedule=schedule,
        values=values,
        blanks=blanks,
        record_digest=rec.digest.hex(),
        is_draft=not schedule.verified,
    )
