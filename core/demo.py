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

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parent / "tests"))

from factory import SimulatedHardwareKeystore          # noqa: E402  (demo-only hardware stub)
from ftr.canonical_cbor import dumps                    # noqa: E402
from ftr.chain import Chain                             # noqa: E402
from ftr.colorimetry import ConformalClassifier, RootPolynomial, _root_poly  # noqa: E402
from ftr.record import FTR, SealedRecord, seal          # noqa: E402
from ftr.verifier import verify_chain, verify_record    # noqa: E402

# Three loci, not two, because that is what a real reagent looks like. Marquis
# develops similar dark colours for related compounds, so the interesting
# abstention is between two *positive* classes — not between positive and a
# blank strip, which are never confusable.
LOCI = {
    "opiate_class":     np.array([28.4, 12.1, -9.6]),   # purple-black
    "amphetamine_class": np.array([34.9, 16.8, -4.1]),  # nearby: 8.6 dE away
    "negative":         np.array([78.2, -1.4, 6.3]),    # unreacted strip
}


def rule(title: str) -> None:
    print(f"\n\033[1m{title}\033[0m\n" + "=" * len(title))


def build_pipeline(rng):
    """L1 transform solved from a synthetic card, L2 calibrated on a held-out split."""
    true_M = np.array([[0.41, 0.21, 0.02], [0.36, 0.72, 0.12], [0.18, 0.07, 0.95],
                       [0.02, 0.01, 0.00], [0.01, 0.02, 0.03], [0.03, 0.00, 0.01]]) * 100
    dev_rgb = rng.uniform(0.05, 0.95, size=(24, 3))
    measured_xyz = _root_poly(dev_rgb) @ true_M + rng.normal(0, 0.4, size=(24, 3))
    transform = RootPolynomial.fit(dev_rgb, measured_xyz)

    labs, lbls = [], []
    for lbl, locus in LOCI.items():
        labs += [locus + rng.normal(0, 2.6, 3) for _ in range(200)]
        lbls += [lbl] * 200
    clf = ConformalClassifier(LOCI, alpha=0.05)
    clf.calibrate(np.array(labs), lbls)
    return transform, clf


def make_record(lab, prediction, transform, frame: bytes, agreeing=4, indicators=()) -> FTR:
    return FTR(
        captured_at={"device_clock": "2026-09-13T14:32:07+05:30",
                     "uptime_ms": 918_233_004, "trusted_time_delta_ms": None},
        operator={"id": "NCB/BLR/2291", "credential_ref": "cred:2291",
                  "biometric_unlock_used": True},
        kit={"reagent_type": "marquis", "kit_photo_sha256": hashlib.sha256(b"lot").digest()},
        card={"card_id": "CARD-IN-2026-0417", "print_batch": "B12"},
        capture={"raw_image_sha256": hashlib.sha256(frame).digest(),
                 "normalised_image_sha256": hashlib.sha256(frame + b"|norm").digest()},
        colorimetry={"lab_x100": [int(round(v * 100)) for v in lab],
                     "calibration_residual_x1000": int(round(transform.residual_delta_e * 1000)),
                     "blur_metric_x1000": 30, "dynamic_range_x1000": 780},
        classification={"model_id": "marquis-loci-v3",
                        "model_sha256": hashlib.sha256(b"marquis-loci-v3").digest(),
                        "alpha_x1000": int(round(prediction.alpha * 1000)),
                        "prediction_set": list(prediction.prediction_set),
                        "label": prediction.label,
                        "threshold_x1000": int(round(prediction.threshold * 1000))},
        location_bundle={"lat_x1e7": 129912000, "lon_x1e7": 777205000, "accuracy_m": 6,
                         "gnss_raw_digest": hashlib.sha256(b"gnss").digest(),
                         "wifi_bssid_set_digest": hashlib.sha256(b"wifi").digest(),
                         "corroboration_channels_agreeing": agreeing,
                         "corroboration_channels_total": 4,
                         "spoof_indicators": list(indicators)},
        device={"android_id_hash": hashlib.sha256(b"dev").digest(),
                "os_patch_level": "2026-08-01", "bootloader_state": "LOCKED",
                "verified_boot_state": "GREEN"},
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

    rule("L1/L2 — calibrate the instrument")
    transform, clf = build_pipeline(rng)
    print(f"  colour transform residual   {transform.residual_delta_e:6.3f} dE2000 "
          f"(gate {'PASS' if transform.passes() else 'FAIL'} at 3.000)")
    print(f"  worst patch                 {transform.max_delta_e:6.3f} dE2000")
    print(f"  conformal threshold         {clf.threshold:6.3f} dE2000 "
          f"from {clf.n_calibration} held-out points at alpha={clf.alpha}")

    rule("Three measurements — one call, two different abstentions")
    keystore = SimulatedHardwareKeystore(workdir / "strongbox.pem")
    chain = Chain(workdir / "chain")
    frames = []

    scenarios = [
        ("clean strip", LOCI["opiate_class"] + np.array([0.9, -0.6, 0.4])),
        ("between classes", (LOCI["opiate_class"] + LOCI["amphetamine_class"]) / 2),
        ("nothing like it", np.array([55.0, -60.0, 70.0])),
    ]
    for name, lab in scenarios:
        p = clf.predict(lab)
        frame = f"synthetic sensor frame: {name}".encode()
        frames.append(frame)
        verdict = p.label if p.label else "INCONCLUSIVE"
        pset = ", ".join(p.prediction_set) or "\u2205"
        print(f"  {name:<16} Lab* {lab[0]:6.1f} {lab[1]:6.1f} {lab[2]:6.1f}"
              f"   set {{{pset}}}  ->  {verdict}")
        print(f"  {'':<16} {p.reason}")
        rec = seal(make_record(lab, p, transform, frame), chain.head(), chain.next_sequence(), keystore)
        chain.append(rec)
        print(f"  {'':<16} sealed #{rec.sequence} digest {rec.digest.hex()[:32]}…\n")

    chain.anchor(0)
    print(f"  anchored up to #0; {chain.status().unanchored} record(s) still in the open window")
    print("  note: the abstentions are sealed and chained exactly like the call. "
          "An inconclusive\n        result is evidence too, and deleting it is the "
          "attack the ledger exists to stop.")

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
