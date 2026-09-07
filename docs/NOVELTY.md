# Novelty and Patentability Argument

**SIH26231 — Digital Companion for Field Drug Testing**
Prior-art survey, honest assessment of what is *not* novel, and the narrowest defensible claim.

---

## 0. Executive summary

The obvious build — *photograph a colorimetric drug test, classify the colour, log GPS and time,
export a PDF* — **is not novel. It is a shipping commercial product and has been for years.**

Any novelty argument that does not begin by conceding that is worthless, and will be dismantled in
about ninety seconds by any judge who has seen a law-enforcement product catalogue.

What survives prior art is narrower and, precisely because it is narrower, defensible:

> A **kit-agnostic** colorimetric measurement whose result is bound, at the moment of capture, into a
> **hardware-attested, append-only, offline-verifiable** record that carries a **calibrated
> abstention guarantee** and emits a **jurisdiction-specific statutory certificate** — such that an
> independent verifier, with no trust in the capturing app, can later re-derive the result from the
> raw frame and state precisely what is proven and what is merely asserted.

The inventive step is **not** the classifier. It is the binding, the abstention bound, and the
verifiability.

---

## 1. Prior art — what already exists

### 1.1 The killer: DetectaChem MobileDetect (commercial, deployed)

A smartphone application paired with colorimetric test pouches. Documented capabilities include:
scanning a **QR code on the pouch** for automated result reading, automated colour interpretation in
seconds, and generation of test reports carrying **GPS mapping, images, notes, date and time**,
shareable as PDF, marketed explicitly as aiding *"evidence collection and chain-of-evidence."*

**This is the naive PS solution, already built, already sold to police.**

What it does *not* appear to do, on the public record:

| Capability | MobileDetect (public info) | Consequence |
|---|---|---|
| Works with arbitrary existing kits | ✗ — tied to their serialised pouches | **The PS explicitly requires kit-agnostic operation** |
| Cryptographic signing of records | Not documented | "Chain-of-evidence" here means structured reporting |
| Hardware key attestation | Not documented | No proof the record came from unmodified hardware |
| Append-only chain / anti-backdating | Not documented | Reports are files; files can be regenerated |
| Independent offline verifier | Not documented | Verification requires trusting the vendor's app |
| Calibrated abstention with error bound | Not documented | "Inconclusive" appears to be a category, not a guarantee |
| Indian statutory certificate output | ✗ | US product; no BSA §63 concept |

⚠️ **Caveat, stated plainly:** these gaps are inferred from public marketing and reseller material,
not from the product's source or a security assessment. Before making any of these claims in a patent
specification, at least one team member must obtain and examine the actual app, or the claims must be
softened to "not disclosed in available literature." Do not assert absence of a feature you have not
tried to find.

### 1.2 Academic smartphone colorimetry — mature field

Extensive published work exists on: smartphone RGB capture of presumptive colour tests (including
methamphetamine via Simon's/Marquis reagents), machine-learning quantification of colorimetric tests,
microfluidic + smartphone presumptive drug field-testing, computer-vision approaches to xylazine
presumptive tests, and the well-established finding that **device-specific calibration is necessary**
for meaningful smartphone colorimetry. Reference-card correction systems (ColorChecker-derived,
HueDx-style local colour transfer) and grey-card intensity non-uniformity correction are standard
technique.

**Conclusion: L1 and L2 of our architecture are, individually, established art.** Claiming novelty in
"using a colour card to calibrate a phone camera" would be indefensible. We use these because they
are correct, and we say so.

### 1.3 Electronic chain-of-custody patents

A family of granted/published US applications covers electronic chain of custody for drug testing —
including mobile applications that accompany specimen collection, capture authentication media, and
maintain digital custody records replacing paper forms (e.g. US20100241451A1, US10244198B2,
US20170302880A1, US20060106718A1).

**Conclusion: "digital chain of custody for a drug test, on a phone" is occupied space.** These are
largely *workflow and records-management* patents. Our differentiation must be in the *cryptographic
and verification mechanism*, not in the idea of digitising custody.

### 1.4 eSakshya — the Government of India's own system

NCRB's **eSakshya** application supports audio-video recording of search and seizure under BNSS,
uploading into encrypted "Sakshya Locker" vaults on the National Government Cloud as part of
CCTNS-2.0, with GPS and timestamps embedded, an officer selfie for authenticity, and — importantly —
an offline path where the officer records locally, **generates a hash value**, and uploads later.

**This is prior art *and* an opportunity.** It establishes that MHA already accepts hash-based
integrity for field-captured evidence. That is a gift: it means our record format is speaking a
language the ministry has already adopted, and the correct posture is integration, not competition.

It also forecloses one bad idea: do not propose a novel blockchain evidence vault. MHA has built the
vault. Proposing a replacement signals that the team did not research the domain.

### 1.5 Our own prior work — disclose it internally

The team's existing filed patent (*Decentralized Spatial-Temporal Data Veracity System*, sole
inventor, filed 2026) covers geospatial filtering, SHA-256 canonical-serialisation fingerprints,
Merkle batch verification, and hardware-bound key architecture in a **distributed-ledger supply-chain
context**.

