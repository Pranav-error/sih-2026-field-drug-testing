/// The Dart diagnosis must reach the same conclusion as the Python one.
///
/// Two implementations that agree on a verdict but disagree on the advice would
/// send an operator and a reviewer in different directions from the same frame.
library;

import 'dart:math' as math;

import 'package:ftr_verify/ftr_verify.dart';
import 'package:test/test.dart';

/// Reference XYZ spanning dark to light and neutral to saturated, like the card.
List<List<double>> _reference() {
  final labs = <List<double>>[
    [8, 0, 0], [20, 2, -1], [35, 0, 1], [50, -1, 0], [65, 1, 1],
    [80, 0, -1], [95, 0, 0], [18, 24, -8], [26, 25, 5], [33, 46, -28],
    [40, 14, 26], [49, 50, 12], [55, -30, 20], [30, 18, -22],
  ];
  return labs.map(_labToXyz).toList();
}

/// Local, because the library has no Lab->XYZ: the verifier only ever goes the
/// other way. Adding one to the package for a test's convenience would be
/// widening the public surface to suit a test.
List<double> _labToXyz(List<double> lab) {
  const white = [95.047, 100.0, 108.883];
  final fy = (lab[0] + 16) / 116;
  final f = [fy + lab[1] / 500, fy, fy - lab[2] / 200];
  const d = 6.0 / 29.0;
  return List<double>.generate(3, (i) {
    final t = f[i] > d ? f[i] * f[i] * f[i] : 3 * d * d * (f[i] - 4 / 29);
    return t * white[i];
  });
}

RootPolynomial _with(List<double> err) {
  final n = err.length;
  return RootPolynomial(
    List.generate(6, (_) => List<double>.filled(3, 0)),
    err.reduce((a, b) => a + b) / n,
    err.reduce(math.max),
    err,
  );
}

void main() {
  final ref = _reference();
  final lab = ref.map(xyzToLab).toList();

  test('a few wild patches read as something on the card', () {
    final err = List<double>.filled(ref.length, 2.0);
    err[3] = 46;
    err[7] = 40;
    err[11] = 47;
    final d = _with(err).diagnose(ref);
    expect(d, contains('something on the card'));
    expect(d, contains('glare'));
  });

  test('error rising as patches darken reads as added light', () {
    final err = lab.map((l) => 14.0 - 0.14 * l[0]).toList();
    final d = _with(err).diagnose(ref);
    expect(d, contains('darker'));
    expect(d, anyOf(contains('black level'), contains('reflection')));
  });

  test('error rising with saturation reads as a stretched gamut', () {
    final err = lab
        .map((l) => 2.0 + 0.22 * math.sqrt(l[1] * l[1] + l[2] * l[2]))
        .toList();
    final d = _with(err).diagnose(ref);
    expect(d, contains('saturated'));
    expect(d, anyOf(contains('gamut'), contains('vivid')));
  });

  test('flat error reads as the illuminant', () {
    final r = math.Random(3);
    final err =
        List<double>.generate(ref.length, (_) => 9.0 + (r.nextDouble() - .5) * .5);
    final d = _with(err).diagnose(ref);
    expect(d, contains('same amount'));
    expect(d, contains('CRI'));
  });

  test('an unreadable pattern admits it rather than guessing', () {
    final r = math.Random(5);
    final err =
        List<double>.generate(ref.length, (_) => 0.5 + r.nextDouble() * 9.5);
    expect(_with(err).diagnose(ref), contains('no clear pattern'));
  });

  test('too few patches says so', () {
    expect(_with([1, 2, 3]).diagnose(ref.sublist(0, 3)),
        contains('too few patches'));
  });
}
