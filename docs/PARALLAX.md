# Closing the replay hole

**SIH26231** · the defence for [`ARCHITECTURE.md`](ARCHITECTURE.md) §10 row 1

[`ROBUSTNESS.md`](ROBUSTNESS.md) §3 reported that the replay defence claimed in the
threat model was false. A photo-lab print and a high-DPI screen both passed every
colorimetric check, reading as **excellent** captures — better than most honest
field frames. This is the fix, and the honest account of what it does not fix.

## Why the original reasoning was wrong

> *Card must be co-planar and co-illuminated with the strip.*

A replay reproduces the **whole scene**. The card, the fiducials, the strip and the
light that fell on all of them are photographed together, so co-planarity and
co-illumination are *preserved*, not broken. Worse, the device transform is solved
against whatever card is in the frame — so a photograph of a card is
**self-consistent by construction**, and normalising against a reproduced chart
makes the reproduction look perfect.

Cheap replays failed only on reproduction artefacts: print blur, screen subpixel
structure. Better equipment removes those. That was never a defence; it was a
quality threshold.

## What a reproduction cannot reproduce

Depth.

Two views of a plane are related exactly by a homography. Rectify both frames using
the homography fitted to the card's four corner fiducials — which lie *on* the card
plane — and every point on that plane lands in the same place in both views. A
point at height *h* above the plane does not:

```
displacement  ≈  b · h / (D − h)        millimetres on the card
```

for camera baseline *b* and distance *D*. So **residual displacement after
rectification is out-of-plane structure**, and a flat reproduction yields exactly
zero of it — at every baseline, at every distance, at any print quality. That is
not a heuristic with a threshold to tune. It is a property of being flat.

## The card needs a tab, and the measurement says so

Measured on the two-view renderer (`core/tests/synth3d.py`), which projects through
a pinhole camera so parallax falls out of the geometry rather than being faked:

| Feature height | Predicted | Measured | Height recovered |
|---|---|---|---|
| 0.0 mm (flat) | 0.0 px | **0.0 px** | — |
| 0.4 mm (a wet strip) | 1.3 px | 1.1 px | 0.3 mm |
| 1.0 mm | 3.4 px | 3.2 px | 1.0 mm |
| 2.0 mm | 6.8 px | 6.7 px | 2.0 mm |
| 4.0 mm | 13.7 px | 13.6 px | 4.0 mm |
| **8.0 mm (the tab)** | **28.2 px** | **28.1 px** | **8.0 mm** |

The measurement tracks the prediction across the whole range and inverts to the
true height, which is what makes this a depth measurement rather than a correlation
with something else.

It also settles a design question. **A wet strip lying on the card is about 0.4 mm
and yields roughly one pixel** — below the noise floor, and not something to rest a
forensic claim on. So the card carries a **liveness tab**: a flap on the same
printed sheet, scored twice and folded up 8 mm and back over the card. No new
hardware, no die-cut, no glue — two fold lines on the sheet that was already being
printed.

It lands in the clear strip between the bottom-left fiducial and the reaction well,
so it covers no patch and never occludes the measurement.

## The attack, before and after

| Attack | Colorimetry alone | With the parallax check |
|---|---|---|
| Photo-lab print | **ACCEPT** — 0.48 ΔE, reads as excellent | **REFUSED** — 0.1 px |
| High-DPI screen | **ACCEPT** — 0.33 ΔE | **REFUSED** — 0.0 px |
| Physical card | accept | **LIVE** — 28.1 px |

The refusal message is written for someone who does not trust us:

> FLAT. Measured 0.1 px of parallax where a physical card predicts 28.2 px. A print
> or a screen gives zero, at any print quality, because it is flat.

## Operating envelope

- **Baseline.** Works from **10 mm** of hand movement between the two frames. An
  officer cannot be asked to measure a baseline, so the check has to tolerate any
  ordinary movement; at 80 mm the card starts leaving the frame.
