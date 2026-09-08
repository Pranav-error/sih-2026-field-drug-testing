"""One frame in, one measurement out — L1 and L2 joined.

This is the only place the halves of L1 meet, and it exists so the app, the demo
and the verifier all run *identical* code. The verifier re-runs this function on
the raw frame and requires the stored Lab triple back, bit for bit; if the app
had its own copy of this logic, that check would prove nothing.

The pipeline abstains rather than guessing. A frame that fails the quality gate
never reaches the classifier: it returns a Measurement with ``prediction`` unset
and the gate's own failures attached, which is what gets sealed.
"""

from __future__ import annotations

from dataclasses import dataclass, replace

import numpy as np

from .card import CARD_V1, CardSpec, tab_centre_mm
from .colorimetry import ConformalClassifier, Prediction, RootPolynomial, srgb_to_linear, xyz_to_lab
from .detect import (Detection, QualityGate, detect_card, estimate_illumination, grade_frame,
                     rectify, sample_patches, sample_well)
from .parallax import ParallaxResult, check_liveness, measure_parallax

__all__ = ["Measurement", "measure", "measure_pair", "reference_xyz",
           "SRGB_TO_XYZ_D65"]

# sRGB primaries under D65, scaled to Y = 100.
SRGB_TO_XYZ_D65 = np.array([
    [0.4124564, 0.3575761, 0.1804375],
    [0.2126729, 0.7151522, 0.0721750],
    [0.0193339, 0.1191920, 0.9503041],
]) * 100


def reference_xyz(spec: CardSpec = CARD_V1) -> np.ndarray:
    """Nominal XYZ of the printed patches.

    Nominal, not measured: see the note in card.py. Replacing this with
    spectrophotometer readings for a print batch is a data change, not a code
    change, which is the whole reason the card carries a ``print_batch``.
    """
    return srgb_to_linear(spec.patch_srgb) @ SRGB_TO_XYZ_D65.T


@dataclass(frozen=True)
class Measurement:
    """Everything one frame yields, including the reasons it yields nothing."""

    detected: bool
    quality: QualityGate | None
    detection: Detection | None
    lab: np.ndarray | None                 # the reaction region, CIELAB
    transform_residual_delta_e: float | None
    illumination_residual_stops: float | None
    prediction: Prediction | None
    refusals: tuple[str, ...]              # why no result, in the operator's words
    liveness: ParallaxResult | None = None
    liveness_live: bool | None = None      # None when no second frame was supplied
    liveness_reason: str = ""
    liveness_geometry: tuple[float, float, float] | None = None  # (h, baseline, distance)

    @property
    def usable(self) -> bool:
        return self.prediction is not None

    def guidance(self) -> str:
        if self.quality is None:
            return "Move back until all four corner markers are in frame."
        return self.quality.guidance()

    def _liveness_fields(self) -> dict:
        """The liveness block of an FTR.

        Recorded even when unchecked, and explicitly so. A record with no liveness
        block would be silently indistinguishable from one where the check was
        skipped; ``checked: False`` says which it is.
        """
        if self.liveness is None or self.liveness_geometry is None:
            return {"checked": False,
                    "note": "single frame — this capture cannot be distinguished "
                            "from a photograph of a card"}
        h, baseline, distance = self.liveness_geometry
        predicted_mm = baseline * h / max(distance - h, 1e-6)
        return {
            "checked": True,
            "live": bool(self.liveness_live),
            "displacement_px_x100": int(round(self.liveness.displacement_px * 100)),
            "predicted_px_x100": int(round(predicted_mm * 10 * 100)),
            "plane_residual_px_x100": int(round(self.liveness.plane_residual_px * 100)),
            "confidence_x1000": int(round(self.liveness.confidence * 1000)),
            "tab_height_mm_x10": int(round(h * 10)),
            "baseline_mm_x10": int(round(baseline * 10)),
            "distance_mm_x10": int(round(distance * 10)),
            "reason": self.liveness_reason,
        }

    def record_fields(self) -> dict:
        """The colorimetry and classification blocks of an FTR.

        Scaled integers throughout — canonical CBOR refuses floats, and the digest
        must not depend on IEEE-754 rounding differing between implementations.
        """
        if self.lab is None or self.quality is None:
            return {"colorimetry": {"measured": False, "refusals": list(self.refusals)}}
        c = {
            "measured": True,
            "lab_x100": [int(round(float(v) * 100)) for v in self.lab],
            "calibration_residual_x1000": int(round(self.transform_residual_delta_e * 1000)),
            "illumination_residual_x1000": int(round(self.illumination_residual_stops * 1000)),
            "blur_x10000": int(round(self.quality.blur * 10000)),
            "clipped_x10000": int(round(self.quality.clipped_fraction * 10000)),
            "light_field_residual_x1000": int(round(self.quality.light_field_residual_stops * 1000)),
            "patch_spread_x10000": int(round(self.quality.patch_spread * 10000)),
            "dynamic_range_x1000": int(round(self.quality.dynamic_range * 1000)),
            "tilt_deg_x10": int(round(self.quality.tilt_degrees * 10)),
            "reprojection_px_x1000": int(round(self.quality.reprojection_px * 1000)),
            "gate_passed": self.quality.passed,
            "refusals": list(self.refusals),
        }
        live = self._liveness_fields()
        if self.prediction is None:
            return {"colorimetry": c, "liveness": live}
        p = self.prediction
        return {"colorimetry": c, "liveness": live, "classification": {
            "alpha_x1000": int(round(p.alpha * 1000)),
            "threshold_x1000": int(round(p.threshold * 1000)),
            "prediction_set": list(p.prediction_set),
            "label": p.label,
            "scores_x1000": {k: int(round(v * 1000)) for k, v in sorted(p.scores.items())},
        }}


