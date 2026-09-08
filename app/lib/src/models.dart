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
