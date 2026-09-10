/// One frame in, one measurement out — on the device, in pure Dart.
///
/// This is the on-device counterpart to `core/ftr/pipeline.py`. It exists so an
/// APK works in a room with no laptop: no bridge, no network, no native code.
///
/// It is deliberately the *same shape* as the Python pipeline — detect, rectify,
/// fit the light field, solve the device transform, sample the well, grade the
/// frame, classify with abstention — so that a verifier re-running the reference
/// implementation is checking the same steps. Where it is weaker it says so:
/// corners come from blob extremes rather than sub-pixel refinement, so a record
/// measured here carries `pipeline: "dart-on-device"` and a verifier can judge
/// the last digit accordingly.
library;

import 'dart:math' as math;

import 'package:image/image.dart' as img;

import 'card.dart';
import 'colorimetry.dart';
import 'detect.dart';

class Quality {
  final int fiducials;
  final double tiltDegrees;
  final double reprojectionPx;
  final double sharpness;
  final double clipped;
  final double dynamicRange;
  final double lightFieldStops;

  const Quality({
    required this.fiducials,
    required this.tiltDegrees,
    required this.reprojectionPx,
    required this.sharpness,
    required this.clipped,
    required this.dynamicRange,
    required this.lightFieldStops,
  });

  // Thresholds are policy. They live together so a change is one edit and shows
  // up in review, and they mirror the Python gate.
  static const maxTilt = 25.0;
  static const maxReprojection = 6.0;   // looser than Python: coarser corners
  static const minSharpness = 0.004;
  static const maxClipped = 0.03;
  static const minDynamicRange = 0.30;
  static const maxLightField = 0.30;

  List<String> failures() {
    final f = <String>[];
    if (fiducials < 4) f.add('only $fiducials of 4 fiducials found');
    if (tiltDegrees > maxTilt) {
      f.add('card tilted ${tiltDegrees.round()}deg, limit ${maxTilt.round()}');
    }
    if (reprojectionPx > maxReprojection) {
      f.add('fiducial fit is loose (${reprojectionPx.toStringAsFixed(1)} px)');
    }
    if (sharpness < minSharpness) f.add('frame is soft');
    if (clipped > maxClipped) {
      f.add('${(clipped * 100).toStringAsFixed(1)}% of the card is clipped');
    }
    if (dynamicRange < minDynamicRange) f.add('not enough light on the card');
    if (lightFieldStops > maxLightField) {
      f.add('a shadow or highlight edge crosses the card');
    }
    return f;
  }

  bool get passed => failures().isEmpty;

  String get guidance {
    if (fiducials < 4) return 'Move back until all four corner markers are in frame.';
    if (tiltDegrees > maxTilt) return 'Hold the phone flatter, parallel to the card.';
    if (clipped > maxClipped) {
      return 'Too bright. Move out of direct light, or shade the card with your hand.';
    }
    if (sharpness < minSharpness) return 'Hold steady, or move further away to focus.';
    if (lightFieldStops > maxLightField) {
      return 'A shadow edge crosses the card. Move so the light is even across all of it.';
    }
    if (dynamicRange < minDynamicRange) return 'Find more light.';
    return 'Hold steady.';
  }
}

class DeviceMeasurement {
  final bool detected;
  final Quality? quality;
  final DartDetection? detection;
  final List<double>? lab;
  final double? cardResidual;
  final Prediction? prediction;
  final List<String> refusals;

  const DeviceMeasurement({
    required this.detected,
    required this.refusals,
    this.quality,
    this.detection,
    this.lab,
    this.cardResidual,
    this.prediction,
  });

  bool get usable => prediction != null;
  String get guidance =>
      quality?.guidance ?? 'Move back until all four corner markers are in frame.';
}

/// sRGB primaries under D65, scaled to Y = 100 — the reference the card's
/// nominal patch colours are expressed against.
List<List<double>> _referenceXyz(CardSpec spec) => spec.patchSrgb.map((p) {
      final lin = p.map(srgbToLinear).toList();
      return List<double>.generate(3, (i) {
        var s = 0.0;
        for (var j = 0; j < 3; j++) {
          s += srgbToXyzD65[i][j] * lin[j];
        }
        return s;
      });
    }).toList();

