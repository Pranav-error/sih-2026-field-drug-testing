"""The append-only device ledger.

A signature proves authorship and integrity. It does not prove *when*, and it
does not stop an operator from producing a record later and dating it earlier.
``prev_record_hash`` makes each record depend on every record before it, so
reordering, silent deletion and backdated insertion all fork the chain — and a
fork is visible to anyone who replays it.

What this buys, stated exactly, because overstating it is worse than useless:

    A record proves it was created no earlier than the record before it and no
    later than the next anchor. It does not prove wall-clock time.

Anchoring bounds the fabrication window. Between anchors the window is open, and
:meth:`Chain.status` reports how wide it is rather than hiding it.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from .record import GENESIS_HASH, SealedRecord

__all__ = ["Chain", "ChainStatus", "ChainBreak"]


@dataclass(frozen=True)
class ChainBreak:
    """One defect found while replaying. ``kind`` is machine-readable."""

    sequence: int
    kind: str          # gap | fork | bad_signature | bad_sequence |
                       # duplicate_genesis | foreign_key
    detail: str


@dataclass(frozen=True)
class ChainStatus:
    length: int
    head: bytes | None
    intact: bool
    breaks: list[ChainBreak]
    unanchored: int
    last_anchor_sequence: int | None

    def summary(self) -> str:
        if self.intact:
            s = f"{self.length}/{self.length} records verified, no gap and no fork"
        else:
            s = f"{len(self.breaks)} break(s) in {self.length} records"
        return f"{s}; {self.unanchored} awaiting anchor"


class Chain:
    """A directory of envelope files, one per record, named by sequence.

    A directory rather than a single file on purpose: appending must never
    rewrite an existing byte, so a partial write can lose at most the record
    being made, never the ones already sealed.
    """

    def __init__(self, root: Path):
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)
        self.anchor_file = self.root / "ANCHOR"

    # -- reading ------------------------------------------------------------ #

    def _paths(self) -> list[Path]:
        return sorted(self.root.glob("[0-9]*.ftr"), key=lambda p: int(p.stem))

    def records(self) -> list[SealedRecord]:
        return [SealedRecord.from_envelope(p.read_bytes()) for p in self._paths()]

    def __len__(self) -> int:
        return len(self._paths())

    def head(self) -> bytes:
        """Digest of the last record, or the genesis hash on an empty chain."""
        paths = self._paths()
        if not paths:
            return GENESIS_HASH
        return SealedRecord.from_envelope(paths[-1].read_bytes()).digest

    def next_sequence(self) -> int:
        paths = self._paths()
        return 0 if not paths else int(paths[-1].stem) + 1

    # -- writing ------------------------------------------------------------ #

    def append(self, rec: SealedRecord) -> Path:
        """Write a sealed record. Refuses to overwrite or to break the chain."""
        seq = rec.sequence
        expected_prev = self.head()
        if seq != self.next_sequence():
            raise ValueError(f"sequence {seq} is not the next slot ({self.next_sequence()})")
        if rec.prev_record_hash != expected_prev:
            raise ValueError(
                f"record #{seq} chains to {rec.prev_record_hash.hex()[:16]}… but the head "
                f"is {expected_prev.hex()[:16]}…"
            )
        path = self.root / f"{seq:06d}.ftr"
        # Belt and braces: next_sequence() is derived from the files present, so
        # the sequence check above should already have caught this. Kept because
        # the one thing this class must never do is overwrite a sealed record.
        if path.exists():
            raise FileExistsError(f"{path} already exists; records are never rewritten")
        path.write_bytes(rec.to_envelope())
        return path

    def anchor(self, sequence: int) -> None:
        """Record that the chain was witnessed externally up to ``sequence``.

        In deployment this is the countersigned response from the anchoring
        service (or the eSakshya upload receipt). Here it is the sequence number
        alone — enough to compute the open window, which is what the honest
        claim depends on.
        """
        self.anchor_file.write_text(str(sequence))

    def last_anchor(self) -> int | None:
        if not self.anchor_file.exists():
            return None
        try:
            return int(self.anchor_file.read_text().strip())
        except ValueError:
            return None

    # -- replay ------------------------------------------------------------- #

    def status(self) -> ChainStatus:
        """Replay from genesis, reporting every defect rather than the first."""
        recs = self.records()
        breaks: list[ChainBreak] = []
        prev_digest = GENESIS_HASH
        genesis_seen = 0
        device_key: str | None = None

        for i, r in enumerate(recs):
            seq = r.sequence
            if seq != i:
                breaks.append(ChainBreak(i, "bad_sequence",
                                         f"file {i:06d}.ftr carries sequence {seq}"))
            if r.prev_record_hash == GENESIS_HASH:
                genesis_seen += 1
                if genesis_seen > 1:
                    breaks.append(ChainBreak(seq, "duplicate_genesis",
                                             "a second record claims to be first on this device"))
            # One chain, one signing key. Records from two handsets dropped
            # into one directory would each verify on their own while the
            # sequence they jointly imply never happened, so the key is checked
            # across the chain and not only inside a record.
            key = (r.attestation or {}).get("public_key_sha256")
            if key is not None:
                if device_key is None:
                    device_key = key
                elif key != device_key:
                    breaks.append(ChainBreak(
                        seq, "foreign_key",
                        "sealed by a different key than the records before it — "
                        "two devices in one chain",
                    ))

            if r.prev_record_hash != prev_digest:
                kind = "gap" if i > 0 else "fork"
                breaks.append(ChainBreak(
                    seq, kind,
                    f"chains to {r.prev_record_hash.hex()[:16]}…, expected {prev_digest.hex()[:16]}…",
                ))
            if not r.signature_valid():
                breaks.append(ChainBreak(seq, "bad_signature",
                                         "signature does not verify over the recomputed digest"))
            prev_digest = r.digest

        anchor = self.last_anchor()
        unanchored = len(recs) if anchor is None else max(0, len(recs) - (anchor + 1))
        return ChainStatus(
            length=len(recs),
            head=prev_digest if recs else None,
            intact=not breaks,
            breaks=breaks,
            unanchored=unanchored,
            last_anchor_sequence=anchor,
        )
