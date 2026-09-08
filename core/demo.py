"""End-to-end demonstration: measure, seal, chain, anchor, verify, tamper.

Run it:

    python core/demo.py [--keep DIR]

It builds a two-record chain from synthetic colorimetry, verifies it, then
performs one attack from the adversary matrix and shows the verifier catching it.
Nothing here touches a controlled substance: the colour data is a surrogate
ladder, exactly as ARCHITECTURE.md §7 describes.
"""

from __future__ import annotations

import argparse
import hashlib
import shutil
import sys
import tempfile
from pathlib import Path

import cv2
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parent / "tests"))

from factory import SimulatedHardwareKeystore          # noqa: E402  (demo-only hardware stub)
from synth import photograph, render_card               # noqa: E402  (demo-only camera)
from synth3d import replay_pair, stereo_pair, tab_texture  # noqa: E402  (two-view rig)
from ftr.canonical_cbor import dumps                    # noqa: E402
from ftr.chain import Chain                             # noqa: E402
from ftr.colorimetry import ConformalClassifier, srgb_to_linear, xyz_to_lab  # noqa: E402
from ftr.card import CARD_V1                            # noqa: E402
from ftr.pipeline import SRGB_TO_XYZ_D65, measure, measure_pair  # noqa: E402
from ftr.record import FTR, SealedRecord, seal          # noqa: E402
from ftr.verifier import verify_chain, verify_record    # noqa: E402

# Three well colours standing in for reagent developments. Surrogates, not
# chemistry: ARCHITECTURE.md §7 explains why a student team cannot lawfully hold
# the real thing, and why substituting NCB colour standards is a data change
# rather than an architecture change.
WELLS = {
    "opiate_class":      (0.28, 0.12, 0.22),   # purple-black
    "amphetamine_class": (0.34, 0.20, 0.14),   # brown
    "negative":          (0.80, 0.78, 0.72),   # unreacted strip
}


def truth_lab(srgb) -> np.ndarray:
    return xyz_to_lab(srgb_to_linear(np.array(srgb)) @ SRGB_TO_XYZ_D65.T)


LOCI = {name: truth_lab(v) for name, v in WELLS.items()}


def rule(title: str) -> None:
    print(f"\n\033[1m{title}\033[0m\n" + "=" * len(title))


def build_classifier(rng) -> ConformalClassifier:
    """Calibrate L2 on jittered reference points.

    In deployment this split is *physical* — held-out frames captured under an
    illuminant the model never saw (§7.5). The jitter here stands in for that so
    the demo runs in a second; it is the one place in this file where a real
    number is replaced by a plausible one, and it is the reason no accuracy claim
    from this demo means anything.
    """
    labs, lbls = [], []
    for name, locus in LOCI.items():
        labs += [locus + rng.normal(0, 2.2, 3) for _ in range(200)]
        lbls += [name] * 200
    clf = ConformalClassifier(LOCI, alpha=0.05)
    clf.calibrate(np.array(labs), lbls)
    return clf


