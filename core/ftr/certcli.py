"""``ftr-certificate`` — emit the statutory certificate and handoff bundle.

    python -m ftr.certcli 000000.ftr
    python -m ftr.certcli 000000.ftr --bundle out/ --raw frame.jpg
"""

from __future__ import annotations

import argparse
from pathlib import Path

from .certificate import Schedule, build_certificate
from .esakshya import write_bundle
from .record import SealedRecord


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="ftr-certificate", description=__doc__)
    p.add_argument("record", type=Path, help="a sealed .ftr record")
    p.add_argument("--bundle", type=Path, help="write a full handoff bundle to this directory")
    p.add_argument("--raw", type=Path, help="the raw frame, to include in the bundle")
    a = p.parse_args(argv)

    if not a.record.is_file():
        print(f"ftr-certificate: no such record: {a.record}")
        return 2

    rec = SealedRecord.from_envelope(a.record.read_bytes())
    schedule = Schedule.load()
    cert = build_certificate(rec, schedule)
    text = cert.text()
    print(text)

    if a.bundle:
        raw = a.raw.read_bytes() if a.raw and a.raw.is_file() else None
        written = write_bundle(rec, a.bundle, certificate_text=text, raw_frame=raw)
        print("\nBundle written:")
        for w in written:
            print(f"  {w}")

    # A draft certificate is not a failure, but it must not exit 0 either: a script
    # that pipes this into a filing system should stop until the Schedule is real.
    return 0 if not cert.is_draft else 3


if __name__ == "__main__":
    raise SystemExit(main())
