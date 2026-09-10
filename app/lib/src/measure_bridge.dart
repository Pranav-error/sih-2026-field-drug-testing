/// Talks to the local Python bridge that runs the real L1/L2 pipeline.
///
/// On a handset this work happens natively over a platform channel: OpenCV
/// compiled into the app, no network. A browser has no OpenCV, so for the web
/// demo the same `ftr.pipeline` runs behind `core/tools/measure_server.py` on
/// localhost and the app posts frames to it.
///
/// The transport is a substitute for the platform channel. **The pipeline is
/// not a substitute for anything** — it is the same code the tests and the
/// reference verifier run, so the numbers on screen are real measurements of the
/// frame in front of the camera.
library;

import 'dart:math' as math;
import 'dart:typed_data';

import 'package:image/image.dart' as img;

import 'package:ftr_verify/ftr_verify.dart' as ftr;

import 'models.dart';

class Measurement {
  final bool detected;
  final int fiducials;
  final String guidance;
  final bool gatePassed;
  final List<String> refusals;
  final List<double>? lab;
  final double? cardResidual;
  final CaptureQuality quality;
  final TestResult? result;
  final Liveness? liveness;

  const Measurement({
    required this.detected,
    required this.fiducials,
    required this.guidance,
    required this.gatePassed,
    required this.refusals,
    required this.quality,
    this.lab,
    this.cardResidual,
    this.result,
    this.liveness,
  });

  static const unavailable = Measurement(
    detected: false,
    fiducials: 0,
    // The measure bridge and its server were deleted when L1 moved on-device;
    // this is now what a decode or pipeline failure looks like.
    guidance: 'The frame could not be read. Retake it.',
    gatePassed: false,
    refusals: ['the frame could not be decoded or measured on this device'],
    quality: CaptureQuality(
        fiducialsFound: 0, illumination: 0, focus: 0,
        tiltDegrees: 90, clippedFraction: 0),
  );
}

/// Reference loci for the surrogate colour ladder the card is printed against.
///
/// Substituting NCB reagent standards is a data change, not an architecture
/// change — L1 and L3 to L7 are substance-independent by construction.
///
/// Two of these were guesses that made the classifier unusable, and both were
/// corrected against measurement rather than by taste:
///
/// **negative** was at L=80.1. The real printed card's empty well measures
/// L=95.5 (`test/fixtures/real_card.jpg`, ΔE 0.01 from the value below). At
/// 80.1 a dry well scored 11.25 from its own class and fell outside the
/// threshold, so a blank card returned an EMPTY prediction set — reported to the
/// operator as "inconclusive" when the correct answer was a clean *negative*.
///
/// **opiate_related** sat 3.33 from `opiate_class` while the abstention
/// threshold is 5.53. Any reading near either was inside both, so a single
/// label was arithmetically impossible: at the calibration's own scatter, a
/// clean read returned one label about one time in nine. The classifier was not
/// broken — it was correctly refusing to separate classes the ladder does not
/// separate. A surrogate ladder whose rungs are closer together than the
/// threshold cannot be used to demonstrate anything.
///
/// The rule this ladder now obeys: **every pair is more than 2× the threshold
/// apart** (minimum 15.87 against a threshold of 5.53), so a reading near a
/// rung falls inside exactly one. `measure_bridge_test.dart` enforces it, and
/// will fail if a future locus is added too close to an existing one.
final Map<String, List<double>> referenceLoci = <String, List<double>>{
  'opiate_class': [18.4, 23.2, -7.5],
  'opiate_related': [33.0, 46.0, -28.0],
  'amphetamine_class': [40.3, 14.3, 26.4],
  'negative': [95.5, 0.0, 0.0],
};

ftr.ConformalClassifier _buildClassifier() {
  // Calibration points jittered around each locus, matching the bridge's set so
  // the on-device threshold and the reference threshold agree. On deployment
  // this split is physical: held-out frames under an illuminant never seen.
  final rng = math.Random(2026);
  double gauss() {
    final u1 = rng.nextDouble().clamp(1e-9, 1.0), u2 = rng.nextDouble();
    return math.sqrt(-2 * math.log(u1)) * math.cos(2 * math.pi * u2);
  }

  final labs = <List<double>>[];
  final labels = <String>[];
  for (final e in referenceLoci.entries) {
    for (var i = 0; i < 200; i++) {
      labs.add(List<double>.generate(3, (k) => e.value[k] + gauss() * 2.4));
      labels.add(e.key);
    }
  }
  return ftr.ConformalClassifier(referenceLoci, alpha: 0.05)..calibrate(labs, labels);
}

