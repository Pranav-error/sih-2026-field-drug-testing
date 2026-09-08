# Where the camera pipeline works, and where it lies

**SIH26231** · findings from `core/tools/robustness.py` and `core/tools/ablation.py`

Three outcomes, and they are not equally bad:

| | |
|---|---|
| **accept + accurate** | the pipeline worked |
| **reject** | it refused — correctly, or over-cautiously |
| **accept + wrong** | **the dangerous quadrant** |

A robustness report that counts only the first two is marketing. A false accept in
the field is a wrong presumptive result attached to a signed, hardware-attested,
independently verifiable record — which is to say, a wrong answer wearing all the
clothes of a right one. Everything below hunts the third case.

All of it is measured on **synthetic frames**. Real ink, paper texture, lens
vignetting and a real ISP will move every threshold quoted here. This is a
rehearsal of the analysis, not the analysis.

---

## 1. The operating envelope

83 conditions swept. After the fixes in §2: **32 accepted and accurate, 51
refused, 0 false accepts**, worst error among accepted frames **3.27 dE2000**.

| Condition | Works to | Refused beyond | Caught by |
|---|---|---|---|
| Tilt | 20° | 25° | tilt estimate from the homography |
| Distance | 0.30× scale | 0.25× | sharpness |
| Rotation | any | — | fiducials are rotation-invariant |
| Creased card | flat only | depth 0.15 | **tilt** — a fold is two planes, and no homography fits both |
| Occluded fiducial | none | any occlusion | fiducial count (3/4 → refuse) |
| Soft shadow | 0.75 depth | — | corrected by INUC |
| **Hard shadow edge** | none | depth 0.20 | substrate probe (§2.1) |
| Mixed illuminants | blend 0.25 | sharper | light-field residual |
| Torch hotspot | none | glare 0.10 | illumination residual |
| Exposure | ×0.5 – ×1.0 | ×0.25 / ×1.3 | dynamic range / clipping |
| Defocus | 0 px | 2 px | sharpness |
| Motion blur | 7 px | 13 px | sharpness, then detection |
| JPEG | q40 | q25 | light-field residual |
| Sensor noise | σ8 | σ15 | patch spread |

Two of these are accidental defences worth keeping deliberately: a **creased card**
is caught by the tilt metric rather than by anything designed for it, and an
**occluded fiducial** is caught by insisting on all four when three would suffice
geometrically. The fourth marker exists precisely so the reprojection residual
means something; refusing at three is what converts that redundancy into a check.

---

## 2. Three defects the sweep found

### 2.1 A hard shadow edge was accepted at 17 dE

The worst finding. INUC fits a **bi-quadratic** illumination surface from the eight
neutral patches. A shadow *edge* is a step, which is not bi-quadratic — and worse,
a step falling between the neutrals is invisible to the fit residual. A synthetic
doorway shadow was accepted carrying **17.3 dE** of error: enough to change which
substance class is reported.

**Fix:** the card substrate is uniform paper, so after dividing out the fitted
light field, every point on it should read the same value. `substrate_residual()`
probes **196 points** across the card and reports the spread of what remains.

| | light-field residual (stops) |
|---|---|
| ideal | 0.042 |
| legitimate soft shadow | 0.057 |
| hard shadow, depth 0.20 | 0.360 |
| hard shadow, depth 0.50 | 1.042 |

The threshold sits at 0.12, in the gap. The lesson generalises: **eight points were
enough to fit a surface and far too few to test one.**

### 2.2 JPEG q10 was accepted at 11.6 dE

Heavy compression corrupts colour without blurring the frame, so nothing in the
original gate noticed. It is now caught by the same substrate probe — block
boundaries put structure into the paper that the light field cannot explain.

### 2.3 Sensor noise was invisible

`PatchSample.spread` was computed and never used. Worse, it was computed as the
standard deviation across all three channels together, which measures the patch's
*colour*: a purple patch has R≠G≠B and looked "noisy" while being perfectly clean.
Now per-channel, relative to brightness, and in the gate.

---

## 3. The finding that matters: replay is not defeated

`ARCHITECTURE.md` §10 row 1 claimed:

> | Photograph a photo of a positive strip (replay) | **Defeated by:** Card must be
> co-planar and co-illuminated with the strip; INUC residual + moiré/screen detection |

**That reasoning is wrong, and the claim is false.**

A replay reproduces the *entire scene* — card, fiducials, strip, and the light that
fell on all of them. Co-planarity and co-illumination are therefore **preserved**,
not broken. Worse, the device transform is solved against whatever card is in the
frame, so a photograph of a card is *self-consistent* by construction: normalising
against a reproduced chart makes the reproduction look like a perfect capture.

