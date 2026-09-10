/// Every asset the app loads at runtime must be declared in pubspec.yaml.
///
/// bsa63_schedule.json sat in app/assets from the day the certificate screen was
/// written and was never declared. The file was in the repo, schedule_sync_test
/// passed because it reads the filesystem, and rootBundle threw only on a real
/// device. Sealing loads it, so every seal failed with "Unable to load asset" —
/// and it failed AFTER the record was already appended, so the ledger grew, the
/// screen showed an error, and the operator tapped again. One tester produced 13
/// records that way before anyone looked at the log.
library;

import 'dart:io';

import 'package:flutter_test/flutter_test.dart';

void main() {
  test('every rootBundle asset is declared and present', () {
    final pubspec = File('pubspec.yaml').readAsStringSync();

    // What the code actually asks rootBundle for.
    final asked = <String>{};
    for (final f in Directory('lib')
        .listSync(recursive: true)
        .whereType<File>()
        .where((f) => f.path.endsWith('.dart'))) {
      for (final m in RegExp(r"""loadString\(\s*['"]([^'"]+)['"]""")
          .allMatches(f.readAsStringSync())) {
        asked.add(m.group(1)!);
      }
    }
    expect(asked, isNotEmpty, reason: 'the scan itself must find something');

    for (final a in asked) {
      expect(File(a).existsSync(), isTrue, reason: '$a is not in the repo');
      expect(pubspec.contains(a), isTrue,
          reason: '$a is loaded at runtime but not declared in pubspec.yaml — '
              'it will throw on a device and pass every test that reads the '
              'filesystem instead of the bundle');
    }
  });
}
