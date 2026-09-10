/// Identifiers that must be unique across every handset in the country.
library;

import 'dart:math';

/// A random RFC 4122 version 4 UUID.
///
/// Replaces a derived string of the form
/// `00000000-0000-4000-a000-<sequence>`, which was wrong twice over. The
/// counter feeding it only advanced when the ledger write *failed*, so on a
/// working device every record carried the same identifier — and even correct,
/// a sequence-derived UUID would collide across devices, because record 3 on
/// every handset in the country would be the same string. That identifier is
/// printed on the §63 certificate and is the routing key of the CCTNS-2.0
/// envelope.
///
/// [Random.secure] rather than [Random]: the identifier ends up in a signed
/// evidentiary record, and a predictable one invites the argument that records
/// could be manufactured to order.
String newRecordUuid() {
  final rnd = Random.secure();
  final b = List<int>.generate(16, (_) => rnd.nextInt(256));
  b[6] = (b[6] & 0x0f) | 0x40; // version 4
  b[8] = (b[8] & 0x3f) | 0x80; // variant 10xx
  String hex(int from, int to) =>
      b.sublist(from, to).map((x) => x.toRadixString(16).padLeft(2, '0')).join();
  return '${hex(0, 4)}-${hex(4, 6)}-${hex(6, 8)}-${hex(8, 10)}-${hex(10, 16)}';
}
