/// How closely do the two measurement implementations actually agree?
///
/// ARCHITECTURE.md §9 asks the verifier to re-run L1/L2 and check the stored
/// classification "reproduces bit-for-bit". Two languages, two least-squares
/// algorithms and two libm implementations will not do that on floating point.
/// So this test *measures* the divergence and asserts a bound, and the bound is
/// what the record and the certificate are allowed to claim.
///
/// It also checks both implementations against the published CIEDE2000
/// conformance data, because two implementations can agree on the same mistake.
library;

import 'dart:convert';
import 'dart:io';

import 'package:ftr_verify/src/colorimetry.dart';
import 'package:test/test.dart';

late Map<String, dynamic> v;

List<double> dl(dynamic x) => (x as List).map((e) => (e as num).toDouble()).toList();

void main() {
  v = jsonDecode(File('test/vectors/colorimetry.json').readAsStringSync())
      as Map<String, dynamic>;

  group('CIEDE2000 against the published conformance data', () {
    final cases = (v['ciede2000_sharma'] as List).cast<Map<String, dynamic>>();
    for (final (i, c) in cases.indexed) {
      test('Sharma case ${i + 1}', () {
        final got = deltaE2000(dl(c['lab1']), dl(c['lab2']));
        expect(got, closeTo(c['expected'] as double, 1e-4),
            reason: 'Dart must match the standard, not merely the Python');
        expect(got, closeTo(c['ours'] as double, 1e-9),
            reason: 'and it must match the Python too');
      });
    }
  });

  group('sRGB to CIELAB', () {
    test('all cases agree to 1e-9', () {
      var worst = 0.0;
      for (final c in (v['lab_from_srgb'] as List).cast<Map<String, dynamic>>()) {
        final srgb = dl(c['srgb']);
        final lin = srgb.map(srgbToLinear).toList();
        final xyz = List<double>.generate(3, (i) {
          var s = 0.0;
          for (var j = 0; j < 3; j++) {
            s += srgbToXyzD65[i][j] * lin[j];
          }
          return s;
        });
        final lab = xyzToLab(xyz);
        final want = dl(c['lab']);
        for (var i = 0; i < 3; i++) {
          final d = (lab[i] - want[i]).abs();
          if (d > worst) worst = d;
        }
      }
      printOnFailure('worst Lab divergence: $worst');
      expect(worst, lessThan(1e-9));
    });
  });

  group('the device transform, solved by a different algorithm', () {
    // Python uses numpy's SVD-based lstsq; this package solves the normal
    // equations with partial pivoting. Agreement here is evidence about the
    // problem being well conditioned, not about a shared library.
    late RootPolynomial fitted;
    late Map<String, dynamic> t;

    setUp(() {
      t = v['transform'] as Map<String, dynamic>;
      fitted = RootPolynomial.fit(
        (t['device_rgb'] as List).map(dl).toList(),
        (t['reference_xyz'] as List).map(dl).toList(),
      );
    });

    test('recovers the same matrix to 1e-6', () {
      final want = (t['matrix'] as List).map(dl).toList();
      var worst = 0.0;
      for (var i = 0; i < want.length; i++) {
        for (var j = 0; j < 3; j++) {
          final d = (fitted.matrix[i][j] - want[i][j]).abs();
          if (d > worst) worst = d;
        }
      }
      printOnFailure('worst matrix coefficient divergence: $worst');
      expect(worst, lessThan(1e-6));
    });

    test('reports the same residual, which is what the quality gate uses', () {
      expect(fitted.residualDeltaE, closeTo(t['residual_delta_e'] as double, 1e-9));
      expect(fitted.maxDeltaE, closeTo(t['max_delta_e'] as double, 1e-9));
    });

    test('maps probe colours to the same Lab within 1e-6 dE', () {
      var worst = 0.0;
      for (final p in (t['probes'] as List).cast<Map<String, dynamic>>()) {
        final got = fitted.toLab(dl(p['rgb']));
        final de = deltaE2000(got, dl(p['lab']));
        if (de > worst) worst = de;
      }
      printOnFailure('worst probe divergence: $worst dE2000');
      expect(worst, lessThan(1e-6));
    });
  });

  group('conformal abstention', () {
    late ConformalClassifier clf;
    late Map<String, dynamic> c;

    setUp(() {
      c = v['conformal'] as Map<String, dynamic>;
      final loci = (c['loci'] as Map<String, dynamic>)
          .map((k, val) => MapEntry(k, dl(val)));
      clf = ConformalClassifier(loci, alpha: c['alpha'] as double);
      clf.calibrate(
        (c['calibration_labs'] as List).map(dl).toList(),
        (c['calibration_labels'] as List).cast<String>(),
      );
    });

    test('reaches the same threshold', () {
      expect(clf.threshold!, closeTo(c['threshold'] as double, 1e-9));
    });

    test('returns the same prediction set for every query', () {
      for (final q in (c['queries'] as List).cast<Map<String, dynamic>>()) {
        final p = clf.predict(dl(q['lab']));
        expect(p.predictionSet, equals((q['prediction_set'] as List).cast<String>()),
            reason: 'prediction sets must match exactly — this is the reported result');
        expect(p.label, equals(q['label']));
      }
    });

    test('covers both abstention modes, not just the confident case', () {
      final sets = (c['queries'] as List)
          .map((q) => ((q as Map)['prediction_set'] as List).length)
          .toList();
      expect(sets, contains(1), reason: 'a confident call');
      expect(sets.any((n) => n > 1), isTrue, reason: 'an ambiguous set');
      expect(sets, contains(0), reason: 'an empty set — resembles nothing calibrated');
    });
  });

  group('what the record may claim', () {
    test('scaled integers survive the divergence', () {
      // lab_x100 quantises to 0.01. If cross-implementation divergence stayed
      // well below half a quantum, the *stored integers* match exactly even
      // though the doubles behind them do not. That is the claim the record can
      // defend, and it is why every measured field is a scaled integer.
      final t = v['transform'] as Map<String, dynamic>;
      final fitted = RootPolynomial.fit(
        (t['device_rgb'] as List).map(dl).toList(),
        (t['reference_xyz'] as List).map(dl).toList(),
      );
      for (final p in (t['probes'] as List).cast<Map<String, dynamic>>()) {
        final got = fitted.toLab(dl(p['rgb']));
        final want = dl(p['lab']);
        for (var i = 0; i < 3; i++) {
          expect((got[i] * 100).round(), equals((want[i] * 100).round()),
              reason: 'lab_x100 must be identical across implementations');
        }
      }
    });
  });
}
