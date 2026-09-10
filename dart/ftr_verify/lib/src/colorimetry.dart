/// L1 back half and L2, in Dart — the second implementation of the measurement.
///
/// Written from the same specification as `core/ftr/colorimetry.py`, not ported
/// from it. Where the Python leans on numpy's SVD-based least squares, this
/// solves the normal equations directly with partial pivoting, because a verifier
/// that inherits the other implementation's numerics is not checking them.
///
/// That difference is deliberate and it has a consequence, measured rather than
/// assumed: see `test/colorimetry_agreement_test.dart` for how far the two
/// implementations actually diverge, and `docs/DETERMINISM.md` for what the
/// record is therefore allowed to claim.
library;

import 'dart:math' as math;

/// CIE D65 white point, 2-degree observer.
const List<double> d65 = [95.047, 100.000, 108.883];

/// sRGB primaries under D65, scaled to Y = 100.
const List<List<double>> srgbToXyzD65 = [
  [41.24564, 35.75761, 18.04375],
  [21.26729, 71.51522, 7.21750],
  [1.93339, 11.91920, 95.03041],
];

/// Undo the sRGB transfer function. Input and output in [0, 1].
double srgbToLinear(double c) =>
    c <= 0.04045 ? c / 12.92 : math.pow((c + 0.055) / 1.055, 2.4).toDouble();

/// CIEXYZ (0–100 scale) to CIELAB.
List<double> xyzToLab(List<double> xyz, [List<double> white = d65]) {
  const d = 6.0 / 29.0;
  final f = <double>[];
  for (var i = 0; i < 3; i++) {
    final t = xyz[i] / white[i];
    f.add(t > d * d * d ? math.pow(t, 1 / 3).toDouble() : t / (3 * d * d) + 4.0 / 29.0);
  }
  return [116 * f[1] - 16, 500 * (f[0] - f[1]), 200 * (f[1] - f[2])];
}

double _deg(double r) => r * 180.0 / math.pi;
double _rad(double d) => d * math.pi / 180.0;

/// CIEDE2000 colour difference.
///
/// CIE76 Euclidean distance overstates differences in the blue region and
/// understates them near neutral, which is exactly where reagent colours live.
/// Using it would build a known bias into the decision threshold.
double deltaE2000(List<double> lab1, List<double> lab2) {
  final l1 = lab1[0], a1 = lab1[1], b1 = lab1[2];
  final l2 = lab2[0], a2 = lab2[1], b2 = lab2[2];

  final c1 = math.sqrt(a1 * a1 + b1 * b1);
  final c2 = math.sqrt(a2 * a2 + b2 * b2);
  final cbar = (c1 + c2) / 2;
  final cbar7 = math.pow(cbar, 7).toDouble();
  final g = 0.5 * (1 - math.sqrt(cbar7 / (cbar7 + math.pow(25.0, 7) + 1e-30)));

  final a1p = (1 + g) * a1, a2p = (1 + g) * a2;
  final c1p = math.sqrt(a1p * a1p + b1 * b1);
  final c2p = math.sqrt(a2p * a2p + b2 * b2);
  final h1p = (_deg(math.atan2(b1, a1p)) + 360) % 360;
  final h2p = (_deg(math.atan2(b2, a2p)) + 360) % 360;

  final dlp = l2 - l1;
  final dcp = c2p - c1p;
  var dhp = h2p - h1p;
  if (dhp > 180) {
    dhp -= 360;
  } else if (dhp < -180) {
    dhp += 360;
  }
  if (c1p * c2p == 0) dhp = 0;
  final dHp = 2 * math.sqrt(c1p * c2p) * math.sin(_rad(dhp / 2));

  final lbp = (l1 + l2) / 2;
  final cbp = (c1p + c2p) / 2;
  final hsum = h1p + h2p;
  double hbp;
  if (c1p * c2p == 0) {
    hbp = hsum;
  } else if ((h1p - h2p).abs() <= 180) {
    hbp = hsum / 2;
  } else {
    hbp = hsum < 360 ? (hsum + 360) / 2 : (hsum - 360) / 2;
  }

  final t = 1 -
      0.17 * math.cos(_rad(hbp - 30)) +
      0.24 * math.cos(_rad(2 * hbp)) +
      0.32 * math.cos(_rad(3 * hbp + 6)) -
      0.20 * math.cos(_rad(4 * hbp - 63));
  final dtheta = 30 * math.exp(-math.pow((hbp - 275) / 25, 2).toDouble());
  final cbp7 = math.pow(cbp, 7).toDouble();
  final rc = 2 * math.sqrt(cbp7 / (cbp7 + math.pow(25.0, 7) + 1e-30));
  final sl = 1 + (0.015 * math.pow(lbp - 50, 2)) / math.sqrt(20 + math.pow(lbp - 50, 2));
  final sc = 1 + 0.045 * cbp;
  final sh = 1 + 0.015 * cbp * t;
  final rt = -math.sin(_rad(2 * dtheta)) * rc;

  final dl = dlp / sl, dc = dcp / sc, dh = dHp / sh;
  return math.sqrt(dl * dl + dc * dc + dh * dh + rt * dc * dh);
}