- **Noise.** Survives σ = 20 sensor noise (28.1 → 26.0 px). Phase correlation needs
  no features, which matters because the tab is small and low-texture.
- **Strictness.** A *known* height predicts a *specific* displacement, so the check
  requires the right amount of depth, not merely some. A 2 mm feature does not
  satisfy an 8 mm expectation.
- **Card motion.** If the card moves or bends between frames the plane residual
  rises and the check refuses rather than reporting a number it cannot support.

## What still gets through — say this out loud

**A synchronised stereo replay.** Parallax proves the scene *had* depth. It does not
prove the depth was there **now**. An attacker holding the genuine two frames — or
a video of a real capture — and replaying them in step with the app's two captures
reproduces the parallax exactly, because it *is* the real parallax.

That is materially harder than printing a photograph: it needs the genuine stereo
pair, and playback synchronised to a capture the attacker does not control. But it
is not defended, and `test_a_synchronised_stereo_replay_still_defeats_this` asserts
it so it cannot be quietly forgotten.

Defeating it needs the app to demand something the attacker cannot predict — an
unpredictable number of frames, a torch challenge pattern, or capture timing only
the app knows. **None of that is built.**

Two further limits, stated rather than discovered later:

- **A physically curved reproduction** produces some parallax. It produces it across
  the whole sheet rather than localised at the tab, and it raises the plane
  residual, so the check should catch it — but that has not been tested, because
  the renderer models flat surfaces only.
- **An attacker who prints the card, folds the tab, and photographs a real reacted
  strip** passes, and should: at that point they have performed a real test on a
  substituted sample. That is sample substitution, which no camera can detect, and
  it already sits in the verifier's UNVERIFIABLE bucket.

## The defence has to reach the record

A liveness check that lives only in the app is a demo. This project's thesis is
that **the record is the product**, so the result is a top-level field of the FTR —
a peer of `colorimetry` and `classification`, because whether the scene was
physically present is a finding about the *test*, not a property of an image file:

```
liveness:
  checked                 false means a single frame — absent is not the same as passed
  live
  displacement_px_x100    what was measured
  predicted_px_x100       what the geometry required
  plane_residual_px_x100  did the card itself re-align
  confidence_x1000
  tab_height_mm_x10 · baseline_mm_x10 · distance_mm_x10
```

Everything needed to re-check the arithmetic is in the record, so a reader can
redo the sum rather than take the number on trust.

**A flat capture is treated as a refusal, not an error.** The record is still
sealed and chained — deleting it is the attack the ledger exists to stop — and it
carries no result plus the reason. Exactly how a failed quality gate behaves.

### What each verifier says

| Record state | Verdict |
|---|---|
| Checked, live | **ASSERTED** — "the app measured 28.1 px against 28.2 px predicted… supply both frames to move this from asserted to proven" |
| Checked, flat | **FAILURE** — "LIVENESS FAILED… The record is authentic; what it photographed is in question" |
| Not checked | **ASSERTED** + an entry in **UNVERIFIABLE** — "cannot be distinguished from a photograph of a card" |

That third row is the point of recording `checked: false` explicitly. A record with
no liveness block would be silently indistinguishable from one where the check
passed, and silence should never read as a pass.

The failure text separates two things a court must not have conflated: the record
is **unaltered**, and what it photographed is **in question**. Those are different
findings and only one of them is about integrity.

Both implementations report on liveness independently, in their own words, and are
tested against each other — Dart cannot re-derive the parallax (it does not read
frames) and says so rather than implying it checked.

## Reproducing

```sh
python core/tools/parallax_study.py           # the sensitivity study above
python -m pytest core/tests/test_parallax.py  # 19 tests
python -m ftr.printable --out card.png        # the card, with the fold lines
```

All of it is measured on synthetic frames. The geometry is exact, but the noise
floor, the confidence threshold and the tolerance are calibrated on simulations and
must be re-derived from the physical capture set ([`CAPTURE.md`](CAPTURE.md)) before
any rejection rate is quoted.
