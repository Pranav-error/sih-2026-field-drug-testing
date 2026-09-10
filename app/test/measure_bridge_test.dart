/// The surrogate colour ladder must actually be usable.
///
/// Two rungs closer together than the abstention threshold make a single label
/// arithmetically impossible: every reading near either falls inside both, and
/// the classifier — correctly — returns two labels forever. That is what put
/// "inconclusive" on the screen every single time, and it looked like a broken
/// scanner rather than a ladder that cannot separate.
library;

import 'package:flutter_test/flutter_test.dart';
import 'package:ftr_verify/ftr_verify.dart' as ftr;
import 'package:field_companion/src/measure_bridge.dart';

void main() {
  final m = OnDeviceMeasurer();
  final loci = referenceLoci;

  test('every pair of loci is more than twice the threshold apart', () {
    final t = m.threshold;
    expect(t, greaterThan(0));

    final keys = loci.keys.toList();
    var worst = double.infinity;
    String worstPair = '';
    for (var i = 0; i < keys.length; i++) {
      for (var j = i + 1; j < keys.length; j++) {
        final d = ftr.deltaE2000(loci[keys[i]]!, loci[keys[j]]!);
        if (d < worst) {
          worst = d;
          worstPair = '${keys[i]} <-> ${keys[j]}';
        }
      }
    }
    expect(worst, greaterThan(2 * t),
        reason: 'closest pair $worstPair is ${worst.toStringAsFixed(2)} apart, '
            'threshold ${t.toStringAsFixed(2)} — a reading near either falls '
            'inside both and no single label is possible');
  });

  test('a reading at any locus returns that label and no other', () {
    for (final e in loci.entries) {
      final p = m.classify(e.value);
      expect(p.predictionSet, [e.key],
          reason: 'a dead-centre reading of ${e.key} must not be ambiguous');
      expect(p.label, e.key);
    }
  });

  test('the negative locus is the card substrate that was actually measured',
      () {
    // test/fixtures/real_card.jpg, empty well: Lab* [95.52, 0.001, 0.009].
    // The old value of L=80.1 was a guess, and it put a dry well 11.25 from its
    // own class — outside the threshold — so a blank card returned an empty
    // prediction set and was reported as inconclusive.
    final p = m.classify([95.52, 0.0012, 0.0086]);
    expect(p.predictionSet, ['negative'],
        reason: 'an empty well on the real printed card must read negative');
  });
}
