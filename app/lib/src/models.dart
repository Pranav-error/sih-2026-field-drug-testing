/// What the UI shows, and where it came from.
///
/// These types are the seam between the record layer and the screens. They carry
/// *measurements and their limits together* — a quality figure without its
/// threshold, or a label without its prediction set, would let a screen render a
/// confident-looking answer the record does not support.
library;

import 'tokens.dart';



/// Live capture quality, as the guidance overlay sees it.
class CaptureQuality {
  final int fiducialsFound;
  final double illumination; // 0..1, higher is better
  final double focus; // 0..1
  final double tiltDegrees;
  final double clippedFraction;

  const CaptureQuality({
    required this.fiducialsFound,
    required this.illumination,
    required this.focus,
    required this.tiltDegrees,
    required this.clippedFraction,
  });

  /// True when the frame is measurable.
  ///
  /// When a real measurement is available the pipeline's own gate decides —
  /// duplicating its thresholds here would let the UI and the record disagree
  /// about whether a frame was usable, which is the last thing this system
  /// should do. These values are the fallback for the simulated path.
  bool get locked =>
      fiducialsFound == 4 &&
      illumination >= 0.85 &&
      focus >= 0.85 &&
      tiltDegrees <= 25 &&
      clippedFraction <= 0.02;

  /// One instruction, naming what to move rather than what went wrong.
  String get guidance {
    if (fiducialsFound < 4) return 'Move back until all four corner markers are in frame.';
    if (tiltDegrees > 25) return 'Hold the phone flatter, parallel to the card.';
    if (clippedFraction > 0.02) {
      return 'Too bright. Move out of direct light, or shade the card with your hand.';
    }
    if (focus < 0.85) return 'Hold steady, or move slightly further away to focus.';
    if (illumination < 0.85) {
      return 'The light is uneven — move your shadow, or the reflection, off the card.';
    }
    return 'Hold steady.';
  }
}

/// Progress toward the second view.
///
/// The operator is never shown a baseline in millimetres. They are shown whether
/// they have moved far enough, because that is the only part they can act on.
class SecondView {
  final double baselineMm;      // estimated from the card's apparent motion
  final bool cardVisible;

  const SecondView({required this.baselineMm, required this.cardVisible});

  /// Ten millimetres is enough for an 8 mm tab at arm's length. The screen must
  /// not imply precision it does not need.
  static const double enoughMm = 10.0;

  bool get ready => cardVisible && baselineMm >= enoughMm;

  double get progress => (baselineMm / enoughMm).clamp(0.0, 1.0);

  String get guidance {
    if (!cardVisible) return 'Keep the whole card in frame.';
    if (baselineMm < enoughMm * 0.4) return 'Move a little to the right and shoot again.';
    if (!ready) return 'Keep going — a few more centimetres.';
    return 'Far enough. Capture the second frame.';
  }
}

/// The two-view liveness check: what was measured, and what the geometry required.
///
/// Both numbers are carried together on purpose. A reader shown only a verdict
/// cannot check it; a reader shown 28.1 against 28.2 can.
class Liveness {
  final bool checked;
  final bool live;
  final double measuredPx;
  final double predictedPx;
  final String reason;

  const Liveness({
    required this.checked,
    required this.live,
    required this.measuredPx,
    required this.predictedPx,
    this.reason = '',
  });

  const Liveness.notChecked()
      : checked = false,
        live = false,
        measuredPx = 0,
        predictedPx = 0,
        reason = 'single frame — this capture cannot be distinguished from a '
            'photograph of a card';
}

/// A completed measurement, or a refusal with its reasons.
class TestResult {
  final List<String> predictionSet;
  final String? label;
  final List<double>? lab;
  final double alpha;
  final double threshold;
  final Map<String, double> scores;
  final List<String> refusals;

  const TestResult({
    required this.predictionSet,
    required this.label,
    required this.lab,
    required this.alpha,
    required this.threshold,
    required this.scores,
    this.refusals = const [],
  });

  bool get refused => refusals.isNotEmpty;
  Outcome get outcome => Outcome.fromPredictionSet(predictionSet);

  /// Why the set is the size it is. Attached to the result, never inferred by
  /// a screen — the reason is part of the finding.
  String get reason {
    if (refused) return refusals.first;
    if (predictionSet.length == 1) {
      return 'single label within ${threshold.toStringAsFixed(2)} dE';
    }
    if (predictionSet.isEmpty) {
      return 'no reference locus within ${threshold.toStringAsFixed(2)} dE — the '
          'measurement resembles nothing this reagent is calibrated for';
    }
    return '${predictionSet.length} labels within ${threshold.toStringAsFixed(2)} dE — '
        'the measurement does not separate them at this risk level';
  }
}

/// The device's own posture, read at launch and shown before the camera.
class DevicePosture {
  final String securityLevel;
  final String verifiedBootState;
  final bool bootloaderLocked;
  final String osPatchLevel;
  final bool mockLocation;
  final int recordCount;
  final int unanchored;
  final Duration sinceAnchor;

  const DevicePosture({
    required this.securityLevel,
    required this.verifiedBootState,
    required this.bootloaderLocked,
    required this.osPatchLevel,
    required this.mockLocation,
    required this.recordCount,
    required this.unanchored,
    required this.sinceAnchor,
  });

  /// True when the device can produce records worth presenting as evidence.
  /// A development build is honestly not one.
  bool get evidenceGrade =>
      (securityLevel == 'STRONGBOX' || securityLevel == 'TEE') &&
      verifiedBootState == 'GREEN' &&
      bootloaderLocked;

  String get anchorWindow {
    final h = sinceAnchor.inHours;
    final m = sinceAnchor.inMinutes % 60;
    return h > 0 ? '${h}h ${m}m' : '${m}m';
  }
}
