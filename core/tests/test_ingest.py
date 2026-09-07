"""Track F tooling. Small synthetic capture sets, because these tests render images."""

import cv2
import numpy as np
import pytest

from ftr.ingest import calibrate, read_captures, refusal_kind, survey
from synth import photograph, render_card

WELLS = {
    "opiate_class": (0.28, 0.12, 0.22),
    "negative": (0.80, 0.78, 0.72),
}


def _write_set(root, conditions, n=3, wells=WELLS, seed=5):
    """Build captures/<label>/<condition>/*.jpg."""
    rng = np.random.default_rng(seed)
    for label, well in wells.items():
        card = render_card(well_srgb=well)
        for cond, kw in conditions.items():
            d = root / label / cond
            d.mkdir(parents=True, exist_ok=True)
            for i in range(n):
                j = dict(kw)
                j.update(tilt=float(rng.uniform(0, 10)), rotation=float(rng.uniform(-15, 15)))
                cv2.imwrite(str(d / f"{i:02d}.jpg"), photograph(card, rng=rng, **j))
    return root


GOOD = {"daylight": dict(illuminant="daylight"), "shade": dict(illuminant="shade", shadow=0.3)}
BAD = {"torch": dict(illuminant="torch", glare=0.28)}


def test_label_and_condition_come_from_the_path(tmp_path):
    _write_set(tmp_path, GOOD, n=2)
    caps = read_captures(tmp_path)
    assert {c.label for c in caps} == set(WELLS)
    assert {c.condition for c in caps} == set(GOOD)


def test_survey_counts_what_is_usable(tmp_path):
    _write_set(tmp_path, GOOD, n=2)
    report, caps = survey(tmp_path)
    assert report.total == len(caps) == 8
    assert report.detected == 8
    assert report.usable == 8, report.text()


def test_survey_names_a_condition_that_is_wholly_unusable(tmp_path):
    """The finding that saves a weekend: stop shooting, fix the protocol."""
    _write_set(tmp_path, {**GOOD, **BAD}, n=3)
    report, _ = survey(tmp_path)
    assert report.by_condition["torch"]["usable"] == 0
    assert report.by_condition["daylight"]["usable"] == 6, "2 labels x 3 frames"
    text = report.text()
    assert "fix the protocol" in text and "torch" in text


def test_refusals_group_by_cause_not_by_measurement():
    a = "light is not smooth across the card (0.50 stops after correction)"
    b = "light is not smooth across the card (0.51 stops after correction)"
    assert refusal_kind(a) == refusal_kind(b), "these are one finding, not two"
    assert refusal_kind(a) != refusal_kind("card tilted 40deg, limit 25")


def test_survey_reports_guidance_the_operator_can_act_on(tmp_path):
    _write_set(tmp_path, BAD, n=3)
    report, _ = survey(tmp_path)
    assert report.usable == 0
    assert any("light" in g.lower() or "reflection" in g.lower() for g in report.guidance_counts)


def test_an_unreadable_file_is_reported_not_crashed_on(tmp_path):
    _write_set(tmp_path, GOOD, n=2)
    (tmp_path / "opiate_class" / "daylight" / "broken.jpg").write_bytes(b"not an image")
    report, caps = survey(tmp_path)
    broken = [c for c in caps if c.path.endswith("broken.jpg")]
    assert len(broken) == 1 and not broken[0].usable
    assert "unreadable" in broken[0].refusals[0]


def test_survey_of_an_empty_directory_says_so(tmp_path):
    report, caps = survey(tmp_path)
    assert report.total == 0 and caps == []
    assert "No images found" in report.text()


# --- calibration ----------------------------------------------------------- #

def test_calibration_needs_at_least_two_labels(tmp_path):
    _write_set(tmp_path, GOOD, n=3, wells={"opiate_class": WELLS["opiate_class"]})
    with pytest.raises(ValueError, match="at least two labels"):
        calibrate(tmp_path, holdout="shade", alpha=0.2)


def test_calibration_rejects_a_holdout_that_is_not_in_the_set(tmp_path):
    _write_set(tmp_path, GOOD, n=3)
    with pytest.raises(ValueError, match="not in the set"):
        calibrate(tmp_path, holdout="moonlight", alpha=0.2)


def test_calibration_refuses_when_too_few_points_and_says_what_to_do(tmp_path):
    """The conformal guarantee is finite-sample. Below the floor there is no
    honest threshold, and the message must be actionable to someone holding a camera."""
    _write_set(tmp_path, GOOD, n=2)
    with pytest.raises(ValueError) as e:
        calibrate(tmp_path, holdout="shade", alpha=0.01)
    msg = str(e.value)
    assert "finite-sample guarantee" in msg
    assert "Capture about" in msg and "--alpha" in msg


def test_calibration_holds_out_a_whole_condition(tmp_path):
    _write_set(tmp_path, {**GOOD, "tungsten": dict(illuminant="tungsten", exposure=0.8)}, n=5)
    report = calibrate(tmp_path, holdout="tungsten", alpha=0.2)
    assert report.holdout_condition == "tungsten"
    assert report.n_evaluated == 10, "every tungsten frame is evaluated, none is fitted"
    assert set(report.loci) == set(WELLS)
    assert "HELD-OUT CONDITION" in report.text()


def test_a_sample_split_is_labelled_as_the_weaker_claim(tmp_path):
    """Random splits flatter the model. The report must not let that pass silently."""
    _write_set(tmp_path, GOOD, n=6)
    report = calibrate(tmp_path, holdout=None, alpha=0.2)
    assert report.holdout_condition is None
    text = report.text()
    assert "held-out SAMPLES" in text
    assert "flatters the model" in text
    assert "Do not quote it as a field accuracy" in text


def test_degradation_under_an_unseen_illuminant_is_abstention_not_error(tmp_path):
    """The property the whole design rests on.

    Under a condition the calibration never saw, the system may lose coverage —
    but it must lose it by abstaining, not by committing to a wrong label.
    """
    _write_set(tmp_path, {**GOOD, "tungsten": dict(illuminant="tungsten", exposure=0.8)}, n=5)
    report = calibrate(tmp_path, holdout="tungsten", alpha=0.2)
    assert report.error_rate == 0.0, (
        f"committed to a wrong label on an unseen illuminant\n{report.text()}"
    )
    assert report.coverage >= report.singleton_rate - 1e-9


def test_the_report_warns_when_coverage_misses_the_stated_bound(tmp_path):
    _write_set(tmp_path, {**GOOD, "tungsten": dict(illuminant="tungsten", exposure=0.8)}, n=5)
    report = calibrate(tmp_path, holdout="tungsten", alpha=0.2)
    if report.coverage < 1 - report.alpha:
        assert "below the stated bound" in report.text()
        assert "not\n    exchangeable" in report.text() or "exchangeable" in report.text()
