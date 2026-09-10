/// End-to-end over the ledger and the handoff bundle, with real signed records.
///
/// The export path had never executed once before this existed. That is exactly
/// the shape of the seal button that reached a handset and did nothing: code
/// that analysed clean, was covered by nothing, and was wrong.
library;

import 'dart:convert';
import 'dart:io';
import 'dart:typed_data';

import 'package:flutter_test/flutter_test.dart';
import 'package:ftr_verify/ftr_verify.dart' as ftr;
import 'package:field_companion/src/handoff.dart';
import 'package:field_companion/src/store.dart';

Map<String, Object?> _body(int seq, Uint8List prev) => {
      'schema_version': 1,
      'record_uuid': 'ledger-${seq.toString().padLeft(4, '0')}',
      'sequence': seq,
      'prev_record_hash': prev,
      'captured_at': '2026-09-09T0$seq:00:00Z',
      'operator': {'operator_id': 'NCB/TEST/0001'},
      'kit': <String, Object?>{},
      'card': {'card_id': 'CARD-TEST', 'print_batch': 'B1'},
      'capture': <String, Object?>{},
      'colorimetry': {'measured': true, 'gate_passed': true},
      'liveness': {'checked': false},
      'classification': {
        'label': 'opiate_class',
        'prediction_set': ['opiate_class'],
      },
      'location_bundle': {
        'available': false,
        'status': 'permission denied',
        'channels_collected': <String>[],
        'channels_not_collected': ['fused_gnss'],
        'spoof_indicators': <String>[],
      },
      'device': <String, Object?>{},
      'ndps': {'fir_reference': 'FIR/2026/0042'},
      'omitted': <String>[],
    };

/// A chain of [n] records sealed by one key, in a fresh temp directory.
({RecordStore store, Directory dir}) _chain(int n, {int seed = 7}) {
  final dir = Directory.systemTemp.createTempSync('ftr-ledger-');
  final store = RecordStore.at(dir);
  final ks = ftr.SoftwareKeystore(seed: seed);
  for (var i = 0; i < n; i++) {
    store.append(ftr.seal(_body(i, store.head), ks));
  }
  return (store: store, dir: dir);
}

