/// The order the screens actually appear in, driven through the real widget.
///
/// Reported from a handset: "there is no window to enter id or reagent, it
/// opens the camera directly". Reading main.dart says otherwise, so the reading
/// is what needs checking — this drives the app the way a thumb does.
library;

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:field_companion/main.dart';
import 'package:field_companion/src/screens.dart';
import 'package:field_companion/src/screens_extra.dart';

void main() {
  testWidgets('Begin field test goes to setup, NOT to the camera', (t) async {
    await t.pumpWidget(const FieldCompanionApp());
    await t.pump();

    expect(find.byType(StandbyScreen), findsOneWidget,
        reason: 'the app must open on the posture report, not a viewfinder');

    await t.tap(find.text('Begin field test'));
    await t.pumpAndSettle();

    expect(find.byType(SetupScreen), findsOneWidget,
        reason: 'reagent, operator and card must be captured before any frame');
    expect(find.byType(CaptureScreen), findsNothing);
  });

  testWidgets('the setup screen actually offers the fields it claims to',
      (t) async {
    await t.pumpWidget(const FieldCompanionApp());
    await t.pump();
    await t.tap(find.text('Begin field test'));
    await t.pumpAndSettle();

    // A screen that exists but shows nothing to fill in reads to an operator
    // exactly like a screen that was skipped.
    expect(find.byType(TextField), findsWidgets);
    // Panel titles render uppercase — matching the rendered string, not the
    // one in the source, because that is what an operator sees.
    for (final label in const [
      'REAGENT', 'OPERATOR', 'REFERENCE CARD', 'LINK TO CASE',
    ]) {
      expect(find.text(label), findsWidgets, reason: 'missing panel: $label');
    }
  });

  testWidgets('only Continue reaches the camera', (t) async {
    await t.pumpWidget(const FieldCompanionApp());
    await t.pump();
    await t.tap(find.text('Begin field test'));
    await t.pumpAndSettle();
    expect(find.byType(CaptureScreen), findsNothing);
    expect(find.text('Open camera'), findsOneWidget);
  });

  testWidgets('an unstamped build says so rather than claiming a version',
      (t) async {
    // These tests run without --dart-define, so this is the unstamped path.
    // A build that showed a plausible default would be lying about which code
    // it contains, which is the exact confusion the stamp exists to end.
    await t.pumpWidget(const FieldCompanionApp());
    await t.pump();
    expect(find.textContaining('unstamped build'), findsOneWidget);
  });

  testWidgets('the setup screen says which step of the flow it is', (t) async {
    await t.pumpWidget(const FieldCompanionApp());
    await t.pump();
    await t.tap(find.text('Begin field test'));
    await t.pumpAndSettle();
    expect(find.text('STEP 1 OF 4'), findsOneWidget);
  });
}