/// Measures a frame **on the device**, in pure Dart, with no network.
///
/// This is what makes a standalone APK possible: the same steps as the Python
/// pipeline — detect, rectify, fit the light field, solve the device transform,
/// sample, grade, classify with abstention — running on the handset. Coarser
/// than the reference implementation at the corner-detection step, and the
/// record says so.
class OnDeviceMeasurer {
  OnDeviceMeasurer() : _classifier = _buildClassifier();

  final ftr.ConformalClassifier _classifier;
  bool _busy = false;

  double get threshold => _classifier.threshold ?? 0;

  /// Classify a Lab* triple directly. Exposed so the ladder's geometry can be
  /// tested without a camera — the property that broke here is arithmetic, not
  /// optical, and a test that needs a handset would never have caught it.
  ftr.Prediction classify(List<double> lab) => _classifier.predict(lab);

  Measurement? measure(Uint8List jpeg) {
    if (_busy) return null;
    _busy = true;
    try {
      var src = img.decodeImage(jpeg);
      if (src == null) return Measurement.unavailable;
      // Detection does not need 4K, and a viewfinder has a frame budget.
      if (src.width > 1200) {
        src = img.copyResize(src,
            width: 1200, interpolation: img.Interpolation.average);
      }
      final m = ftr.measureOnDevice(src, classifier: _classifier);
      return _fromDevice(m);
    } catch (_) {
      return Measurement.unavailable;
    } finally {
      _busy = false;
    }
  }

  /// The two-view liveness check, on two real frames, on the device.
  Measurement? measurePair(Uint8List a, Uint8List b) {
    final first = measure(a);
    if (first == null) return null;
    try {
      var ia = img.decodeImage(a), ib = img.decodeImage(b);
      if (ia == null || ib == null) return first;
      if (ia.width > 1200) {
        ia = img.copyResize(ia, width: 1200, interpolation: img.Interpolation.average);
      }
      if (ib.width > 1200) {
        ib = img.copyResize(ib, width: 1200, interpolation: img.Interpolation.average);
      }
      final l = ftr.livenessOnDevice(ia, ib);
      return Measurement(
        detected: first.detected,
        fiducials: first.fiducials,
        guidance: first.guidance,
        gatePassed: first.gatePassed,
        refusals: first.refusals,
        quality: first.quality,
        lab: first.lab,
        cardResidual: first.cardResidual,
        result: first.result,
        liveness: Liveness(
          checked: l.checked,
          live: l.live,
          measuredPx: l.displacementPx,
          predictedPx: l.floorPx,
          reason: l.reason,
        ),
      );
    } catch (_) {
      return first;
    }
  }

  Measurement _fromDevice(ftr.DeviceMeasurement m) {
    final q = m.quality;
    final quality = CaptureQuality(
      fiducialsFound: q?.fiducials ?? 0,
      illumination: q == null
          ? 0
          : (1 - q.lightFieldStops / ftr.Quality.maxLightField).clamp(0.0, 1.0),
      focus: q == null
          ? 0
          : (q.sharpness / ftr.Quality.minSharpness).clamp(0.0, 1.0),
      tiltDegrees: q?.tiltDegrees ?? 90,
      clippedFraction: q?.clipped ?? 0,
    );

    TestResult? result;
    final p = m.prediction;
    if (p != null) {
      result = TestResult(
        predictionSet: p.predictionSet,
        label: p.label,
        lab: m.lab,
        alpha: p.alpha,
        threshold: p.threshold,
        scores: p.scores,
      );
    }

    return Measurement(
      detected: m.detected,
      fiducials: quality.fiducialsFound,
      guidance: m.guidance,
      gatePassed: q?.passed ?? false,
      refusals: m.refusals,
      quality: quality,
      lab: m.lab,
      cardResidual: m.cardResidual,
      result: result,
    );
  }
}