/// Bilinear sample of the source image at a point, in linear RGB.
List<double> _sampleLinear(img.Image src, double x, double y) {
  final x0 = x.floor().clamp(0, src.width - 1);
  final y0 = y.floor().clamp(0, src.height - 1);
  final p = src.getPixel(x0, y0);
  return [srgbToLinear(p.r / 255), srgbToLinear(p.g / 255), srgbToLinear(p.b / 255)];
}

/// Trimmed mean over a square region in the card's millimetre grid.
///
/// Trimming discards the brightest and darkest eighth, which is what rejects a
/// torch highlight or a dust speck without modelling either.
({List<double> rgb, double clipped}) _samplePatch(
    img.Image src, List<double> h, double cxMm, double cyMm, double halfMm) {
  final samples = <List<double>>[];
  var clipped = 0, total = 0;
  const steps = 7;
  for (var i = 0; i < steps; i++) {
    for (var j = 0; j < steps; j++) {
      final mx = cxMm - halfMm + 2 * halfMm * i / (steps - 1);
      final my = cyMm - halfMm + 2 * halfMm * j / (steps - 1);
      final p = applyHomography(h, mx * pxPerMm, my * pxPerMm);
      if (p[0].isNaN || p[0] < 0 || p[1] < 0 ||
          p[0] >= src.width || p[1] >= src.height) {
        continue;
      }
      final raw = src.getPixel(p[0].floor(), p[1].floor());
      total++;
      if (raw.r >= 252 || raw.g >= 252 || raw.b >= 252) clipped++;
      samples.add(_sampleLinear(src, p[0], p[1]));
    }
  }
  if (samples.isEmpty) return (rgb: [0.0, 0.0, 0.0], clipped: 1.0);

  samples.sort((a, b) {
    final la = 0.2126 * a[0] + 0.7152 * a[1] + 0.0722 * a[2];
    final lb = 0.2126 * b[0] + 0.7152 * b[1] + 0.0722 * b[2];
    return la.compareTo(lb);
  });
  final drop = samples.length ~/ 8;
  final keep = samples.sublist(drop, samples.length - drop);
  final mean = List<double>.filled(3, 0);
  for (final s in keep) {
    for (var i = 0; i < 3; i++) {
      mean[i] += s[i] / keep.length;
    }
  }
  return (rgb: mean, clipped: total == 0 ? 1.0 : clipped / total);
}

/// Fit a multiplicative illumination surface from the grey ladder, and report
/// how much structure the fit could not explain.
///
/// Bi-quadratic in card coordinates, fitted in log space so a shadow that halves
/// the light is a constant offset rather than a shape to chase. Mean-normalised
/// over the card so it corrects *spatial* variation only: the global illuminant
/// cast is the device transform's job, fitted against all 23 patches rather than
/// these 8.
({List<List<double>> coeffs, double residualStops}) _fitLightField(
    List<List<double>> patchRgb, CardSpec spec) {
  final idx = spec.neutralIndex;
  final basis = <List<double>>[];
  final target = <List<double>>[];

  for (final i in idx) {
    final c = spec.patchCentresMm[i];
    final x = c[0] / spec.widthMm, y = c[1] / spec.heightMm;
    basis.add([1, x, y, x * x, x * y, y * y]);
    final expected = spec.patchSrgb[i].map(srgbToLinear).toList();
    target.add(List<double>.generate(3, (k) =>
        math.log(math.max(patchRgb[i][k], 1e-6) / math.max(expected[k], 1e-6))));
  }

  final coeffs = _lstsq(basis, target);

  var sq = 0.0;
  var n = 0;
  for (var i = 0; i < basis.length; i++) {
    for (var k = 0; k < 3; k++) {
      var pred = 0.0;
      for (var j = 0; j < 6; j++) {
        pred += basis[i][j] * coeffs[j][k];
      }
      final d = target[i][k] - pred;
      sq += d * d;
      n++;
    }
  }
  final residualStops = math.sqrt(sq / n) / math.ln2;

  // Mean-normalise over the card.
  var meanLog = List<double>.filled(3, 0);
  var count = 0;
  for (var gx = 0; gx <= 10; gx++) {
    for (var gy = 0; gy <= 10; gy++) {
      final x = gx / 10, y = gy / 10;
      final b = [1.0, x, y, x * x, x * y, y * y];
      for (var k = 0; k < 3; k++) {
        var v = 0.0;
        for (var j = 0; j < 6; j++) {
          v += b[j] * coeffs[j][k];
        }
        meanLog[k] += v;
      }
      count++;
    }
  }
  for (var k = 0; k < 3; k++) {
    coeffs[0][k] -= meanLog[k] / count;
  }
  return (coeffs: coeffs, residualStops: residualStops);
}

