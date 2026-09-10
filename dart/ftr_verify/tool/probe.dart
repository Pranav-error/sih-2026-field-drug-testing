import 'dart:io';
import 'package:image/image.dart' as img;
import 'package:ftr_verify/ftr_verify.dart';

void main() {
  var im = img.decodeImage(File('test/fixtures/real_card.jpg').readAsBytesSync())!;
  if (im.width > 1200) {
    im = img.copyResize(im, width: 1200, interpolation: img.Interpolation.average);
  }
  final m = measureOnDevice(im);
  print('detected      : ${m.detected}');
  print('guidance      : ${m.guidance}');
  print('gate passed   : ${m.quality?.passed}');
  print('refusals      : ${m.refusals}');
  print('well Lab*     : ${m.lab}');
  print('card residual : ${m.cardResidual}');
  print('prediction    : ${m.prediction?.predictionSet} label=${m.prediction?.label}');
  print('scores        : ${m.prediction?.scores}');
  print('threshold     : ${m.prediction?.threshold}');
}