Measured, against an adversary who invests in the reproduction:

| Attack | Verdict | dE |
|---|---|---|
| Print replay — cheap inkjet | reject (soft) | 1.49 |
| Print replay — good inkjet | reject (light field) | 0.45 |
| **Print replay — photo lab print** | **ACCEPT** | **0.48** |
| **Print replay — dye-sublimation** | **ACCEPT** | **0.45** |
| Screen replay — phone LCD, close | reject (light field) | 4.09 |
| Screen replay — phone LCD, further | reject (light field) | 1.85 |
| **Screen replay — high-DPI OLED** | **ACCEPT** | **0.33** |
| **Screen replay — defocused subpixels** | **ACCEPT** | **0.45** |

What catches a *cheap* replay is reproduction artefacts — print blur, screen
subpixel structure. Better equipment removes them, and the good reproductions do
not merely pass: they read as **excellent** captures, better than most honest
field frames.

`test_a_QUALITY_replay_defeats_the_pipeline` asserts this vulnerability
deliberately, so it cannot be quietly forgotten.

### What would actually defend against it

None of these is built, and each has a cost:

1. **Parallax across two frames.** A real strip sits *on* the card and has
   thickness; a print is flat. Two frames from slightly different angles reveal
   micro-relief that no flat reproduction has. Cheapest honest defence, and it
   needs a second capture.
2. **Active illumination differential.** Torch on, torch off. A physical strip's
   specular response differs from paper's. Weaker than parallax, and defeated by a
   glossy print.
3. **A physically unclonable card feature.** A random speckle pattern recorded at
   issue; a photocopy loses the fine structure. Strongest, but it edges toward
   "new hardware", which the PS forbids, and it requires a card registry.

### What the threat model should say instead

> | 1 | Photograph a photo of a positive strip (replay) | Cheap reproductions fail on blur or subpixel structure | **A quality print or a high-DPI screen passes, and reads as an excellent capture. Not defended. Needs multi-frame parallax or a physically unclonable card.** |

That is a worse row than the original. It is also true, and a threat model that
overstates its defences is worth less than no threat model at all — a judge who
finds this gap themselves concludes the team never looked.

---

## 4. Ablation: the learned component does not earn its place

`ARCHITECTURE.md` §11 says TFLite is used for L2 *"if a learned component survives
ablation"*. It does not.

960 synthetic frames, 4 classes (two deliberately ~5 dE apart), 6 illuminants.
Every arm wrapped in the **same** conformal layer, so what is compared is the score
function and not whether abstention exists. Evaluated on a **held-out illuminant**,
rotated through all six.

| Scorer | Coverage | Commits | Errors |
|---|---|---|---|
| **A. nearest locus, ΔE2000** | **94.9%** | **94.9%** | **0.0%** |
| B. Mahalanobis to class covariance | 91.1% | 91.1% | 0.0% |
| C. logistic regression on Lab | 94.1% | 94.1% | 0.0% |

Per-holdout coverage exposes why B fails: it collapses to **60.5%** on tungsten,
because per-class covariance estimated under other illuminants does not transfer.

**The simplest scorer wins outright** — best coverage, best commit rate, and it is
the only one a defence expert can recompute on paper. Logistic regression is 0.8
points *worse*; there is nothing to trade a closed-form score away for.

Two things hold across every arm:

- **Errors are 0.0% everywhere.** Under an illuminant it has never seen, the system
  loses coverage by abstaining, not by committing to a wrong label. That is the
  behaviour the whole design exists to produce, and it now has a number.
- **Coverage sits just under the 95% bound.** The calibration set is not perfectly
  exchangeable with an unseen illuminant. That is the honest finding, and the
  response is to capture that illuminant into the calibration set — never to lower
  α until the number looks better.

---

## 5. On datasets

There is no public dataset of colorimetric drug-test strip images. The published
smartphone-colorimetry work (pH strips, peroxide strips, urinalysis) describes
datasets built for each study and does not release them. The problem statement's
own `dataset_link` is empty, which is why §7 makes data acquisition part of the
deliverable rather than an assumption.

Everything in this document therefore rests on `core/tests/synth.py`, a synthetic
camera. It reproduces the optical problem — distinguishing nearby colours under
uncontrolled illumination — and **none of the chemistry**. It has no ink, no paper
gloss, no real ISP, and no reagent.

