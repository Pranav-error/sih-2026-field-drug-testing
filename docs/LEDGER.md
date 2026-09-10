# The ledger — storage, offline behaviour, and why there is no database

*Companion to `ARCHITECTURE.md`. Everything below is checked against the code;
where something is not built, it says NOT IMPLEMENTED rather than describing an
intention.*

---

## 1. There is no database

The store is a directory. `app/lib/src/store.dart` (`RecordStore`) and
`core/ftr/chain.py` (`Chain`) are the same structure in two languages:

```
<app documents>/ftr-chain/
    000000.ftr      000000.a.jpg   000000.b.jpg
    000001.ftr      000001.a.jpg   000001.b.jpg
    ...
    ANCHOR
    export/20260909T1412Z/…
```

One file per record, named by sequence. `.ftr` is the canonical-CBOR envelope:
the signed body, the signature, and the attestation chain. The frames beside it
are the images the record's `raw_image_sha256` fields point at.

### Why not SQLite

**A database's core feature is the wrong feature here.** `UPDATE` and `DELETE`
are the two operations an evidence ledger must not have. Building on a store
that offers them means the guarantee rests entirely on our discipline in never
calling them, and a reviewer has to audit every call site to believe it. With a
directory of write-once files, `append()` is the only writer and it is 15 lines
that a reviewer can read in full.

**One file is one failure.** A corrupted SQLite page can take the whole
database. A partial write here loses at most the record being made; the ones
already sealed are untouched bytes on disk and still verify.

**A challenger must be able to verify without our stack.** A defence expert
hands `000042.ftr` to `python -m ftr.cli record` or
`dart run ftr_verify:ftrverify record` and gets an answer. No schema, no
migration history, no ORM, no engine version. If the evidence lived in a
database, verifying it would mean trusting the tool that read it out.

**Ordering is already in the data.** The thing a database index would give us —
knowing which record came after which — is in the record itself, as
`prev_record_hash` inside the signed body. The filesystem is not being trusted
for it. Rename every file at random and the chain still reconstructs.

### What we give up, honestly

No queries. Finding "every test in Belgaum in March" means reading every record
— fine at the scale one handset produces (a few thousand records over its
life), and wrong at district scale. Aggregation belongs in **CCTNS-2.0**, which
is the system of record; building a queryable evidence store here would create a
second surveillance surface with no benefit, and `ARCHITECTURE.md §12` lists it
among the things this project deliberately does not build.

### Cost of a replay

`status()` ECDSA-verifies every record — measured at **~4.4 ms each** on a
developer machine, and several times that on a handset. The log screen used to
call it on every widget rebuild, alongside a second full parse, so a few hundred
records blocked the main thread for seconds at a time. `RecordStore` now caches
the replay and invalidates it in `append()`, which is the only place the truth
changes. A stale cache here would be a chain break the log fails to show, so
nothing else may clear it; `refresh()` exists for a caller with reason to believe
the directory changed underneath it.

### Capacity

A record is ~2 KB; the two frames are ~200 KB each. About **400 KB per test**,
so roughly **10,000 field tests per 4 GB free**. The Log screen shows the ledger
path and bytes used, so this is a number an officer can see rather than a number
in a document.

---

## 2. Offline

**The app has no `INTERNET` permission.** `AndroidManifest.xml` requests
`CAMERA`, `ACCESS_FINE_LOCATION` and `ACCESS_COARSE_LOCATION` — nothing else.
This is not "works offline"; it is *cannot go online*, enforced by Android
rather than promised by us.

Everything on the critical path runs on the handset:

| Stage | Where it runs |
|---|---|
| Detect card, correct illumination, measure ΔE | `pipeline.dart`, pure Dart, on-device |
| Conformal classification | on-device |
| Sign | StrongBox / TEE, in the secure element |
| Append to the chain | the handset's filesystem |
| BSA §63 certificate | on-device |
| eSakshya envelope | on-device |
| Verify | on-device (Verifier screen) |

