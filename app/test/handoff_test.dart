/// The certificate text that goes into a handoff bundle is filed and signed by
/// hand, so the property worth pinning is the one that makes the whole layer
/// defensible: **the renderer never fills in a blank.**
///
/// A rendered certificate with an auto-completed attestation is a forgery
/// mechanism, and it would be an easy regression — the values map is right
/// there, and "helpfully" defaulting a missing key looks like a bug fix.
library;

import 'package:flutter_test/flutter_test.dart';
import 'package:field_companion/src/certificate.dart';

Certificate _cert({
  Map<String, String> values = const {},
  bool draft = true,
  List<String> missing = const [],
}) =>
    Certificate(
      schedule: const {
        'verified': false,
        'verification_level': 'secondary',
        'parts': [
          {
            'title': 'PART A',
            'subtitle': '(to be filled by the party)',
            'preamble': 'I do hereby solemnly affirm',
            'items': [
              {'key': 'device_type', 'label': 'Device type'},
              {'key': 'make_model', 'label': 'Make & Model'},
            ],
          },
        ],
      },
      values: values,
      blanks: const ['make_model'],
      missingFromRecord: missing,
      isDraft: draft,
      digestHex: 'ab' * 32,
    );

void main() {
  test('a field with no value renders as a blank to be completed', () {
    final text = renderCertificate(_cert(values: {'device_type': 'Mobile'}));
    expect(text, contains('Mobile'));
    expect(text, contains('[to be completed]'));
    // The blank must be a blank, not an empty string that reads as "answered".
    expect(text, contains('____'));
  });

  test('the signature line is never pre-filled', () {
    final text = renderCertificate(_cert(values: {'device_type': 'Mobile'}));
    final sig = text
        .split('\n')
        .firstWhere((l) => l.startsWith('Signature:'), orElse: () => '');
    expect(sig, isNotEmpty, reason: 'the signature line must be present');
    expect(sig.replaceAll('_', '').replaceAll(' ', ''),
        'Signature:Date:',
        reason: 'nothing but underscores may sit on the signature line');
  });

  test('an unverified Schedule can only produce a DRAFT', () {
    final text = renderCertificate(_cert());
    expect(text, contains('STATUS: DRAFT'));
    expect(text, contains('NOT FOR FILING'));
  });

  test('fields the record could not supply are named, not silently dropped', () {
    final text = renderCertificate(_cert(missing: ['IMEI/UIN/UID/MAC/Cloud ID']));
    expect(text, contains('NOT SUPPLIED BY THE RECORD'));
    expect(text, contains('IMEI/UIN/UID/MAC/Cloud ID'));
  });

  test('the record digest is carried into the text', () {
    expect(renderCertificate(_cert()), contains('ab' * 32));
  });
}