List<double> _gainAt(List<List<double>> coeffs, double xMm, double yMm, CardSpec spec) {
  final x = xMm / spec.widthMm, y = yMm / spec.heightMm;
  final b = [1.0, x, y, x * x, x * y, y * y];
  return List<double>.generate(3, (k) {
    var v = 0.0;
    for (var j = 0; j < 6; j++) {
      v += b[j] * coeffs[j][k];
    }
    return math.exp(v);
  });
}

List<List<double>> _lstsq(List<List<double>> a, List<List<double>> b) {
  final n = a[0].length, m = b[0].length, rows = a.length;
  final ata = List.generate(n, (_) => List<double>.filled(n, 0));
  final atb = List.generate(n, (_) => List<double>.filled(m, 0));
  for (var i = 0; i < n; i++) {
    for (var j = 0; j < n; j++) {
      var s = 0.0;
      for (var k = 0; k < rows; k++) {
        s += a[k][i] * a[k][j];
      }
      ata[i][j] = s + (i == j ? 1e-9 : 0);   // ridge: 8 points, 6 terms
    }
    for (var j = 0; j < m; j++) {
      var s = 0.0;
      for (var k = 0; k < rows; k++) {
        s += a[k][i] * b[k][j];
      }
      atb[i][j] = s;
    }
  }
  for (var col = 0; col < n; col++) {
    var pivot = col;
    for (var r = col + 1; r < n; r++) {
      if (ata[r][col].abs() > ata[pivot][col].abs()) pivot = r;
    }
    if (ata[pivot][col].abs() < 1e-14) continue;
    final t1 = ata[col]; ata[col] = ata[pivot]; ata[pivot] = t1;
    final t2 = atb[col]; atb[col] = atb[pivot]; atb[pivot] = t2;
    final d = ata[col][col];
    for (var j = 0; j < n; j++) {
      ata[col][j] /= d;
    }
    for (var j = 0; j < m; j++) {
      atb[col][j] /= d;
    }
    for (var r = 0; r < n; r++) {
      if (r == col) continue;
      final f = ata[r][col];
      if (f == 0) continue;
      for (var j = 0; j < n; j++) {
        ata[r][j] -= f * ata[col][j];
      }
      for (var j = 0; j < m; j++) {
        atb[r][j] -= f * atb[col][j];
      }
    }
  }
  return atb;
}

