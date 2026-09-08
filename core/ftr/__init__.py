"""Field Test Record — the evidentiary core of the SIH26231 field drug companion.

The classifier is not the product. The record is. This package implements the
record: canonical encoding, hardware-bound signing, the append-only device
ledger, and the independent verifier that re-derives all of it without trusting
the app that produced it.

    from ftr import FTR, Chain, seal, verify_record

Layers, as numbered in docs/ARCHITECTURE.md:

    L1  detect.detect_card              fiducials, homography, INUC, sampling, gate
        colorimetry.RootPolynomial      device RGB -> CIELAB, with residual
    L2  colorimetry.ConformalClassifier label + prediction set + stated alpha
        pipeline.measure                one frame in, one measurement out
    L4  record.seal                     canonical CBOR -> SHA-256 -> signature
    L5  chain.Chain                     append-only ledger, anchoring window
    L6  certificate.build_certificate   BSA 2023 s.63 certificate, Part A populated
        esakshya.build_envelope         CCTNS-2.0 handoff — not a parallel store
    L7  verifier.verify_record          proven / asserted / unverifiable

    ingest.survey / ingest.calibrate    track F: is this capture set usable, and
                                        what does it generalise to?

``pipeline`` and ``detect`` need OpenCV and numpy. The verifier's integrity checks
— canonical encoding, digest, chain replay — deliberately do not, so a challenger
can run them with nothing but the standard library.
"""

from .canonical_cbor import CborError, dumps, is_canonical, loads
from .card import CARD_V1, CardSpec
from .certificate import Certificate, Schedule, build_certificate
from .chain import Chain, ChainBreak, ChainStatus
from .esakshya import build_envelope, write_bundle
from .colorimetry import (ConformalClassifier, Prediction, RootPolynomial, delta_e_2000,
                          srgb_to_linear, xyz_to_lab)
from .record import FTR, GENESIS_HASH, SCHEMA_VERSION, SealedRecord, seal
from .signing import Attestation, Keystore, SoftwareKeystore, verify_signature
from .verifier import Report, verify_chain, verify_record

__version__ = "0.1.0"

__all__ = [
    "CborError", "dumps", "loads", "is_canonical",
    "CARD_V1", "CardSpec",
    "ConformalClassifier", "Prediction", "RootPolynomial",
    "delta_e_2000", "srgb_to_linear", "xyz_to_lab",
    "Certificate", "Schedule", "build_certificate",
    "build_envelope", "write_bundle",
    "Chain", "ChainBreak", "ChainStatus",
    "FTR", "SealedRecord", "seal", "GENESIS_HASH", "SCHEMA_VERSION",
    "Attestation", "Keystore", "SoftwareKeystore", "verify_signature",
    "Report", "verify_record", "verify_chain",
    "__version__",
]