There is no degraded offline mode because there is no online mode. A record
sealed at a checkpoint with no tower is byte-identical to one sealed in a lab.

**Time, written unambiguously.** `captured_at.device_clock` is UTC with an
explicit `Z`, and `device_utc_offset_minutes` records what the handset was set
to. A bare local ISO string carries no zone at all — a record made at 07:06 IST
reads as 07:06 to whoever assumes otherwise. The timestamp is only a claim
either way (§3); an ambiguous claim is strictly worse than a precise one.

**Location, when there is no fix.** `location.dart` never throws and never
invents. Every failure path returns a `Fix` whose `status` names what happened
(permission denied, service off, timed out), and that goes into the signed body
as `available: false`. Both verifiers then say *"No position was recorded"*
rather than leaving a silence that reads as a pass.

**Corroboration, stated honestly.** The record reports the one channel actually
collected (`fused_gnss`) and names the four from `ARCHITECTURE.md §5` that are
not (`raw_gnss_cn0`, `wifi_bssid_set`, `serving_cell`, `kinematics`). Both
verifiers refuse to describe one agreeing channel as "all channels agreed" —
true, and deeply misleading — and print the uncollected list beside it.

---

## 3. Time, and what an anchor buys

The signature proves **who** sealed a record. The chain proves **what order**
records were sealed in. Neither proves **when**: a handset asserts its own
clock, and an offline handset cannot be contradicted.

So `captured_at` is reported by both verifiers as a *claim*, never as proven.

What bounds the lie is anchoring. `RecordStore.anchor(sequence)` writes an
`ANCHOR` file — the sequence on the first line, the UTC time on the second, two
lines rather than JSON so a person with `cat` understands it and so a file from
an older build still parses. `unanchored` reports how many records have never
been witnessed outside the device — the width of the window in which a timestamp
could have been fabricated — and `lastAnchorAt` gives how long that window has
been open. A chain that has never been anchored reads **"never anchored"**, not
a duration. Both numbers are on the standby screen and the Handoff screen.

**Exporting is what anchors.** Once a bundle leaves the handset, rewriting those
records is contradicted by a copy the app cannot reach. That is a **weaker**
anchor than a countersigning timestamp authority, and it is labelled as one in
`MANIFEST.json`, on the Handoff screen, and here.

> **NOT IMPLEMENTED: a countersigned timestamp (RFC 3161 or equivalent).** It
> requires a network round-trip, which would mean re-adding `INTERNET` and
> giving up the guarantee in §2. The right home for it is the receiving system
> at ingest, not the handset.

---

## 4. Handoff — how a record leaves the device

`app/lib/src/handoff.dart`, `exportChain()`. Writes a self-contained directory
and hands it to the Android share sheet (`share_plus`) — USB, Files, a
supervisor's laptop, whatever is already in use. No network client.

```
export/20260909T1412Z/
    000000.ftr            the evidence
    000000.esakshya.json  routing envelope for CCTNS-2.0
    000000.bsa63.txt      BSA §63 certificate, blanks left blank
    000000.a.jpg          the frames the hashes refer to
    MANIFEST.json         chain head, signing key, file list, anchor note
    README.txt            both verifier commands, for someone who does not trust us
```

**The `.ftr` goes in as raw bytes, not as JSON.** The digest is over the
canonical CBOR and nothing else, so a bundle carrying only a JSON rendering
would be unverifiable. Everything else in the directory is derived and
recomputable.

This mirrors eSakshya's own offline flow — record locally, hash, hand over
later — which is the same trust model, not a workaround for missing one.

> **NOT IMPLEMENTED: upload to eSakshya / CCTNS-2.0.** The envelope's field
> names are marked `PROVISIONAL` in the envelope itself because no published
> ingest specification has been found (`ARCHITECTURE.md §13`, open question 2).
> Writing an uploader against a guessed schema would produce something that
> looks integrated and is not.

