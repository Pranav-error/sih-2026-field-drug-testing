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
import 'package:field_companion/main.dart';
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
  lastAnchorAt: null,
);

/// What a genuine StrongBox handset actually reports: the key is in hardware,
/// and the boot state is deferred to the attestation certificate.
const realHandsetPosture = DevicePosture(
  securityLevel: 'STRONGBOX',
  verifiedBootState: 'IN ATTESTATION',
  bootloaderLocked: null,
  osPatchLevel: 'IN ATTESTATION',
  mockLocation: null,
  recordCount: 3,
  unanchored: 3,
  lastAnchorAt: null,
);

const devPosture = DevicePosture(
  securityLevel: 'SOFTWARE',
  verifiedBootState: 'UNKNOWN',
  bootloaderLocked: false,
  osPatchLevel: '1970-01-01',
  mockLocation: false,
  recordCount: 2,
  unanchored: 2,
  lastAnchorAt: null,
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
      // The app cannot establish boot state, so a real handset never reaches it.
      expect(realHandsetPosture.evidenceGrade, isFalse);
    });

    testWidgets('a StrongBox handset is NEVER told it uses a software key',
        (t) async {
      // The bug this pins: the warning keyed off evidenceGrade, which is false
      // on real hardware because verified boot reads IN ATTESTATION rather than
      // GREEN. A genuine StrongBox device was told its records were for
      // development only.
      await t.pumpWidget(wrap(const StandbyScreen(posture: realHandsetPosture)));
      expect(find.textContaining('software key'), findsNothing);
      expect(find.textContaining('never be presented as evidence'), findsNothing);
      expect(find.text('STRONGBOX'), findsWidgets);
      // What it says instead: where the answer actually lives.
      expect(find.textContaining('attestation certificate'), findsOneWidget);
    });

    testWidgets('standby names the card the operator entered, not a constant',
        (t) async {
      await t.pumpWidget(wrap(const StandbyScreen(
          posture: realHandsetPosture, cardId: 'CARD-IN-2026-0417')));
      expect(find.text('CARD-IN-2026-0417'), findsOneWidget);
    });

    testWidgets('with no card entered it says so rather than inventing one',
        (t) async {
      await t.pumpWidget(wrap(const StandbyScreen(posture: realHandsetPosture)));
      expect(find.text('Not set'), findsOneWidget);
    });

    testWidgets('an UNKNOWN security level is not announced as a software key',
        (t) async {
      // reportedLevel() returns UNKNOWN whenever the KeyInfo lookup throws — a
      // StrongBox key can land here. Calling that a development key is the same
      // false statement, one branch over.
      const unknown = DevicePosture(
        securityLevel: 'UNKNOWN',
        verifiedBootState: 'IN ATTESTATION',
        bootloaderLocked: null,
        osPatchLevel: 'IN ATTESTATION',
        mockLocation: null,
        recordCount: 0,
        unanchored: 0,
        lastAnchorAt: null,
      );
      expect(unknown.usesSoftwareKey, isFalse);
      expect(unknown.securityLevelUnknown, isTrue);
      await t.pumpWidget(wrap(const StandbyScreen(posture: unknown)));
      expect(find.textContaining('never be presented as evidence'), findsNothing);
      expect(find.textContaining('did not report what backs'), findsOneWidget);
    });

    testWidgets('a genuine software build is still warned about', (t) async {
      expect(devPosture.usesSoftwareKey, isTrue);
      await t.pumpWidget(wrap(const StandbyScreen(posture: devPosture)));
      expect(find.textContaining('never be presented as evidence'), findsOneWidget);
    });

    testWidgets('nothing unknown is rendered as a finding', (t) async {
      await t.pumpWidget(wrap(const StandbyScreen(posture: realHandsetPosture)));
      // "Off" would be a claim about a check that never ran.
      expect(find.text('Not checked yet'), findsOneWidget);
      expect(find.text('Off'), findsNothing);
      // The bootloader is not asserted LOCKED on the app's say-so.
      expect(find.text('LOCKED'), findsNothing);
    });

    testWidgets('the anchoring debt is on the home screen', (t) async {
      await t.pumpWidget(wrap(const StandbyScreen(posture: goodPosture)));
      expect(find.textContaining('Awaiting anchor'), findsOneWidget);
      // Never anchored must read as never anchored, not as a duration.
      expect(find.text('never anchored'), findsOneWidget);
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

    testWidgets('a record that failed to persist says why, not just that it did',
        (t) async {
      // "NO — memory only" with no cause is the same silence that let the seal
      // failure vanish for a build. An officer cannot act on it.
      await t.pumpWidget(wrap(SealedScreen(
        digestHex: 'ef' * 32,
        sequence: 3,
        securityLevel: 'STRONGBOX',
        anchorWindow: '1m',
        anchored: false,
        stored: false,
        storeError: 'FileSystemException: No space left on device',
      )));
      expect(find.textContaining('NO — memory only'), findsOneWidget);
      expect(find.textContaining('No space left on device'), findsOneWidget);
      expect(find.textContaining('not in the chain'), findsOneWidget);
    });

    testWidgets('a record that persisted carries no failure text', (t) async {
      await t.pumpWidget(wrap(SealedScreen(
        digestHex: 'ef' * 32,
        sequence: 3,
        securityLevel: 'STRONGBOX',
        anchorWindow: '1m',
        anchored: false,
        stored: true,
      )));
      expect(find.textContaining('not in the chain'), findsNothing);
    });

    testWidgets('the screen never claims a fingerprint that never happened',
        (t) async {
      // The record carries biometric_unlock_used: false — the key is created
      // without setUserAuthenticationRequired. The screen used to print
      // "Use authorised by: Fingerprint" directly above it.
      await t.pumpWidget(wrap(SealedScreen(
        digestHex: 'ab' * 32,
        sequence: 1,
        securityLevel: 'STRONGBOX',
        anchorWindow: '2m',
        anchored: false,
        stored: true,
      )));
      expect(find.textContaining('Fingerprint'), findsNothing);
      expect(find.text('Nothing'), findsOneWidget);
      expect(find.textContaining('not gated on user authentication'),
          findsOneWidget);
    });

    testWidgets('a frame-write failure does not read as a lost record',
        (t) async {
      // append() succeeded; only writeFrames() threw. Saying "NO — memory only"
      // here is wrong in the dangerous direction: an officer would re-run a
      // test that already sealed.
      await t.pumpWidget(wrap(SealedScreen(
        digestHex: 'ab' * 32,
        sequence: 1,
        securityLevel: 'STRONGBOX',
        anchorWindow: '2m',
        anchored: false,
        stored: true,
        frameError: 'FileSystemException: No space left on device',
      )));
      expect(find.textContaining('NO — memory only'), findsNothing);
      expect(find.textContaining('sealed and in the chain'), findsOneWidget);
      expect(find.text('NOT WRITTEN'), findsOneWidget);
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
  _responsiveRules();
  _livenessRules();

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


/// The two-frame capture, and rule 8: absent is never shown as passed.
///
/// The second-view screen is the one most likely to be cut by someone who does
/// not know why it exists. A quality print passes every colour check; what it
/// cannot fake is depth. See docs/PARALLAX.md.
void _livenessRules() {
  group('rule 8 — absent is never shown as passed', () {
    testWidgets('a record with no liveness check says NOT RUN, in the same place '
        'a result would appear', (t) async {
      await t.pumpWidget(wrap(ResultScreen(
        result: result(['opiate_class'], label: 'opiate_class'),
        liveness: const Liveness.notChecked(),
      )));
      expect(find.text('NOT RUN'), findsOneWidget);
      expect(find.textContaining('photograph of a card'), findsOneWidget);
    });

    testWidgets('a live capture shows the measurement AND what was predicted',
        (t) async {
      await t.pumpWidget(wrap(ResultScreen(
        result: result(['opiate_class'], label: 'opiate_class'),
        liveness: const Liveness(
            checked: true, live: true, measuredPx: 28.1, predictedPx: 28.2),
      )));
      // A reader shown only a verdict cannot check it; shown both, they can.
      expect(find.textContaining('28.1 px'), findsOneWidget);
      expect(find.textContaining('28.2 px predicted'), findsOneWidget);
    });

    testWidgets('a flat capture says the scene was flat, not "error"', (t) async {
      await t.pumpWidget(wrap(ResultScreen(
        result: result(const []),
        liveness: const Liveness(
            checked: true, live: false, measuredPx: 0.1, predictedPx: 28.2,
            reason: 'FLAT. A print or a screen gives zero, because it is flat.'),
      )));
      expect(find.textContaining('scene was flat'), findsOneWidget);
      expect(find.textContaining('Error'), findsNothing);
      expect(find.textContaining('Failed'), findsNothing);
    });
  });

  group('the second view is gated on having actually moved', () {
    const notYet = SecondView(baselineMm: 2.0, cardVisible: true);
    const far = SecondView(baselineMm: 14.0, cardVisible: true);
    const lost = SecondView(baselineMm: 30.0, cardVisible: false);

    testWidgets('the shutter is blocked until the operator has moved enough',
        (t) async {
      var fired = false;
      await t.pumpWidget(wrap(
          SecondViewScreen(view: notYet, onCapture: () => fired = true)));
      await t.tap(find.byType(PrimaryButton));
      expect(fired, isFalse);
      expect(find.text('Move a little further'), findsOneWidget);
    });

    testWidgets('a sufficient movement arms it', (t) async {
      var fired = false;
      await t.pumpWidget(
          wrap(SecondViewScreen(view: far, onCapture: () => fired = true)));
      await t.tap(find.text('Capture second frame'));
      expect(fired, isTrue);
    });

    test('losing the card blocks the capture whatever the baseline', () {
      expect(lost.ready, isFalse);
      expect(lost.guidance, contains('whole card in frame'));
    });

    test('guidance tells the operator what to do, never the geometry', () {
      expect(notYet.guidance, contains('Move'));
      expect(far.guidance, contains('Far enough'));
      // No stereo baselines, no millimetres, no parallax lecture.
      for (final g in [notYet.guidance, far.guidance, lost.guidance]) {
        expect(g.toLowerCase(), isNot(contains('parallax')));
        expect(g.toLowerCase(), isNot(contains('baseline')));
        expect(g, isNot(contains('mm')));
      }
    });

    testWidgets('the screen says why the second frame exists, once', (t) async {
      await t.pumpWidget(wrap(const SecondViewScreen(view: far)));
      expect(find.textContaining('physically present'), findsOneWidget);
      expect(find.textContaining('evidence too'), findsOneWidget);
    });

    testWidgets('a single-frame capture is offered, and says what it costs',
        (t) async {
      // Field conditions are not negotiable with software. The escape hatch is
      // offered at lower weight and the consequence is stated, rather than the
      // option being hidden and an officer improvising around it.
      var skipped = false;
      await t.pumpWidget(wrap(SecondViewScreen(
        view: const SecondView(baselineMm: 2.0, cardVisible: true),
        onSkip: () => skipped = true,
      )));
      expect(find.text('Continue with one frame only'), findsOneWidget);
      expect(find.textContaining('cannot then be told apart from a photograph'),
          findsOneWidget);
      await t.tap(find.text('Continue with one frame only'));
      expect(skipped, isTrue,
          reason: 'the escape must work even before the operator has moved');
    });

    testWidgets('the single-frame option is absent when it is not offered',
        (t) async {
      await t.pumpWidget(wrap(const SecondViewScreen(
        view: SecondView(baselineMm: 2.0, cardVisible: true))));
      expect(find.text('Continue with one frame only'), findsNothing);
    });

    test('ten millimetres is enough — the screen must not imply precision', () {
      expect(SecondView.enoughMm, 10.0);
      expect(const SecondView(baselineMm: 10.0, cardVisible: true).ready, isTrue);
    });
  });
}

/// The app targets an issued handset, but it is demoed in a desktop browser.
///
/// The capture viewfinder is a 3:4 box. Unconstrained on a 2000px-wide window it
/// becomes ~2600px tall, pushing the quality meters and the shutter off screen —
/// the app looks frozen when it is only enormous. This is a real bug found by
/// running the web build, not a hypothetical.
void _responsiveRules() {
  group('the app stays usable on a wide screen', () {
    testWidgets('a desktop window renders a phone-width column, not a stretched one',
        (t) async {
      await t.binding.setSurfaceSize(const Size(1600, 900));
      addTearDown(() => t.binding.setSurfaceSize(null));

      await t.pumpWidget(wrap(const PhoneFrame(child: StandbyScreen(posture: goodPosture))));
      await t.pumpAndSettle();

      final w = t.getSize(find.byType(Scaffold).first).width;
      expect(w, lessThanOrEqualTo(PhoneFrame.width + 1),
          reason: 'the UI must not stretch to the full window width');
    });

    testWidgets('the whole capture screen fits without overflowing', (t) async {
      await t.binding.setSurfaceSize(const Size(1600, 900));
      addTearDown(() => t.binding.setSurfaceSize(null));

      const good = CaptureQuality(
          fiducialsFound: 4, illumination: 0.96, focus: 0.94,
          tiltDegrees: 3, clippedFraction: 0);
      await t.pumpWidget(wrap(const PhoneFrame(child: CaptureScreen(quality: good))));
      await t.pumpAndSettle();

      // The shutter is the thing that ends up off screen when this breaks.
      // A RenderFlex overflow fails the test on its own, so reaching the
      // shutter at all is the assertion.
      expect(find.text('Capture frame'), findsOneWidget);
    });

    testWidgets('an actual phone viewport is left alone', (t) async {
      await t.binding.setSurfaceSize(const Size(390, 844));
      addTearDown(() => t.binding.setSurfaceSize(null));

      await t.pumpWidget(wrap(const PhoneFrame(child: StandbyScreen(posture: goodPosture))));
      await t.pumpAndSettle();

      final w = t.getSize(find.byType(Scaffold).first).width;
      expect(w, 390, reason: 'on a real handset the app fills the screen');
    });
  });
}
