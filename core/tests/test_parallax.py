"""The replay defence: two views, and the depth a reproduction cannot have.

docs/ROBUSTNESS.md §3 recorded that a quality print or a high-DPI screen defeated
the pipeline entirely, reading as an *excellent* capture. These tests are the
defence, and the last of them is the honest statement of what still gets through.
"""

import numpy as np
import pytest

from ftr.card import PX_PER_MM
from ftr.detect import detect_card
from ftr.parallax import check_liveness, measure_parallax
from synth import render_card
from synth3d import replay_pair, stereo_pair, tab_texture

TAB_QUAD = np.array([[21.0, 63.0], [40.0, 63.0], [40.0, 77.0], [21.0, 77.0]])
TAB_CENTRE = (30.5, 70.0)
TAB_H = 8.0
DIST = 150.0
BASE = 50.0


@pytest.fixture(scope="module")
def card():
    return render_card()


def _measure(a, b, baseline=BASE, distance=DIST):
    da, db = detect_card(a), detect_card(b)
    assert da is not None and da.complete, "card not found in frame A"
    assert db is not None and db.complete, "card not found in frame B"
    return measure_parallax(a, b, da, db, TAB_CENTRE, 9.0,
                            baseline_mm=baseline, distance_mm=distance)


def _pair(card, **kw):
    return stereo_pair(card, baseline_mm=kw.pop("baseline_mm", BASE),
                       distance_mm=DIST, raised=(tab_texture(), TAB_H, TAB_QUAD), **kw)


# --- the geometry is real, not a heuristic --------------------------------- #

@pytest.mark.parametrize("height", [1.0, 2.0, 4.0, 8.0])
def test_measured_parallax_matches_the_predicted_geometry(card, height):
    """d = b·h/(D−h). If the measurement tracks the prediction across heights,
    the check is measuring depth rather than correlating with something else."""
    a, b = stereo_pair(card, baseline_mm=BASE, distance_mm=DIST,
                       raised=(tab_texture(), height, TAB_QUAD))
    r = _measure(a, b)
    predicted = BASE * height / (DIST - height) * PX_PER_MM
    assert r.displacement_px == pytest.approx(predicted, rel=0.12, abs=0.6), (
        f"{height} mm: measured {r.displacement_px:.1f} px, predicted {predicted:.1f}"
    )


def test_the_implied_height_recovers_the_real_one(card):
    """Inverting the geometry should return the feature's actual height."""
    a, b = _pair(card)
    r = _measure(a, b)
    assert r.implied_height_mm == pytest.approx(TAB_H, abs=0.6)


def test_a_flat_card_gives_no_parallax(card):
    a, b = stereo_pair(card, baseline_mm=BASE, distance_mm=DIST, raised=None)
    r = _measure(a, b)
    assert r.displacement_px < 1.5, "a flat scene must produce almost nothing"


# --- the attack ------------------------------------------------------------ #

@pytest.mark.parametrize("medium", ["print", "screen"])
def test_a_quality_replay_is_now_refused(card, medium):
    """The attack that defeated the pipeline in ROBUSTNESS.md §3.

    A photo-lab print and a high-DPI screen both passed every colorimetric check
    reading as near-perfect captures. Neither has depth, and no print quality
    changes that: flatness is not an artefact, it is the medium.
    """
    a, b = replay_pair(card, baseline_mm=BASE, distance_mm=DIST, medium=medium,
                       raised=(tab_texture(), TAB_H, TAB_QUAD))
    r = _measure(a, b)
    live, why = check_liveness(r, TAB_H, BASE, DIST)
    assert not live, f"a {medium} replay was accepted as live"
    assert "FLAT" in why
    assert r.displacement_px < 1.5


def test_a_physical_card_is_accepted(card):
    """The defence is worthless if it also refuses honest captures."""
    a, b = _pair(card)
    live, why = check_liveness(r := _measure(a, b), TAB_H, BASE, DIST)
    assert live, why
    assert "Depth confirmed" in why