void main() {
  group('the ledger', () {
    test('records chain, and the store agrees with the verifier', () {
      final c = _chain(3);
      addTearDown(() => c.dir.deleteSync(recursive: true));

      expect(c.store.length, 3);
      expect(c.store.status().intact, isTrue, reason: c.store.status().breaks.join('; '));

      final recs = c.store.records();
      for (var i = 1; i < recs.length; i++) {
        expect(ftr.bytesEqual(recs[i].prevRecordHash, recs[i - 1].digest), isTrue);
      }
    });

    test('the replay cache is dropped when a record is appended', () {
      // status() ECDSA-verifies every record, so it is cached. A cache that
      // outlived an append would hide a chain break from the log screen, which
      // is worse than the cost it saves.
      final c = _chain(2);
      addTearDown(() => c.dir.deleteSync(recursive: true));

      expect(c.store.status().intact, isTrue);
      expect(c.store.records().length, 2);

      final other = ftr.SoftwareKeystore(seed: 99);
      c.store.append(ftr.seal(_body(2, c.store.head), other));

      expect(c.store.records().length, 3, reason: 'stale record cache');
      expect(c.store.status().intact, isFalse, reason: 'stale status cache');
    });

    test('a repeated status() does not re-verify from scratch', () {
      final c = _chain(3);
      addTearDown(() => c.dir.deleteSync(recursive: true));
      final first = Stopwatch()..start();
      c.store.status();
      first.stop();
      final second = Stopwatch()..start();
      c.store.status();
      second.stop();
      expect(second.elapsedMicroseconds, lessThan(first.elapsedMicroseconds),
          reason: 'the second call should be a cache hit');
    });

    test('a record is never rewritten', () {
      final c = _chain(1);
      addTearDown(() => c.dir.deleteSync(recursive: true));
      final ks = ftr.SoftwareKeystore(seed: 7);
      // Same slot, different content: the guard is the slot, not the bytes.
      expect(() => c.store.append(ftr.seal(_body(0, ftr.genesisHash), ks)),
          throwsA(isA<StateError>()));
    });

    test('a second device cannot be spliced into the chain', () {
      final c = _chain(2);
      addTearDown(() => c.dir.deleteSync(recursive: true));

      // Correctly chained, correctly sequenced, different key. Each record
      // verifies on its own; the ordering they jointly assert never happened.
      final other = ftr.SoftwareKeystore(seed: 99);
      c.store.append(ftr.seal(_body(2, c.store.head), other));

      final st = c.store.status();
      expect(st.intact, isFalse);
      expect(st.breaks.any((b) => b.contains('two devices in one chain')), isTrue,
          reason: st.breaks.join('; '));
    });

    test('an anchor records when it happened, not only how far it reached', () {
      final c = _chain(2);
      addTearDown(() => c.dir.deleteSync(recursive: true));
      expect(c.store.lastAnchorAt, isNull);

      final before = DateTime.now().toUtc();
      c.store.anchor(1);
      final at = c.store.lastAnchorAt;

      expect(at, isNotNull);
      expect(at!.isBefore(before.subtract(const Duration(seconds: 5))), isFalse);
      expect(c.store.lastAnchor, 1);
    });

    test('an ANCHOR file written by an older build still parses', () {
      // Older builds wrote the sequence alone. Failing to read it would make a
      // witnessed chain look unwitnessed after an update — an anchor silently
      // lost is worse than one never made.
      final c = _chain(2);
      addTearDown(() => c.dir.deleteSync(recursive: true));
      File('${c.store.path}/ANCHOR').writeAsStringSync('1');

      expect(c.store.lastAnchor, 1);
      expect(c.store.lastAnchorAt, isNull);
      expect(c.store.unanchored, 0);
    });

    test('unanchored counts every record until something witnesses them', () {
      final c = _chain(3);
      addTearDown(() => c.dir.deleteSync(recursive: true));
      expect(c.store.lastAnchor, isNull);
      expect(c.store.unanchored, 3);
      c.store.anchor(1);
      expect(c.store.unanchored, 1);
    });
  });

  group('the handoff bundle', () {
    test('writes every record, and anchors the chain to the head', () async {
      final c = _chain(2);
      addTearDown(() => c.dir.deleteSync(recursive: true));

      final res = await exportChain(c.store);

      expect(res.dir.existsSync(), isTrue);
      // Derived files must never land inside the append-only ledger.
      expect(res.dir.path.startsWith(c.store.path), isFalse,
          reason: 'the bundle must be a sibling of the ledger, not inside it');
      expect(c.store.length, 2, reason: 'exporting must not add to the chain');
      expect(res.bytes, greaterThan(0));
      expect(res.anchoredTo, 1);
      expect(c.store.unanchored, 0, reason: 'exporting is what witnesses');

      final names = res.files.map((f) => f.uri.pathSegments.last).toSet();
      expect(names, containsAll(['000000.ftr', '000001.ftr', 'MANIFEST.json',
        'README.txt', '000000.esakshya.json']));
    });

    test('the .ftr in the bundle still verifies, byte for byte', () async {
      final c = _chain(1);
      addTearDown(() => c.dir.deleteSync(recursive: true));
      final res = await exportChain(c.store);

      final ftrFile =
          res.files.firstWhere((f) => f.path.endsWith('000000.ftr'));
      // The whole point of shipping raw bytes: a challenger runs the verifier
      // over this file without our app, our schema, or our JSON.
      final report = ftr.verifyRecord(ftrFile.readAsBytesSync());

      // These records are sealed with a software key, so the verdict is FAIL —
      // and must be. What matters is *why*: the bytes are intact and the
      // signature checks out; what fails is the key's security level. A bundle
      // that corrupted the record in transit would fail for a different reason,
      // and this test would then be asserting the wrong thing.
      expect(report.failures.any((f) => f.toUpperCase().contains('SOFTWARE')),
          isTrue,
          reason: 'expected a key-provenance failure, got: '
              '${report.failures.join(" | ")}');
      expect(report.proven.any((p) => p.contains('signature')), isTrue,
          reason: 'the exported bytes must still verify as authentic');

      expect(ftrFile.readAsBytesSync(),
          ftr.toEnvelope(c.store.records().first),
          reason: 'the bundle must carry the record byte for byte');
    });

    test('the manifest names the head it was cut from', () async {
      final c = _chain(2);
      addTearDown(() => c.dir.deleteSync(recursive: true));
      final res = await exportChain(c.store);

      final m = jsonDecode(res.files
          .firstWhere((f) => f.path.endsWith('MANIFEST.json'))
          .readAsStringSync()) as Map<String, Object?>;

      expect(m['record_count'], 2);
      expect(m['chain_head_sequence'], 1);
      expect(m['chain_head_sha256'], ftr.hex(c.store.records().last.digest));
      expect(m['chain_intact'], isTrue);
      // The anchor must never read as a countersignature.
      expect('${m['anchor_note']}', contains('NOT a countersignature'));
    });

    test('the envelope carries the FIR forward and marks itself provisional',
        () async {
      final c = _chain(1);
      addTearDown(() => c.dir.deleteSync(recursive: true));
      final res = await exportChain(c.store);

      final e = jsonDecode(res.files
          .firstWhere((f) => f.path.endsWith('.esakshya.json'))
          .readAsStringSync()) as Map<String, Object?>;

      expect((e['routing'] as Map)['fir_reference'], 'FIR/2026/0042');
      expect('${e['interface_status']}', startsWith('PROVISIONAL'));
      expect(e['system_of_record'], 'CCTNS-2.0');
      expect((e['result'] as Map)['presumptive'], isTrue);
      expect((e['result'] as Map)['confirmatory'], isFalse);
    });

    test('an empty chain refuses to export rather than writing nothing',
        () async {
      final dir = Directory.systemTemp.createTempSync('ftr-empty-');
      addTearDown(() => dir.deleteSync(recursive: true));
      await expectLater(
          exportChain(RecordStore.at(dir)), throwsA(isA<StateError>()));
    });
  });
}