def make_record(m, frame_bytes: bytes, agreeing: int = 4, indicators=()) -> FTR:
    """Build an FTR from a real Measurement. Colorimetry comes straight from L1."""
    fields = m.record_fields()
    return FTR(
        captured_at={"device_clock": "2026-09-13T14:32:07+05:30",
                     "uptime_ms": 918_233_004, "trusted_time_delta_ms": None},
        operator={"id": "NCB/BLR/2291", "credential_ref": "cred:2291",
                  "biometric_unlock_used": True},
        kit={"reagent_type": "marquis", "kit_photo_sha256": hashlib.sha256(b"lot").digest()},
        card={"card_id": "CARD-IN-2026-0417", "print_batch": "B12",
              "values": "nominal — no spectrophotometer reading for this batch"},
        capture={"raw_image_sha256": hashlib.sha256(frame_bytes).digest(),
                 "normalised_image_sha256": hashlib.sha256(frame_bytes + b"|norm").digest()},
        colorimetry=fields["colorimetry"],
        liveness=fields["liveness"],
        classification=fields.get("classification", {"measured": False}),
        location_bundle={"lat_x1e7": 129912000, "lon_x1e7": 777205000, "accuracy_m": 6,
                         "gnss_raw_digest": hashlib.sha256(b"gnss").digest(),
                         "wifi_bssid_set_digest": hashlib.sha256(b"wifi").digest(),
                         "corroboration_channels_agreeing": agreeing,
                         "corroboration_channels_total": 4,
                         "spoof_indicators": list(indicators)},
        device={"android_id_hash": hashlib.sha256(b"dev").digest(),
                "os_patch_level": "2026-08-01", "bootloader_state": "LOCKED",
                "verified_boot_state": "GREEN",
                # Required by the Schedule to BSA s.63 — see docs/CERTIFICATE.md.
                # The FTR schema originally lacked these; transcribing the Act
                # was what revealed the certificate could not be completed.
                "make_model": "Google Pixel 7a",
                "serial_number": "1A2B3C4D5E",
                "device_identifier": "IMEI 350000000000001"},
        ndps={"seizure_memo_ref": "SM-2026-0913-07", "sample_ids": ["S1", "S2"]},
        omitted=["kit.lot"],
    )


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--keep", type=Path, help="write the chain here instead of a temp dir")
    a = ap.parse_args()

    workdir = a.keep or Path(tempfile.mkdtemp(prefix="ftr-demo-"))
    workdir.mkdir(parents=True, exist_ok=True)
    rng = np.random.default_rng(2026)

    rule("L2 — calibrate the abstention threshold")
    clf = build_classifier(rng)
    print(f"  conformal threshold         {clf.threshold:6.3f} dE2000 "
          f"from {clf.n_calibration} points at alpha={clf.alpha}")
    print(f"  reference loci              " +
          ", ".join(f"{k} L*{v[0]:.0f}" for k, v in LOCI.items()))

    rule("L1 — photograph three strips, in three different conditions")
    keystore = SimulatedHardwareKeystore(workdir / "strongbox.pem")
    chain = Chain(workdir / "chain")
    frames: list[bytes] = []

    scenarios = [
        ("opiate, good light", "opiate_class", dict(illuminant="daylight")),
        ("amphetamine, shadow", "amphetamine_class", dict(illuminant="shade", shadow=0.6, tilt=12)),
        ("opiate, torch glare", "opiate_class", dict(illuminant="torch", glare=0.25)),
    ]

    for name, well, conditions in scenarios:
        photo = photograph(render_card(well_srgb=WELLS[well]), rng=rng, **conditions)
        ok, buf = cv2.imencode(".jpg", photo, [cv2.IMWRITE_JPEG_QUALITY, 92])
        frame = buf.tobytes()
        frames.append(frame)

        m = measure(cv2.imdecode(np.frombuffer(frame, np.uint8), cv2.IMREAD_COLOR), clf)

        print(f"  {name}")
        if m.lab is not None:
            print(f"    measured Lab*   {m.lab[0]:6.1f} {m.lab[1]:6.1f} {m.lab[2]:6.1f}"
                  f"   (truth {LOCI[well][0]:.1f} {LOCI[well][1]:.1f} {LOCI[well][2]:.1f})")
            print(f"    card residual   {m.transform_residual_delta_e:.3f} dE   "
                  f"illumination {m.illumination_residual_stops:.3f} stops   "
                  f"gate {'PASS' if m.quality.passed else 'FAIL'}")
        if m.usable:
            p = m.prediction
            pset = ", ".join(p.prediction_set) or "\u2205"
            print(f"    result          {{{pset}}}  ->  {p.label or 'INCONCLUSIVE'}")
        else:
            print(f"    result          REFUSED — {m.refusals[0]}")
            print(f"    operator sees   \"{m.guidance()}\"")

        rec = seal(make_record(m, frame), chain.head(), chain.next_sequence(), keystore)
        chain.append(rec)
        print(f"    sealed          #{rec.sequence}  {rec.digest.hex()[:32]}...\n")

    chain.anchor(0)
    print(f"  anchored up to #0; {chain.status().unanchored} record(s) in the open window")
    print("  note: the refusal was sealed and chained exactly like the two results.")
    print("        A frame the instrument would not read is evidence too, and deleting")
    print("        it is the attack the ledger exists to stop.")

    rule("Adversary §10 row 1 — photograph a print of the whole scene")
    raised = (tab_texture(), CARD_V1.tab_height_mm, np.array(CARD_V1.tab_quad_mm))
    honest = stereo_pair(render_card(well_srgb=WELLS["opiate_class"]), raised=raised)
    forged = replay_pair(render_card(well_srgb=WELLS["opiate_class"]),
                         medium="print", raised=raised)
    for label, (fa, fb) in [("physical card", honest), ("photo-lab print of it", forged)]:
        m = measure_pair(fa, fb, clf)
        lv = m.record_fields()["liveness"]
        got, want = lv["displacement_px_x100"] / 100, lv["predicted_px_x100"] / 100
        print(f"  {label:<24} parallax {got:5.1f} px   predicted {want:5.1f} px   "
              f"{'LIVE' if lv['live'] else 'REFUSED'}")
        if not lv["live"]:
            print(f"  {'':<24} {m.refusals[-1][:86]}")
    print("  A quality print passes every colour check — it is flat, and flatness is")
    print("  not an artefact better equipment removes. It is the medium.")

    rule("Independent verifier — the honest chain")
    print(verify_chain(chain.root).text())

    rule("Adversary §10 row 2 — edit the image after capture")
    blob = sorted(chain.root.glob("[0-9]*.ftr"))[0].read_bytes()
    bad = verify_record(blob, images={"raw_image_sha256": frames[0] + b" (retouched)"})
    for line in bad.failures:
        print(f"  x  {line}")
    print(f"  verdict: {'VERIFIED' if bad.ok else 'VERIFICATION FAILED'}")

    rule("Adversary §10 row 3 — rewrite the stored result")
    rec = SealedRecord.from_envelope(blob)
    body = rec.body
    body["classification"]["label"] = "negative"
    forged = dumps({"v": 1, "body": dumps(body), "sig": rec.signature,
                    "pub": rec.public_key_der, "att": rec.attestation})
    bad = verify_record(forged)
    for line in bad.failures:
        print(f"  x  {line}")
    print(f"  verdict: {'VERIFIED' if bad.ok else 'VERIFICATION FAILED'}")

    rule("Adversary §10 row 5 — delete the unfavourable record from the middle")
    victim = sorted(chain.root.glob("[0-9]*.ftr"))[1]
    stash = victim.read_bytes()
    victim.unlink()
    bad = verify_chain(chain.root)
    for line in bad.failures:
        print(f"  x  {line}")
    print(f"  verdict: {'VERIFIED' if bad.ok else 'VERIFICATION FAILED'}")
    victim.write_bytes(stash)

    rule("Adversary §10 row 5, residual — truncate the head instead")
    head = sorted(chain.root.glob("[0-9]*.ftr"))[-1]
    stash = head.read_bytes()
    head.unlink()
    trunc = verify_chain(chain.root)
    print(f"  verdict: {'VERIFIED' if trunc.ok else 'VERIFICATION FAILED'}  "
          "<- the known gap, and the verifier says so rather than hiding it:")
    for line in trunc.unverifiable:
        print(f"  .  {line}")
    head.write_bytes(stash)

    if a.keep:
        print(f"\nChain kept at {chain.root}")
        print(f"Verify it yourself:  python -m ftr.cli chain {chain.root}")
    else:
        shutil.rmtree(workdir, ignore_errors=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
