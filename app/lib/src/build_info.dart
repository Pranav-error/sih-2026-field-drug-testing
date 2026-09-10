/// Which build this is.
///
/// Added because it could not be answered. Every APK sent out was called v10,
/// several were built from different commits, and when a tester reported "there
/// is no screen to enter the operator id" there was no way to tell whether the
/// app was wrong or the APK was old. It was the APK — the setup screen had been
/// there for weeks. A build with no identity turns every report into an
/// argument about what was installed.
///
/// Stamped at build time:
///
///   flutter build apk --release \
///     --dart-define=BUILD_COMMIT=$(git rev-parse --short HEAD) \
///     --dart-define=BUILD_DATE=$(date -u +%Y-%m-%dT%H:%MZ)
///
/// Left honest when it is not: an unstamped build says so rather than showing a
/// plausible default that would be wrong.
library;

class BuildInfo {
  static const commit =
      String.fromEnvironment('BUILD_COMMIT', defaultValue: '');
  static const date = String.fromEnvironment('BUILD_DATE', defaultValue: '');

  static bool get stamped => commit.isNotEmpty;

  /// What to show the operator, and what to read out over the phone.
  static String get label =>
      stamped ? '$commit  ·  $date' : 'unstamped build — commit unknown';
}
