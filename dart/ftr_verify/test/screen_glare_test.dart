/// A real frame from a real handset, and the diagnosis it must produce.
///
/// `screen_glare.jpg` is an actual capture from a OnePlus CPH2585 photographing
/// the reference card displayed in Preview on a glossy MacBook screen at night.
/// It refused at 7.5 dE, and three separate theories about why — low-CRI
/// lighting, wide-gamut P3, print colour management — were all wrong. None of
/// them reproduced in simulation either.
///
/// The frame settles it. The pattern across the card is unambiguous:
///
///   neutral patches      median 2.6 dE   fine
///   coloured patches     median 9.4 dE   not fine
///   among the coloured   r(lightness) = -0.63   darker is worse
///
/// That is grey light added on top. It desaturates a dark colour, which a
/// root-polynomial with no constant term cannot undo, while leaving a dark
/// neutral merely brighter, which the per-channel gain absorbs. Veiling glare
/// on the glass, plus the screen's own black level.
library;

import 'dart:io';

import 'package:image/image.dart' as img;
import 'package:ftr_verify/ftr_verify.dart';
import 'package:test/test.dart';

void main() {
  late DeviceMeasurement m;

  setUpAll(() {
    var im = img.decodeImage(
        File('test/fixtures/screen_glare.jpg').readAsBytesSync())!;
    if (im.width > 1200) {
      im = img.copyResize(im,
          width: 1200, interpolation: img.Interpolation.average);
    }
    m = measureOnDevice(im);
  });

  test('the card is found and the frame is otherwise good', () {
    // This is the part that made the failure confusing: geometry, focus,
    // exposure and illumination evenness are all fine. Only colour is wrong.
    expect(m.detected, isTrue);
    expect(m.quality!.fiducials, 4);
    expect(m.quality!.clipped, lessThan(0.01));
    expect(m.quality!.lightFieldStops, lessThan(0.4));
  });

  test('it is refused, and never mismeasured', () {
    expect(m.prediction, isNull, reason: 'no reading may be reported');
    expect(m.cardResidual, greaterThan(3.0));
    expect(m.refusals.any((r) => r.contains('did not reproduce')), isTrue);
  });

  test('the diagnosis names grey light added on top', () {
    final why = m.refusals.firstWhere((r) => r.startsWith('likely cause'));
    expect(why, contains('neutral patches are fine'));
    expect(why, contains('darker ones are worst'));
    expect(why, contains('grey light added on top'));
    // And says what to do about it.
    expect(why, anyOf(contains('reflection'), contains('print the card')));
  });

  test('it does not fall through to the "no clear pattern" branch', () {
    // The branch this frame originally hit, because the global lightness
    // correlation was -0.47 — diluted by the neutrals, which were fine.
    final why = m.refusals.firstWhere((r) => r.startsWith('likely cause'));
    expect(why, isNot(contains('no clear pattern')));
  });
}
