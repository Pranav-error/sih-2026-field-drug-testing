/// The Dart half of the cross-implementation contract.
///
/// These vectors were produced by the Python implementation, which has never seen
/// this code. If both suites pass against the same files, the digest a §63
/// certificate states is reproducible by two independently written encoders —
/// which is the only reason it is worth stating.
///
/// Regenerate with: python core/tools/gen_vectors.py
library;

import 'dart:convert';
import 'dart:io';
import 'dart:typed_data';

import 'package:crypto/crypto.dart' as crypto;
import 'package:ftr_verify/src/canonical_cbor.dart' as cbor;
import 'package:ftr_verify/ftr_verify_io.dart';
import 'package:test/test.dart';

final vectors = Directory('test/vectors');

Uint8List unhex(String s) {
  final out = Uint8List(s.length ~/ 2);
  for (var i = 0; i < out.length; i++) {
    out[i] = int.parse(s.substring(i * 2, i * 2 + 2), radix: 16);
  }
  return out;
}

String tohex(Uint8List b) => b.map((x) => x.toRadixString(16).padLeft(2, '0')).join();

void main() {
  final spec = jsonDecode(File('${vectors.path}/encoding.json').readAsStringSync())
      as Map<String, dynamic>;

  group('canonical CBOR agrees with the Python encoder', () {
    for (final c in (spec['accept'] as List).cast<Map<String, dynamic>>()) {
      test('accepts and reproduces: ${c['name']}', () {
        final want = unhex(c['hex'] as String);

        expect(cbor.isCanonical(want), isTrue,
            reason: 'Python produced it, so Dart must consider it canonical');

        final reencoded = cbor.encode(cbor.decode(want));
        expect(tohex(reencoded), equals(c['hex']),
            reason: 'decode then encode must reproduce the exact bytes');

        final digest = crypto.sha256.convert(want).toString();
        expect(digest, equals(c['sha256']),
            reason: 'both implementations must reach the same digest');
      });
    }

    for (final c in (spec['reject'] as List).cast<Map<String, dynamic>>()) {
      test('rejects: ${c['name']} (${c['why']})', () {
        expect(cbor.isCanonical(unhex(c['hex'] as String)), isFalse);
      });
    }
  });

  group('a chain sealed by Python', () {
    test('verifies in Dart, signature and all', () {
      final report = verifyChain(Directory('${vectors.path}/chain'));
      expect(report.ok, isTrue, reason: report.failures.join('\n'));
      expect(report.proven.any((p) => p.contains('individually verify')), isTrue);
      expect(report.proven.any((p) => p.contains('no gap and no fork')), isTrue);
    });

    test('reports the unanchored window rather than hiding it', () {
      final report = verifyChain(Directory('${vectors.path}/chain'));
      expect(report.asserted.any((a) => a.contains('unanchored')), isTrue);
    });

    test('reports head truncation as unverifiable', () {
      final report = verifyChain(Directory('${vectors.path}/chain'));
      expect(report.unverifiable.any((u) => u.contains('head')), isTrue);
    });

    test('surfaces a location disagreement without failing the record', () {
      final f = File('${vectors.path}/chain/000002.ftr');
      final report = verifyRecord(f.readAsBytesSync());
      expect(report.ok, isTrue, reason: 'a disagreement is recorded, not a failure');
      expect(report.asserted.any((a) => a.contains('Only 2 of 4')), isTrue);
      expect(report.asserted.any((a) => a.contains('310 km')), isTrue);
    });

    test('recomputes the digest rather than trusting the file', () {
      final blob = File('${vectors.path}/chain/000000.ftr').readAsBytesSync();
      final env = cbor.decode(blob) as Map;
      expect(env.containsKey('digest'), isFalse);
      expect(env.containsKey('hash'), isFalse);

      final rec = SealedRecord.fromEnvelope(blob);
      expect(tohex(rec.digest), equals(tohex(sha256(rec.bodyCbor))));
    });
  });

  group('attacks Python built are caught by Dart', () {
    final manifest = jsonDecode(File('${vectors.path}/manifest.json').readAsStringSync())
        as Map<String, dynamic>;

    for (final entry in (manifest['tampered'] as Map<String, dynamic>).entries) {
      test('${entry.key}: ${entry.value}', () {
        final report = verifyChain(Directory('${vectors.path}/tampered/${entry.key}'));
        expect(report.ok, isFalse, reason: 'this chain must not verify');
        expect(report.failures, isNotEmpty);
      });
    }

    test('a rewritten result breaks the signature, not merely the text', () {
      final f = File('${vectors.path}/tampered/rewritten_result/000000.ftr');
      final report = verifyRecord(f.readAsBytesSync());
      expect(report.ok, isFalse);
      expect(report.failures.any((x) => x.contains('does not verify')), isTrue);
    });
  });

  group('liveness — both implementations must read it the same way', () {
    Uint8List sealWith(Map<String, Object?> liveness) {
      final body = <String, Object?>{
        'schema_version': 1,
        'record_uuid': '00000000-0000-4000-c000-000000000001',
        'sequence': 0,
        'prev_record_hash': genesisHash,
        'captured_at': {'device_clock': '2026-09-13T16:00:00+05:30'},
        'operator': {'id': 'NCB/BLR/2291'},
        'kit': {'reagent_type': 'marquis'},
        'card': {'card_id': 'CARD-IN-2026-0417'},
        'capture': <String, Object?>{},
        'colorimetry': {'measured': true, 'gate_passed': true},
        'liveness': liveness,
        'classification': {'label': 'opiate_class', 'prediction_set': ['opiate_class']},
        'location_bundle': <String, Object?>{},
        'device': <String, Object?>{},
        'ndps': <String, Object?>{},
        'omitted': <String>[],
      };
      return toEnvelope(seal(body, SoftwareKeystore(seed: 3)));
    }

    test('a flat capture FAILS, and separates record integrity from content', () {
      final report = verifyRecord(sealWith({
        'checked': true, 'live': false,
        'displacement_px_x100': 10, 'predicted_px_x100': 2820,
        'tab_height_mm_x10': 80, 'baseline_mm_x10': 500,
      }));
      expect(report.ok, isFalse);
      expect(report.failures.any((f) => f.contains('LIVENESS FAILED')), isTrue);
      expect(report.failures.any((f) => f.contains('record is authentic')), isTrue,
          reason: 'an authentic record of a photograph is not an altered record');
    });

    test('a live capture is asserted, not proven — Dart cannot re-derive it', () {
      final report = verifyRecord(sealWith({
        'checked': true, 'live': true,
        'displacement_px_x100': 2810, 'predicted_px_x100': 2820,
        'tab_height_mm_x10': 80, 'baseline_mm_x10': 500,
      }));
      expect(report.asserted.any((a) => a.contains('parallax')), isTrue);
      expect(report.failures.where((f) => f.contains('LIVENESS')), isEmpty);
    });

    test('an unchecked capture is flagged, not silently accepted', () {
      final report = verifyRecord(sealWith({'checked': false}));
      expect(report.asserted.any((a) => a.contains('single frame')), isTrue);
      expect(report.unverifiable.any((u) => u.contains('physically present')), isTrue);
    });
  });

  group('location is reported honestly, or reported as absent', () {
    Report withLocation(Map<String, Object?> loc) {
      final body = <String, Object?>{
        'schema_version': 1,
        'record_uuid': 'loc-0001',
        'sequence': 0,
        'prev_record_hash': genesisHash,
        'captured_at': '2026-09-09T00:00:00Z',
        'operator': <String, Object?>{},
        'kit': <String, Object?>{},
        'card': <String, Object?>{},
        'capture': <String, Object?>{},
        'colorimetry': {'measured': true, 'gate_passed': true},
        'liveness': {'checked': false},
        'classification': {'label': 'opiate_class', 'prediction_set': ['opiate_class']},
        'location_bundle': loc,
        'device': <String, Object?>{},
        'ndps': <String, Object?>{},
        'omitted': <String>[],
      };
      return verifyRecord(toEnvelope(seal(body, SoftwareKeystore(seed: 4))));
    }

    test('one agreeing channel is never reported as corroboration', () {
      // "1 of 1 channels agreed" is true, and would read as a pass. It is the
      // same shape as the fabricated 4-of-4 bundle this replaced.
      final r = withLocation({
        'available': true,
        'corroboration_channels_agreeing': 1,
        'corroboration_channels_total': 1,
        'channels_collected': ['fused_gnss'],
        'channels_not_collected': ['raw_gnss_cn0', 'wifi_bssid_set'],
        'spoof_indicators': <String>[],
      });
      final text = r.asserted.join(' ');
      expect(text, contains('not corroboration'));
      expect(text, contains('raw_gnss_cn0'));
      expect(r.proven.any((p) => p.contains('location channel')), isFalse);
    });

    test('an unavailable fix is stated, not left silent', () {
      final r = withLocation({
        'available': false,
        'status': 'permission denied',
        'channels_collected': <String>[],
        'channels_not_collected': ['fused_gnss'],
        'spoof_indicators': <String>[],
      });
      final text = r.asserted.join(' ');
      expect(text, contains('No position was recorded'));
      expect(text, contains('permission denied'));
    });
  });

  group('a genuine hardware record must not read as a modified device', () {
    // Regression: PlatformKeystore reports verified boot as IN_ATTESTATION,
    // because the authoritative value is inside the certificate and the app
    // refuses to assert it. The verifier used to fall through to its "modified
    // device" branch and FAIL every real StrongBox record — reading the app's
    // honesty as evidence against it.
    Uint8List sealHardware(String vbs, {int chainLen = 3}) {
      final body = <String, Object?>{
        'schema_version': 1,
        'record_uuid': '00000000-0000-4000-d000-000000000001',
        'sequence': 0,
        'prev_record_hash': genesisHash,
        'captured_at': {'device_clock': '2026-09-09T14:00:00+05:30'},
        'operator': {'id': 'NCB/BLR/2291'},
        'kit': {'reagent_type': 'marquis'},
        'card': {'card_id': 'CARD-IN-2026-0417'},
        'capture': <String, Object?>{},
        'colorimetry': {'measured': true, 'gate_passed': true},
        'liveness': {'checked': true, 'live': true,
            'displacement_px_x100': 2810, 'predicted_px_x100': 400},
        'classification': {'label': 'opiate_class', 'prediction_set': ['opiate_class']},
        'location_bundle': <String, Object?>{},
        'device': <String, Object?>{},
        'ndps': <String, Object?>{},
        'omitted': <String>[],
      };
      final rec = seal(body, SoftwareKeystore(seed: 11));
      final att = Map<String, Object?>.from(rec.attestation)
        ..['security_level'] = 'STRONGBOX'
        ..['verified_boot_state'] = vbs
        ..['bootloader_locked'] = false
        ..['cert_chain'] = List.generate(
            chainLen, (i) => Uint8List.fromList([0x30, 0x03, i]));
      return cbor.encode({
        'v': 1, 'body': rec.bodyCbor, 'sig': rec.signature,
        'pub': rec.publicKeyDer, 'att': att,
      });
    }

    test('IN_ATTESTATION is reported as asserted, never as a failure', () {
      final report = verifyRecord(sealHardware('IN_ATTESTATION'));
      expect(report.failures.any((f) => f.contains('modified device')), isFalse,
          reason: 'the app declining to assert verified boot is honesty, not evidence '
              'of tampering');
      expect(report.asserted.any((a) => a.contains('attestation certificate')), isTrue);
      expect(report.asserted.any((a) => a.contains('3 in the chain')), isTrue);
    });

    test('a genuinely bad boot state still fails', () {
      final report = verifyRecord(sealHardware('ORANGE'));
      expect(report.failures.any((f) => f.contains('modified device')), isTrue);
    });

    test('a supplied chain suppresses the no-attestation caveat', () {
      final report = verifyRecord(sealHardware('IN_ATTESTATION'));
      expect(report.asserted.any((a) => a.contains('No attestation certificate chain')),
          isFalse);
    });
  });
}