---

## 4b. Upgrading without losing the ledger

Every build up to `1b51409` shipped with "uninstall first", which destroyed the
records — so no chain survived two builds, and the append-only ledger was the
one property testing could never exercise. Two things forced it, both now fixed:

**A stale signing key.** A key left by an older build threw
`InvalidKeyException` and only an uninstall cleared it. `HardwareKeystore.sign`
now catches that, deletes the alias, regenerates and retries once. Safe here
specifically because this key *signs future records* rather than decrypting past
ones: sealed records carry their own public key and attestation chain and keep
verifying. What is lost is the claim that one device signed the whole chain — so
the app says the key was replaced, and the chain check reports a `foreign_key`
break rather than letting it pass quietly.

**One unparseable record.** It threw from every screen that listed records, so a
schema change bricked the log and the cure was again uninstalling — destroying
the records the ledger exists to keep. `RecordStore` now collects those in
`unreadable`, keeps loading the rest, takes `head` from the last *readable*
record, and reports each as a break saying explicitly that the file has **not**
been deleted and a build that understands it still can.

`./install.sh` does the rest: `adb install -r -d`, records kept.

## 5. Two devices

Each handset has its own StrongBox key, so each has its own chain. The chains
are independent by construction.

The attack that follows from that: copy a second phone's records into the
first's directory so the ledger looks continuous. Every record verifies, every
hash links — and the ordering the directory now asserts was never witnessed by
one device.

Both implementations check the signing key **across** the chain, not only
inside a record, and report a `foreign_key` break. Proved by
`core/tests/test_chain.py::test_a_second_device_cannot_be_spliced_into_a_chain`,
with a companion test asserting the check does not fire on the ordinary
single-device case.

> **NOT IMPLEMENTED: reconciling two devices' chains into one case view.** That
> is a CCTNS-2.0 join across FIR reference, not something a handset can do.

---

## 6. Why not blockchain

A fair question, because the chain here *is* the useful half of one: every
record commits to its predecessor's hash, so rewriting record 40 invalidates
every record after it. That property is a hash chain, and it is about thirty
lines of code.

What a blockchain adds on top is **distributed consensus** — a protocol for
mutually distrusting parties to agree on a single ordering without a trusted
coordinator. Three reasons it is the wrong tool here:

**1. There is no disagreement to resolve.** Consensus answers "whose version of
the ledger is real when several parties are writing?" Here one handset writes
its own chain, signed by a key in its own secure element. There is no second
writer to disagree with, and CCTNS-2.0 is already the coordinator once records
leave the device.

**2. It cannot help with the actual problem, which is at the sensor.** A
blockchain makes a *recorded* value immutable. It says nothing about whether the
value was true when written. Every real attack on this system — photographing a
printed card, a torch hotspot faking a colour, a substituted strip — happens
*before* anything is written. That is what the parallax liveness check, the
substrate residual over 196 probe points and the illumination gate are for. Put
a fabricated reading on a blockchain and you have a permanently immutable
fabrication.

**3. It breaks the offline guarantee.** Any consensus mechanism needs to reach
other nodes. A network-dependent seal fails exactly where this system has to
work — a checkpoint with no tower — and it would mean re-adding `INTERNET`.

There is also a legal point. Under **BSA 2023 §63**, admissibility turns on a
certificate identifying the device and the hash of the record, given by a person
in charge. What a court needs is an unambiguous hash and a signature traceable
to identified hardware — which is what StrongBox key attestation provides. A
distributed ledger is not a category the statute contemplates, and offering one
adds an explanation burden without adding evidentiary weight.

**Where a shared ledger would genuinely earn its place:** across agencies that
do not trust each other and must not have a single administrator — a chain of
custody spanning NCB, state police and an FSL, where each handoff is signed by
the receiving party. That is a CCTNS-2.0-scale design decision about the
national system, and a real one. It is not something a field device chooses, and
it does not change anything on the handset.
