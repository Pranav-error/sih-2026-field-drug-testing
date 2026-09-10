/// Upgrading over an existing ledger must not require a wipe.
///
/// Every build so far shipped with "uninstall first", which also destroyed the
/// records — so no chain survived two builds, and testing restarted from zero
/// each time. The two things that forced it are fixed here and in
/// HardwareKeystore: a record this build cannot parse is reported rather than
/// thrown, and a stale signing key is regenerated on use.
library;

import 'dart:io';
import 'dart:typed_data';

import 'package:flutter_test/flutter_test.dart';
import 'package:ftr_verify/ftr_verify.dart' as ftr;
import 'package:field_companion/src/store.dart';

Map<String, Object?> _body(int seq, Uint8List prev) => {
      'schema_version': 1,
      'record_uuid': 'up-$seq',
      'sequence': seq,
      'prev_record_hash': prev,
      'captured_at': {'device_clock': '2026-09-10T00:00:00Z'},
      'operator': <String, Object?>{},
      'kit': <String, Object?>{},
      'card': <String, Object?>{},
      'capture': <String, Object?>{},
      'colorimetry': {'measured': true, 'gate_passed': true},
      'liveness': {'checked': false},
      'classification': {'measured': false},
      'location_bundle': {'available': false, 'status': 'test'},
      'device': <String, Object?>{},
      'ndps': <String, Object?>{},
      'omitted': <String>[],
    };

void main() {
  late Directory dir;
  late RecordStore store;

  setUp(() {
    dir = Directory.systemTemp.createTempSync('ftr-upgrade-');
    store = RecordStore.at(dir);
    final ks = ftr.SoftwareKeystore(seed: 5);
    for (var i = 0; i < 3; i++) {
      store.append(ftr.seal(_body(i, store.head), ks));
    }
  });

  tearDown(() => dir.deleteSync(recursive: true));

  test('a record this build cannot parse does not take the log down', () {
    // What an older or newer schema looks like from here.
    File('${dir.path}/000003.ftr').writeAsBytesSync(
        Uint8List.fromList([0xDE, 0xAD, 0xBE, 0xEF, 0x00, 0x11]));
    store.refresh();

    expect(() => store.records(), returnsNormally);
    expect(store.records().length, 3, reason: 'the readable ones still load');
    expect(store.unreadable.length, 1);
    expect(store.unreadable.first, contains('000003.ftr'));
  });

  test('an unreadable record is reported as a break, never ignored', () {
    File('${dir.path}/000003.ftr').writeAsBytesSync(
        Uint8List.fromList([0xDE, 0xAD, 0xBE, 0xEF]));
    store.refresh();

    final st = store.status();
    expect(st.intact, isFalse, reason: 'silently dropping it would be worse');
    expect(st.breaks.any((b) => b.contains('NOT been')), isTrue,
        reason: 'the operator must be told the record still exists');
  });

  test('a corrupt tail does not corrupt the head the next record chains to', () {
    final headBefore = store.head;
    File('${dir.path}/000003.ftr').writeAsBytesSync(
        Uint8List.fromList([0x00, 0x01]));
    store.refresh();
    expect(store.head, headBefore,
        reason: 'head comes from the last READABLE record');
  });

  test('a fresh install still starts from genesis', () {
    final empty = Directory.systemTemp.createTempSync('ftr-empty-');
    addTearDown(() => empty.deleteSync(recursive: true));
    expect(RecordStore.at(empty).head, ftr.genesisHash);
  });
}
