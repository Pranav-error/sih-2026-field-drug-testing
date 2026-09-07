"""The Field Test Record — schema, digest, and the sealed envelope.

Structure and vocabulary follow ARCHITECTURE.md §6. Two rules shape everything:

1. **Every measured quantity is a scaled integer.** ``delta_e_x1000``, ``lab_x100``.
   The scale is in the field name so a reader never has to guess, and the digest
   never depends on float rounding.

2. **Absent is not the same as zero.** A field the operator could not supply is
   omitted and named in ``omitted[]``. A kit lot that was illegible is recorded
   as illegible, never as an empty string that later reads as "no lot".
"""

from __future__ import annotations

import hashlib
import uuid
from dataclasses import dataclass, field
from typing import Any

from .canonical_cbor import dumps, loads
from .signing import Attestation, Keystore, verify_signature

__all__ = ["FTR", "SealedRecord", "SCHEMA_VERSION", "GENESIS_HASH"]

SCHEMA_VERSION = 1

# The chain's zero element. A record carrying this as prev_record_hash claims to
# be the first on its device, and the verifier checks that claim is unique.
GENESIS_HASH = b"\x00" * 32


def _sha256(b: bytes) -> bytes:
    return hashlib.sha256(b).digest()


@dataclass
class FTR:
    """One field test, before sealing.

    Construct it, call :meth:`body` for the canonical structure, or hand it to
    :func:`seal` to bind it to a device and a chain position.
    """

    operator: dict[str, Any]
    kit: dict[str, Any]
    card: dict[str, Any]
    capture: dict[str, Any]
    colorimetry: dict[str, Any]
    classification: dict[str, Any]
    location_bundle: dict[str, Any]
    device: dict[str, Any]
    captured_at: dict[str, Any]
    ndps: dict[str, Any] = field(default_factory=dict)
    omitted: list[str] = field(default_factory=list)
    record_uuid: str = field(default_factory=lambda: str(uuid.uuid4()))

    def body(self, prev_record_hash: bytes, sequence: int) -> dict[str, Any]:
        """The exact structure that gets encoded and hashed.

        ``sequence`` is inside the signed body so a record cannot be silently
        relocated in the chain: moving it changes the digest, which breaks the
        signature.
        """
        if len(prev_record_hash) != 32:
            raise ValueError("prev_record_hash must be 32 bytes")
        if sequence < 0:
            raise ValueError("sequence must be non-negative")
        return {
            "schema_version": SCHEMA_VERSION,
            "record_uuid": self.record_uuid,
            "sequence": sequence,
            "prev_record_hash": prev_record_hash,
            "captured_at": self.captured_at,
            "operator": self.operator,
            "kit": self.kit,
            "card": self.card,
            "capture": self.capture,
            "colorimetry": self.colorimetry,
            "classification": self.classification,
            "location_bundle": self.location_bundle,
            "device": self.device,
            "ndps": self.ndps,
            "omitted": sorted(self.omitted),
        }


@dataclass(frozen=True)
class SealedRecord:
    """A sealed FTR: canonical bytes, their digest, and the signature over it."""

    body_cbor: bytes
    digest: bytes
    signature: bytes
    attestation: dict[str, Any]
    public_key_der: bytes

    # -- accessors ---------------------------------------------------------- #

    @property
    def body(self) -> dict[str, Any]:
        return loads(self.body_cbor)

    @property
    def sequence(self) -> int:
        return self.body["sequence"]

    @property
    def prev_record_hash(self) -> bytes:
        return self.body["prev_record_hash"]

    # -- serialisation ------------------------------------------------------ #

    def to_envelope(self) -> bytes:
        """Self-contained bytes: body, signature, key and attestation together.

        The envelope is what gets exported, and it carries everything the
        verifier needs. It deliberately does *not* carry the digest — a verifier
        that trusts a supplied digest is not verifying anything.
        """
        return dumps({
            "v": SCHEMA_VERSION,
            "body": self.body_cbor,
            "sig": self.signature,
            "pub": self.public_key_der,
            "att": self.attestation,
        })

    @classmethod
    def from_envelope(cls, blob: bytes) -> "SealedRecord":
        e = loads(blob)
        missing = {"body", "sig", "pub", "att"} - set(e)
        if missing:
            raise ValueError(f"envelope missing field(s): {', '.join(sorted(missing))}")
        body = e["body"]
        return cls(
            body_cbor=body,
            digest=_sha256(body),   # recomputed, never read from the file
            signature=e["sig"],
            attestation=e["att"],
            public_key_der=e["pub"],
        )

    def signature_valid(self) -> bool:
        return verify_signature(self.public_key_der, self.digest, self.signature)


def seal(ftr: FTR, prev_record_hash: bytes, sequence: int, keystore: Keystore) -> SealedRecord:
    """Encode, hash and sign. This is the irreversible step the UI warns about."""
    body_cbor = dumps(ftr.body(prev_record_hash, sequence))
    digest = _sha256(body_cbor)
    att: Attestation = keystore.attestation()
    return SealedRecord(
        body_cbor=body_cbor,
        digest=digest,
        signature=keystore.sign(digest),
        attestation=att.to_record(),
        public_key_der=att.public_key_der,
    )
