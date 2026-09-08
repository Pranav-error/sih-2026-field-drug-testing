"""Fetch the measured spectral data this project depends on.

Not committed to the repository: the camera database is CC BY-NC-SA 4.0, and
vendoring a share-alike dataset into a repo whose licence is not yet settled is
a decision nobody has made. Fetching it explicitly also keeps the provenance
visible instead of burying a third-party measurement in our own git history.

    python core/tools/fetch_spectral_data.py
"""

from __future__ import annotations

import hashlib
import sys
import urllib.request
from pathlib import Path

DEST = Path(__file__).resolve().parents[2] / "data" / "spectral"

FILES = {
    "camspec_database.txt": (
        "https://zenodo.org/api/records/3245883/files/camspec_database.txt/content",
        "32a2700478d4f2b61d7018efebb399ad4f89a152f64a46831b58c1e44c2a8db2",
    ),
    "camlist.txt": (
        "https://zenodo.org/api/records/3245883/files/camlist&equipment.txt/content",
        "90fd42186ecb7bc9eee051872571fbe1e826fa958bb04b3d0483ea9d788d34b8",
    ),
}


def main() -> int:
    DEST.mkdir(parents=True, exist_ok=True)
    for name, (url, want) in FILES.items():
        path = DEST / name
        if path.exists() and hashlib.sha256(path.read_bytes()).hexdigest() == want:
            print(f"  {name}: already present and matches")
            continue
        print(f"  {name}: fetching…")
        with urllib.request.urlopen(url, timeout=60) as r:
            blob = r.read()
        got = hashlib.sha256(blob).hexdigest()
        if got != want:
            print(f"  {name}: SHA-256 MISMATCH\n    expected {want}\n    got      {got}")
            print("  Refusing to write. The upstream record may have changed —")
            print("  check Zenodo 3245883 before updating the expected hash.")
            return 1
        path.write_bytes(blob)
        print(f"  {name}: {len(blob)} bytes, sha256 verified")
    print(f"\n-> {DEST}")
    print("Jiang, Liu, Gu & Susstrunk (2013), CC BY-NC-SA 4.0. See data/spectral/README.md")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
