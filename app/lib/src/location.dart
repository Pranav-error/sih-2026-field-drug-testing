/// Real position, honestly graded — or nothing at all.
///
/// This replaces a hardcoded location bundle that asserted four of four
/// corroboration channels agreeing when no location had ever been read. That was
/// the same class of claim as a biometric that never happened: a record stating
/// something the device never observed.
///
/// **What this does and does not do.** It reads the fused GNSS fix and Android's
/// own mock-location flag. It does **not** implement the multi-channel
/// corroboration of `ARCHITECTURE.md` §5 — raw GNSS per-satellite C/N₀, the Wi-Fi
/// BSSID neighbourhood, serving-cell identity and kinematic plausibility are not
/// gathered, because Flutter exposes none of them without native work on each.
/// So the bundle reports **one** channel, names it, and says the rest were not
/// collected. One honest channel beats four invented ones.
library;

import 'package:geolocator/geolocator.dart';

class Fix {
  final double? latitude;
  final double? longitude;
  final double? accuracyMetres;
  final bool mocked;
  final String status;

  const Fix({
    this.latitude,
    this.longitude,
    this.accuracyMetres,
    required this.mocked,
    required this.status,
  });

  bool get available => latitude != null && longitude != null;

  /// The location block of an FTR.
  ///
  /// Scaled integers, because canonical CBOR refuses floats and the digest must
  /// not depend on IEEE-754 rounding.
  Map<String, Object?> toRecord() {
    final indicators = <String>[
      if (mocked) 'Android reports this position came from a mock provider',
    ];
    return {
      'available': available,
      'status': status,
      if (latitude != null) 'lat_x1e7': (latitude! * 1e7).round(),
      if (longitude != null) 'lon_x1e7': (longitude! * 1e7).round(),
      if (accuracyMetres != null) 'accuracy_m_x10': (accuracyMetres! * 10).round(),
      // One channel, named. ARCHITECTURE.md §5 describes five; four of them are
      // not collected in this build and the record must not imply otherwise.
      'channels_collected': const ['fused_gnss'],
      'channels_not_collected': const [
        'raw_gnss_cn0', 'wifi_bssid_set', 'serving_cell', 'kinematics',
      ],
      'corroboration_channels_agreeing': available ? 1 : 0,
      'corroboration_channels_total': 1,
      'spoof_indicators': indicators,
    };
  }
}

class LocationReader {
  /// Read a position, or report exactly why there is none.
  ///
  /// Never throws and never fabricates: every failure path returns a Fix whose
  /// `status` says what happened, so the record carries the reason rather than a
  /// plausible-looking coordinate.
  static Future<Fix> read() async {
    try {
      if (!await Geolocator.isLocationServiceEnabled()) {
        return const Fix(mocked: false, status: 'location services are switched off');
      }
      var permission = await Geolocator.checkPermission();
      if (permission == LocationPermission.denied) {
        permission = await Geolocator.requestPermission();
      }
      if (permission == LocationPermission.denied ||
          permission == LocationPermission.deniedForever) {
        return const Fix(mocked: false, status: 'location permission was refused');
      }

      final p = await Geolocator.getCurrentPosition(
        locationSettings: const LocationSettings(
          accuracy: LocationAccuracy.high,
          timeLimit: Duration(seconds: 12),
        ),
      );
      return Fix(
        latitude: p.latitude,
        longitude: p.longitude,
        accuracyMetres: p.accuracy,
        // Android's own flag. Not a defence against a determined spoofer — that
        // is what the unimplemented multi-channel corroboration is for — but it
        // catches the trivial case and is recorded either way.
        mocked: p.isMocked,
        status: p.isMocked ? 'fix obtained, MOCK PROVIDER DETECTED' : 'fix obtained',
      );
    } catch (e) {
      return Fix(mocked: false, status: 'no fix: $e');
    }
  }
}
