/// Design tokens, from docs/DESIGN.md.
///
/// Two rules encoded here rather than left to each screen:
///
///  * **Colour never means good or bad.** `positive`, `negative` and `abstain`
///    are outcome colours, not success/failure colours. There is deliberately no
///    `success` token to reach for: an interface that celebrates a positive
///    pressures the operator toward one.
///  * **Measured quantities are set in mono.** Anything the verifier can
///    recompute uses `mono`; prose uses `ui`. The typeface tells the reader
///    whether a number is evidence.
library;

import 'package:flutter/material.dart';

class Tokens {
  const Tokens._();

  // light
  static const ground = Color(0xFFF7F6F9);
  static const surface = Color(0xFFFFFFFF);
  static const surface2 = Color(0xFFF0EEF4);
  static const ink = Color(0xFF1A1726);
  static const ink2 = Color(0xFF413A55);
  static const muted = Color(0xFF6A6478);
  static const rule = Color(0xFFDEDAE7);
  static const ruleSoft = Color(0xFFEAE7F0);
  static const accent = Color(0xFF6B3FA0);
  static const accentSoft = Color(0xFFEDE6F6);

  /// Outcome colours. Not semantic success/failure — see the class doc.
  static const positive = Color(0xFFA32C4A);
  static const positiveSoft = Color(0xFFF8E4E9);
  static const negative = Color(0xFF0F7B6C);
  static const negativeSoft = Color(0xFFDFF0EC);
  static const abstain = Color(0xFFA66A00);
  static const abstainSoft = Color(0xFFF8EEDC);

  // The design uses Archivo and IBM Plex Mono. Neither is bundled yet, and an
  // unbundled family in Flutter falls back SILENTLY to the platform default —
  // which for the mono family would quietly turn every measured quantity into
  // proportional text and break the rule that the typeface tells a reader whether
  // a number is evidence. So each name is paired with a real fallback stack, and
  // `monoStyle` is the only way the rest of the app is allowed to ask for mono.
  static const ui = 'Archivo';
  static const uiFallback = <String>['Roboto', 'Helvetica Neue', 'Arial'];
  static const mono = 'IBMPlexMono';
  static const monoFallback = <String>['monospace', 'Roboto Mono', 'Courier New', 'Courier'];

  /// Every measured quantity goes through here. Anything the verifier can
  /// recompute — hashes, dE, Lab, alpha, coordinates — is set in this style.
  static TextStyle monoStyle({
    double size = 12.5,
    FontWeight weight = FontWeight.w500,
    Color colour = ink,
    double? spacing,
  }) =>
      TextStyle(
        fontFamily: mono,
        fontFamilyFallback: monoFallback,
        fontSize: size,
        fontWeight: weight,
        color: colour,
        letterSpacing: spacing,
        fontFeatures: const [FontFeature.tabularFigures()],
      );

  /// Minimum touch target. Gloves, sunlight, and an issued handset.
  static const double touchTarget = 48;
}

/// Outcome of a test, and how it is presented.
///
/// Deliberately an enum rather than a bool: `positive` and `negative` are both
/// results, and `inconclusive` is a third result rather than the absence of one.
enum Outcome {
  presumptivePositive('Presumptive positive', Tokens.positive, Tokens.positiveSoft),
  presumptiveNegative('Presumptive negative', Tokens.negative, Tokens.negativeSoft),
  inconclusive('Inconclusive', Tokens.abstain, Tokens.abstainSoft);

  const Outcome(this.label, this.colour, this.soft);
  final String label;
  final Color colour;
  final Color soft;

  /// A prediction set maps to exactly one outcome. A set that is not a singleton
  /// is an abstention, whatever its contents.
  static Outcome fromPredictionSet(List<String> set, {String negativeLabel = 'negative'}) {
    if (set.length != 1) return Outcome.inconclusive;
    return set.single == negativeLabel
        ? Outcome.presumptiveNegative
        : Outcome.presumptivePositive;
  }
}

ThemeData buildTheme(Brightness brightness) {
  final dark = brightness == Brightness.dark;
  final scheme = ColorScheme.fromSeed(
    seedColor: Tokens.accent,
    brightness: brightness,
  );
  return ThemeData(
    useMaterial3: true,
    colorScheme: scheme,
    scaffoldBackgroundColor: dark ? const Color(0xFF141220) : Tokens.ground,
    fontFamily: Tokens.ui,
    fontFamilyFallback: Tokens.uiFallback,
  );
}
