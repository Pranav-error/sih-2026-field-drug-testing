/// L6 handoff — getting a record off the handset without a network.
///
/// The app has no INTERNET permission, deliberately, so "sync to CCTNS-2.0" can
/// never be an upload from here. It is an **export**: a self-contained directory
/// that a supervisor's machine ingests over USB or the Android share sheet.
///
/// That is not a workaround. eSakshya's own offline flow is record locally,
/// hash, hand over later — the same trust model. And an export is the stronger
/// half of the two anyway: the moment a bundle leaves this device, any later
/// rewrite of those records is contradicted by a copy the app cannot reach.
///
/// The rule the whole bundle turns on: **the `.ftr` file is the evidence.**
/// Everything else in the directory is derived from it and can be recomputed by
/// someone who does not trust us. The envelope is a routing convenience; a
/// bundle carrying only the JSON would be unverifiable, because the digest is
/// over the canonical CBOR and nothing else.
library;

import 'dart:convert';
import 'dart:io';

import 'package:ftr_verify/ftr_verify.dart' as ftr;

import 'certificate.dart';
import 'store.dart';

class BundleResult {
  const BundleResult({
    required this.dir,
    required this.files,
    required this.bytes,
    required this.anchoredTo,
  });

  final Directory dir;
  final List<File> files;
  final int bytes;

  /// Sequence the chain is witnessed up to now that this bundle exists.
  final int anchoredTo;
}

/// Write a handoff bundle for every record in the chain, and anchor to it.
Future<BundleResult> exportChain(
  RecordStore store, {
  Certificate Function(ftr.SealedRecord rec)? certificateFor,
}) async {
  final recs = store.records();
  if (recs.isEmpty) {
    throw StateError('nothing to export: the chain is empty');
  }

  final stamp = DateTime.now().toUtc().toIso8601String().replaceAll(':', '');
  final dir = Directory('${store.exportRoot.path}/${stamp.substring(0, 15)}Z');
  dir.createSync(recursive: true);

  final written = <File>[];
  File put(String name, List<int> bytes) {
    final f = File('${dir.path}/$name')..writeAsBytesSync(bytes);
    written.add(f);
    return f;
  }

  for (final rec in recs) {
    final stem = rec.sequence.toString().padLeft(6, '0');

    // Raw bytes, not a JSON rendering. This is the file a challenger verifies.
    put('$stem.ftr', ftr.toEnvelope(rec));

    final cert = certificateFor?.call(rec);
    put(
      '$stem.esakshya.json',
      utf8.encode('${const JsonEncoder.withIndent('  ').convert(
        buildEnvelope(rec, certificateStatus: cert?.status),
      )}\n'),
    );
    if (cert != null) {
      put('$stem.bsa63.txt', utf8.encode('${renderCertificate(cert)}\n'));
    }

    // The frames the record's image hashes point at. Without them the hashes in
    // the record name files nobody outside this handset can produce, and the
    // verifier's image check is unrunnable rather than merely unrun.
    final fr = store.frames(rec.sequence);
    if (fr.a != null) put('$stem.a.jpg', fr.a!);
    if (fr.b != null) put('$stem.b.jpg', fr.b!);
  }

  final head = recs.last;
  put(
    'MANIFEST.json',
    utf8.encode('${const JsonEncoder.withIndent('  ').convert({
      'bundle_version': 1,
      'produced_by': 'SIH26231 field companion',
      'exported_at': DateTime.now().toUtc().toIso8601String(),
      'record_count': recs.length,
      'chain_head_sha256': ftr.hex(head.digest),
      'chain_head_sequence': head.sequence,
      'signing_key_sha256': head.attestation['public_key_sha256'],
      'key_security_level': head.attestation['security_level'],
      'chain_intact': store.status().intact,
      'files': written.map((f) => f.uri.pathSegments.last).toList()..sort(),
      'anchor_note':
          'Exporting witnesses the chain up to sequence ${head.sequence}. This '
              'is an export receipt, NOT a countersignature from a timestamping '
              'authority: it bounds the window in which these records could have '
              'been rewritten, it does not prove wall-clock time.',
    })}\n'),
  );

  put('README.txt', utf8.encode(_readme(recs.length, head)));

  store.anchor(head.sequence);

  return BundleResult(
    dir: dir,
    files: written,
    bytes: written.fold<int>(0, (n, f) => n + f.lengthSync()),
    anchoredTo: head.sequence,
  );
}

String _readme(int count, ftr.SealedRecord head) => '''
Field Test Record handoff bundle (SIH26231)
===========================================

$count sealed record(s). Chain head: ${ftr.hex(head.digest)}

  *.ftr            the sealed record. THIS is the evidence; everything else
                   here is derived from it and can be recomputed.
  *.esakshya.json  routing envelope for CCTNS-2.0. Field names are PROVISIONAL:
                   no published ingest specification has been found for them.
  *.bsa63.txt      certificate under BSA 2023 s.63, Part A pre-populated. Every
                   field a human must attest is left blank on purpose.
  *.a.jpg/*.b.jpg  the frames the record's image hashes refer to.
  MANIFEST.json    what this bundle contains and what chain it came from.

Verify without trusting the app that produced this. Two independent
implementations; run both, and treat a disagreement as a failure:

  python -m ftr.cli chain .
  dart run ftr_verify:ftrverify chain .

CCTNS-2.0 is the system of record. This bundle is a handoff into it, not a
parallel evidence store.

A presumptive field test is a screening indication. It does not identify a
substance, does not establish quantity, and does not replace laboratory
analysis under NDPS procedure.
''';
