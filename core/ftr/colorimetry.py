"""L1 normalisation and L2 abstention — the measurement, and its honesty.

Naive RGB off a phone camera is not a measurement. Ambient illuminant, auto
white balance, auto exposure and undisclosed vendor ISP processing all move the
numbers. What makes a number defensible is that it was solved against known
reference reflectances printed in the same frame, and that the residual error of
that solve is reported alongside the result.

Deterministic first, learning second: the transform here is least squares with a
root-polynomial expansion. It is auditable, explainable to a court, and cheap to
defend. Only L2 sees a learned component, and it operates on three normalised
dimensions rather than three million pixels.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

__all__ = [
    "srgb_to_linear", "linear_to_srgb", "xyz_to_lab", "lab_to_xyz", "lab_to_srgb",
    "delta_e_2000", "RootPolynomial",
    "ConformalClassifier", "Prediction", "D65",
]

# CIE D65 white point, 2° observer.
D65 = np.array([95.047, 100.000, 108.883])


# --------------------------------------------------------------------------- #
# colour space
# --------------------------------------------------------------------------- #

def srgb_to_linear(rgb: np.ndarray) -> np.ndarray:
    """Undo the sRGB transfer function. Input and output in [0, 1]."""
    rgb = np.asarray(rgb, dtype=float)
    return np.where(rgb <= 0.04045, rgb / 12.92, ((rgb + 0.055) / 1.055) ** 2.4)


def xyz_to_lab(xyz: np.ndarray, white: np.ndarray = D65) -> np.ndarray:
    """CIEXYZ (0–100 scale) to CIELAB.

    Lab is used rather than RGB or HSV because distance in Lab is perceptually
    and physically meaningful, which is what makes a threshold on it defensible.
    """
    t = np.asarray(xyz, dtype=float) / white
    d = 6.0 / 29.0
    f = np.where(t > d ** 3, np.cbrt(t), t / (3 * d ** 2) + 4.0 / 29.0)
    fx, fy, fz = f[..., 0], f[..., 1], f[..., 2]
    return np.stack([116 * fy - 16, 500 * (fx - fy), 200 * (fy - fz)], axis=-1)


def lab_to_xyz(lab: np.ndarray, white: np.ndarray = D65) -> np.ndarray:
    """Inverse of :func:`xyz_to_lab`."""
    lab = np.asarray(lab, dtype=float)
    fy = (lab[..., 0] + 16.0) / 116.0
    fx = fy + lab[..., 1] / 500.0
    fz = fy - lab[..., 2] / 200.0
    f = np.stack([fx, fy, fz], axis=-1)
    d = 6.0 / 29.0
    t = np.where(f > d, f ** 3, 3.0 * d * d * (f - 4.0 / 29.0))
    return t * white


def linear_to_srgb(rgb: np.ndarray) -> np.ndarray:
    """Inverse of :func:`srgb_to_linear`."""
    rgb = np.clip(np.asarray(rgb, dtype=float), 0.0, 1.0)
    return np.where(rgb <= 0.0031308, rgb * 12.92,
                    1.055 * np.power(rgb, 1 / 2.4) - 0.055)


def lab_to_srgb(lab: np.ndarray) -> np.ndarray:
    """Lab* to sRGB in 0..1, clipped to gamut.

    Used to *print* a colour the pipeline will later measure — the demonstration
    cards, whose well is filled with a known locus. Clipping matters: a locus
    outside the printer's gamut comes back measurably different, so the caller
    is told how far the round trip moved rather than being left to assume it
    did not.
    """
    from .pipeline import SRGB_TO_XYZ_D65      # local: pipeline imports us
    xyz = lab_to_xyz(np.asarray(lab, dtype=float))
    lin = xyz @ np.linalg.inv(SRGB_TO_XYZ_D65).T
    return np.clip(linear_to_srgb(lin), 0.0, 1.0)


def delta_e_2000(lab1: np.ndarray, lab2: np.ndarray) -> np.ndarray:
    """CIEDE2000 colour difference.

    CIE76 Euclidean distance systematically overstates differences in the blue
    region and understates them near neutral — which is exactly where reagent
    colours live. Using it would put a known bias into the decision threshold.
    """
    lab1 = np.atleast_2d(np.asarray(lab1, dtype=float))
    lab2 = np.atleast_2d(np.asarray(lab2, dtype=float))
    L1, a1, b1 = lab1[..., 0], lab1[..., 1], lab1[..., 2]
    L2, a2, b2 = lab2[..., 0], lab2[..., 1], lab2[..., 2]

    C1, C2 = np.hypot(a1, b1), np.hypot(a2, b2)
    Cbar = (C1 + C2) / 2
    G = 0.5 * (1 - np.sqrt(Cbar ** 7 / (Cbar ** 7 + 25.0 ** 7 + 1e-30)))
    a1p, a2p = (1 + G) * a1, (1 + G) * a2
    C1p, C2p = np.hypot(a1p, b1), np.hypot(a2p, b2)
    h1p = np.degrees(np.arctan2(b1, a1p)) % 360
    h2p = np.degrees(np.arctan2(b2, a2p)) % 360

    dLp = L2 - L1
    dCp = C2p - C1p
    dhp = h2p - h1p
    dhp = np.where(dhp > 180, dhp - 360, np.where(dhp < -180, dhp + 360, dhp))
    dhp = np.where(C1p * C2p == 0, 0.0, dhp)
    dHp = 2 * np.sqrt(C1p * C2p) * np.sin(np.radians(dhp / 2))

    Lbp = (L1 + L2) / 2
    Cbp = (C1p + C2p) / 2
    hsum = h1p + h2p
    hbp = np.where(
        C1p * C2p == 0, hsum,
        np.where(np.abs(h1p - h2p) <= 180, hsum / 2,
                 np.where(hsum < 360, (hsum + 360) / 2, (hsum - 360) / 2)),
    )
    T = (1 - 0.17 * np.cos(np.radians(hbp - 30))
         + 0.24 * np.cos(np.radians(2 * hbp))
         + 0.32 * np.cos(np.radians(3 * hbp + 6))
         - 0.20 * np.cos(np.radians(4 * hbp - 63)))
    dtheta = 30 * np.exp(-(((hbp - 275) / 25) ** 2))
    Rc = 2 * np.sqrt(Cbp ** 7 / (Cbp ** 7 + 25.0 ** 7 + 1e-30))
    Sl = 1 + (0.015 * (Lbp - 50) ** 2) / np.sqrt(20 + (Lbp - 50) ** 2)
    Sc = 1 + 0.045 * Cbp
    Sh = 1 + 0.015 * Cbp * T
    Rt = -np.sin(np.radians(2 * dtheta)) * Rc

    de = np.sqrt((dLp / Sl) ** 2 + (dCp / Sc) ** 2 + (dHp / Sh) ** 2
                 + Rt * (dCp / Sc) * (dHp / Sh))
    return de.squeeze()


# --------------------------------------------------------------------------- #
# L1 — device transform
# --------------------------------------------------------------------------- #

def _root_poly(rgb: np.ndarray) -> np.ndarray:
    """Root-polynomial expansion, degree 2 (Finlayson et al.).

    Every term has the units of intensity, so the fit is exposure-invariant:
    doubling the light scales all terms equally. Plain polynomial terms are not,
    which is why a plain polynomial fit drifts when the officer steps into shade.
    """
    r, g, b = rgb[:, 0], rgb[:, 1], rgb[:, 2]
    eps = 1e-12
    return np.stack([
        r, g, b,
        np.sqrt(np.maximum(r * g, eps)),
        np.sqrt(np.maximum(g * b, eps)),
        np.sqrt(np.maximum(r * b, eps)),
    ], axis=1)


@dataclass
class RootPolynomial:
    """Per-device-model RGB to XYZ transform, solved from the card's own patches."""

    matrix: np.ndarray            # (6, 3)
    residual_delta_e: float       # mean CIEDE2000 on the patches used to fit
    max_delta_e: float
    per_patch_delta_e: np.ndarray = None  # type: ignore[assignment]

    @classmethod
    def fit(cls, device_rgb: np.ndarray, reference_xyz: np.ndarray) -> "RootPolynomial":
        """Solve the transform. ``device_rgb`` is linear RGB in [0, 1]."""
        device_rgb = np.asarray(device_rgb, dtype=float)
        reference_xyz = np.asarray(reference_xyz, dtype=float)
        if device_rgb.shape[0] != reference_xyz.shape[0]:
            raise ValueError("need one reference XYZ per measured patch")
        if device_rgb.shape[0] < 6:
            raise ValueError("need at least 6 patches to solve a 6-term transform")

        A = _root_poly(device_rgb)
        M, *_ = np.linalg.lstsq(A, reference_xyz, rcond=None)
        de = delta_e_2000(xyz_to_lab(A @ M), xyz_to_lab(reference_xyz))
        de = np.atleast_1d(de)
        # Kept, not discarded. The mean says the fit failed; only the per-patch
        # spread says WHY, and an operator holding a refusal with one number has
        # nothing to act on.
        return cls(matrix=M, residual_delta_e=float(de.mean()),
                   max_delta_e=float(de.max()), per_patch_delta_e=de.copy())

    def to_lab(self, device_rgb: np.ndarray) -> np.ndarray:
        rgb = np.atleast_2d(np.asarray(device_rgb, dtype=float))
        return xyz_to_lab(_root_poly(rgb) @ self.matrix).squeeze()

    def passes(self, limit_delta_e: float = 3.0) -> bool:
        """Calibration gate. A failed gate is recorded, not silently swallowed."""
        return self.residual_delta_e <= limit_delta_e

    def diagnose(self, reference_xyz: np.ndarray) -> str:
        """Name the most likely cause of a failed fit, from the shape of the error.

        A refusal carrying one number tells the operator that something is wrong
        and nothing about what to change; they retake the same frame in the same
        conditions and get the same number back. The card deliberately spans dark
        to light and neutral to saturated, so the *pattern* of error across it is
        diagnostic:

          one or two patches far worse    -> a local artefact, not the lighting
          error rises as patches darken   -> light added on top of the card
          error rises with saturation     -> gamut stretch or a vivid picture mode
          error flat across the card      -> the illuminant's spectrum

        Decided by correlation rather than group means, because the groups
        overlap: the card's dark patches are also its least saturated, so a mean
        comparison attributes a chroma effect to lightness and vice versa.

        Returns a hint, and is worded as one. It is not a verdict, and it never
        appears in a sealed record — a guess about someone's lighting is not
        evidence.
        """
        de = np.atleast_1d(np.asarray(self.per_patch_delta_e, dtype=float))
        if de.size < 6:
            return "too few patches to say why."

        lab = xyz_to_lab(np.asarray(reference_xyz, dtype=float))
        lightness, chroma = lab[:, 0], np.hypot(lab[:, 1], lab[:, 2])

        # Outliers first, robustly. A median-absolute-deviation score survives
        # the very outliers it is looking for, which a mean and standard
        # deviation do not.
        med = float(np.median(de))
        mad = float(np.median(np.abs(de - med))) or 1e-9
        z = 0.6745 * (de - med) / mad
        # A minority of patches, each far outside the rest of the distribution.
        # Fraction-based rather than a fixed count: a glare spot lands on however
        # many patches it covers, and capping at two missed a three-patch
        # reflection that scored z=10 against a median of 7.
        n_out = int((z > 6).sum())
        if 0 < n_out <= max(2, de.size // 4) and float(de.max()) > 2.5 * med:
            return (f"{n_out} of {de.size} patches are far worse than the rest "
                    f"(worst {de.max():.1f} dE against a typical {med:.1f}) — "
                    "that is something on the card, not the light: a glare spot, "
                    "a reflection, or an object resting on it.")

        def r(x, mask=None):
            x = np.asarray(x, dtype=float)
            d = de
            if mask is not None:
                x, d = x[mask], de[mask]
            if x.size < 4 or np.std(x) < 1e-9 or np.std(d) < 1e-9:
                return 0.0
            return float(np.corrcoef(x, d)[0, 1])

        # Neutral against chromatic first, because it is the sharpest cut the
        # card offers and the one a global correlation hides. A real frame from
        # a handset had 2.8 dE across the neutrals and 10.1 across the colours,
        # while the lightness correlation over ALL patches was only -0.47 — the
        # neutrals, being fine, dragged it under any sane threshold.
        chromatic = chroma > 10
        neutral = ~chromatic
        if chromatic.sum() >= 4 and neutral.sum() >= 3:
            # Medians, not means. The card carries one very dark, nearly-neutral
            # patch (L 6.8, chroma 5.7) that a grey lift hits hardest of all; on
            # a real frame it scored 19.7 dE and dragged the neutral MEAN to 4.65
            # while the median stayed at 2.6. A mean here lets the single worst
            # patch veto the diagnosis of the effect that produced it.
            n_mean = float(np.median(de[neutral]))
            c_mean = float(np.median(de[chromatic]))
            if n_mean < 4.0 and c_mean > 2 * n_mean:
                # Within the chromatic patches, does the error grow as they
                # darken? A grey lift added on top desaturates a dark colour —
                # which a transform with no constant term cannot undo — while
                # leaving a dark neutral merely brighter, which the per-channel
                # gain absorbs.
                r_dark = r(lightness, chromatic)
                if r_dark < -0.4:
                    return (f"the neutral patches are fine ({n_mean:.1f} dE) but "
                            f"the coloured ones are not ({c_mean:.1f} dE), and "
                            f"among those the darker ones are worst "
                            f"(r={r_dark:+.2f}). That is grey light added on top "
                            "of the card — a reflection on glossy paper or a "
                            "screen, or a screen's own black level. Kill the "
                            "reflections, raise the screen brightness, or print "
                            "the card.")
                r_sat = r(chroma, chromatic)
                if r_sat > 0.4:
                    return (f"the neutral patches are fine ({n_mean:.1f} dE) and "
                            "the coloured ones get worse the more saturated they "
                            f"are (r={r_sat:+.2f}) — the colours are being "
                            "stretched. A wide-gamut or 'vivid' display, or "
                            "colour management left on when the card was "
                            "printed.")
                return (f"the neutral patches are fine ({n_mean:.1f} dE) but the "
                        f"coloured ones are not ({c_mean:.1f} dE). The greys "
                        "reproduce and the hues do not, which points at the "
                        "light's spectrum or the display's primaries rather "
                        "than at exposure.")

        r_light, r_chroma = r(lightness), r(chroma)

        # Darker patches worse -> negative correlation with lightness.
        if r_light < -0.5 and abs(r_light) > abs(r_chroma):
            return ("the error grows as the patches get darker "
                    f"(r={r_light:+.2f}) — light is being added on top of the "
                    "card. A reflection on a glossy surface, or the black level "
                    "of a screen if the card is displayed rather than printed.")
        if r_chroma > 0.5 and abs(r_chroma) > abs(r_light):
            return ("the error grows with how saturated the patch is "
                    f"(r={r_chroma:+.2f}) — the colours are being stretched. A "
                    "wide-gamut or 'vivid' display, or colour management left on "
                    "when the card was printed.")
        if float(de.max() - de.min()) < max(3.0, med):
            return (f"every patch is wrong by about the same amount "
                    f"({de.min():.1f}-{de.max():.1f} dE) — that is the light's "
                    "spectrum, not its evenness. A low-CRI bulb, or two "
                    "different lights on one card. Daylight or a high-CRI lamp "
                    "is the fix.")
        return (f"the error is spread unevenly across the card "
                f"({de.min():.1f}-{de.max():.1f} dE) with no clear pattern by "
                "lightness or saturation. Check for a reflection, and retake in "
                "daylight before looking further.")



@dataclass(frozen=True)
class Prediction:
    """The output of L2. ``label`` is None whenever the set is not a singleton."""

    prediction_set: tuple[str, ...]
    label: str | None
    alpha: float
    scores: dict[str, float]      # nonconformity per label, CIEDE2000 to its locus
    threshold: float

    @property
    def inconclusive(self) -> bool:
        return self.label is None

    @property
    def reason(self) -> str:
        if self.label is not None:
            return f"single label within threshold {self.threshold:.2f}"
        if not self.prediction_set:
            return (f"no reference locus within {self.threshold:.2f} dE — the measurement "
                    "resembles nothing this reagent is calibrated for")
        return (f"{len(self.prediction_set)} labels within {self.threshold:.2f} dE — "
                "the measurement does not separate them at this risk level")


class ConformalClassifier:
    """Distance to reference loci in Lab, with a calibrated abstention threshold.

    Conformal prediction is what turns 'inconclusive' from a softmax cutoff into a
    quantity with a stated error bound: at risk level alpha, on exchangeable data,
    the true label is in the returned set at least 1-alpha of the time. That
    sentence survives cross-examination. "The model was 87% confident" does not.

    It also degrades honestly. A poor frame widens the set and pushes toward
    abstention, rather than producing a confident wrong answer in exactly the
    conditions where a confident wrong answer does the most damage.
    """

    def __init__(self, loci: dict[str, np.ndarray], alpha: float = 0.05):
        if not 0 < alpha < 1:
            raise ValueError("alpha must be in (0, 1)")
        self.loci = {k: np.asarray(v, dtype=float) for k, v in loci.items()}
        self.alpha = alpha
        self.threshold: float | None = None
        self.n_calibration = 0

    def _score(self, lab: np.ndarray, label: str) -> float:
        return float(delta_e_2000(np.atleast_2d(lab), np.atleast_2d(self.loci[label])))

    def calibrate(self, labs: np.ndarray, labels: list[str]) -> float:
        """Set the threshold from a held-out physical split.

        The quantile index is the finite-sample conformal correction: with n
        calibration points the threshold must be the ceil((n+1)(1-alpha))-th
        smallest score, not the empirical (1-alpha) quantile. Getting this wrong
        loses the guarantee, quietly.
        """
        labs = np.atleast_2d(np.asarray(labs, dtype=float))
        if len(labs) != len(labels):
            raise ValueError("need one label per calibration measurement")
        n = len(labels)
        if n < int(np.ceil(1 / self.alpha)) - 1:
            raise ValueError(
                f"alpha={self.alpha} needs at least {int(np.ceil(1/self.alpha)) - 1} "
                f"calibration points for a finite-sample guarantee; got {n}"
            )
        scores = np.array([self._score(labs[i], labels[i]) for i in range(n)])
        k = int(np.ceil((n + 1) * (1 - self.alpha)))
        self.threshold = float(np.sort(scores)[min(k, n) - 1])
        self.n_calibration = n
        return self.threshold

    def predict(self, lab: np.ndarray) -> Prediction:
        if self.threshold is None:
            raise RuntimeError("classifier is not calibrated; call calibrate() first")
        scores = {lbl: self._score(lab, lbl) for lbl in self.loci}
        pset = tuple(sorted(l for l, s in scores.items() if s <= self.threshold))
        return Prediction(
            prediction_set=pset,
            label=pset[0] if len(pset) == 1 else None,
            alpha=self.alpha,
            scores=scores,
            threshold=self.threshold,
        )
