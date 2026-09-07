"""``ftrverify`` — command line entry point for the independent verifier.

Deliberately dependency-light and offline. Anyone challenging a record should be
able to run this on a machine that has never spoken to us.

    python -m ftr.cli record  path/to/000003.ftr [--image raw_image_sha256=frame.jpg]
    python -m ftr.cli chain   path/to/chain-dir
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from .verifier import verify_chain, verify_record


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(
        prog="ftrverify",
        description="Verify a Field Test Record or a device chain. Reports what is "
                    "proven, what is merely asserted, and what is unverifiable.",
    )
    sub = p.add_subparsers(dest="cmd", required=True)

    pr = sub.add_parser("record", help="verify one .ftr envelope")
    pr.add_argument("path", type=Path)
    pr.add_argument("--image", action="append", default=[], metavar="FIELD=PATH",
                    help="supply an image so its hash can be checked, e.g. "
                         "raw_image_sha256=frame.jpg (repeatable)")

    pc = sub.add_parser("chain", help="verify every record in a chain directory")
    pc.add_argument("path", type=Path)

    a = p.parse_args(argv)

    if a.cmd == "record":
        if not a.path.is_file():
            print(f"ftrverify: no such record: {a.path}", file=sys.stderr)
            return 2
        images = {}
        for spec in a.image:
            if "=" not in spec:
                print(f"ftrverify: --image expects FIELD=PATH, got {spec!r}", file=sys.stderr)
                return 2
            fieldname, _, ipath = spec.partition("=")
            ip = Path(ipath)
            if not ip.is_file():
                print(f"ftrverify: no such image: {ip}", file=sys.stderr)
                return 2
            images[fieldname] = ip.read_bytes()
        report = verify_record(a.path.read_bytes(), images=images)
    else:
        if not a.path.is_dir():
            print(f"ftrverify: no such chain directory: {a.path}", file=sys.stderr)
            return 2
        report = verify_chain(a.path)

    print(report.text())
    return 0 if report.ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