/// Run a frame through detection, normalisation, and — if it earns one — L2.
DeviceMeasurement measureOnDevice(img.Image src,
    {ConformalClassifier? classifier, CardSpec? card}) {
  final spec = card ?? cardV1;

  final gray = toGray(src);
  final binary = adaptiveThreshold(gray);
  final ordered = orderMarkers(findFiducials(binary, gray.width, gray.height));
  if (ordered == null) {
    return const DeviceMeasurement(
      detected: false,
      refusals: ['fewer than four fiducials found — the card was not fully in '
          'frame, or the print is damaged'],
    );
  }

  // Each marker contributes the one outer corner that sits at the card's own
  // extremity, which is what makes the four points span the card.
  final srcPts = <List<double>>[
    ordered[0].corners[0],
    ordered[1].corners[1],
    ordered[2].corners[2],
    ordered[3].corners[3],
  ];
  final dstPts = spec.markerCornersMm
      .map((p) => [p[0] * pxPerMm, p[1] * pxPerMm])
      .toList();

  final h = homographyFrom(dstPts, srcPts);   // card grid -> image
  if (h == null) {
    return const DeviceMeasurement(
        detected: false, refusals: ['the four markers are degenerate']);
  }

  var reproj = 0.0;
  for (var i = 0; i < 4; i++) {
    final p = applyHomography(h, dstPts[i][0], dstPts[i][1]);
    reproj += math.sqrt(math.pow(p[0] - srcPts[i][0], 2) +
        math.pow(p[1] - srcPts[i][1], 2)) / 4;
  }

  final half = spec.patchSizeMm * 0.35;
  final raw = <List<double>>[];
  var clipped = 0.0;
  for (final c in spec.patchCentresMm) {
    final s = _samplePatch(src, h, c[0], c[1], half);
    raw.add(s.rgb);
    clipped += s.clipped / spec.patchCentresMm.length;
  }

  final light = _fitLightField(raw, spec);
  final corrected = <List<double>>[];
  for (var i = 0; i < raw.length; i++) {
    final c = spec.patchCentresMm[i];
    final g = _gainAt(light.coeffs, c[0], c[1], spec);
    corrected.add(List<double>.generate(
        3, (k) => raw[i][k] / math.max(g[k], 1e-6)));
  }

  final reference = _referenceXyz(spec);
  final transform = RootPolynomial.fit(corrected, reference);

  final well = _samplePatch(src, h, spec.wellCentreMm[0], spec.wellCentreMm[1],
      spec.wellRadiusMm * 0.7);
  final wellGain = _gainAt(light.coeffs, spec.wellCentreMm[0], spec.wellCentreMm[1], spec);
  final lab = transform.toLab(List<double>.generate(
      3, (k) => math.max(well.rgb[k] / math.max(wellGain[k], 1e-6), 1e-5)));

  var lumMin = 1e9, lumMax = -1e9;
  for (final p in raw) {
    final l = 0.2126 * p[0] + 0.7152 * p[1] + 0.0722 * p[2];
    lumMin = math.min(lumMin, l);
    lumMax = math.max(lumMax, l);
  }

  final quality = Quality(
    fiducials: 4,
    tiltDegrees: tiltFrom(h),
    reprojectionPx: reproj,
    sharpness: _sharpness(gray),
    clipped: clipped,
    dynamicRange: lumMax - lumMin,
    lightFieldStops: light.residualStops,
  );

  final refusals = quality.failures();
  if (!transform.passes()) {
    refusals.add('the card\'s own patches did not reproduce '
        '(${transform.residualDeltaE.toStringAsFixed(2)} dE) — no measurement '
        'from this frame is trustworthy');
    // And why. A refusal carrying one number sends the operator back to retake
    // the same frame in the same conditions and get the same number.
    refusals.add('likely cause: ${transform.diagnose(reference)}');
  }

  Prediction? prediction;
  if (refusals.isEmpty && classifier != null) prediction = classifier.predict(lab);

  return DeviceMeasurement(
    detected: true,
    quality: quality,
    detection: DartDetection(
        markers: ordered, homography: h,
        reprojectionPx: reproj, tiltDegrees: quality.tiltDegrees),
    lab: lab,
    cardResidual: transform.residualDeltaE,
    prediction: prediction,
    refusals: refusals,
  );
}

/// Laplacian variance, normalised by contrast so a low-contrast but sharp frame
/// is not called soft.
double _sharpness(Gray g) {
  var mean = 0.0;
  for (final v in g.data) {
    mean += v / g.data.length;
  }
  var variance = 0.0;
  for (final v in g.data) {
    variance += (v - mean) * (v - mean) / g.data.length;
  }
  var lap = 0.0;
  var n = 0;
  for (var y = 1; y < g.height - 1; y += 2) {
    for (var x = 1; x < g.width - 1; x += 2) {
      final v = -4 * g.at(x, y) +
          g.at(x - 1, y) + g.at(x + 1, y) + g.at(x, y - 1) + g.at(x, y + 1);
      lap += v * v.toDouble();
      n++;
    }
  }
  if (n == 0 || variance < 1e-9) return 0;
  // Both terms are in the same 0-255 units, so the ratio matches the Python
  // gate's var(laplacian)/var(grey). An extra 255 here made every frame read as
  // soft, which is the kind of scaling slip that only shows up on a real photo.
  return (lap / n) / variance;
}

// --------------------------------------------------------------------------- //
// two-view liveness, on the device
// --------------------------------------------------------------------------- //

class DeviceLiveness {
  final bool checked;
  final bool live;
  final double displacementPx;
  final double planeResidualPx;
  final double floorPx;
  final String reason;

  const DeviceLiveness({
    required this.checked,
    required this.live,
    required this.displacementPx,
    required this.planeResidualPx,
    required this.floorPx,
    required this.reason,
  });
}

