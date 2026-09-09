/// The Dart verifier — same three buckets, written independently.
///
/// This file is deliberately free of `dart:io` so it runs unchanged in a browser
/// and inside the Flutter app — an in-app verifier that could not run in the app
/// would be a strange thing to have built. The chain verifier, which reads a
/// directory, lives in `verifier_io.dart`.
///
/// This file exists to disagree with `core/ftr/verifier.py` if either is wrong.
/// It is not a port: the wording is its own, so that a reader comparing the two
/// reports is comparing two readings of the record rather than one text echoed
/// twice. What must match exactly is the *verdict* and the digest — never the prose.
library;

import 'dart:typed_data';

import 'canonical_cbor.dart' as cbor;
import 'record.dart';

class Report {
  final proven = <String>[];
  final asserted = <String>[];
  final unverifiable = <String>[];
  final failures = <String>[];

  bool get ok => failures.isEmpty;

  String text() {
    final b = StringBuffer();
    void block(String title, List<String> items, String mark) {
      if (items.isEmpty) return;
      b.writeln(title);
      b.writeln('-' * title.length);
      for (final it in items) {
        for (final (i, line) in _wrap(it, 74).indexed) {
          b.writeln(' ${i == 0 ? mark : ' '}  $line');
        }
      }
      b.writeln();
    }

    block('FAILED', failures, 'x');
    block('PROVEN', proven, '+');
    block('ASSERTED, NOT PROVEN', asserted, '~');
    block('UNVERIFIABLE FROM THIS BUNDLE', unverifiable, '.');
    b.writeln('${ok ? 'VERIFIED' : 'VERIFICATION FAILED'} — ${proven.length} proven, '
        '${asserted.length} asserted, ${unverifiable.length} unverifiable');
    if (ok) {
      b.writeln('A verified record is not a true result. It is an unaltered one.');
    }
    return b.toString();
  }
}

List<String> _wrap(String s, int w) {
  final out = <String>[];
  var line = '';
  for (final word in s.split(RegExp(r'\s+'))) {
    if (line.isNotEmpty && line.length + 1 + word.length > w) {
      out.add(line);
      line = word;
    } else {
      line = line.isEmpty ? word : '$line $word';
    }
  }
  if (line.isNotEmpty) out.add(line);
  return out.isEmpty ? [''] : out;
}

