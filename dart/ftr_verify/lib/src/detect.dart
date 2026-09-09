/// L1 in pure Dart — finding the card, on the device, with no native code.
///
/// The Python pipeline uses OpenCV's ArUco detector. An APK that must work in a
/// room with no laptop cannot call a localhost bridge, and shipping OpenCV over
/// FFI is a build problem in its own right. So this is a detector written for
/// exactly one job: find the four corner fiducials of *our* card.
///
/// It does not decode ArUco bit patterns. It does not need to — the card is
/// ours, the markers are at known corners, and the discriminator that matters is
/// simpler than identity: a fiducial is a dark square **with white inside it**,
/// while every colour patch on the card is a dark square that is solid. That one
/// test separates the four markers from the twenty-three patches, and it is far
/// more robust to implement than a bit decoder.
///
/// Accuracy is lower than OpenCV's sub-pixel corner refinement, and the record
/// says so: a frame measured this way carries `pipeline: "dart-on-device"`, so a
/// verifier re-running the reference implementation knows why the last digit may
/// differ and can judge accordingly.
library;

import 'dart:math' as math;
import 'dart:typed_data';

import 'package:image/image.dart' as img;

/// A greyscale view of a frame, kept flat because every pass over it is hot.
class Gray {
  final Uint8List data;
  final int width;
  final int height;
  const Gray(this.data, this.width, this.height);

  int at(int x, int y) => data[y * width + x];
}

class Quad {
  /// Corners in image pixels, ordered top-left, top-right, bottom-right,
  /// bottom-left of the shape itself.
  final List<List<double>> corners;
  final double area;
  const Quad(this.corners, this.area);

  List<double> get centre {
    var cx = 0.0, cy = 0.0;
    for (final c in corners) {
      cx += c[0];
      cy += c[1];
    }
    return [cx / 4, cy / 4];
  }
}

class DartDetection {
  final List<Quad> markers;      // ordered TL, TR, BR, BL of the card
  final List<double> homography; // 3x3 row-major: card mm-grid px -> image px
  final double reprojectionPx;
  final double tiltDegrees;

  const DartDetection({
    required this.markers,
    required this.homography,
    required this.reprojectionPx,
    required this.tiltDegrees,
  });

  bool get complete => markers.length == 4;
}

// --------------------------------------------------------------------------- //
// greyscale and thresholding
// --------------------------------------------------------------------------- //

Gray toGray(img.Image src) {
  final out = Uint8List(src.width * src.height);
  var i = 0;
  for (var y = 0; y < src.height; y++) {
    for (var x = 0; x < src.width; x++) {
      final p = src.getPixel(x, y);
      // Rec. 709 luma, the same weights the Python side samples with.
      out[i++] = (0.2126 * p.r + 0.7152 * p.g + 0.0722 * p.b).round().clamp(0, 255);
    }
  }
  return Gray(out, src.width, src.height);
}

/// Adaptive threshold against a box-blurred local mean.
///
/// A global threshold fails the moment one corner of the card is in shadow,
/// which is the common case rather than the exotic one. The integral image keeps
/// this O(pixels) regardless of window size.
Uint8List adaptiveThreshold(Gray g, {int window = 0, int offset = 7}) {
  final w = g.width, h = g.height;
  final win = window > 0 ? window : math.max(15, (math.min(w, h) ~/ 24) | 1);
  final r = win ~/ 2;

  // Integral image, one row and column of padding.
  final integral = Int64List((w + 1) * (h + 1));
  for (var y = 0; y < h; y++) {
    var rowSum = 0;
    for (var x = 0; x < w; x++) {
      rowSum += g.at(x, y);
      integral[(y + 1) * (w + 1) + x + 1] =
          integral[y * (w + 1) + x + 1] + rowSum;
    }
  }

  int boxSum(int x0, int y0, int x1, int y1) =>
      (integral[(y1 + 1) * (w + 1) + x1 + 1] -
              integral[y0 * (w + 1) + x1 + 1] -
              integral[(y1 + 1) * (w + 1) + x0] +
              integral[y0 * (w + 1) + x0])
          .toInt();

  final out = Uint8List(w * h);
  for (var y = 0; y < h; y++) {
    final y0 = math.max(0, y - r), y1 = math.min(h - 1, y + r);
    for (var x = 0; x < w; x++) {
      final x0 = math.max(0, x - r), x1 = math.min(w - 1, x + r);
      final n = (x1 - x0 + 1) * (y1 - y0 + 1);
      final mean = boxSum(x0, y0, x1, y1) / n;
      // 1 marks ink; the fiducials are the darkest large shapes on the card.
      out[y * w + x] = g.at(x, y) < mean - offset ? 1 : 0;
    }
  }
  return out;
}