/// How far the tab region moved against the card plane between two views.
///
/// Both frames are mapped onto the card's own millimetre grid, so everything ON
/// the card lands in the same place and only out-of-plane structure moves. A
/// flat reproduction gives zero, at any print quality, because it is flat.
///
/// This is the weaker form of the check, and says so: without a known baseline
/// and camera distance the feature's height is not pinned, so it tests that the
/// card re-aligned and the tab moved against it, rather than that the tab moved
/// by the amount an 8 mm feature would.
DeviceLiveness livenessOnDevice(img.Image a, img.Image b, {CardSpec? card}) {
  final spec = card ?? cardV1;

  List<double>? homographyFor(img.Image src) {
    final gray = toGray(src);
    final ordered = orderMarkers(
        findFiducials(adaptiveThreshold(gray), gray.width, gray.height));
    if (ordered == null) return null;
    final srcPts = [
      ordered[0].corners[0], ordered[1].corners[1],
      ordered[2].corners[2], ordered[3].corners[3],
    ];
    final dstPts = spec.markerCornersMm
        .map((p) => [p[0] * pxPerMm, p[1] * pxPerMm])
        .toList();
    return homographyFrom(dstPts, srcPts);
  }

  final ha = homographyFor(a), hb = homographyFor(b);
  if (ha == null || hb == null) {
    return const DeviceLiveness(
      checked: false, live: false, displacementPx: 0, planeResidualPx: 0,
      floorPx: 2.0, reason: 'the card was not found in both frames',
    );
  }

  /// Mean absolute difference between the two rectified views over a region of
  /// the card, at a candidate offset. Minimising this finds how far the region
  /// moved between the frames.
  double cost(double cxMm, double cyMm, double halfMm, double dxPx, double dyPx) {
    var sum = 0.0;
    var n = 0;
    const steps = 13;
    for (var i = 0; i < steps; i++) {
      for (var j = 0; j < steps; j++) {
        final mx = cxMm - halfMm + 2 * halfMm * i / (steps - 1);
        final my = cyMm - halfMm + 2 * halfMm * j / (steps - 1);
        final pa = applyHomography(ha, mx * pxPerMm, my * pxPerMm);
        final pb = applyHomography(hb, mx * pxPerMm + dxPx, my * pxPerMm + dyPx);
        if (pa[0].isNaN || pb[0].isNaN) continue;
        if (pa[0] < 0 || pa[1] < 0 || pa[0] >= a.width || pa[1] >= a.height) continue;
        if (pb[0] < 0 || pb[1] < 0 || pb[0] >= b.width || pb[1] >= b.height) continue;
        final va = a.getPixel(pa[0].floor(), pa[1].floor());
        final vb = b.getPixel(pb[0].floor(), pb[1].floor());
        final la = 0.2126 * va.r + 0.7152 * va.g + 0.0722 * va.b;
        final lb = 0.2126 * vb.r + 0.7152 * vb.g + 0.0722 * vb.b;
        sum += (la - lb).abs();
        n++;
      }
    }
    return n == 0 ? 1e9 : sum / n;
  }

  /// Search a small offset grid for the shift that best aligns a region.
  double bestShift(double cxMm, double cyMm, double halfMm) {
    var best = 1e18, bestR = 0.0;
    for (var dx = -40.0; dx <= 40.0; dx += 2) {
      for (var dy = -20.0; dy <= 20.0; dy += 2) {
        final c = cost(cxMm, cyMm, halfMm, dx, dy);
        if (c < best) {
          best = c;
          bestR = math.sqrt(dx * dx + dy * dy);
        }
      }
    }
    return bestR;
  }

  // How well the card itself re-aligned: anything here means the card moved or
  // bent, and the tab reading is then measuring that instead of depth.
  var plane = 0.0;
  const probes = [[26.0, 22.0], [66.0, 22.0], [26.0, 42.0], [66.0, 42.0]];
  for (final p in probes) {
    plane += bestShift(p[0], p[1], 4.0) / probes.length;
  }

  final tab = spec.tabCentreMm;
  final raw = bestShift(tab[0], tab[1], 7.0);
  final displacement = math.max(0.0, raw - plane);

  const floor = 4.0;          // below this is search noise, not depth
  const planeLimit = 6.0;

  bool live;
  String reason;
  if (plane > planeLimit) {
    live = false;
    reason = 'the card did not re-align between frames '
        '(${plane.toStringAsFixed(1)} px): it moved or bent';
  } else if (displacement < floor) {
    live = false;
    reason = 'FLAT. ${displacement.toStringAsFixed(1)} px of parallax at the tab. '
        'A print or a screen gives zero at any print quality, because it is flat';
  } else {
    live = true;
    reason = '${displacement.toStringAsFixed(1)} px of parallax at the tab while '
        'the card plane re-aligned: the scene has depth';
  }

  return DeviceLiveness(
    checked: true, live: live,
    displacementPx: displacement, planeResidualPx: plane,
    floorPx: floor, reason: reason,
  );
}