Report verifyRecord(Uint8List blob, {Map<String, Uint8List>? images}) {
  final r = Report();

  late SealedRecord rec;
  try {
    rec = SealedRecord.fromEnvelope(blob);
  } catch (e) {
    r.failures.add('Envelope will not decode: $e');
    return r;
  }

  if (cbor.isCanonical(rec.bodyCbor)) {
    r.proven.add('The record body is canonically encoded: it decodes and re-encodes '
        'to the same bytes, so any implementation reaches the same digest.');
  } else {
    r.failures.add('The record body is not canonical CBOR. Its digest is not '
        'reproducible, so no signature over it means anything.');
    return r;
  }

  final body = rec.body;
  r.proven.add('SHA-256 of the body recomputes to ${hex(rec.digest)}.');

  if (rec.signatureValid) {
    r.proven.add('The signature verifies against the recomputed digest under the '
        'public key carried in the envelope.');
  } else {
    r.failures.add('The signature does not verify over the recomputed digest. The '
        'record has been altered since it was sealed, or it was never sealed by this key.');
  }

  final att = rec.attestation;
  final level = att['security_level'] as String? ?? 'UNKNOWN';
  switch (level) {
    case 'STRONGBOX':
      r.proven.add('Key attestation states the signing key was generated in '
          'StrongBox, a discrete secure element, and is non-exportable.');
    case 'TEE':
      r.proven.add('Key attestation states the signing key was generated in the TEE '
          'and is non-exportable. Weaker than StrongBox: no discrete secure element.');
    default:
      r.failures.add('Signing key security level is $level. The key is not '
          'hardware-backed, so the signature proves only that whoever held the key '
          'file made this record. It says nothing about which device produced it. '
          'Development records must never be presented as evidence.');
  }

  if (att['key_exportable'] == true) {
    r.asserted.add('The key is marked exportable, so a copy may exist elsewhere. '
        'Authorship is not established by this signature alone.');
  }

  final vbs = att['verified_boot_state'] as String? ?? 'UNKNOWN';
  final locked = att['bootloader_locked'] == true;
  final chain = (att['cert_chain'] as List?) ?? const [];
  if (vbs == 'IN_ATTESTATION') {
    // The app deliberately refuses to assert verified boot: the authoritative
    // value lives inside the attestation certificate, and a verifier taking the
    // app's word for it would be trusting the software whose integrity is in
    // question. This implementation does not parse that extension — the Python
    // reference does — so it says so rather than guessing, and above all rather
    // than reading the app's honesty as evidence of a modified device.
    r.asserted.add('Verified boot state and bootloader lock are carried inside the '
        'attestation certificate (${chain.length} in the chain), not in the record. '
        'This implementation does not parse that extension; run the reference '
        'verifier to read them.');
  } else if (vbs == 'GREEN' && locked) {
    r.proven.add('Verified boot was GREEN and the bootloader locked when the key was '
        'attested: the device was running unmodified signed firmware.');
  } else if (vbs == 'UNKNOWN') {
    r.asserted.add('Verified boot state is unknown; device integrity is not established.');
  } else {
    r.failures.add('Verified boot state is $vbs and the bootloader is '
        '${locked ? 'locked' : 'unlocked'}. The record was produced on a modified device.');
  }

  if ((att['cert_chain_len'] as int? ?? 0) == 0 && chain.isEmpty) {
    r.asserted.add('No attestation certificate chain is present, so the hardware '
        'claims above cannot be traced to a root certificate authority.');
  }

  final capture = body['capture'];
  if (capture is Map) {
    capture.forEach((k, want) {
      if (k is! String || !k.endsWith('_sha256') || want is! Uint8List) return;
      final name = k.substring(0, k.length - '_sha256'.length);
      final supplied = images?[k];
      if (supplied == null) {
        r.asserted.add('$k is recorded as ${hex(want).substring(0, 16)}… but the file '
            'was not supplied to this verifier, so the image behind it was not checked.');
      } else if (bytesEqual(sha256(supplied), want)) {
        r.proven.add('The supplied $name hashes to the value in the record: the image '
            'is byte-identical to the one sealed at capture.');
      } else {
        r.failures.add('The supplied $name does NOT match the hash in the record. '
            'The image has been altered since capture.');
      }
    });
  }

  final live = (body['liveness'] as Map?) ?? const {};
  if (live.isEmpty) {
    r.asserted.add('This record carries no liveness block. It predates the check, or '
        'was made by an app that does not perform one.');
  } else if (live['checked'] != true) {
    r.asserted.add('No liveness check was performed — a single frame was captured. '
        'This record cannot be told apart from a photograph of a card, which is the '
        'attack two-view parallax exists to refuse.');
  } else {
    final got = (live['displacement_px_x100'] as int? ?? 0) / 100;
    final want = (live['predicted_px_x100'] as int? ?? 0) / 100;
    final h = (live['tab_height_mm_x10'] as int? ?? 0) / 10;
    if (live['live'] == true) {
      r.asserted.add('The app measured ${got.toStringAsFixed(1)} px of parallax '
          'against ${want.toStringAsFixed(1)} px predicted for the '
          '${h.toStringAsFixed(0)} mm liveness tab, and concluded the scene had '
          'depth. This implementation cannot re-derive that — it does not read '
          'frames — so it stands as asserted.');
    } else {
      r.failures.add('LIVENESS FAILED at capture: ${got.toStringAsFixed(1)} px of '
          'parallax against ${want.toStringAsFixed(1)} px predicted. The scene was '
          'flat, which is what a photograph of a print or a screen looks like. The '
          'record is authentic; what it photographed is in question.');
    }
  }

  if (live['checked'] != true) {
    r.unverifiable.add('Whether the strip photographed was physically present '
        'rather than a printed or displayed image of one. Nothing in a single frame '
        'can establish that.');
  }

  final ts = body['captured_at'];
  if (ts is Map && ts['device_clock'] != null) {
    r.asserted.add('Capture time is stated as ${ts['device_clock']}, taken from the '
        'device clock. Nothing here proves the clock was correct; only the chain and '
        'an anchor bound when this record was made.');
  }
  final op = (body['operator'] as Map?) ?? const {};
  if (op['biometric_unlock_used'] == true) {
    r.asserted.add('Key use was gated by a biometric. That binds the record to the '
        'enrolled device, not to the named person.');
  } else {
    // Silence would read as a pass. It does not: an ungated key means nothing
    // in this record connects it to a person.
    r.asserted.add('Key use was NOT gated by a biometric. Nothing in this record '
        'connects it to a person at all — only to the device that signed it.');
  }
  if (op['id'] == null || '${op['id']}'.isEmpty) {
    r.asserted.add('No operator credential was recorded. The record does not name '
        'who performed the test.');
  }
  final kit = body['kit'];
  if (kit is Map && kit['reagent_type'] != null) {
    r.asserted.add('Reagent is declared as ${kit['reagent_type']} by the operator. It '
        'is not machine-read, by design — the system is kit-agnostic.');
  }
  for (final name in (body['omitted'] as List? ?? const [])) {
    r.asserted.add("Field '$name' was recorded as unavailable at capture.");
  }

  final loc = body['location_bundle'];
  if (loc is Map) {
    final agree = loc['corroboration_channels_agreeing'] as int?;
    final total = loc['corroboration_channels_total'] as int?;
    final notCollected =
        ((loc['channels_not_collected'] as List?) ?? const []).join(', ');
    if (loc['available'] == false) {
      r.asserted.add('No position was recorded: '
          '${loc['status'] ?? 'reason not stated'}. Nothing in this record places '
          'it anywhere.');
    } else if (agree != null && total != null && total > 0) {
      final collected =
          ((loc['channels_collected'] as List?) ?? const ['unspecified']).join(', ');
      if (agree == total && total < 2) {
        // One agreeing channel is not corroboration. Calling it "all channels
        // agreed" would be true and deeply misleading.
        r.asserted.add('$agree of $total location channel(s) agreed — collected: '
            '$collected. NOT collected: $notCollected. A single channel is a claim, '
            'not corroboration.');
      } else if (agree == total) {
        r.proven.add('All $total independent location channels agreed at capture.');
      } else {
        r.asserted.add('Only $agree of $total location channels agreed. The '
            'disagreement is recorded below and is available to either party.');
      }
    }
    for (final ind in (loc['spoof_indicators'] as List? ?? const [])) {
      r.asserted.add('Location anomaly recorded at capture: $ind');
    }
  }

  final cls = body['classification'];
  final alpha = (cls is Map ? cls['alpha_x1000'] : null) ?? '?';
  r.unverifiable.addAll([
    'Whether the substance photographed is the substance seized. No bundle of bytes '
        'can establish this; it rests on the seizure procedure and the witnesses.',
    'Whether the colorimetric reaction had fully developed when the frame was taken.',
    'The correctness of the result itself. This is a presumptive screening test '
        'reported at risk level alpha=$alpha/1000; it is not confirmatory and does '
        'not identify a substance.',
  ]);
  return r;
}
