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
import 'dart:math' as math;
import 'dart:typed_data';

import 'package:image/image.dart' as img;

import 'package:ftr_verify/ftr_verify.dart' as ftr;
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

/// Reference loci for the surrogate colour ladder the card is printed against.
///
/// Substituting NCB reagent standards is a data change, not an architecture
/// change — L1 and L3 to L7 are substance-independent by construction.
final _loci = <String, List<double>>{
  'opiate_class': [18.4, 23.2, -7.5],
  'opiate_related': [22.1, 20.4, -4.8],
  'amphetamine_class': [40.3, 14.3, 26.4],
  'negative': [80.1, -1.2, 5.9],
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
  for (final e in _loci.entries) {
    for (var i = 0; i < 200; i++) {
      labs.add(List<double>.generate(3, (k) => e.value[k] + gauss() * 2.4));
      labels.add(e.key);
    }
  }
  return ftr.ConformalClassifier(_loci, alpha: 0.05)..calibrate(labs, labels);
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

class MeasureBridge {
  MeasureBridge({String? endpoint})
      : endpoint = endpoint ??
            const String.fromEnvironment('BRIDGE',
                defaultValue: 'http://127.0.0.1:8824/');

  /// Where the pipeline is running.
  ///
  /// On a handset `127.0.0.1` is the phone itself, which has no bridge — so for
  /// an APK demo this must point at the laptop's address on the same network.
  /// Set it at build time with `--dart-define=BRIDGE=http://192.168.1.20:8824/`,
  /// or edit it in the app, because a venue's addresses are never the ones you
  /// built against.
  String endpoint;
  bool _inFlight = false;

  /// True once a request has come back from a real bridge.
  bool reachable = false;

  Future<bool> ping() async {
    try {
      final r = await http
          .get(Uri.parse(endpoint))
          .timeout(const Duration(seconds: 4));
      reachable = r.statusCode == 200;
    } catch (_) {
      reachable = false;
    }
    return reachable;
  }

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
      reachable = true;
      return _parse(jsonDecode(response.body) as Map<String, dynamic>);
    } catch (_) {
      reachable = false;
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
      reachable = true;
      return _parse(jsonDecode(response.body) as Map<String, dynamic>);
    } catch (_) {
      reachable = false;
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
