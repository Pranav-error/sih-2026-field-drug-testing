# Capture protocol — track F

**SIH26231** · the critical path

Track F cannot be compressed by working harder in the last 48 hours
([`ARCHITECTURE.md`](ARCHITECTURE.md) §11). Everything else in this repository is
finished or nearly so; none of it produces a number worth quoting until this is done.

The failure this document exists to prevent: photograph two thousand cards over
three weekends, then discover a third of them are unusable because of a reflection
nobody noticed at the time.

## Before the first session

1. **Print cards.** `python -m ftr.printable --out card.png --serial 0417 --batch B12`
   at 100% scale, **matte** stock, **colour management off**. Gloss puts a specular
   highlight on the patches, which is the one degradation the pipeline rejects
   outright rather than corrects. Print several; a creased card is a capture
   condition, not a write-off.
2. **Record the batch.** `print_batch` goes into every record. One batch per print
   run, and keep one card per batch unused as the archive copy.
3. **Photograph one card and run `survey` before the session proper.** Five minutes
   here is worth a weekend.

## Filing convention

The label and the condition are both read from the path, so filing the photographs
*is* recording the capture matrix:

```
captures/<label>/<illuminant>/<anything>.jpg
```

```
captures/
  opiate_class/
    daylight/      IMG_0001.jpg …
    shade/
    tungsten/
    fluorescent/
    torch/
  amphetamine_class/
    …
  negative/
    …
```

Labels are surrogate colorimetric targets, not controlled substances (§7). Use the
same label names the reference loci will carry.

## During the session

```sh
python -m ftr.ingest survey captures/ --json survey.json
```

Run it **at the end of every session**, not at the end of the project. It reports:

- what fraction of the set is usable,
- **why** the rest is not, grouped by cause rather than by measurement,
- what to tell the person holding the phone,
- usable rate broken down by label and by condition,
- any condition with **nothing** usable — which is a protocol problem, and more
  photographs under it will not help.

Refusals are grouped by cause, so `0.50 stops` and `0.51 stops` count as one
finding rather than two. That grouping is the difference between seeing a problem
and burying it.

## Target matrix

From §7.2, and the thing to actually plan the sessions around:

| Axis | Levels |
|---|---|
| Illuminant | daylight, open shade, tungsten, fluorescent, phone torch |
| Exposure | −1, 0, +1 bias |
| Angle | 0°, 10°, 20°, 30° |
| Device | ≥ 3 phone models |
| Card condition | pristine, creased, faded, partially occluded |
| Surface | dry, wet |

Aim for **≥ 2,000 usable** frames, not 2,000 taken. `survey` is what tells the
difference.

## Calibration, and the only accuracy claim worth making

```sh
python -m ftr.ingest calibrate captures/ --holdout tungsten
```

This fits the reference loci and the conformal threshold on everything *except*
one illuminant, then evaluates on that illuminant alone. §7.5: **held-out
condition, not held-out samples.** A random split flatters the model, and the
report says so in as many words when you ask for one.

Rotate the holdout through every illuminant and report the worst.

### What a real result looks like

On a synthetic set, holding out tungsten:

```
  frames evaluated   36
  coverage            83.3%   (target >= 95%)
  singleton rate      83.3%   (how often it commits)
  error rate           0.0%   (committed and wrong)

  ! Coverage is below the stated bound. The calibration set is not
    exchangeable with this condition — which is the finding, not a bug.
```

Read that carefully, because it is the shape of an honest result. Coverage missed
its bound under an unseen illuminant — and the error rate was **zero**. The system
did not get things wrong; it abstained more. That is the degradation the whole
design is built to produce, and it is a far better sentence in front of a judge
than a 97% accuracy figure from a random split.

If coverage misses the bound, the honest responses are: capture that illuminant
into the calibration set, tighten the protocol, or state the limitation. Never
lower α to make the number look better — α is the guarantee, not a dial.

## What the tooling will not do for you

- It cannot tell you the surrogate ladder resembles real reagent chemistry. It
  does not. Substituting NCB colour standards is a data change, not an
  architecture change, and the submission should say so unprompted (§7).
- It cannot photograph a creased card for you, and the degraded-condition set is
  the one most likely to be skipped and most likely to matter in the field.
- Nominal patch values are what the card is *printed to*, not what it *is*. Real
  values need a spectrophotometer reading per print batch. Until that exists,
  every accuracy figure carries the nominal-values caveat.
