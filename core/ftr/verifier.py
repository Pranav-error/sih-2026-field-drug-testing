"""The independent verifier.

Runs with no network and no trust in the app that produced the record. It sorts
every claim into one of three buckets and prints all three at equal weight:

    PROVEN         re-derived here, from the bytes, by this program
    ASSERTED       present in the record, but nothing in the bundle establishes it
    UNVERIFIABLE   outside what any bundle of bytes could establish

The third bucket is the reason the program exists. A verifier that only ever
prints VALID teaches courts to over-trust it, which is a worse outcome than the
subjective status quo it replaces.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from .attestation import parse_attestation
from .canonical_cbor import dumps, is_canonical, loads
from .chain import Chain
from .record import SealedRecord

__all__ = ["Report", "verify_record", "verify_chain"]


@dataclass
class Report:
    proven: list[str] = field(default_factory=list)
    asserted: list[str] = field(default_factory=list)
    unverifiable: list[str] = field(default_factory=list)
    failures: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.failures

    def text(self, width: int = 78) -> str:
        def block(title: str, items: list[str], mark: str) -> list[str]:
            if not items:
                return []
            out = [title, "-" * len(title)]
            for it in items:
                first = True
                for line in _wrap(it, width - 4):
                    out.append(f" {mark if first else ' '}  {line}")
                    first = False
            out.append("")
            return out

        lines: list[str] = []
        if self.failures:
            lines += block("FAILED", self.failures, "x")
        lines += block("PROVEN", self.proven, "+")
        lines += block("ASSERTED, NOT PROVEN", self.asserted, "~")
        lines += block("UNVERIFIABLE FROM THIS BUNDLE", self.unverifiable, ".")
        verdict = "VERIFIED" if self.ok else "VERIFICATION FAILED"
        lines.append(f"{verdict} — {len(self.proven)} proven, "
                     f"{len(self.asserted)} asserted, {len(self.unverifiable)} unverifiable")
        if self.ok:
            lines.append("A verified record is not a true result. It is an unaltered one.")
        return "\n".join(lines)


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

def verify_record(blob: bytes, images: dict[str, bytes] | None = None) -> Report:
    """Verify one envelope. ``images`` maps a record field name to file bytes."""
    r = Report()

    try:
        rec = SealedRecord.from_envelope(blob)
    except Exception as e:
        r.failures.append(f"Envelope will not decode: {e}")
        return r

    # 1. canonical encoding ------------------------------------------------- #
    if is_canonical(rec.body_cbor):
        r.proven.append(
            "The record body is canonically encoded: it decodes and re-encodes to "
            "the same bytes, so the digest is reproducible by any implementation."
        )
    else:
        r.failures.append(
            "The record body is not canonical CBOR. Its digest is not reproducible, "
            "so no signature over it means anything."
        )
        return r

    body = rec.body
    r.proven.append(f"SHA-256 of the body recomputes to {rec.digest.hex()}.")

    # 2. signature ---------------------------------------------------------- #
    if rec.signature_valid():
        r.proven.append(
            "The signature verifies against the recomputed digest under the "
            "public key carried in the envelope."
        )
    else:
        r.failures.append(
            "The signature does not verify over the recomputed digest. The record "
            "has been altered since it was sealed, or it was never sealed by this key."
        )

    # 3. what the key actually proves --------------------------------------- #
    att = rec.attestation or {}
    level = att.get("security_level", "UNKNOWN")

    # The certificate outranks the record. Everything in `att` was written by the
    # app; the attestation extension was written by the secure element and signed
    # by it. Where they disagree the certificate wins, and the disagreement is
    # itself reported — an app claiming more than its own hardware attests to is
    # the single most interesting thing a verifier could find.
    chain = att.get("cert_chain") or []
    info = parse_attestation(chain[0]) if chain else None
    if info is not None:
        level = info.attestation_security_level
        r.proven.append(
            f"The attestation certificate states the key is {level}-backed. This "
            "is read from the certificate, not from the record: the app's own "
            "claim about its hardware carries no weight."
        )
        claimed = att.get("security_level")
        if claimed and claimed != level:
            r.failures.append(
                f"The record claims a {claimed} key; the attestation certificate "
                f"says {level}. The record overstates its own hardware."
            )
        if info.verified_boot_state is not None:
            if info.boot_colour == "GREEN" and info.device_locked:
                r.proven.append(
                    "Verified boot was GREEN and the bootloader locked, per the "
                    "attestation certificate: the device was running unmodified "
                    "signed firmware when the key was created."
                )
            else:
                r.failures.append(
                    f"Verified boot is {info.boot_colour} and the bootloader "
                    f"{'locked' if info.device_locked else 'unlocked'}, per the "
                    "attestation certificate. The key was created on a modified "
                    "device."
                )
        else:
            r.asserted.append(
                "The attestation certificate carries no root-of-trust block, so "
                "verified boot state could not be read from it."
            )
        r.asserted.append(
            f"The attestation chain is {len(chain)} certificate(s) long. This "
            "verifier reads the leaf but does not yet walk the chain to a Google "
            "hardware root, so the certificate's own authenticity is unchecked."
        )
    if level == "STRONGBOX":
        r.proven.append(
            "Key attestation states the signing key was generated in StrongBox, a "
            "discrete secure element, and is non-exportable."
        )
    elif level == "TEE":
        r.proven.append(
            "Key attestation states the signing key was generated in the TEE and is "
            "non-exportable. This is weaker than StrongBox: no discrete secure element."
        )
    else:
        r.failures.append(
            f"Signing key security level is {level}. The key is not hardware-backed, so "
            "the signature proves only that whoever held the key file made this record. "
            "It says nothing about which device produced it. Development records must "
            "never be presented as evidence."
        )

    if att.get("key_exportable"):
        r.asserted.append(
            "The key is marked exportable, so a copy may exist elsewhere. Authorship "
            "is not established by this signature alone."
        )

    vbs = att.get("verified_boot_state", "UNKNOWN")
    if info is not None:
        pass          # already reported from the certificate, which outranks this
    elif vbs == "GREEN" and att.get("bootloader_locked"):
        r.proven.append(
            "Verified boot was GREEN and the bootloader locked when the key was "
            "attested: the device was running unmodified signed firmware."
        )
    elif vbs in ("UNKNOWN", "IN_ATTESTATION"):
        r.asserted.append("Verified boot state is unknown; device integrity is not established.")
    else:
        r.failures.append(
            f"Verified boot state is {vbs} and the bootloader "
            f"{'is locked' if att.get('bootloader_locked') else 'is unlocked'}. "
            "The record was produced on a modified device."
        )

    if not att.get("cert_chain_len") and not chain:
        r.asserted.append(
            "No attestation certificate chain is present, so the hardware claims above "
            "cannot be traced to a root certificate authority."
        )

    # 4. images ------------------------------------------------------------- #
    import hashlib
    cap = body.get("capture", {})
    for fieldname, want in cap.items():
        if not fieldname.endswith("_sha256") or not isinstance(want, bytes):
            continue
        supplied = (images or {}).get(fieldname)
        if supplied is None:
            r.asserted.append(
                f"{fieldname} is recorded as {want.hex()[:16]}… but the file was not "
                "supplied to this verifier, so the image behind it was not checked."
            )
        elif hashlib.sha256(supplied).digest() == want:
            r.proven.append(
                f"The supplied {fieldname.removesuffix('_sha256')} hashes to the value in "
                "the record: the image is byte-identical to the one sealed at capture."
            )
        else:
            r.failures.append(
                f"The supplied {fieldname.removesuffix('_sha256')} does NOT match the "
                "hash in the record. The image has been altered since capture."
            )

    # 5. liveness ----------------------------------------------------------- #
    live = body.get("liveness", {})
    if not live:
        r.asserted.append(
            "This record carries no liveness block at all. It predates the check, or "
            "the app that made it does not perform one."
        )
    elif not live.get("checked"):
        r.asserted.append(
            "No liveness check was performed — only one frame was captured. This "
            "record cannot be distinguished from a photograph of a card, which is "
            "the attack two-view parallax exists to refuse."
        )
    else:
        got = live.get("displacement_px_x100", 0) / 100
        want = live.get("predicted_px_x100", 0) / 100
        h = live.get("tab_height_mm_x10", 0) / 10
        base = live.get("baseline_mm_x10", 0) / 10
        if live.get("live"):
            r.asserted.append(
                f"The app measured {got:.1f} px of parallax against {want:.1f} px "
                f"predicted for the {h:.0f} mm liveness tab over a {base:.0f} mm "
                "baseline, and concluded the scene had depth. Re-deriving this "
                "requires both frames; supply them to move it from asserted to proven."
            )
        else:
            r.failures.append(
                f"LIVENESS FAILED at capture: {got:.1f} px of parallax against "
                f"{want:.1f} px predicted. The scene was flat, which is what a "
                "photograph of a print or a screen looks like. The record is "
                "authentic; what it photographed is in question."
            )

    # 6. claims the bundle carries but cannot support ----------------------- #
    ts = body.get("captured_at", {})
    if "device_clock" in ts:
        r.asserted.append(
            f"Capture time is stated as {ts['device_clock']}, taken from the device "
            "clock. Nothing here proves the clock was correct; only the chain and an "
            "anchor bound when this record was made."
        )
    operator = body.get("operator", {})
    if operator.get("biometric_unlock_used"):
        r.asserted.append(
            "Key use was gated by a biometric. That binds the record to the enrolled "
            "device, not to the named person."
        )
    else:
        r.asserted.append(
            "Key use was NOT gated by a biometric. Nothing in this record connects it "
            "to a person at all — only to the device that signed it."
        )
    if not operator.get("id"):
        r.asserted.append(
            "No operator credential was recorded. The record does not name who "
            "performed the test."
        )
    kit = body.get("kit", {})
    if kit.get("reagent_type"):
        r.asserted.append(
            f"Reagent is declared as {kit['reagent_type']} by the operator. It is not "
            "machine-read, by design — the system is kit-agnostic."
        )
    for name in body.get("omitted", []):
        r.asserted.append(f"Field '{name}' was recorded as unavailable at capture.")

    loc = body.get("location_bundle", {})
    score = loc.get("corroboration_channels_agreeing")
    total = loc.get("corroboration_channels_total")
    not_collected = loc.get("channels_not_collected") or []
    if loc.get("available") is False:
        r.asserted.append(
            f"No position was recorded: {loc.get('status', 'reason not stated')}. "
            "Nothing in this record places it anywhere."
        )
    elif score is not None and total:
        collected = ", ".join(loc.get("channels_collected") or ["unspecified"])
        if score == total:
            # A single agreeing channel is not corroboration. Reporting it as
            # "all channels agreed" would be true and deeply misleading.
            r.asserted.append(
                f"{score} of {total} location channel(s) agreed — collected: {collected}. "
                + (f"NOT collected: {', '.join(not_collected)}. A single channel is a "
                   "claim, not corroboration." if total < 2 else "")
            )
        else:
            r.asserted.append(
                f"Only {score} of {total} location channels agreed. The disagreement is "
                "recorded below and is available to either party."
            )
    for ind in loc.get("spoof_indicators", []):
        r.asserted.append(f"Location anomaly recorded at capture: {ind}")

    # 7. the floor ---------------------------------------------------------- #
    cls = body.get("classification", {})
    if not live.get("checked"):
        r.unverifiable.append(
            "Whether the strip photographed was physically present, rather than a "
            "printed or displayed image of one. Nothing in a single frame can "
            "establish that."
        )
    r.unverifiable += [
        "Whether the substance photographed is the substance seized. No bundle of "
        "bytes can establish this; it rests on the seizure procedure and the witnesses.",
        "Whether the colorimetric reaction had fully developed when the frame was taken.",
        "The correctness of the result itself. This is a presumptive screening test "
        f"reported at risk level alpha={cls.get('alpha_x1000', '?')}/1000; it is not "
        "confirmatory and does not identify a substance.",
    ]
    return r


def verify_chain(root: Path, verbose: bool = False) -> Report:
    """Verify every record in a chain directory, then the chain itself."""
    chain = Chain(root)
    r = Report()
    n = len(chain)
    if n == 0:
        r.failures.append(f"No records found in {root}.")
        return r

    bad = 0
    # Per-record findings, counted rather than repeated. A chain of forty records
    # would otherwise print forty copies of the same caveat and bury the one that
    # differs — which is the opposite of what a reader needs.
    seen: dict[str, int] = {}
    for path in sorted(Path(root).glob("[0-9]*.ftr")):
        sub = verify_record(path.read_bytes())
        if not sub.ok:
            bad += 1
            r.failures += [f"record {path.stem}: {f}" for f in sub.failures]
        for item in sub.asserted:
            seen[item] = seen.get(item, 0) + 1

    if bad == 0:
        r.proven.append(f"All {n} records individually verify: canonical, hashed and signed.")

    for item, count in sorted(seen.items(), key=lambda kv: (-kv[1], kv[0])):
        scope = "every record" if count == n else f"{count} of {n} records"
        r.asserted.append(f"[{scope}] {item}")

    st = chain.status()
    if st.intact:
        r.proven.append(
            f"The chain replays from genesis to record #{n - 1} with no gap and no fork: "
            "no record was reordered, removed from the middle, or inserted after the fact."
        )
    else:
        for b in st.breaks:
            r.failures.append(f"chain break at #{b.sequence} [{b.kind}]: {b.detail}")

    if st.last_anchor_sequence is None:
        r.asserted.append(
            f"This chain has never been anchored. All {st.length} records could have been "
            "produced at any time; the ledger fixes their order, not their date."
        )
    elif st.unanchored:
        r.asserted.append(
            f"{st.unanchored} record(s) after #{st.last_anchor_sequence} are unanchored. "
            "Each proves only that it was made after the record before it and before the "
            "next anchor."
        )
    else:
        r.proven.append(f"Every record is anchored up to #{st.last_anchor_sequence}.")

    r.unverifiable.append(
        "Whether records were removed from the *head* of the chain. Truncation is "
        "detectable only against an external anchor, never from the files alone."
    )
    return r