def measure(image_bgr: np.ndarray, classifier: ConformalClassifier | None = None,
            spec: CardSpec = CARD_V1) -> Measurement:
    """Run a frame through L1 and, if it earns one, L2."""
    det = detect_card(image_bgr, spec)
    if det is None or not det.complete:
        found = () if det is None else det.markers_found
        return Measurement(
            detected=False, quality=None, detection=det, lab=None,
            transform_residual_delta_e=None, illumination_residual_stops=None,
            prediction=None,
            refusals=(f"only {len(found)} of 4 fiducials resolved — the card was not "
                      "fully in frame, or the print is damaged",),
        )

    rect = rectify(image_bgr, det, spec)
    first = sample_patches(rect, spec)
    gain, illum_residual = estimate_illumination(first, spec)
    patches = sample_patches(rect, spec, gain=gain)
    quality = grade_frame(rect, det, patches, illum_residual, spec, gain=gain)

    transform = RootPolynomial.fit(patches.rgb, reference_xyz(spec))
    well_rgb, _ = sample_well(rect, spec, gain=gain)
    lab = np.atleast_1d(transform.to_lab(well_rgb[None, :]))

    refusals = list(quality.failures())
    if not transform.passes():
        refusals.append(
            f"colour transform residual {transform.residual_delta_e:.2f} dE exceeds 3.00 — "
            "the card's own patches did not reproduce, so no measurement from it is trustworthy"
        )

    prediction = None
    if not refusals and classifier is not None:
        prediction = classifier.predict(lab)

    return Measurement(
        detected=True, quality=quality, detection=det, lab=lab,
        transform_residual_delta_e=transform.residual_delta_e,
        illumination_residual_stops=illum_residual,
        prediction=prediction, refusals=tuple(refusals),
    )


def measure_pair(frame_a: np.ndarray, frame_b: np.ndarray,
                 classifier: ConformalClassifier | None = None,
                 spec: CardSpec = CARD_V1,
                 baseline_mm: float = 50.0, distance_mm: float = 150.0) -> Measurement:
    """Measure from two views, and check the scene was not flat.

    Frame A carries the measurement; frame B exists only to establish depth. A
    flat capture is treated exactly like any other gate failure: it becomes a
    refusal, so the record is still sealed — deleting it is the attack the ledger
    exists to stop — but it carries no result and states why.
    """
    m = measure(frame_a, classifier, spec)
    if not m.detected or spec.tab_height_mm <= 0:
        return m

    det_b = detect_card(frame_b, spec)
    if det_b is None or not det_b.complete:
        return replace(
            m, prediction=None,
            refusals=m.refusals + ("the second frame does not show the card — "
                                   "liveness could not be established",))

    tab = tab_centre_mm(spec)
    result = measure_parallax(frame_a, frame_b, m.detection, det_b, tab,
                              baseline_mm=baseline_mm, distance_mm=distance_mm, spec=spec)
    live, why = check_liveness(result, spec.tab_height_mm, baseline_mm, distance_mm)

    refusals = m.refusals
    prediction = m.prediction
    if not live:
        refusals = refusals + (why,)
        prediction = None

    return replace(m, liveness=result, liveness_live=live, liveness_reason=why,
                   liveness_geometry=(spec.tab_height_mm, baseline_mm, distance_mm),
                   refusals=refusals, prediction=prediction)
