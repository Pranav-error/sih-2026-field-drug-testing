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

import 'dart:convert';
import 'dart:typed_data';

import 'package:http/http.dart' as http;

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
    guidance: 'Measure bridge not running — start core/tools/measure_server.py',
    gatePassed: false,
    refusals: ['the measure bridge is not reachable'],
    quality: CaptureQuality(
        fiducialsFound: 0, illumination: 0, focus: 0,
        tiltDegrees: 90, clippedFraction: 0),
  );
}

class MeasureBridge {
  MeasureBridge({this.endpoint = 'http://127.0.0.1:8824/'});

  final String endpoint;
  bool _inFlight = false;

  /// Measure two frames together: the colour from the first, and the liveness
  /// from the pair. This is the call the second view makes.
  Future<Measurement?> measurePair(Uint8List a, Uint8List b) async {
    if (_inFlight) return null;
    _inFlight = true;
    try {
      final response = await http
          .post(Uri.parse(endpoint),
              headers: const {'Content-Type': 'application/json'},
              body: jsonEncode({'frame': base64Encode(a), 'frame_b': base64Encode(b)}))
          .timeout(const Duration(seconds: 30));
      if (response.statusCode != 200) return Measurement.unavailable;
      return _parse(jsonDecode(response.body) as Map<String, dynamic>);
    } catch (_) {
      return Measurement.unavailable;
    } finally {
      _inFlight = false;
    }
  }

  /// Measure one frame. Returns null when a request is already in flight, so a
  /// slow round trip cannot queue up behind the viewfinder's frame rate.
  Future<Measurement?> measure(Uint8List jpeg) async {
    if (_inFlight) return null;
    _inFlight = true;
    try {
      final response = await http
          .post(Uri.parse(endpoint),
              headers: const {'Content-Type': 'application/json'},
              body: jsonEncode({'frame': base64Encode(jpeg)}))
          .timeout(const Duration(seconds: 12));
      if (response.statusCode != 200) return Measurement.unavailable;
      return _parse(jsonDecode(response.body) as Map<String, dynamic>);
    } catch (_) {
      return Measurement.unavailable;
    } finally {
      _inFlight = false;
    }
  }

  Measurement _parse(Map<String, dynamic> j) {
    double d(String k, [double fallback = 0]) =>
        (j[k] as num?)?.toDouble() ?? fallback;

    final quality = CaptureQuality(
      fiducialsFound: (j['fiducials'] as num?)?.toInt() ?? 0,
      illumination: d('illumination'),
      focus: d('focus'),
      tiltDegrees: d('tilt_degrees', 90),
      clippedFraction: d('clipped'),
    );

    TestResult? result;
    final p = j['prediction'] as Map<String, dynamic>?;
    if (p != null) {
      result = TestResult(
        predictionSet: (p['set'] as List).cast<String>(),
        label: p['label'] as String?,
        lab: (j['lab'] as List?)?.map((v) => (v as num).toDouble()).toList(),
        alpha: (p['alpha'] as num).toDouble(),
        threshold: (p['threshold'] as num).toDouble(),
        scores: (p['scores'] as Map).map(
            (k, v) => MapEntry(k as String, (v as num).toDouble())),
      );
    }

    Liveness? live;
    final l = j['liveness'] as Map<String, dynamic>?;
    if (l != null) {
      live = l['checked'] == true
          ? Liveness(
              checked: true,
              live: l['live'] == true,
              measuredPx: (l['displacement_px'] as num).toDouble(),
              predictedPx: (l['floor_px'] as num?)?.toDouble() ?? 2.0,
              reason: l['reason'] as String? ?? '',
            )
          : const Liveness.notChecked();
    }

    return Measurement(
      liveness: live,
      detected: j['detected'] == true,
      fiducials: quality.fiducialsFound,
      guidance: j['guidance'] as String? ?? 'Hold steady.',
      gatePassed: j['gate_passed'] == true,
      refusals: ((j['refusals'] as List?) ?? const []).cast<String>(),
      lab: (j['lab'] as List?)?.map((v) => (v as num).toDouble()).toList(),
      cardResidual: (j['card_residual'] as num?)?.toDouble(),
      quality: quality,
      result: result,
    );
  }
}
