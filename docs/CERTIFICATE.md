# The §63 certificate — what the Act actually asks for

**SIH26231** · track E · supporting note to [`ARCHITECTURE.md`](ARCHITECTURE.md) §8

Section 63 of the Bharatiya Sakshya Adhiniyam 2023 replaced §65B of the Indian
Evidence Act on 1 July 2024. §63(4)(c) points at a Schedule, and the Schedule sets
out the certificate.

The Schedule has now been **transcribed** into
[`../core/ftr/data/bsa63_schedule.json`](../core/ftr/data/bsa63_schedule.json)
from a bare-Act repository (advocatekhoj.com, 2026-09-08). It is no longer a
paraphrase. It is also **not yet Gazette-verified**, so every certificate the app
emits is still stamped `DRAFT — NOT FOR FILING`, and the banner says exactly what
remains:

> compare `data/bsa63_schedule.json` against the eGazette PDF of the Act, then set
> `verification_level` to `official` and `verified` to true.

That is the whole remaining task for track E. It is an hour with the Gazette PDF.

## What the Schedule actually says

Structure, confirmed:

| | Part A | Part B |
|---|---|---|
| Filled by | **the Party** | **the Expert** |
| Opens with | "I … do hereby solemnly affirm and sincerely state" | same |
| Device tick-list | Computer/Storage Media, DVR, **Mobile**, Flash Drive, CD/DVD, Server, Cloud, Other | same |
| Device fields | Make & Model, Color, Serial Number, IMEI/UIN/UID/MAC/Cloud ID | same |
| Hash value | **required** | **also required** |
| Algorithms | ☐ SHA1 ☐ **SHA256** ☐ MD5 ☐ Other | same |
| Signature | (Name and signature) | (Name, designation and signature) |
| Footer | Date DD/MM/YYYY, Time IST 24h, Place | same |

Three things worth noting, all of which the earlier paraphrase got wrong:

1. **Part A is filled by "the Party", not "the person in charge of the device".**
   Different words, different person, potentially different oath.
2. **Part B also states the hash.** The expert is not merely endorsing Part A; they
   state the hash value on their own responsibility, from their own examination.
   The app therefore populates *nothing* in Part B — not even the hash it computed.
3. **SHA256 is named in the Schedule itself.** The record's choice of SHA-256 is not
   merely conventional; it is one of the algorithms the statute puts on the form.

## The finding: the record schema was incomplete

Transcribing the Schedule exposed a gap nobody would have found by reading
`ARCHITECTURE.md`. The certificate requires:

- Make & Model
- Serial Number
- IMEI/UIN/UID/MAC/Cloud ID

**The FTR carried none of them.** It carried `android_id_hash`, which is a
privacy-preserving identifier and exactly the wrong thing for a form that asks for
an IMEI. The schema had been designed against a description of the statute rather
than the statute.

Rather than leave that to be discovered by a magistrate, the certificate names it:

```
Statutory fields the record cannot supply:
  - Make & Model of the device
  - Serial Number of the device
  - IMEI/UIN/UID/MAC/Cloud ID
  These must be completed by hand, or the record schema extended.
```

`device.make_model`, `device.serial_number` and `device.device_identifier` are now
part of the record shape, and a record carrying them produces a certificate with no
missing fields. There is a privacy question here that track E should own: an IMEI
in a signed, distributed record is a persistent device identifier, and the Schedule
asks for it in plain text.

## What the app fills, and what it never will

**Machine-filled:** the Mobile tick-box, the hash value, the SHA256 tick-box, and a
free-text device field carrying the record UUID, ledger position, verified-boot
state, patch level and key security level. Plus make/model/serial/IMEI when the
record carries them.

**Never machine-filled:** every declaration beginning "I … do hereby solemnly
affirm", the lawful-control statement, the Owned/Maintained/Managed/Operated
selection, both signature blocks, both date/time/place blocks, and the whole of
Part B.

An auto-filled signature line is a forgery mechanism, and an auto-filled oath is
worse. `test_no_oath_or_signature_is_ever_machine_filled` holds that line.

## Emitting one

```sh
ftr-certificate record.ftr                       # prints the certificate, exits 3 while DRAFT
ftr-certificate record.ftr --bundle out/ --raw frame.jpg
```

The CLI exits **3** while the Schedule is unverified, so a script cannot pipe a
draft into a filing system.

## Provenance of this transcription

- Section 63 text: [indiankanoon.org/doc/125020475](https://indiankanoon.org/doc/125020475/) — the section, but **not** the Schedule.
- The Schedule: [advocatekhoj.com bare-Act library](https://www.advocatekhoj.com/library/bareacts/bharatiyaaakshya2023/b.php).

Neither is the Gazette. The project's rule is that reference text is transcribed
from a source and never written from memory — see
[`DETERMINISM.md`](DETERMINISM.md) for the CIEDE2000 incident that established it.
This transcription honours the rule; verifying it against the Gazette completes it.
