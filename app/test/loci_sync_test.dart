/// One ladder, two implementations.
///
/// The loci were duplicated across `measure_bridge.dart`, `core/demo.py`,
/// `core/tools/make_dataset.py` and a now-deleted `measure_server.py`. Four
/// copies of a number that decides what a field test reports is four chances
/// for the app and the reference implementation to disagree about what a colour
/// means — and the disagreement would show up as a wrong classification, not as
/// a crash.
///
/// `core/ftr/data/surrogate_loci.json` is the source. This fails if the app
/// drifts from it, the same way `schedule_sync_test.dart` guards the §63
/// Schedule.
library;

import 'dart:convert';
import 'dart:io';

import 'package:flutter_test/flutter_test.dart';
import 'package:field_companion/src/measure_bridge.dart';

void main() {
  final source = File('../core/ftr/data/surrogate_loci.json');

  test('the app ladder matches the one in core/ftr/data', () {
    expect(source.existsSync(), isTrue, reason: 'source of truth moved');
    final want = (jsonDecode(source.readAsStringSync())
        as Map<String, dynamic>)['loci_lab'] as Map<String, dynamic>;

    expect(referenceLoci.keys.toSet(), want.keys.toSet());
    for (final k in want.keys) {
      final a = (want[k] as List).map((v) => (v as num).toDouble()).toList();
      expect(referenceLoci[k], a, reason: 'locus $k has drifted');
    }
  });

  test('the negative locus is still the measured substrate, not a guess', () {
    // Regression: it was 80.1 while the real card measures 95.5, which put a
    // dry well outside its own threshold and reported a blank card as
    // inconclusive.
    expect(referenceLoci['negative']![0], greaterThan(90.0));
  });
}
