/// L6 on the device — the statutory certificate and the CCTNS-2.0 envelope.
///
/// A Dart counterpart to `core/ftr/certificate.py` and `esakshya.py`, so an
/// officer can produce the certificate at the point of seizure rather than
/// waiting for someone to run a Python CLI over the record later.
///
/// The three rules from the Python are kept exactly, because they are the whole
/// reason this layer is defensible:
///
///  1. **The app never signs for anyone.** Every field a human must attest is
///     emitted blank and marked. The Schedule's declarations begin "I do hereby
///     solemnly affirm" — precisely the things no program may assert.
///  2. **Nothing is asserted that the record does not carry.** A field the record
///     cannot supply is named as missing rather than left silently blank.
///  3. **An unverified Schedule can only produce a DRAFT.**
library;

import 'dart:convert';

import 'package:flutter/services.dart' show rootBundle;
import 'package:ftr_verify/ftr_verify.dart' as ftr;

class Certificate {
  final Map<String, dynamic> schedule;
  final Map<String, String> values;
  final List<String> blanks;
  final List<String> missingFromRecord;
  final bool isDraft;
  final String digestHex;

  const Certificate({
    required this.schedule,
    required this.values,
    required this.blanks,
    required this.missingFromRecord,
    required this.isDraft,
    required this.digestHex,
  });

  String get status => isDraft ? 'DRAFT — NOT FOR FILING' : 'READY FOR SIGNATURE';

  String get verificationLevel =>
      schedule['verification_level'] as String? ?? 'paraphrase';

  List<Map<String, dynamic>> get parts =>
      (schedule['parts'] as List).cast<Map<String, dynamic>>();
}

class ScheduleLoader {
  static Map<String, dynamic>? _cached;

  /// The Schedule, bundled as an asset from `core/ftr/data/`. One source of
  /// truth stays in Python; `test/schedule_sync_test.dart` fails if it drifts.
  static Future<Map<String, dynamic>> load() async {
    if (_cached != null) return _cached!;
    final raw = await rootBundle.loadString('assets/bsa63_schedule.json');
    return _cached = jsonDecode(raw) as Map<String, dynamic>;
  }
}

Certificate buildCertificate(
    ftr.SealedRecord rec, Map<String, dynamic> schedule) {
  final body = rec.body;
  final device = (body['device'] as Map?) ?? const {};
  final att = rec.attestation;

  final values = <String, String>{
    // The Schedule's own tick-list. A phone is "Mobile".
    'device_type': 'Mobile',
    // Both parts require the hash and the algorithm, and SHA256 is one of the
    // algorithms the Schedule names on its face.
    'hash_value': ftr.hex(rec.digest),
    'hash_value__algorithm': 'SHA256',
  };

  void put(String key, Object? v) {
    if (v != null && '$v'.isNotEmpty) values[key] = '$v';
  }

  put('make_model', device['make_model']);
  put('serial_number', device['serial_number']);
  put('device_identifier', device['device_identifier']);

  values['other_device_information'] = [
    'Field Test Record ${body['record_uuid'] ?? 'unknown'}',
    'sequence ${body['sequence'] ?? '?'} on this device\'s append-only ledger',
    'signing key security level ${att['security_level'] ?? 'UNKNOWN'}',
    'attestation chain ${(att['cert_chain'] as List?)?.length ?? 0} certificate(s)',
    'measured by ${body['pipeline'] ?? 'unknown'} pipeline',
  ].join('; ');

  // Statutory fields the record is expected to supply but cannot. Named rather
  // than left blank, so the gap is not discovered by a magistrate.
  const expected = {
    'make_model': 'Make & Model of the device',
    'serial_number': 'Serial Number of the device',
    'device_identifier': 'IMEI/UIN/UID/MAC/Cloud ID',
  };
  final missing = <String>[];
  expected.forEach((k, label) {
    if (!values.containsKey(k)) missing.add(label);
  });

  final blanks = <String>[];
  for (final part in (schedule['parts'] as List).cast<Map<String, dynamic>>()) {
    for (final item in (part['items'] as List).cast<Map<String, dynamic>>()) {
      final key = item['key'] as String;
      if (!values.containsKey(key)) blanks.add(key);
    }
  }

  return Certificate(
    schedule: schedule,
    values: values,
    blanks: blanks,
    missingFromRecord: missing,
    isDraft: schedule['verified'] != true,
    digestHex: ftr.hex(rec.digest),
  );
}

