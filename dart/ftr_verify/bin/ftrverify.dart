/// ftrverify — the Dart verifier.
///
///     dart run ftr_verify:ftrverify chain  path/to/chain-dir
///     dart run ftr_verify:ftrverify record path/to/000000.ftr [--image FIELD=PATH]
library;

import 'dart:io';
import 'dart:typed_data';

import 'package:ftr_verify/src/verifier.dart';

void main(List<String> argv) {
  if (argv.length < 2) {
    stderr.writeln('usage: ftrverify (record <file> [--image FIELD=PATH] | chain <dir>)');
    exit(2);
  }
  final cmd = argv[0];
  final target = argv[1];

  late Report report;
  if (cmd == 'record') {
    final f = File(target);
    if (!f.existsSync()) {
      stderr.writeln('ftrverify: no such record: $target');
      exit(2);
    }
    final images = <String, Uint8List>{};
    for (var i = 2; i < argv.length; i++) {
      if (argv[i] != '--image' || i + 1 >= argv.length) continue;
      final spec = argv[++i];
      final k = spec.indexOf('=');
      if (k < 0) {
        stderr.writeln('ftrverify: --image expects FIELD=PATH, got $spec');
        exit(2);
      }
      images[spec.substring(0, k)] = File(spec.substring(k + 1)).readAsBytesSync();
    }
    report = verifyRecord(f.readAsBytesSync(), images: images);
  } else if (cmd == 'chain') {
    final d = Directory(target);
    if (!d.existsSync()) {
      stderr.writeln('ftrverify: no such chain directory: $target');
      exit(2);
    }
    report = verifyChain(d);
  } else {
    stderr.writeln('ftrverify: unknown command $cmd');
    exit(2);
  }

  stdout.write(report.text());
  exit(report.ok ? 0 : 1);
}
