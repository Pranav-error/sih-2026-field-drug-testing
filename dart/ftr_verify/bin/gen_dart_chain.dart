/// Seal a chain in Dart, for the Python suite to verify.
///
/// The existing cross-implementation test runs one direction: Python seals, Dart
/// verifies. That leaves the more interesting direction untested — a format only
/// one implementation can *write* is not a format, and the app writes in Dart.
///
///     dart run bin/gen_dart_chain.dart <output-dir>
library;

import 'dart:convert';
import 'dart:io';
import 'dart:typed_data';

import 'package:ftr_verify/src/record.dart';
import 'package:ftr_verify/src/seal.dart';

Uint8List bytes(String s) => Uint8List.fromList(utf8.encode(s));

void main(List<String> argv) {
  final out = Directory(argv.isEmpty ? 'build/dart-chain' : argv[0]);
  if (out.existsSync()) out.deleteSync(recursive: true);
  out.createSync(recursive: true);

  // Fixed seed: the chain must be byte-identical between runs, or a committed
  // fixture would churn on every regeneration and the diff would be worthless.
  final ks = SoftwareKeystore(seed: 20260908);

  final scenarios = [
    ('opiate_class', ['opiate_class'], 4, <String>[]),
    ('negative', ['negative'], 4, <String>[]),
    (null, ['opiate_class', 'amphetamine_class'], 2,
        <String>['serving cell conflicts with fix by 310 km']),
  ];

  var prev = genesisHash;
  for (final (i, (label, pset, agreeing, anomalies)) in scenarios.indexed) {
    final frame = bytes('synthetic frame $i sealed by dart');
    final body = buildBody(
      recordUuid: '00000000-0000-4000-9000-${i.toString().padLeft(12, '0')}',
      sequence: i,
      prevRecordHash: prev,
      capturedAt: {'device_clock': '2026-09-13T15:0$i:00+05:30', 'uptime_ms': 900000 + i},
      operator_: {'id': 'NCB/BLR/2291', 'biometric_unlock_used': true},
      kit: {'reagent_type': 'marquis', 'kit_photo_sha256': sha256(bytes('lot'))},
      card: {'card_id': 'CARD-IN-2026-0417', 'print_batch': 'B12'},
      capture: {
        'raw_image_sha256': sha256(frame),
        'normalised_image_sha256': sha256(bytes('normalised $i')),
      },
      colorimetry: {
        'measured': true,
        'lab_x100': [1840, 2320, -750],
        'calibration_residual_x1000': 337,
        'gate_passed': true,
        'refusals': <String>[],
      },
      classification: {
        'model_id': 'marquis-loci-v3',
        'alpha_x1000': 50,
        'prediction_set': pset,
        'label': label,
      },
      locationBundle: {
        'lat_x1e7': 129912000,
        'lon_x1e7': 777205000,
        'accuracy_m': 6,
        'corroboration_channels_agreeing': agreeing,
        'corroboration_channels_total': 4,
        'spoof_indicators': anomalies,
      },
      device: {
        'os_patch_level': '2026-08-01',
        'bootloader_state': 'UNKNOWN',
        'verified_boot_state': 'UNKNOWN',
      },
      ndps: {'seizure_memo_ref': 'SM-2026-0913-07', 'sample_ids': ['S1', 'S2']},
      omitted: ['kit.lot'],
    );

    final rec = seal(body, ks);
    File('${out.path}/${i.toString().padLeft(6, '0')}.ftr')
        .writeAsBytesSync(toEnvelope(rec));
    prev = rec.digest;
    stdout.writeln('sealed #$i  ${hex(rec.digest).substring(0, 32)}...');
  }

  File('${out.path}/ANCHOR').writeAsStringSync('0');
  stdout.writeln('wrote ${scenarios.length} records to ${out.path}');
}
