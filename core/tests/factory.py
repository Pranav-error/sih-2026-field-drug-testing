"""Sample records. Values are illustrative; no real case or operator is depicted."""

from __future__ import annotations

import hashlib

from ftr.record import FTR
from ftr.signing import Attestation, SoftwareKeystore

RAW_FRAME = b"pretend this is a 12-megapixel sensor frame"


def sample_ftr(label: str = "positive", **over) -> FTR:
    d = dict(
        captured_at={"device_clock": "2026-09-13T14:32:07+05:30",
                     "uptime_ms": 918_233_004,
                     "trusted_time_delta_ms": None},
        operator={"id": "NCB/BLR/2291", "credential_ref": "cred:2291",
                  "biometric_unlock_used": True},
        kit={"reagent_type": "marquis", "kit_photo_sha256": hashlib.sha256(b"lot").digest()},
        card={"card_id": "CARD-IN-2026-0417", "print_batch": "B12"},
        capture={"raw_image_sha256": hashlib.sha256(RAW_FRAME).digest(),
                 "normalised_image_sha256": hashlib.sha256(b"normalised").digest()},
        colorimetry={"lab_x100": [2840, 1210, -960], "calibration_residual_x1000": 1420,
                     "blur_metric_x1000": 30, "dynamic_range_x1000": 780},
        classification={"model_id": "marquis-loci-v3",
                        "model_sha256": hashlib.sha256(b"model").digest(),
                        "alpha_x1000": 50, "prediction_set": [label], "label": label},
        location_bundle={"lat_x1e7": 129912000, "lon_x1e7": 777205000, "accuracy_m": 6,
                         "gnss_raw_digest": hashlib.sha256(b"gnss").digest(),
                         "wifi_bssid_set_digest": hashlib.sha256(b"wifi").digest(),
                         "corroboration_channels_agreeing": 4,
                         "corroboration_channels_total": 4,
                         "spoof_indicators": []},
        device={"android_id_hash": hashlib.sha256(b"dev").digest(),
                "os_patch_level": "2026-08-01", "bootloader_state": "LOCKED",
                "verified_boot_state": "GREEN"},
        ndps={"seizure_memo_ref": "SM-2026-0913-07", "sample_ids": ["S1", "S2"]},
        omitted=["kit.lot"],
    )
    d.update(over)
    return FTR(**d)


class SimulatedHardwareKeystore(SoftwareKeystore):
    """A software key that *reports* a hardware attestation. Tests only.

    This exists so the hardware verification path can be exercised before any
    handset is in hand. It deliberately lives in the test tree and nowhere near
    the package: shipping a class that lets software claim StrongBox would
    destroy the only thing the record is for.
    """

    def __init__(self, path, level="STRONGBOX", verified_boot="GREEN", locked=True):
        super().__init__(path, os_patch_level="2026-08-01")
        self._level, self._vb, self._locked = level, verified_boot, locked

    def attestation(self) -> Attestation:
        return Attestation(
            security_level=self._level,
            verified_boot_state=self._vb,
            bootloader_locked=self._locked,
            os_patch_level="2026-08-01",
            key_exportable=False,
            public_key_der=self.public_key_der,
            cert_chain=[b"leaf", b"intermediate", b"root"],
        )
