# Architecture diagram — design brief

Copy-paste brief for a design tool. Describes the SIH26231 high-level architecture
diagram: structure, exact text, and the intent that must survive a redesign.

---

## What it is

A high-level system architecture diagram for a Smart India Hackathon slide.
The system photographs a colorimetric drug-test strip and turns the result into
court-admissible evidence.

**Landscape, roughly 16:9 or a little wider. Must stay legible projected on a
screen from the back of a room.**

## The organising idea — do not lose this

Most architecture diagrams are grouped by *component*. This one is grouped by
**trust boundary**: who is being asked to believe what, and on whose word. That is
the entire argument of the system, so the four horizontal bands are the primary
structure and the boxes are secondary.

Read top to bottom. Flow inside each band reads left to right.

---

## Band 1 — PHYSICAL WORLD
*Right-aligned caption:* "exists before any software runs · no new hardware"

Three boxes, left to right, joined by arrows:

1. **EXISTING REAGENT KIT** — "whatever NCB already buys / no vendor lock-in, reagent is declared"
2. **PRINTED REFERENCE CARD** — "matte A4 · 4 fiducials · 15 patches / 8 neutrals · reaction well"
3. **ONE FRAME** — "card and strip together, co-planar, under one light"

Boxes 1 and 2 are neutral grey (they are not ours). Box 3 is the accent blue —
it is where our system begins.

## Band 2 — THE HANDSET — software a court has no reason to trust
*Right-aligned caption:* "everything here is re-derivable from the raw frame by somebody else"

Four boxes in a row, joined left to right:

1. **L1 MEASURE** — "fiducials → homography / → divide out the light field / → CIELAB, with a residual"
2. **L2 DECIDE** — "conformal prediction set / {positive} · {a,b} · ∅ / with a stated error bound α"
3. **L3 CORROBORATE** — "GNSS raw · Wi-Fi · cell · motion / agreement scored, and every disagreement recorded"
4. **QUALITY GATE** — "a frame that cannot be measured yields an ABSTENTION, never a confident guess"

Boxes 1–3 accent blue. Box 4 in **amber**, because it is a refusal, not a step.

Below that row, a full-width horizontal strip:

> **canonical CBOR — deterministic bytes, no floats, so two independent
> implementations reach the same digest, forever**

## Band 3 — SECURE ELEMENT — StrongBox / TEE
*Right-aligned caption:* "key generated inside, non-exportable, attested to a hardware root"

Two wide boxes side by side, arrow between them, in a **darker blue** than band 2
(this is hardware, not software):

1. **L4 SEAL** — "SHA-256 → signed inside the secure element / → key attestation chain attached"
2. **L5 CHAIN** — "prev_record_hash → append-only ledger / anchoring window stated, never hidden"

## Band 4 — ANYONE, LATER — no network, no trust in us
*Right-aligned caption:* "the only part that makes the rest worth anything"

Give this band a faint green-tinted background so it reads as different in kind.
Three boxes:

1. **L6 STATUTORY OUTPUT** (amber) — "BSA 2023 section 63 certificate / Part A
   auto-populated: hash value + algorithm" … then, after a gap, "every oath left
   blank for a human"
2. **HANDOFF** (amber) — "eSakshya / CCTNS-2.0 envelope / routed by FIR + seizure
   memo" … then "CCTNS-2.0 stays the system of record — no parallel silo built"
3. **L7 INDEPENDENT VERIFIER** (green/teal, visually the strongest box on the
   diagram) — "recompute · check signature · walk attestation · replay chain ·
   re-run L1/L2" … then "**PROVEN / ASSERTED / UNVERIFIABLE**" … then "two
   implementations: Python + Dart"

Under the verifier, in italic teal:

> *A verified record is not a true result. It is an unaltered one.*

---

## Arrows between bands — label every one

Each arrow says what actually crosses the boundary. This is the point of the
diagram; unlabelled arrows lose it.

| From | To | Label |
|---|---|---|
| ONE FRAME (band 1) | L1 MEASURE (band 2) | **the captured frame** |
| canonical CBOR strip | L4 SEAL | **digest** |
| L4 SEAL | L6 STATUTORY OUTPUT | *(unlabelled)* |
| L4 SEAL | HANDOFF | *(unlabelled)* |
| L5 CHAIN | L7 INDEPENDENT VERIFIER | **the sealed record** |
| L6 | HANDOFF | *(unlabelled, short)* |

The frame arrow travels right-to-left (ONE FRAME is at the right of band 1, L1 is
at the left of band 2). Route it orthogonally through the gap between the bands —
an arc curves back up through the physical boxes and reads as pointing the wrong
way.

---

## Palette

```
accent blue    #0070C0    handset layers, primary
deep blue      #134E7A    secure element — hardware, so darker
teal / green   #0F7B6C    the verifier, and the closing line
amber          #A66A00    refusals, and anything awaiting a human
crimson        #A32C4A    only if something must read as a warning
neutral grey   #7A7A85    the physical objects that are not ours
ink            #14121C    body text
band ground    #F7F8FA    bands 1–3
band ground    #F3FAF8    band 4, faintly green
```

Blue for the accent because the SIH template uses `#0070C0`. Amber and teal are
semantic, not decorative: **amber always means a human or a refusal, teal always
means something a stranger can check.** Do not use green to mean "good" — a
positive drug test is not a success state, and nothing in this diagram should
imply it is.

## Typography

Clean sans throughout. Box titles bold, in a solid colour bar across the top of
each box, white text. Body text small, regular, centred, generous line spacing.
Band labels bold in grey, band captions italic and smaller.

## Rules that matter more than the styling

1. **The bands are the structure.** If a redesign makes the boxes prominent and the
   bands decorative, it has lost the argument.
2. **Every cross-band arrow carries a label.**
3. **The bottom band should feel like the destination**, not a footnote — it is
   the widest, and it is where the closing line sits.
4. Keep the phrases "software a court has no reason to trust" and "no network, no
   trust in us" verbatim. They are doing the persuading.
5. Boxes must be sized to their text. Do not let body text overflow a box.
