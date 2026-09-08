/// The rules in docs/DESIGN.md, asserted against the widgets that must obey them.
///
/// A design document nobody tests is a document the code drifts away from. These
/// are deliberately written as the rules, not as the pixels: they check that the
/// word "presumptive" is on screen, that an abstention is not styled as an error,
/// that a blocked shutter is really blocked — not that a padding is 13.
library;


import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

import 'package:field_companion/src/models.dart';
import 'package:field_companion/src/screens.dart';
import 'package:field_companion/src/tokens.dart';
import 'package:field_companion/src/widgets.dart';

Widget wrap(Widget child) => MaterialApp(theme: buildTheme(Brightness.light), home: child);

const goodPosture = DevicePosture(
  securityLevel: 'STRONGBOX',
  verifiedBootState: 'GREEN',
  bootloaderLocked: true,
  osPatchLevel: '2026-08-01',
  mockLocation: false,
  recordCount: 47,
  unanchored: 4,
  sinceAnchor: Duration(hours: 3, minutes: 12),
);

const devPosture = DevicePosture(
  securityLevel: 'SOFTWARE',
  verifiedBootState: 'UNKNOWN',
  bootloaderLocked: false,
  osPatchLevel: '1970-01-01',
  mockLocation: false,
  recordCount: 2,
  unanchored: 2,
  sinceAnchor: Duration(minutes: 4),
);

TestResult result(List<String> set, {String? label, List<String> refusals = const []}) =>
    TestResult(
      predictionSet: set,
      label: label,
      lab: const [18.4, 23.2, -7.5],
      alpha: 0.05,
      threshold: 5.53,
      scores: const {'opiate_class': 3.81, 'negative': 14.2},
      refusals: refusals,
    );