This matters twice over:
- It is **self prior art** for the generic idea of "cryptographically binding a spatial-temporal
  claim." A second filing must claim something the first does not.
- It is **strong evidence of competence** to the SIH panel. Say it.

The differentiators here versus that filing: no distributed ledger; a **sensor-measurement** whose
*derivation* is bound rather than a submitted datum; **calibrated abstention** as a first-class
output; and **statutory certificate generation** under a specific evidentiary regime.

---

## 2. What we do *not* claim

Stated up front, in the submission and in any specification:

1. ✗ Photographing a colorimetric test with a phone.
2. ✗ Using a reference colour card for illuminant correction.
3. ✗ Classifying a colour change by machine learning.
4. ✗ Recording GPS and timestamp with a field test.
5. ✗ Digital chain of custody for drug testing.
6. ✗ Hashing a file to detect tampering.
7. ✗ Storing evidence in an encrypted government cloud.

Conceding these costs nothing and buys enormous credibility. A team that lists what it did *not*
invent is far more believable when it says what it did.

---

## 3. The candidate inventive steps

Three, in descending order of defensibility.

### Claim A — Derivation-bound measurement record *(strongest)*

Existing systems bind an **image** and a **result**. They do not bind the **derivation** connecting
them.

Our record binds, in one signature: the raw sensor frame hash, the calibration transform and its
residual, the reference-card identity, the model identity hash, the conformal risk level α, and the
resulting prediction set — so that an independent verifier can **re-execute the entire derivation
from the raw frame and confirm the stored conclusion reproduces**.

The technical effect: the record is not merely *tamper-evident*, it is **reproducible**. A verifier
does not have to trust that the app classified honestly; it can recompute. Substituting a biased
model is detected because `model_sha256` is inside the signature and the verifier re-runs it.

To our knowledge no field-test system binds *the calibration and the model* into the evidentiary
record. This is the narrowest, most novel, and most technically-effect-laden claim.

### Claim B — Multi-channel location corroboration with recorded disagreement

Instead of trusting a fused GPS fix, capture a bundle of physically independent channels — raw GNSS
measurements and per-satellite C/N₀, Wi-Fi BSSID neighbourhood, serving/neighbour cell IDs, and
kinematic plausibility against the previous record — compute an agreement score, and **store the
disagreements inside the signed record**.

The inventive character is the last clause. Existing anti-spoofing systems *reject* suspicious
locations. Ours **records the inconsistency as evidence**, because in a criminal proceeding the
suppression of an anomaly is itself a defect. Forging a location now requires coherent, simultaneous
falsification across channels that no consumer spoofing tool addresses together.

Weaker than A, because multi-signal spoof detection is a known art; the novelty is in the
evidentiary treatment rather than the detection itself.

### Claim C — Automated statutory certificate generation *(weakest as a patent, strongest as a demo)*

Automatic emission of a pre-populated **BSA §63 Schedule Part A** certificate at the moment of
capture, with the hash value and algorithm already filled from the signing operation, plus NDPS Rules
2022 linkage fields.

**Be realistic: this is very likely unpatentable.** It is closer to document automation and
legal-form generation than to a technical effect. But it is *the single most persuasive thing to
demonstrate live*, because it converts an abstract security property into a piece of paper an
investigating officer can file. Keep it in the pitch. Keep it out of the claims.

---

## 4. Patentability under Indian law — the §3(k) problem

This is the part most student teams get wrong.

**Section 3(k) of the Patents Act, 1970** excludes from patentability *"a mathematical or business
method or a computer programme per se or algorithms."* The CRI (Computer Related Inventions)
Guidelines direct examiners to look past claim drafting to whether there is a **technical effect** or
a contribution beyond the program itself.

