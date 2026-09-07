"""Field Test Record — the evidentiary core of the SIH26231 field drug companion.

The classifier is not the product. The record is. This package implements the
record: canonical encoding, hardware-bound signing, the append-only device
ledger, and the independent verifier that re-derives all of it without trusting
the app that produced it.

    from ftr import FTR, Chain, seal, verify_record

Layers, as numbered in docs/ARCHITECTURE.md:

    L1  colorimetry.RootPolynomial      device RGB -> CIELAB, with residual
    L2  colorimetry.ConformalClassifier label + prediction set + stated alpha
    L4  record.seal                     canonical CBOR -> SHA-256 -> signature
    L5  chain.Chain                     append-only ledger, anchoring window
    L7  verifier.verify_record          proven / asserted / unverifiable
"""

from .canonical_cbor import CborError, dumps, is_canonical, loads
from .chain import Chain, ChainBreak, ChainStatus
from .record import FTR, GENESIS_HASH, SCHEMA_VERSION, SealedRecord, seal
from .signing import Attestation, Keystore, SoftwareKeystore, verify_signature
from .verifier import Report, verify_chain, verify_record

__version__ = "0.1.0"

__all__ = [
    "CborError", "dumps", "loads", "is_canonical",
    "Chain", "ChainBreak", "ChainStatus",
    "FTR", "SealedRecord", "seal", "GENESIS_HASH", "SCHEMA_VERSION",
    "Attestation", "Keystore", "SoftwareKeystore", "verify_signature",
    "Report", "verify_record", "verify_chain",
    "__version__",
]
