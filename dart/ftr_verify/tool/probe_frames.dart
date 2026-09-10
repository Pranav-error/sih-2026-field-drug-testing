import 'dart:io';
import 'package:image/image.dart' as img;
import 'package:ftr_verify/ftr_verify.dart';

void main(List<String> args) {
  final dir = Directory(args[0]);
  final files = dir.listSync().whereType<File>().toList()
    ..sort((a, b) => a.path.compareTo(b.path));
  print('DART on-device pipeline (what the APK actually runs)');
  print('${'frame'.padRight(22)} ${'residual'.padLeft(9)}  detail');
  print('=' * 78);
  for (final f in files) {
    var im = img.decodeImage(f.readAsBytesSync())!;
    if (im.width > 1200) {
      im = img.copyResize(im, width: 1200, interpolation: img.Interpolation.average);
    }
    final m = measureOnDevice(im);
    final name = f.uri.pathSegments.last.replaceAll('.jpg', '');
    if (!m.detected) {
      print('${name.padRight(22)} ${'-'.padLeft(9)}  NOT DETECTED: ${m.guidance}');
      continue;
    }
    final r = m.cardResidual;
    final tag = (r == null) ? '-' : r.toStringAsFixed(2);
    final refusal = m.refusals.isEmpty ? 'OK' : m.refusals.first;
    print('${name.padRight(22)} ${tag.padLeft(9)}  ${refusal.length > 46 ? refusal.substring(0, 46) : refusal}');
  }
}
