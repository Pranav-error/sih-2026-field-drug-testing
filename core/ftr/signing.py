"""Signing keys and the attestation record that grades them.

On an Android handset the signing key is generated inside StrongBox or the TEE,
cannot be exported, and Google's key attestation returns a certificate chain to a
hardware root asserting exactly that. That chain is what converts *an app claims
it signed this* into *this device's secure hardware signed this*.

This module models the same shape on a workstation so the record format, the
chain and the verifier can be built and tested before any handset exists — and it
is deliberately loud about the difference. A development key produces
``security_level = "SOFTWARE"``, and the verifier downgrades every hardware claim
to "asserted" when it sees one. A prototype that silently pretends to be
hardware-backed would teach us to trust a record that proves nothing.

Security levels, weakest to strongest:

    SOFTWARE    key lives in a file. Proves nothing about the device.
    TEE         key in the trusted execution environment. Non-exportable.
    STRONGBOX   key in a discrete secure element. Non-exportable, tamper-resistant.
"""

from __future__ import annotations

import hashlib
import json
import os
from dataclasses import dataclass
from pathlib import Path

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec, utils as asym_utils

__all__ = ["Attestation", "Keystore", "SoftwareKeystore", "verify_signature", "SECURITY_LEVELS"]

# Ordered weakest to strongest; the verifier reports the level rather than
# pass/fail, because "which hardware" is the whole question a court will ask.
SECURITY_LEVELS = ("SOFTWARE", "TEE", "STRONGBOX")


@dataclass(frozen=True)
class Attestation:
    """What the keystore asserts about the key that produced a signature.

    On Android these fields are read out of the attestation certificate
    extension, not taken on the app's word.
    """

    security_level: str
    verified_boot_state: str      # GREEN | YELLOW | ORANGE | RED | UNKNOWN
    bootloader_locked: bool
    os_patch_level: str
    key_exportable: bool
    public_key_der: bytes
    cert_chain: list[bytes]       # leaf first, hardware root last

    def to_record(self) -> dict:
        return {
            "security_level": self.security_level,
            "verified_boot_state": self.verified_boot_state,
            "bootloader_locked": self.bootloader_locked,
            "os_patch_level": self.os_patch_level,
            "key_exportable": self.key_exportable,
            "public_key_sha256": hashlib.sha256(self.public_key_der).digest(),
            "cert_chain_len": len(self.cert_chain),
        }


class Keystore:
    """Interface the app and the verifier agree on.

    The Android implementation backs these three methods with
    ``KeyGenParameterSpec.Builder(...).setIsStrongBoxBacked(true)`` and
    ``setAttestationChallenge(digest)``. Nothing else in the codebase needs to
    know which implementation it is holding.
    """

    def sign(self, digest: bytes) -> bytes:
        raise NotImplementedError

    def attestation(self) -> Attestation:
        raise NotImplementedError

    @property
    def public_key_der(self) -> bytes:
        raise NotImplementedError


class SoftwareKeystore(Keystore):
    """Development keystore. P-256 on disk, honestly labelled SOFTWARE."""

    def __init__(self, key_path: Path, os_patch_level: str = "1970-01-01"):
        self.key_path = Path(key_path)
        self._os_patch_level = os_patch_level
        if self.key_path.exists():
            self._key = serialization.load_pem_private_key(self.key_path.read_bytes(), password=None)
        else:
            self._key = ec.generate_private_key(ec.SECP256R1())
            self.key_path.parent.mkdir(parents=True, exist_ok=True)
            self.key_path.write_bytes(
                self._key.private_bytes(
                    encoding=serialization.Encoding.PEM,
                    format=serialization.PrivateFormat.PKCS8,
                    encryption_algorithm=serialization.NoEncryption(),
                )
            )
            os.chmod(self.key_path, 0o600)

    @property
    def public_key_der(self) -> bytes:
        return self._key.public_key().public_bytes(
            encoding=serialization.Encoding.DER,
            format=serialization.PublicFormat.SubjectPublicKeyInfo,
        )

    def sign(self, digest: bytes) -> bytes:
        # Prehashed: the digest is the artefact, so we sign it directly rather
        # than re-hashing a serialisation the verifier would have to reproduce.
        return self._key.sign(digest, ec.ECDSA(asym_utils.Prehashed(hashes.SHA256())))

    def attestation(self) -> Attestation:
        return Attestation(
            security_level="SOFTWARE",
            verified_boot_state="UNKNOWN",
            bootloader_locked=False,
            os_patch_level=self._os_patch_level,
            key_exportable=True,          # it is a file. say so.
            public_key_der=self.public_key_der,
            cert_chain=[],                # no chain: there is no root to chain to
        )


def verify_signature(public_key_der: bytes, digest: bytes, signature: bytes) -> bool:
    """True if ``signature`` is a valid ECDSA signature over ``digest``."""
    try:
        pub = serialization.load_der_public_key(public_key_der)
        pub.verify(signature, digest, ec.ECDSA(asym_utils.Prehashed(hashes.SHA256())))
        return True
    except (InvalidSignature, ValueError, TypeError):
        return False
