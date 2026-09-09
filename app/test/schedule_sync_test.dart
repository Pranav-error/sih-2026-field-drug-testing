/// The bundled Schedule must not drift from the Python one.
///
/// `assets/bsa63_schedule.json` is a copy of `core/ftr/data/bsa63_schedule.json`.
/// Two copies of statutory text is a bad idea; this test makes the copy safe by
/// failing the moment they diverge, so the Python file stays the one source of
/// truth and the app never renders labels the reference implementation disowns.
library;

import 'dart:convert';
import 'dart:io';

import 'package:flutter_test/flutter_test.dart';

void main() {
  test('the bundled Schedule matches the one in core/ftr/data', () {
    final bundled = File('assets/bsa63_schedule.json');
    final source = File('../core/ftr/data/bsa63_schedule.json');
    expect(bundled.existsSync(), isTrue, reason: 'the asset is missing');
    expect(source.existsSync(), isTrue, reason: 'the Python source is missing');

    final a = jsonDecode(bundled.readAsStringSync());
    final b = jsonDecode(source.readAsStringSync());
    expect(jsonEncode(a), equals(jsonEncode(b)),
        reason: 'copy assets/bsa63_schedule.json from core/ftr/data/ — the '
            'Python file is the source of truth for statutory text');
  });

  test('the Schedule is still marked as not Gazette-verified', () {
    // If this fails without someone having checked the Gazette, a flag was
    // flipped that should not have been. Certificates would stop saying DRAFT.
    final s = jsonDecode(File('assets/bsa63_schedule.json').readAsStringSync());
    expect(s['verified'], isFalse);
    expect(s['verification_level'], 'secondary');
  });
}
