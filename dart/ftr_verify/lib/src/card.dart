/// The printed card, in Dart. Mirrors `core/ftr/card.py` exactly.
///
/// Both implementations must agree on where every patch is, or they measure
/// different things from the same photograph. `test/card_agreement_test.dart`
/// checks these against the Python spec rather than trusting the transcription.
library;

const double pxPerMm = 10;

class CardSpec {
  final String idPrefix;
  final double widthMm;
  final double heightMm;
  final double markerSizeMm;
  final List<List<double>> markerOriginsMm;   // TL, TR, BR, BL
  final double patchSizeMm;
  final List<List<double>> patchCentresMm;
  final List<List<double>> patchSrgb;
  final List<int> neutralIndex;
  final List<double> wellCentreMm;
  final double wellRadiusMm;
  final double tabHeightMm;
  final List<List<double>> tabQuadMm;

  const CardSpec({
    required this.idPrefix,
    required this.widthMm,
    required this.heightMm,
    required this.markerSizeMm,
    required this.markerOriginsMm,
    required this.patchSizeMm,
    required this.patchCentresMm,
    required this.patchSrgb,
    required this.neutralIndex,
    required this.wellCentreMm,
    required this.wellRadiusMm,
    required this.tabHeightMm,
    required this.tabQuadMm,
  });

  /// The one outer corner of each marker that lies at the card's extremity —
  /// the same four points the Python detector fits its homography to.
  List<List<double>> get markerCornersMm {
    final s = markerSizeMm;
    final tl = markerOriginsMm[0], tr = markerOriginsMm[1];
    final br = markerOriginsMm[2], bl = markerOriginsMm[3];
    return [
      [tl[0], tl[1]],
      [tr[0] + s, tr[1]],
      [br[0] + s, br[1] + s],
      [bl[0], bl[1] + s],
    ];
  }

  List<double> get tabCentreMm {
    var x = 0.0, y = 0.0;
    for (final p in tabQuadMm) {
      x += p[0] / tabQuadMm.length;
      y += p[1] / tabQuadMm.length;
    }
    return [x, y];
  }
}

List<List<double>> _grid(double x0, double y0, int cols, int rows, double pitch) {
  final out = <List<double>>[];
  for (var r = 0; r < rows; r++) {
    for (var c = 0; c < cols; c++) {
      out.add([x0 + c * pitch, y0 + r * pitch]);
    }
  }
  return out;
}

final _colourCentres = _grid(26.0, 22.0, 5, 3, 10.0);
const _neutralCentres = <List<double>>[
  [26.0, 10.0], [50.0, 10.0], [74.0, 10.0],
  [8.0, 34.0], [92.0, 34.0],
  [26.0, 56.0], [50.0, 56.0], [74.0, 56.0],
];

const _colourSrgb = <List<double>>[
  [0.42, 0.19, 0.38], [0.24, 0.14, 0.31], [0.16, 0.10, 0.17], [0.55, 0.30, 0.20], [0.36, 0.20, 0.13],
  [0.20, 0.13, 0.10], [0.13, 0.16, 0.30], [0.10, 0.11, 0.19], [0.08, 0.08, 0.11], [0.79, 0.64, 0.16],
  [0.62, 0.41, 0.12], [0.17, 0.43, 0.36], [0.12, 0.29, 0.25], [0.70, 0.24, 0.28], [0.44, 0.15, 0.19],
];
const _neutralSrgb = <List<double>>[
  [0.09, 0.09, 0.09], [0.30, 0.30, 0.30], [0.52, 0.52, 0.52],
  [0.20, 0.20, 0.20], [0.66, 0.66, 0.66],
  [0.40, 0.40, 0.40], [0.78, 0.78, 0.78], [0.91, 0.91, 0.91],
];

final cardV1 = CardSpec(
  idPrefix: 'CARD-IN-2026',
  widthMm: 100.0,
  heightMm: 80.0,
  markerSizeMm: 14.0,
  markerOriginsMm: const [[3.0, 3.0], [83.0, 3.0], [83.0, 63.0], [3.0, 63.0]],
  patchSizeMm: 9.0,
  patchCentresMm: [..._colourCentres, ..._neutralCentres],
  patchSrgb: const [..._colourSrgb, ..._neutralSrgb],
  neutralIndex: List<int>.generate(8, (i) => _colourSrgb.length + i),
  wellCentreMm: const [50.0, 70.0],
  wellRadiusMm: 8.0,
  tabHeightMm: 8.0,
  tabQuadMm: const [[21.0, 66.0], [40.0, 66.0], [40.0, 80.0], [21.0, 80.0]],
);
