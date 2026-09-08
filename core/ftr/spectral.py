"""Physically-based camera simulation from measured spectral data.

The synthetic camera in `tests/synth.py` models an illuminant as a global RGB
gain. That is a convenient fiction, and it has one consequence that invalidates
every cross-illuminant result taken from it:

    **A per-channel gain cannot produce metamerism.**

Two surfaces that a camera records as the same RGB under daylight, and as
different RGB under fluorescent light, are *the* reason colour constancy is hard.
Under a gain model they can never diverge: whatever matched under one illuminant
matches under all of them, because both are scaled identically. Held-out-illuminant
accuracy measured that way is accuracy on an easier problem than reality.

This module does it properly. A camera's response is the integral over wavelength
of what it is looking at, what is lighting it, and what the sensor is sensitive to:

    R_c = ∫ reflectance(λ) · illuminant(λ) · sensitivity_c(λ) dλ

All three come from measurement, not from invention:

* **Camera sensitivities** — Jiang, Liu, Gu & Süsstrunk (2013), 28 cameras
  measured with a monochromator and a PR655 spectrometer. 400–720 nm, 10 nm steps.
  CC BY-NC-SA 4.0, from Zenodo record 3245883.
* **Illuminant SPDs** — CIE standard illuminants via colour-science.
* **Reflectances** — the BabelColor average of the ColorChecker, via colour-science.

What this does *not* give us is reagent chemistry. There is no public spectral
library of NDPS presumptive-test colour developments, so the "reaction" spectra
here are still surrogates — real measured reflectances of real coloured surfaces,
standing in for real measured reflectances of a real reaction. The optics are now
honest; the chemistry is still borrowed.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import numpy as np

__all__ = ["WAVELENGTHS", "load_cameras", "illuminant_spd", "colourchecker_reflectances",
           "render_rgb", "CAMSPEC_PATH", "Camera"]

# The grid the Jiang database is measured on. Everything is resampled to it rather
# than the other way round: interpolating measured sensitivities onto a finer grid
# would invent precision the instrument did not have.
WAVELENGTHS = np.arange(400, 730, 10)

CAMSPEC_PATH = Path(__file__).resolve().parents[2] / "data" / "spectral" / "camspec_database.txt"


@dataclass(frozen=True)
class Camera:
    name: str
    sensitivities: np.ndarray   # (33, 3), R G B columns

    @property
    def kind(self) -> str:
        n = self.name.lower()
        if "nokia" in n or "iphone" in n:
            return "mobile"
        if "grasshopper" in n or "point grey" in n:
            return "industrial"
        if "nex" in n or "e-pl" in n or "pentax q" in n:
            return "compact"
        return "dslr"


def load_cameras(path: Path = CAMSPEC_PATH) -> dict[str, Camera]:
    """Parse the Jiang database: a name line, then R, G and B rows of 33 values."""
    if not path.exists():
        raise FileNotFoundError(
            f"{path} not found. Fetch it with: python core/tools/fetch_spectral_data.py"
        )
    lines = [ln.strip() for ln in path.read_text().splitlines() if ln.strip()]
    cams: dict[str, Camera] = {}
    i = 0
    while i + 3 < len(lines) + 1:
        name = lines[i]
        try:
            rows = [np.fromstring(lines[i + k], sep="\t") for k in (1, 2, 3)]
        except IndexError:
            break
        if any(r.size != len(WAVELENGTHS) for r in rows):
            i += 1
            continue
        cams[name] = Camera(name, np.stack(rows, axis=1))
        i += 4
    return cams


def illuminant_spd(name: str) -> np.ndarray:
    """A CIE illuminant, resampled to the measurement grid and normalised.

    Normalised so that every illuminant delivers the same total energy: this
    isolates the *spectral shape*, which is what causes metamerism, from overall
    brightness, which the exposure model already covers.
    """
    import colour

    sd = colour.SDS_ILLUMINANTS[name].copy()
    values = np.array([sd[w] if w in sd.wavelengths else np.interp(w, sd.wavelengths, sd.values)
                       for w in WAVELENGTHS], dtype=float)
    return values / values.mean()


def colourchecker_reflectances(which: str = "babel_average") -> dict[str, np.ndarray]:
    """ColorChecker patch reflectance spectra, resampled to the grid."""
    import colour

    out = {}
    for name, sd in colour.SDS_COLOURCHECKERS[which].items():
        out[name] = np.array(
            [sd[w] if w in sd.wavelengths else np.interp(w, sd.wavelengths, sd.values)
             for w in WAVELENGTHS], dtype=float)
    return out


def render_rgb(reflectance: np.ndarray, illuminant: np.ndarray, camera: Camera,
               white_balance: bool = True) -> np.ndarray:
    """Linear camera RGB for one surface, one light and one sensor.

    With ``white_balance``, the response is divided by the response to a perfect
    white diffuser under the same light — which is what a camera's auto white
    balance approximates, and what makes the numbers comparable across illuminants.
    It is deliberately *not* a perfect correction: the per-channel scaling cannot
    undo a spectral mismatch, which is exactly the residual error the card exists
    to measure.
    """
    resp = (reflectance[:, None] * illuminant[:, None] * camera.sensitivities).sum(axis=0)
    if white_balance:
        white = (illuminant[:, None] * camera.sensitivities).sum(axis=0)
        resp = resp / np.clip(white, 1e-12, None)
    return resp


def render_many(reflectances: dict[str, np.ndarray], illuminant: np.ndarray,
                camera: Camera, **kw) -> tuple[list[str], np.ndarray]:
    names = list(reflectances)
    return names, np.array([render_rgb(reflectances[n], illuminant, camera, **kw)
                            for n in names])