So: no number here is a field accuracy, and none belongs in the submission without
the sentence that says so. What this work does establish is that the analysis
machinery is built and exercised, so when the physical capture set arrives
(`CAPTURE.md`), nothing is being written for the first time against a deadline.

## Reproducing

```sh
python core/tools/robustness.py                    # the envelope sweep
python core/tools/make_dataset.py /tmp/ds --per-condition 40
python core/tools/ablation.py /tmp/ds              # A vs B vs C
python -m pytest core/tests/test_robustness.py     # 34 tests
```

---

## 6. The synthetic camera was measuring an easier problem

Everything in §1–§4 was measured with `tests/synth.py`, which models an illuminant
as a **per-channel RGB gain**. That has a consequence which invalidates every
cross-illuminant claim taken from it:

> **A per-channel gain cannot produce metamerism.** Two surfaces the camera records
> identically under one light are recorded identically under *all* of them, because
> both are scaled by the same factor.

Metamerism — surfaces that match under one illuminant and diverge under another —
is the entire reason colour constancy is hard. A simulator without it is testing
an easier problem than the field.

`core/ftr/spectral.py` fixes this by rendering the way a camera actually works:

```
R_c = ∫ reflectance(λ) · illuminant(λ) · sensitivity_c(λ) dλ
```

with all three terms measured rather than invented — see
[`../data/spectral/README.md`](../data/spectral/README.md) for sources and licence.

### Metamerism is real, and large

Relative RGB separation between two ColorChecker patches, through the Nokia N900
sensor (the only mobile camera in the database):

| Patch A | Patch B | D65 | A | FL11 | swing |
|---|---|---|---|---|---|
| blue | white 9.5 | 6.71 | 9.53 | 8.36 | **2.81** |
| blue | yellow | 3.88 | 6.02 | 5.25 | **2.14** |
| purple | white 9.5 | 9.23 | 9.65 | 10.65 | **1.41** |

Under the gain model every one of those swings is exactly **0.00**.

### What the card-in-frame approach actually achieves

Leave-one-patch-out on the chart — fit the transform on 23 patches, predict the
24th, compare against its true colour under D65. The held-out patch is a surface
the transform has never seen, which is the situation of the reaction well.

Median ΔE2000 across all 28 cameras:

| D65 | D50 | A | FL2 | FL11 | LED-B3 |
|---|---|---|---|---|---|
| **0.50** | 0.66 | **1.24** | 1.01 | 1.17 | 0.63 |

A non-reference illuminant costs about **2.5×**. Two details worth keeping:

- **The mobile sensor is fine.** Nokia N900 scores 0.62 / 0.97 — mid-pack, better
  than several DSLRs. The approach does not depend on a good camera.
- **Industrial sensors are worst** (Point Grey, 2.53 dE). Unusual sensitivities are
  harder to fit with six root-polynomial terms, which is a bound on the method.

### The ablation, redone honestly

8,064 measurements rendered across 28 cameras × 6 illuminants × 4 classes (two
deliberately close), every arm in the same conformal wrapper:

| Split | A. nearest locus | B. Mahalanobis | C. logistic |
|---|---|---|---|
| Held-out **illuminant** | **94.5%** | 91.8% | 94.5% |
| Held-out **camera** | **95.1%** | 94.8% | 94.8% |
| Calibrate on DSLRs → deploy on phones | **93.2%** | 92.8% | 92.0% |

**The verdict from §4 survives contact with physics.** Nearest-locus ΔE2000 is best
or tied-best in every split, and it remains the only one a defence expert can
recompute on paper. Errors stay at **0.0% in every cell**: under an unseen light or
an unseen sensor, the system loses coverage by abstaining, never by committing to a
wrong label.

Two findings that are new, and that only the physical renderer could produce:

1. **Cross-camera generalisation is good** — 95.1%, the only split that meets the
   95% bound. The card-in-frame normalisation does its job across sensors, which is
   the thing that makes a kit-agnostic, handset-agnostic deployment plausible.
2. **Calibrating on the wrong device class costs about 2 points.** Fit on DSLRs,
   deploy on phones, and coverage falls to 93.2%. The capture matrix's "≥3 device
   models" should mean three *issued handsets*, not three cameras.

### What is still borrowed

The reaction spectra are ColorChecker patches standing in for reagent
developments. There is no public spectral library of NDPS presumptive-test colour
developments and no public dataset of colorimetric drug-test strip images — the
published smartphone-colorimetry work releases none of its data. The optics are now
honest; the chemistry is still borrowed, and the submission should say so before
anyone asks.
