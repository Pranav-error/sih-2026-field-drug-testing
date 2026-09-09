# What we need, and what we must not go looking for

Track F is the critical path. Everything else is built; **no number in this
repository is a field accuracy** because no printed card has been through the
capture matrix. This is the shopping list, in priority order.

> **First, the hard line.** Do not attempt to obtain controlled substances, and do
> not attempt to obtain live NDPS reagent kits without written authorisation from
> the department. A student team cannot lawfully hold either, and the architecture
> was designed from the start so that neither is required: L1 and L3–L7 are
> substance-independent, and L2 needs only reference colours. Substituting NCB
> standards is a **data change, not an architecture change**. Anyone who suggests
> otherwise has misunderstood the design.

---

## 1. Photographs of the printed card — the blocker

**Nobody else can do this. It needs a person, a printer, and a weekend.**

Print cards: `python -m ftr.printable --out card.png --serial 0417 --batch B12`
— 100% scale, **matte** stock, colour management **off**. Score and fold the tab.

Then photograph, filing as `captures/<label>/<illuminant>/<anything>.jpg`, because
the folder names *are* the capture matrix:

| Axis | Levels needed |
|---|---|
| Illuminant | daylight, open shade, tungsten, fluorescent, phone torch — **5 minimum** |
| Exposure | −1, 0, +1 bias |
| Angle | 0°, 10°, 20°, 30° |
| Device | **≥ 3 issued handsets**, not three cameras — see §6 |
| Card condition | pristine, creased, faded, partially occluded |
| Surface | dry and wet |

Target **≥ 2,000 usable** frames — not 2,000 taken. Run
`ftr-ingest survey captures/` **at the end of every session**, not at the end of the
project: it reports what fraction is usable and *why the rest is not*, and names any
condition where nothing is usable, which is a protocol problem more photographs will
not fix.

### Also needed: pairs for liveness

For each condition, some **two-frame pairs** — same scene, hand moved ~2–5 cm
between shots. That is what the parallax check consumes. Roughly 200 pairs is
enough to characterise it.

### And the negative case, which is the best demo you have

Photograph **the card displayed on a phone screen**, and **a printed photograph of
the card**. Those are the replay attack. They should be refused.

---

## 2. Reagent colour standards — what a real reaction looks like

Right now every "reaction colour" in this repository is a ColorChecker patch
standing in for chemistry. The optics are honest; the chemistry is borrowed.

What would replace it, in descending order of usefulness:

1. **The colour reference chart that ships inside a presumptive test kit.** Every
   Marquis/Mecke/Scott kit includes one. A flat, well-lit photograph of that chart
   is legal, safe, and directly usable — it *is* the manufacturer's statement of
   what each result looks like.
2. **Published colour tables** from forensic literature or a manufacturer's
   datasheet: "Marquis + opiates → purple to black", with any Munsell or Pantone
   references if given.
3. **NCB's own SOP or training material** naming the expected colour developments
   for the reagents in scope. Ask, in writing, through the department.

⚠ **Transcribe these; never write them from memory.** A recalled CIEDE2000 value
already cost a debugging cycle here — see `DETERMINISM.md`.

---

## 3. Which reagents are actually in scope

The PS does not say. This decides the number of reference loci and therefore how
hard the classification problem is — two well-separated colours is easy, four
overlapping ones is the real problem. **Ask NCB.** Failing that, state the assumed
set in the submission rather than leaving it implicit.

---

## 4. The §63 Schedule, from the Gazette

The certificate labels in `core/ftr/data/bsa63_schedule.json` are transcribed from
a bare-Act repository, **not** the official Gazette, so every certificate is stamped
`DRAFT — NOT FOR FILING`.

**One afternoon's work:** open the eGazette PDF of the Bharatiya Sakshya Adhiniyam
2023, compare the Schedule word for word, then set `verification_level` to
`"official"` and `verified` to `true`. That single flag turns every certificate the
system emits from a draft into a filable document.

---

## 5. Spectrophotometer reading of the printed card batch

The card's patch colours are **nominal** — what it is printed *to*, not what it
*is*. Offset printing, paper stock and ink batch shift colour by several ΔE.

If any university lab has a spectrophotometer or a colorimeter, one reading of one
printed batch replaces the nominal values with measured ones, keyed by
`print_batch`. Until then every accuracy figure carries the nominal-values caveat.

Not a blocker. But it is the difference between "about right" and "measured".

---

## 6. Which handsets police are actually issued

Two things depend on it:

- **StrongBox availability.** It is not universal. The app falls back to the TEE and
  records the weaker guarantee, but knowing the real distribution changes what the
  submission can claim.
- **The capture matrix.** "Three device models" must mean three *issued handsets*.
  Measured on rendered data, calibrating on DSLRs and deploying on phones costs
  about two points of coverage — so the wrong three devices is a real error.

---

## 7. Whether eSakshya has a documented ingest interface

`ARCHITECTURE.md` §13 question 2, still open. The envelope we emit is well-formed
and **marked PROVISIONAL** because no published specification has been found. If NCRB
or NIC will confirm the format, the envelope stops being plausible and starts being
correct.

---

## What is already sourced, and needs nothing

| | |
|---|---|
| Camera spectral sensitivities | Jiang et al. (2013), 28 cameras, Zenodo 3245883 — fetched by script, SHA-verified |
| CIE illuminant SPDs, 1931 observer, ColorChecker reflectances | `colour-science`, BSD-3 |
| CIEDE2000 conformance data | Sharma, Wu & Dalal (2005) — ⚠ transcribe the full table from the paper before quoting it |
| NDPS caseload, court backlog, forensic spend | NCRB *Crime in India 2022*; MHA 2022–2026 |
| BSA §63 section text | indiankanoon.org/doc/125020475 |

---

## If you can only do one thing

**§1.** Print ten cards, fold the tabs, and photograph them across five illuminants
with two handsets. Even 200 usable frames turns every figure in the submission from
*"measured on synthetic frames"* into *"measured on real captures"* — and that is
the sentence a judge will ask about.