/// The CCTNS-2.0 handoff envelope.
///
/// Deliberately not a parallel evidence store: CCTNS-2.0 stays the system of
/// record. Field names are PROVISIONAL — no published ingest specification has
/// been found — and the envelope says so about itself.
Map<String, Object?> buildEnvelope(ftr.SealedRecord rec, {String? certificateStatus}) {
  final body = rec.body;
  final ndps = (body['ndps'] as Map?) ?? const {};
  final cls = (body['classification'] as Map?) ?? const {};
  final col = (body['colorimetry'] as Map?) ?? const {};
  final live = (body['liveness'] as Map?) ?? const {};
  final loc = (body['location_bundle'] as Map?) ?? const {};

  return {
    'envelope_version': 1,
    'interface_status': 'PROVISIONAL — field names are not taken from a published '
        'eSakshya/CCTNS-2.0 ingest specification.',
    'produced_by': 'SIH26231 field companion',
    'system_of_record': 'CCTNS-2.0',
    'routing': {
      'fir_reference': ndps['fir_reference'],
      'seizure_memo_ref': ndps['seizure_memo_ref'],
      'sample_ids': ndps['sample_ids'] ?? const [],
    },
    'record': {
      'record_uuid': body['record_uuid'],
      'sequence': body['sequence'],
      'hash_value': ftr.hex(rec.digest),
      'hash_algorithm': 'SHA-256',
      'signature_algorithm': 'ECDSA-P256',
      'key_security_level': rec.attestation['security_level'],
      'pipeline': body['pipeline'],
    },
    'result': {
      'presumptive': true,
      'confirmatory': false,
      'label': cls['label'],
      'prediction_set': cls['prediction_set'] ?? const [],
      'alpha_x1000': cls['alpha_x1000'],
      'gate_passed': col['gate_passed'],
      'refusals': col['refusals'] ?? const [],
      'liveness_checked': live['checked'],
      'liveness_live': live['live'],
    },
    // Carried forward deliberately: an envelope that dropped the anomalies would
    // hand the receiving system a cleaner story than the record tells.
    'location': {
      'channels_agreeing': loc['corroboration_channels_agreeing'],
      'channels_total': loc['corroboration_channels_total'],
      'anomalies': loc['spoof_indicators'] ?? const [],
    },
    if (certificateStatus != null)
      'certificate': {
        'statute': 'Bharatiya Sakshya Adhiniyam 2023, section 63',
        'status': certificateStatus,
      },
    'caveat': 'Presumptive field test. A screening indication only: it does not '
        'identify a substance, does not establish quantity, and does not replace '
        'laboratory analysis under NDPS procedure.',
  };
}

/// Render the certificate as plain text, for the handoff bundle.
///
/// Plain text on purpose: the certificate is filed on paper and signed by hand,
/// and a format nobody needs a viewer for is one nobody can claim was altered
/// in rendering. Blanks are printed as blanks — the whole point of this layer is
/// that the app never signs for a human — and anything the record could not
/// supply is named rather than silently omitted.
String renderCertificate(Certificate c) {
  final b = StringBuffer()
    ..writeln('CERTIFICATE UNDER SECTION 63, BHARATIYA SAKSHYA ADHINIYAM 2023')
    ..writeln('=' * 62)
    ..writeln()
    ..writeln('STATUS: ${c.status}')
    ..writeln('Schedule text verification level: ${c.verificationLevel}');
  if (c.isDraft) {
    b
      ..writeln()
      ..writeln('This is a DRAFT. The Schedule text bundled with this app has not')
      ..writeln('been checked against the official eGazette publication, so nothing')
      ..writeln('here may be filed until it has been.');
  }
  if (c.missingFromRecord.isNotEmpty) {
    b
      ..writeln()
      ..writeln('NOT SUPPLIED BY THE RECORD — must be completed by hand:');
    for (final m in c.missingFromRecord) {
      b.writeln('  - $m');
    }
  }

  for (final part in c.parts) {
    b
      ..writeln()
      ..writeln('-' * 62)
      ..writeln('${part['title']}')
      ..writeln('-' * 62);
    final preamble = part['preamble'] as String?;
    if (preamble != null && preamble.isNotEmpty) {
      b
        ..writeln()
        ..writeln(preamble);
    }
    b.writeln();
    for (final item in (part['items'] as List).cast<Map<String, dynamic>>()) {
      final key = item['key'] as String;
      final label = item['label'] as String? ?? key;
      final value = c.values[key];
      b.writeln('  $label:'.padRight(46) +
          (value ?? '________________________  [to be completed]'));
    }
  }

  b
    ..writeln()
    ..writeln('-' * 62)
    ..writeln('Signature: ______________________   Date: ______________')
    ..writeln()
    ..writeln('Record digest (SHA256): ${c.digestHex}')
    ..writeln()
    ..writeln('A presumptive field test is a screening indication. It does not')
    ..writeln('identify a substance and does not replace laboratory analysis.');
  return b.toString();
}
