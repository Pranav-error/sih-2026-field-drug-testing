/// The identifier that reaches the §63 certificate and the CCTNS-2.0 envelope.
library;

import 'package:flutter_test/flutter_test.dart';
import 'package:field_companion/src/record_id.dart';

void main() {
  test('two records never share an identifier', () {
    // The bug: the uuid was derived from a counter that only advanced when the
    // ledger write FAILED, so on a working device every record was
    // 00000000-0000-4000-a000-000000000000.
    final seen = <String>{};
    for (var i = 0; i < 5000; i++) {
      expect(seen.add(newRecordUuid()), isTrue, reason: 'collision at $i');
    }
  });

  test('it is a well-formed RFC 4122 version 4 UUID', () {
    final re = RegExp(
        r'^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$');
    for (var i = 0; i < 200; i++) {
      expect(newRecordUuid(), matches(re));
    }
  });

  test('it is not derived from anything a second device would also produce', () {
    // A sequence-derived uuid collides across handsets: record 3 on every phone
    // in the country would carry the same string.
    expect(newRecordUuid(), isNot(newRecordUuid()));
    expect(newRecordUuid().startsWith('00000000-0000'), isFalse);
  });
}