# --- the operating envelope ------------------------------------------------ #

@pytest.mark.parametrize("baseline", [10.0, 20.0, 30.0, 50.0])
def test_a_small_hand_movement_is_enough(card, baseline):
    """An officer cannot be asked to measure a baseline. It has to work for any
    ordinary movement between two frames."""
    a, b = _pair(card, baseline_mm=baseline)
    r = _measure(a, b, baseline=baseline)
    live, why = check_liveness(r, TAB_H, baseline, DIST)
    assert live, f"baseline {baseline} mm: {why}"


@pytest.mark.parametrize("noise", [1.2, 9.0, 20.0])
def test_the_check_survives_a_noisy_sensor(card, noise):
    a, b = _pair(card, noise=noise)
    r = _measure(a, b)
    live, why = check_liveness(r, TAB_H, BASE, DIST)
    assert live, f"noise {noise}: {why}"
    assert r.confidence > 0.35


def test_a_feature_too_short_to_measure_is_refused(card):
    """A wet strip lying on the card is ~0.4 mm and yields about a pixel. The
    check must refuse rather than guess — which is why the card needs a tab."""
    a, b = stereo_pair(card, baseline_mm=BASE, distance_mm=DIST,
                       raised=(tab_texture(), 0.4, TAB_QUAD))
    live, why = check_liveness(_measure(a, b), TAB_H, BASE, DIST)
    assert not live, "1 px of parallax must not be accepted as proof of depth"


def test_liveness_needs_the_RIGHT_amount_of_depth_not_merely_some(card):
    """A known height predicts a specific displacement, so an attacker must
    introduce not just depth but the correct depth."""
    a, b = stereo_pair(card, baseline_mm=BASE, distance_mm=DIST,
                       raised=(tab_texture(), 2.0, TAB_QUAD))
    live, why = check_liveness(_measure(a, b), TAB_H, BASE, DIST)
    assert not live, "a 2 mm feature must not satisfy an 8 mm expectation"


# --- what still gets through ------------------------------------------------ #

def test_a_synchronised_stereo_replay_still_defeats_this(card):
    """**This test asserts a vulnerability that remains, and is meant to.**

    Parallax proves the scene had depth. It does not prove the depth was there
    *now*. An attacker holding the original two frames — or a video of the real
    capture — and replaying them in step with the app's two captures reproduces
    the parallax exactly, because it *is* the real parallax.

    That is a materially harder attack than printing a photograph: it needs the
    genuine stereo pair, and playback synchronised to a capture the attacker does
    not control. But it is not defended, and the threat model says so.

    Defeating it needs the app to choose something the attacker cannot predict —
    an unpredictable number of frames, a challenge pattern from the torch, or
    timing the app alone knows. None of that is built.
    """
    a, b = stereo_pair(card, baseline_mm=BASE, distance_mm=DIST,
                       raised=(tab_texture(), TAB_H, TAB_QUAD))
    # The attacker replays exactly these two frames. Nothing about them changed.
    live, why = check_liveness(_measure(a, b), TAB_H, BASE, DIST)
    assert live, (
        "a synchronised stereo replay is indistinguishable from the real capture "
        "by this check alone — if that ever stops being true, invert this test"
    )


# --- the defence has to reach the record ----------------------------------- #

