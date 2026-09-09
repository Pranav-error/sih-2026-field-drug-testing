/// Field Test Records, plus the parts that need a filesystem.
///
/// Import this from a CLI or anything else with a disk. The plain
/// `ftr_verify.dart` entry point stays free of `dart:io` so the same sealing and
/// record-verification code runs in a browser and inside the Flutter app.
library;

export 'ftr_verify.dart';
export 'src/verifier_io.dart' show verifyChain;