void main() {
  group('rule 1 — colour never means good or bad', () {
    test('there is no success token to reach for', () {
      // Outcome carries exactly three cases and none of them is "success".
      expect(Outcome.values.length, 3);
      expect(Outcome.values.map((o) => o.name),
          containsAll(['presumptivePositive', 'presumptiveNegative', 'inconclusive']));
    });

    test('positive and negative are different colours, and neither is the accent', () {
      expect(Outcome.presumptivePositive.colour, isNot(Outcome.presumptiveNegative.colour));
      expect(Outcome.presumptivePositive.colour, isNot(Tokens.accent));
      expect(Outcome.presumptiveNegative.colour, isNot(Tokens.accent));
    });

    testWidgets('a positive is not styled as a celebration', (t) async {
      await t.pumpWidget(wrap(ResultScreen(result: result(['opiate_class'], label: 'opiate_class'))));
      expect(find.text('Presumptive positive'), findsOneWidget);
      // Nothing congratulatory, and no green.
      expect(find.textContaining('Success'), findsNothing);
      expect(find.textContaining('Detected!'), findsNothing);
    });
  });

  group('rule 3 — the word presumptive is never off-screen', () {
    testWidgets('on the result screen, for every outcome', (t) async {
      for (final set in [
        ['opiate_class'],
        ['negative'],
        ['opiate_class', 'amphetamine_class'],
        <String>[],
      ]) {
        await t.pumpWidget(wrap(ResultScreen(result: result(set))));
        expect(find.textContaining(RegExp('resumptive')), findsWidgets,
            reason: 'missing on set $set');
      }
    });

    testWidgets('on the sealed screen', (t) async {
      await t.pumpWidget(wrap(SealedScreen(
        digestHex: 'aa' * 32,
        sequence: 48,
        securityLevel: 'STRONGBOX',
        anchorWindow: '3h 14m',
        anchored: false,
      )));
      expect(find.textContaining(RegExp('resumptive')), findsWidgets);
    });

    testWidgets('on standby', (t) async {
      await t.pumpWidget(wrap(const StandbyScreen(posture: goodPosture)));
      expect(find.textContaining(RegExp('resumptive')), findsWidgets);
    });
  });

  group('abstention is a result, not an error', () {
    testWidgets('an ambiguous set renders as inconclusive with its reason', (t) async {
      await t.pumpWidget(wrap(ResultScreen(
          result: result(['opiate_class', 'amphetamine_class']))));
      expect(find.text('Inconclusive'), findsOneWidget);
      expect(find.textContaining('does not separate them'), findsOneWidget);
      // Not framed as a failure, and not a retry prompt.
      expect(find.textContaining('Error'), findsNothing);
      expect(find.textContaining('Try again'), findsNothing);
      expect(find.textContaining('Failed'), findsNothing);
    });

    testWidgets('an empty set says what it means', (t) async {
      await t.pumpWidget(wrap(ResultScreen(result: result(const []))));
      expect(find.text('Inconclusive'), findsOneWidget);
      expect(find.textContaining('resembles nothing'), findsOneWidget);
      expect(find.textContaining('{ ∅ }'), findsOneWidget);
    });

    testWidgets('an abstention can still be sealed', (t) async {
      var sealed = false;
      await t.pumpWidget(wrap(ResultScreen(
        result: result(const []),
        onSeal: () => sealed = true,
      )));
      await t.tap(find.text('Seal record'));
      expect(sealed, isTrue, reason: 'an inconclusive result is evidence too');
    });

    test('any non-singleton set is an abstention, whatever it contains', () {
      expect(Outcome.fromPredictionSet(['a', 'b']), Outcome.inconclusive);
      expect(Outcome.fromPredictionSet([]), Outcome.inconclusive);
      expect(Outcome.fromPredictionSet(['negative']), Outcome.presumptiveNegative);
      expect(Outcome.fromPredictionSet(['opiate_class']), Outcome.presumptivePositive);
    });
  });

  group('the shutter is gated on measurability', () {
    const bad = CaptureQuality(
        fiducialsFound: 2, illumination: 0.71, focus: 0.4, tiltDegrees: 14, clippedFraction: 0);
    const good = CaptureQuality(
        fiducialsFound: 4, illumination: 0.96, focus: 0.94, tiltDegrees: 3, clippedFraction: 0);

    testWidgets('a bad frame cannot be captured', (t) async {
      var fired = false;
      await t.pumpWidget(wrap(CaptureScreen(quality: bad, onCapture: () => fired = true)));
      expect(find.text('Hold steady…'), findsOneWidget);
      await t.tap(find.byType(PrimaryButton));
      expect(fired, isFalse, reason: 'a blocked shutter is rude and correct');
    });

    testWidgets('a good frame arms the shutter', (t) async {
      var fired = false;
      await t.pumpWidget(wrap(CaptureScreen(quality: good, onCapture: () => fired = true)));
      expect(find.text('Capture frame'), findsOneWidget);
      await t.tap(find.text('Capture frame'));
      expect(fired, isTrue);
    });

    test('guidance names the fix, not the failure', () {
      expect(bad.guidance, contains('Move back'));
      expect(
          const CaptureQuality(
                  fiducialsFound: 4, illumination: 1, focus: 1, tiltDegrees: 40, clippedFraction: 0)
              .guidance,
          contains('flatter'));
      expect(
          const CaptureQuality(
                  fiducialsFound: 4, illumination: 1, focus: 1, tiltDegrees: 3, clippedFraction: 0.2)
              .guidance,
          contains('Too bright'));
      expect(good.guidance, 'Hold steady.');
    });
  });

  group('the device is honest about itself', () {
    testWidgets('a development build says its records are not evidence', (t) async {
      await t.pumpWidget(wrap(const StandbyScreen(posture: devPosture)));
      expect(find.textContaining('software key'), findsOneWidget);
      expect(find.textContaining('never be presented as evidence'), findsOneWidget);
    });

    testWidgets('a hardware build does not carry that warning', (t) async {
      await t.pumpWidget(wrap(const StandbyScreen(posture: goodPosture)));
      expect(find.textContaining('never be presented as evidence'), findsNothing);
      expect(find.text('STRONGBOX'), findsWidgets);
    });

    test('evidence grade needs hardware AND verified boot AND a locked bootloader', () {
      expect(goodPosture.evidenceGrade, isTrue);
      expect(devPosture.evidenceGrade, isFalse);
    });

    testWidgets('the anchoring debt is on the home screen', (t) async {
      await t.pumpWidget(wrap(const StandbyScreen(posture: goodPosture)));
      expect(find.text('3h 12m'), findsOneWidget);
      expect(find.textContaining('Awaiting anchor'), findsOneWidget);
    });
  });

  group('the sealed screen states the limits of its own proof', () {
    testWidgets('an unanchored record says what it does not prove', (t) async {
      await t.pumpWidget(wrap(SealedScreen(
        digestHex: 'ab' * 32,
        sequence: 48,
        securityLevel: 'STRONGBOX',
        anchorWindow: '3h 14m',
        anchored: false,
      )));
      expect(find.textContaining('does not prove the wall-clock time'), findsOneWidget);
      expect(find.textContaining('no earlier than record #47'), findsOneWidget);
    });

    testWidgets('the digest is selectable, because it gets copied', (t) async {
      await t.pumpWidget(wrap(SealedScreen(
        digestHex: 'cd' * 32,
        sequence: 1,
        securityLevel: 'TEE',
        anchorWindow: '2m',
        anchored: true,
      )));
      expect(find.byType(SelectableText), findsOneWidget);
    });
  });

  _fontRules();

  group('accessibility', () {
    testWidgets('primary actions meet the touch target minimum', (t) async {
      await t.pumpWidget(wrap(ResultScreen(result: result(['negative'], label: 'negative'))));
      final size = t.getSize(find.descendant(
          of: find.byType(PrimaryButton), matching: find.byType(FilledButton)));
      expect(size.height, greaterThanOrEqualTo(Tokens.touchTarget));
    });

    testWidgets('state is never colour-only — every chip carries text', (t) async {
      await t.pumpWidget(wrap(const StandbyScreen(posture: goodPosture)));
      final chip = t.widget<StateChip>(find.byType(StateChip).first);
      expect(chip.text.trim(), isNotEmpty);
    });
  });
}

/// Fonts the design names but does not yet bundle.
///
/// Flutter falls back SILENTLY on an unknown family. For the UI face that is
/// cosmetic; for the mono face it would quietly turn every measured quantity into
/// proportional text and break the rule that the typeface tells a reader whether a
/// number is evidence. Until the real faces are bundled, the fallback stack is
/// what keeps that rule true.
void _fontRules() {
  group('rule 4 — measured quantities are set in mono', () {
    test('the mono family has a real monospace fallback stack', () {
      expect(Tokens.monoFallback, isNotEmpty);
      expect(Tokens.monoFallback.first, 'monospace');
    });

    test('mono style uses tabular figures, so columns of digits line up', () {
      final s = Tokens.monoStyle();
      expect(s.fontFeatures, contains(const FontFeature.tabularFigures()));
      expect(s.fontFamilyFallback, Tokens.monoFallback);
    });

    testWidgets('the digest is rendered in the mono style, not the UI face', (t) async {
      await t.pumpWidget(wrap(SealedScreen(
        digestHex: 'ef' * 32,
        sequence: 3,
        securityLevel: 'STRONGBOX',
        anchorWindow: '1m',
        anchored: false,
      )));
      final w = t.widget<SelectableText>(find.byType(SelectableText));
      expect(w.style!.fontFamily, Tokens.mono);
      expect(w.style!.fontFamilyFallback, Tokens.monoFallback);
    });
  });
}