class TestLivenessReachesTheEvidence:
    """A defence the verifier cannot see is not evidence.

    The whole thesis of this project is that the record is the product. Parallax
    that lives only in the app is a demo; parallax bound into the sealed record and
    reported by an independent verifier is a finding.
    """

    def _pipe(self, card, **kw):
        from ftr.card import CARD_V1
        from ftr.pipeline import measure_pair
        raised = (tab_texture(), CARD_V1.tab_height_mm, np.array(CARD_V1.tab_quad_mm))
        if kw.pop("replay", None):
            a, b = replay_pair(card, baseline_mm=BASE, distance_mm=DIST,
                               medium=kw.pop("medium", "print"), raised=raised)
        else:
            a, b = stereo_pair(card, baseline_mm=BASE, distance_mm=DIST, raised=raised)
        return measure_pair(a, b, baseline_mm=BASE, distance_mm=DIST)

    def test_a_live_capture_records_its_geometry(self, card):
        m = self._pipe(card)
        live = m.record_fields()["liveness"]
        assert live["checked"] is True and live["live"] is True
        # everything a reader needs to check the arithmetic themselves
        for k in ("displacement_px_x100", "predicted_px_x100", "tab_height_mm_x10",
                  "baseline_mm_x10", "distance_mm_x10", "confidence_x1000"):
            assert k in live, f"{k} missing — the claim would not be re-checkable"

    def test_a_flat_capture_becomes_a_refusal_and_is_still_sealed(self, card):
        """Consistent with every other gate: refuse the result, keep the record.
        Deleting it is the attack the ledger exists to stop."""
        m = self._pipe(card, replay=True)
        assert m.record_fields()["liveness"]["live"] is False
        assert not m.usable, "a flat capture must not yield a result"
        assert any("FLAT" in x for x in m.refusals)

    def test_a_single_frame_record_says_so_rather_than_staying_silent(self, card):
        """Absent is not the same as passed."""
        from ftr.pipeline import measure
        a, _ = stereo_pair(card, baseline_mm=BASE, distance_mm=DIST,
                           raised=(tab_texture(), 8.0, np.array([[21.0, 66.0], [40.0, 66.0],
                                                                [40.0, 80.0], [21.0, 80.0]])))
        live = measure(a).record_fields()["liveness"]
        assert live["checked"] is False
        assert "photograph of a card" in live["note"]

    def test_the_liveness_block_survives_canonical_encoding(self, card):
        """Canonical CBOR refuses floats. Catch a stray one here, not at sealing."""
        from ftr.canonical_cbor import dumps
        dumps(self._pipe(card).record_fields())

    def _seal(self, tmp_path, measurement, name):
        import hashlib
        from factory import SimulatedHardwareKeystore, sample_ftr
        from ftr.chain import Chain
        from ftr.record import seal
        f = sample_ftr()
        fields = measurement.record_fields()
        f.colorimetry = fields["colorimetry"]
        f.liveness = fields["liveness"]
        chain = Chain(tmp_path / name)
        rec = seal(f, chain.head(), 0, SimulatedHardwareKeystore(tmp_path / f"{name}.pem"))
        chain.append(rec)
        return rec

    def test_the_verifier_reports_a_live_capture_as_asserted(self, card, tmp_path):
        """The app measured it; this verifier did not. That is asserted, not proven."""
        from ftr.verifier import verify_record
        rec = self._seal(tmp_path, self._pipe(card), "live")
        report = verify_record(rec.to_envelope())
        assert report.ok
        assert any("parallax" in a and "asserted" in a for a in report.asserted)

    def test_the_verifier_FAILS_a_flat_capture(self, card, tmp_path):
        """A record of a photograph of a strip must not read as VERIFIED."""
        from ftr.verifier import verify_record
        rec = self._seal(tmp_path, self._pipe(card, replay=True), "flat")
        report = verify_record(rec.to_envelope())
        assert not report.ok
        assert any("LIVENESS FAILED" in f for f in report.failures)
        assert any("record is authentic" in f for f in report.failures), (
            "must separate the record's integrity from what it photographed"
        )

    def test_the_verifier_flags_a_record_with_no_liveness_check(self, card, tmp_path):
        from ftr.pipeline import measure
        from ftr.verifier import verify_record
        a, _ = stereo_pair(card, baseline_mm=BASE, distance_mm=DIST,
                           raised=(tab_texture(), 8.0, TAB_QUAD))
        rec = self._seal(tmp_path, measure(a), "single")
        report = verify_record(rec.to_envelope())
        assert report.ok, "a single-frame record is authentic, just weaker"
        assert any("cannot be distinguished from a photograph" in x
                   for x in report.asserted)
        assert any("physically present" in u for u in report.unverifiable)