// --------------------------------------------------------------------------- //
// L1 — device transform
// --------------------------------------------------------------------------- //

/// Root-polynomial expansion, degree 2 (Finlayson et al.).
///
/// Every term carries the units of intensity, so the fit is exposure-invariant:
/// scaling the light scales all terms equally.
List<double> rootPoly(List<double> rgb) {
  const eps = 1e-12;
  final r = rgb[0], g = rgb[1], b = rgb[2];
  return [
    r, g, b,
    math.sqrt(math.max(r * g, eps)),
    math.sqrt(math.max(g * b, eps)),
    math.sqrt(math.max(r * b, eps)),
  ];
}

/// Solve `A x = b` in the least-squares sense via the normal equations.
///
/// Deliberately not the same algorithm numpy uses. Six parameters against
/// twenty-three well-spread patches is comfortably conditioned, and using an
/// independent method is the point: if both implementations land on the same
/// transform, that is evidence about the *problem*, not about a shared library.
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
      ata[i][j] = s;
    }
    for (var j = 0; j < m; j++) {
      var s = 0.0;
      for (var k = 0; k < rows; k++) {
        s += a[k][i] * b[k][j];
      }
      atb[i][j] = s;
    }
  }

  // Gauss-Jordan with partial pivoting on [AtA | Atb].
  for (var col = 0; col < n; col++) {
    var pivot = col;
    for (var r = col + 1; r < n; r++) {
      if (ata[r][col].abs() > ata[pivot][col].abs()) pivot = r;
    }
    if (ata[pivot][col].abs() < 1e-14) {
      throw StateError('the transform is singular — the card patches do not span '
          'enough of the space to solve it');
    }
    if (pivot != col) {
      final t1 = ata[col]; ata[col] = ata[pivot]; ata[pivot] = t1;
      final t2 = atb[col]; atb[col] = atb[pivot]; atb[pivot] = t2;
    }
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

class RootPolynomial {
  final List<List<double>> matrix; // 6 x 3
  final double residualDeltaE;
  final double maxDeltaE;

  /// CIEDE2000 per fitted patch. Kept, not discarded: the mean says the fit
  /// failed, only the spread says why, and an operator holding a refusal with
  /// one number has nothing to act on.
  final List<double> perPatchDeltaE;

  RootPolynomial(this.matrix, this.residualDeltaE, this.maxDeltaE,
      [this.perPatchDeltaE = const []]);

  /// Solve the transform. [deviceRgb] is linear RGB in [0, 1].
  factory RootPolynomial.fit(List<List<double>> deviceRgb, List<List<double>> referenceXyz) {
    if (deviceRgb.length != referenceXyz.length) {
      throw ArgumentError('need one reference XYZ per measured patch');
    }
    if (deviceRgb.length < 6) {
      throw ArgumentError('need at least 6 patches to solve a 6-term transform');
    }
    final a = deviceRgb.map(rootPoly).toList();
    final m = _lstsq(a, referenceXyz);

    var sum = 0.0, worst = 0.0;
    final per = <double>[];
    for (var i = 0; i < a.length; i++) {
      final pred = List<double>.filled(3, 0);
      for (var j = 0; j < 3; j++) {
        for (var k = 0; k < 6; k++) {
          pred[j] += a[i][k] * m[k][j];
        }
      }
      final de = deltaE2000(xyzToLab(pred), xyzToLab(referenceXyz[i]));
      sum += de;
      per.add(de);
      if (de > worst) worst = de;
    }
    return RootPolynomial(m, sum / a.length, worst, per);
  }

  List<double> toLab(List<double> deviceRgb) {
    final p = rootPoly(deviceRgb);
    final xyz = List<double>.filled(3, 0);
    for (var j = 0; j < 3; j++) {
      for (var k = 0; k < 6; k++) {
        xyz[j] += p[k] * matrix[k][j];
      }
    }
    return xyzToLab(xyz);
  }

  bool passes([double limitDeltaE = 3.0]) => residualDeltaE <= limitDeltaE;

  /// Name the most likely cause of a failed fit, from the shape of the error.
  ///
  /// Mirrors `RootPolynomial.diagnose` in the Python. A refusal carrying one
  /// number sends the operator back to retake the same frame in the same
  /// conditions and get the same number; the card spans dark to light and
  /// neutral to saturated, so the pattern of error across it is diagnostic.
  ///
  /// A hint, and worded as one. It never enters a sealed record — a guess about
  /// somebody's lighting is not evidence.
  String diagnose(List<List<double>> referenceXyz) {
    final de = List<double>.from(perPatchDeltaE);
    if (de.length < 6 || de.length != referenceXyz.length) {
      return 'too few patches to say why.';
    }

    final sorted = List<double>.from(de)..sort();
    double median(List<double> v) {
      final n = v.length;
      return n.isOdd ? v[n ~/ 2] : (v[n ~/ 2 - 1] + v[n ~/ 2]) / 2;
    }

    final med = median(sorted);
    final devs = de.map((d) => (d - med).abs()).toList()..sort();
    final mad = median(devs) == 0 ? 1e-9 : median(devs);
    final lo = sorted.first, hi = sorted.last;

    // A minority of patches, each far outside the rest of the distribution.
    // Fraction-based: a glare spot lands on however many patches it covers.
    var nOut = 0;
    for (final d in de) {
      if (0.6745 * (d - med) / mad > 6) nOut++;
    }
    final cap = de.length ~/ 4 < 2 ? 2 : de.length ~/ 4;
    if (nOut > 0 && nOut <= cap && hi > 2.5 * med) {
      return '$nOut of ${de.length} patches are far worse than the rest '
          '(worst ${hi.toStringAsFixed(1)} dE against a typical '
          '${med.toStringAsFixed(1)}) — that is something on the card, not the '
          'light: a glare spot, a reflection, or an object resting on it.';
    }

    final lab = referenceXyz.map(xyzToLab).toList();
    final light = lab.map((l) => l[0]).toList();
    final chroma =
        lab.map((l) => math.sqrt(l[1] * l[1] + l[2] * l[2])).toList();

    double corr(List<double> x) {
      final n = x.length;
      final mx = x.reduce((a, b) => a + b) / n;
      final my = de.reduce((a, b) => a + b) / n;
      var sxy = 0.0, sxx = 0.0, syy = 0.0;
      for (var i = 0; i < n; i++) {
        final dx = x[i] - mx, dy = de[i] - my;
        sxy += dx * dy;
        sxx += dx * dx;
        syy += dy * dy;
      }
      if (sxx < 1e-12 || syy < 1e-12) return 0;
      return sxy / math.sqrt(sxx * syy);
    }

    final rLight = corr(light), rChroma = corr(chroma);

    if (rLight < -0.5 && rLight.abs() > rChroma.abs()) {
      return 'the error grows as the patches get darker '
          '(r=${rLight.toStringAsFixed(2)}) — light is being added on top of the '
          'card. A reflection on a glossy surface, or the black level of a screen '
          'if the card is displayed rather than printed.';
    }
    if (rChroma > 0.5 && rChroma.abs() > rLight.abs()) {
      return 'the error grows with how saturated the patch is '
          '(r=${rChroma.toStringAsFixed(2)}) — the colours are being stretched. '
          'A wide-gamut or "vivid" display, or colour management left on when '
          'the card was printed.';
    }
    if (hi - lo < (med > 3.0 ? med : 3.0)) {
      return 'every patch is wrong by about the same amount '
          '(${lo.toStringAsFixed(1)}-${hi.toStringAsFixed(1)} dE) — that is the '
          "light's spectrum, not its evenness. A low-CRI bulb, or two different "
          'lights on one card. Daylight or a high-CRI lamp is the fix.';
    }
    return 'the error is spread unevenly across the card '
        '(${lo.toStringAsFixed(1)}-${hi.toStringAsFixed(1)} dE) with no clear '
        'pattern by lightness or saturation. Check for a reflection, and retake '
        'in daylight before looking further.';
  }
}

// --------------------------------------------------------------------------- //
// L2 — conformal abstention
// --------------------------------------------------------------------------- //

class Prediction {
  final List<String> predictionSet;
  final String? label;
  final double alpha;
  final Map<String, double> scores;
  final double threshold;

  Prediction(this.predictionSet, this.label, this.alpha, this.scores, this.threshold);

  bool get inconclusive => label == null;

  String get reason {
    if (label != null) {
      return 'single label within threshold ${threshold.toStringAsFixed(2)}';
    }
    if (predictionSet.isEmpty) {
      return 'no reference locus within ${threshold.toStringAsFixed(2)} dE — the '
          'measurement resembles nothing this reagent is calibrated for';
    }
    return '${predictionSet.length} labels within ${threshold.toStringAsFixed(2)} dE — '
        'the measurement does not separate them at this risk level';
  }
}

/// Distance to reference loci in Lab, with a calibrated abstention threshold.
///
/// At risk level alpha, on exchangeable data, the true label is in the returned
/// set at least 1-alpha of the time. That sentence survives cross-examination;
/// "the model was 87% confident" does not.
class ConformalClassifier {
  final Map<String, List<double>> loci;
  final double alpha;
  double? threshold;
  int nCalibration = 0;

  ConformalClassifier(this.loci, {this.alpha = 0.05}) {
    if (alpha <= 0 || alpha >= 1) throw ArgumentError('alpha must be in (0, 1)');
  }

  double _score(List<double> lab, String label) => deltaE2000(lab, loci[label]!);

  /// Set the threshold from a held-out split.
  ///
  /// The quantile index is the finite-sample conformal correction: with n
  /// calibration points the threshold is the ceil((n+1)(1-alpha))-th smallest
  /// score, not the empirical (1-alpha) quantile. Getting this wrong loses the
  /// guarantee quietly.
  double calibrate(List<List<double>> labs, List<String> labels) {
    if (labs.length != labels.length) {
      throw ArgumentError('need one label per calibration measurement');
    }
    final n = labels.length;
    final need = (1 / alpha).ceil() - 1;
    if (n < need) {
      throw ArgumentError('alpha=$alpha needs at least $need calibration points '
          'for a finite-sample guarantee; got $n');
    }
    final scores = List<double>.generate(n, (i) => _score(labs[i], labels[i]))..sort();
    final k = ((n + 1) * (1 - alpha)).ceil();
    threshold = scores[math.min(k, n) - 1];
    nCalibration = n;
    return threshold!;
  }

  Prediction predict(List<double> lab) {
    final t = threshold;
    if (t == null) {
      throw StateError('classifier is not calibrated; call calibrate() first');
    }
    final scores = <String, double>{};
    for (final k in loci.keys) {
      scores[k] = _score(lab, k);
    }
    final set = scores.keys.where((k) => scores[k]! <= t).toList()..sort();
    return Prediction(set, set.length == 1 ? set.first : null, alpha, scores, t);
  }
}
