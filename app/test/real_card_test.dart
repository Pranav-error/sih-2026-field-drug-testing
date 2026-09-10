/// The whole pipeline, on a photograph of the real printed card.
///
/// Every other test in this app runs on synthetic input. This one runs on the
/// frame an officer's phone actually produced, which is where the last three
/// defects were found — a ×255 in the sharpness normalisation, a keystore
/// digest mismatch, and a reference locus set 15 ΔE away from the card's own
/// substrate.
library;

import 'dart:io';

import 'package:flutter_test/flutter_test.dart';
import 'package:image/image.dart' as img;
import 'package:field_companion/src/measure_bridge.dart';

void main() {
  final file = File('../dart/ftr_verify/test/fixtures/real_card.jpg');

  test('the real card is detected, passes the gate, and yields ONE label', () {
    expect(file.existsSync(), isTrue, reason: 'fixture moved');
    var im = img.decodeImage(file.readAsBytesSync())!;
    if (im.width > 1200) {
      im = img.copyResize(im, width: 1200, interpolation: img.Interpolation.average);
    }

    final m = OnDeviceMeasurer().measure(
      img.encodeJpg(im, quality: 92),
    );

    expect(m, isNotNull);
    expect(m!.detected, isTrue, reason: m.guidance);
    expect(m.gatePassed, isTrue, reason: m.refusals.join('; '));
    expect(m.refusals, isEmpty);

    // The bug this pins: result was null here, main.dart substituted a
    // hardcoded constant, and the operator saw a plausible "inconclusive"
    // reading on every single capture with no way to tell it apart from a
    // working one.
    expect(m.result, isNotNull,
        reason: 'a card that detects and passes the gate must produce a result');

    // An empty well is a NEGATIVE presumptive test, and that is a successful
    // outcome, not an inconclusive one.
    expect(m.result!.predictionSet, ['negative']);
    expect(m.result!.label, 'negative');
    expect(m.result!.outcome.name, isNot(contains('inconclusive')));
  });
}