// --------------------------------------------------------------------------- //
// connected components, and the square-with-white-inside test
// --------------------------------------------------------------------------- //

/// Find dark blobs that are square and contain white — i.e. our fiducials.
///
/// The interior test is what makes this work without decoding ArUco: every
/// colour patch on the card is a *solid* dark square, and every fiducial is a
/// dark square with a white bit pattern inside it.
List<Quad> findFiducials(Uint8List binary, int w, int h,
    {double minAreaFraction = 0.0004, double maxAreaFraction = 0.06}) {
  final labels = Int32List(w * h);
  final found = <Quad>[];
  final minArea = (w * h * minAreaFraction).round();
  final maxArea = (w * h * maxAreaFraction).round();

  final stackX = Int32List(w * h);
  final stackY = Int32List(w * h);
  var label = 0;

  for (var sy = 0; sy < h; sy++) {
    for (var sx = 0; sx < w; sx++) {
      if (binary[sy * w + sx] != 1 || labels[sy * w + sx] != 0) continue;
      label++;

      var top = 0;
      stackX[top] = sx;
      stackY[top] = sy;
      top++;
      labels[sy * w + sx] = label;

      var area = 0;
      var minX = sx, maxX = sx, minY = sy, maxY = sy;
      // Extreme points along the diagonals give the four corners of a rotated
      // square without needing contour tracing or polygon approximation.
      var bestSum = 1 << 30, bestSumXY = <double>[0, 0];
      var worstSum = -(1 << 30), worstSumXY = <double>[0, 0];
      var bestDiff = 1 << 30, bestDiffXY = <double>[0, 0];
      var worstDiff = -(1 << 30), worstDiffXY = <double>[0, 0];

      while (top > 0) {
        top--;
        final x = stackX[top], y = stackY[top];
        area++;
        if (x < minX) minX = x;
        if (x > maxX) maxX = x;
        if (y < minY) minY = y;
        if (y > maxY) maxY = y;

        final s = x + y, d = x - y;
        if (s < bestSum) { bestSum = s; bestSumXY = [x.toDouble(), y.toDouble()]; }
        if (s > worstSum) { worstSum = s; worstSumXY = [x.toDouble(), y.toDouble()]; }
        if (d < bestDiff) { bestDiff = d; bestDiffXY = [x.toDouble(), y.toDouble()]; }
        if (d > worstDiff) { worstDiff = d; worstDiffXY = [x.toDouble(), y.toDouble()]; }

        for (var k = 0; k < 4; k++) {
          final nx = x + (k == 0 ? 1 : k == 1 ? -1 : 0);
          final ny = y + (k == 2 ? 1 : k == 3 ? -1 : 0);
          if (nx < 0 || ny < 0 || nx >= w || ny >= h) continue;
          if (binary[ny * w + nx] != 1 || labels[ny * w + nx] != 0) continue;
          labels[ny * w + nx] = label;
          stackX[top] = nx;
          stackY[top] = ny;
          top++;
        }
      }

      if (area < minArea || area > maxArea) continue;

      final bw = maxX - minX + 1, bh = maxY - minY + 1;
      final aspect = bw / bh;
      if (aspect < 0.6 || aspect > 1.65) continue;          // roughly square
      if (area / (bw * bh) < 0.5) continue;                  // reasonably filled

      // The discriminator: a fiducial's interior is not solid. Sample the middle
      // of the bounding box and require a mix of ink and paper.
      var ink = 0, total = 0;
      final ix0 = minX + bw ~/ 4, ix1 = maxX - bw ~/ 4;
      final iy0 = minY + bh ~/ 4, iy1 = maxY - bh ~/ 4;
      for (var y = iy0; y <= iy1; y++) {
        for (var x = ix0; x <= ix1; x++) {
          total++;
          if (binary[y * w + x] == 1) ink++;
        }
      }
      if (total == 0) continue;
      final inkFraction = ink / total;
      // A solid patch is ~1.0; a marker's interior carries white bits.
      if (inkFraction > 0.92 || inkFraction < 0.25) continue;

      found.add(Quad(
        [bestSumXY, worstDiffXY, worstSumXY, bestDiffXY],
        area.toDouble(),
      ));
    }
  }

  found.sort((a, b) => b.area.compareTo(a.area));
  return found;
}

