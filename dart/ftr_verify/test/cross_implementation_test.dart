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
import 'package:ftr_verify/src/record.dart';
import 'package:ftr_verify/src/verifier.dart';
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
}