A claim reading *"a method of classifying a colour and storing a hash"* is a computer programme per
se and will be refused.

What gives this invention a fighting chance:

| Element | Why it reads as technical, not abstract |
|---|---|
| Hardware secure element (StrongBox/TEE) with non-exportable keys and an attestation chain to a hardware root | The claim is anchored in a **physical security device**, not pure computation. This is the same structural move that carried the team's first filing. |
| Physical reference artefact + optical correction of a **sensor's** response | A calibration of measurement apparatus — a technical, physical process |
| Verified-boot state captured from hardware attestation | Device-state fact, not a computed abstraction |
| Reproducible re-derivation as the enabling mechanism | Concrete technical effect: a third party can detect model substitution, which is impossible without the binding |

**Drafting guidance:** claim the *system* (device + secure element + reference artefact + verifier),
never the method in isolation. Recite the hardware root of trust in claim 1. Keep the colour
classification as a dependent, enabling step — it is the weakest ground and should never carry the
independent claim.

**Realistic assessment:** this is filable as a provisional, and the REVA IPR cell has done it before
for this inventor. Whether it survives examination is a genuinely open question, and the honest
answer to *"will you get a patent?"* is **"a provisional secures the priority date; grant is
uncertain and depends on how the §3(k) objection is met."** Do not promise a grant to anyone.

---

## 5. Freedom-to-operate notes

- The US electronic-chain-of-custody patents are **US-jurisdiction**; they do not block Indian
  deployment, and much of that family is old enough that term expiry should be checked.
- MobileDetect's protection likely centres on the **pouch + QR + reader** combination. Our
  kit-agnostic design deliberately avoids that combination — which is not just a legal convenience,
  it is what the PS demanded.
- Nothing here requires a licence to any reagent chemistry. We measure colour; we do not make or
  modify any chemical.

---

## 6. How to argue this at the finale

The five-minute version, in order:

1. **"Here is what already exists."** Put MobileDetect and eSakshya on a slide. This inoculates you.
   Every other team will claim novelty for something already sold; you will be the team that knows
   the market.
2. **"The gap is not detection, it's admissibility."** Quote the PS's own sentence back.
3. **"Watch it fail correctly."** Bad lighting → inconclusive with a stated bound, not a wrong
   positive.
4. **"Now watch me attack it."** Run the adversary matrix live: edit the image, backdate the record,
   spoof the GPS, swap the model. The verifier catches each one, and *says what it cannot catch*.
5. **"And here is the certificate."** Print the §63 Part A with the hash filled in. Hand it to the
   NCB judge on paper.

Step 5 is the moment. Everything before it is engineering; that is the moment it becomes evidence.

### The one sentence to leave them with

> *The validation does not happen where it can be tampered with.*

The same sentence that carried the team's first patent — now pointed at a strip of paper instead of a
harvest coordinate.

---

## 7. Verification status of every claim in this document

| Claim | Status |
|---|---|
| MobileDetect exists with QR/GPS/report features | **Verified** — vendor and reseller literature |
| MobileDetect lacks signing/attestation/verifier | **Inferred from absence in public material** — must be checked before asserting |
| Academic smartphone colorimetry is mature | **Verified** — multiple peer-reviewed sources |
| Device-specific calibration is necessary | **Verified** — published finding |
| eCoC patent family exists (US) | **Verified** — patent numbers listed |
| eSakshya features, hash-on-offline, Sakshya Locker, CCTNS-2.0 | **Verified** — NIC/NCRB and MHA-adjacent sources |
| BSA §63 replaced §65B from 1 July 2024; two-part Schedule certificate; hash + algorithm required | **Verified across multiple legal sources** — but transcribe exact field labels from the bare Act |
| NDPS (Seizure, Storage, Sampling and Disposal) Rules, 2022 (GSR 899(E)) replaced standing orders | **Verified** |
| Android Key Attestation, StrongBox, chain to Google root, verified-boot state | **Verified** — Android developer/AOSP documentation |
| §3(k) excludes computer programme per se | **Verified** — statutory text |
| Our design is unpatented in this exact combination | **NOT VERIFIED** — no professional prior-art search performed. Request a patentability search from the REVA IPR cell before filing. |

The last row is the important one. **Do not tell the panel this is novel. Tell them what you searched,
what you found, and where you think the gap is.** That is a stronger claim than certainty, and it is
the only one that is true.