/// Order four detected markers as the card's top-left, top-right, bottom-right
/// and bottom-left, by their positions relative to the group's centre.
List<Quad>? orderMarkers(List<Quad> markers) {
  if (markers.length < 4) return null;
  final four = markers.take(4).toList();
  var cx = 0.0, cy = 0.0;
  for (final m in four) {
    final c = m.centre;
    cx += c[0] / 4;
    cy += c[1] / 4;
  }
  Quad? tl, tr, br, bl;
  for (final m in four) {
    final c = m.centre;
    if (c[0] < cx && c[1] < cy) tl = m;
    else if (c[0] >= cx && c[1] < cy) tr = m;
    else if (c[0] >= cx && c[1] >= cy) br = m;
    else bl = m;
  }
  if (tl == null || tr == null || br == null || bl == null) return null;
  return [tl, tr, br, bl];
}

// --------------------------------------------------------------------------- //
// homography
// --------------------------------------------------------------------------- //

/// Solve the 3x3 homography mapping four source points to four destinations.
///
/// Direct linear transform: eight unknowns, eight equations, solved by
/// Gauss-Jordan with partial pivoting. Four correspondences is the minimum, and
/// the card gives exactly four — which is also why the reprojection residual is
/// only meaningful because we insist on all four markers rather than accepting
/// three.
List<double>? homographyFrom(List<List<double>> src, List<List<double>> dst) {
  final a = List.generate(8, (_) => List<double>.filled(9, 0));
  for (var i = 0; i < 4; i++) {
    final x = src[i][0], y = src[i][1];
    final u = dst[i][0], v = dst[i][1];
    a[i * 2] = [x, y, 1, 0, 0, 0, -u * x, -u * y, u];
    a[i * 2 + 1] = [0, 0, 0, x, y, 1, -v * x, -v * y, v];
  }

  for (var col = 0; col < 8; col++) {
    var pivot = col;
    for (var r = col + 1; r < 8; r++) {
      if (a[r][col].abs() > a[pivot][col].abs()) pivot = r;
    }
    if (a[pivot][col].abs() < 1e-9) return null;   // degenerate: collinear points
    final t = a[col];
    a[col] = a[pivot];
    a[pivot] = t;

    final d = a[col][col];
    for (var j = col; j < 9; j++) {
      a[col][j] /= d;
    }
    for (var r = 0; r < 8; r++) {
      if (r == col) continue;
      final f = a[r][col];
      if (f == 0) continue;
      for (var j = col; j < 9; j++) {
        a[r][j] -= f * a[col][j];
      }
    }
  }
  return [
    a[0][8], a[1][8], a[2][8],
    a[3][8], a[4][8], a[5][8],
    a[6][8], a[7][8], 1.0,
  ];
}

List<double> applyHomography(List<double> h, double x, double y) {
  final den = h[6] * x + h[7] * y + h[8];
  if (den.abs() < 1e-12) return [double.nan, double.nan];
  return [
    (h[0] * x + h[1] * y + h[2]) / den,
    (h[3] * x + h[4] * y + h[5]) / den,
  ];
}

/// Angle between the card plane and the sensor plane, as a scale-free proxy.
///
/// The same estimate the Python side uses: exact metric tilt needs the camera
/// intrinsics, and neither the operator guidance nor the quality gate needs it.
double tiltFrom(List<double> h) {
  final n1 = math.sqrt(h[0] * h[0] + h[3] * h[3]);
  final n2 = math.sqrt(h[1] * h[1] + h[4] * h[4]);
  if (n1 == 0 || n2 == 0) return 90;
  final cosBetween = ((h[0] * h[1] + h[3] * h[4]) / (n1 * n2)).abs();
  final skew = math.asin(cosBetween.clamp(0.0, 1.0)) * 180 / math.pi;
  final aspect = n1 > n2 ? n1 / n2 : n2 / n1;
  final foreshorten = math.acos((1.0 / aspect).clamp(0.0, 1.0)) * 180 / math.pi;
  return math.max(skew, foreshorten);
}
