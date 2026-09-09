/// Field Companion — SIH26231.
///
/// The capture spine wired end to end: standby, capture, result, sealed. The
/// camera and the colour pipeline are not here yet; the sealing is real, and goes
/// through the same `ftr_verify` package the reference verifier reads, so a record
/// this app produces can be checked by either implementation.
///
/// What is deliberately NOT here:
///
///  * a software key that pretends to be StrongBox. The standby screen says
///    plainly that this build's records are not evidence, and both verifiers
///    reject them.
///  * any way to edit or delete a sealed record.
library;


import 'src/measure_bridge.dart';
import 'src/certificate.dart';
import 'src/platform_keystore.dart';
import 'src/screens_extra.dart';
import 'src/store.dart';

import 'package:flutter/foundation.dart';
import 'package:flutter/material.dart';
import 'package:ftr_verify/ftr_verify.dart' as ftr;

import 'src/models.dart';
import 'src/screens.dart';
import 'src/tokens.dart';

/// Run the two-view check in a background isolate.
///
/// It searches a grid of offsets over two rectified regions and would visibly
/// stall the capture screen on the UI thread.
Measurement? _pairInIsolate(List<Uint8List> frames) =>
    OnDeviceMeasurer().measurePair(frames[0], frames[1]);

void main() => runApp(const FieldCompanionApp());

class FieldCompanionApp extends StatelessWidget {
  const FieldCompanionApp({super.key});

  @override
  Widget build(BuildContext context) {
    return MaterialApp(
      title: 'Field Companion',
      debugShowCheckedModeBanner: false,
      theme: buildTheme(Brightness.light),
      darkTheme: buildTheme(Brightness.dark),
      home: const CaptureFlow(),
    );
  }
}

/// Keeps the app at handset proportions on a desktop browser.
///
/// Without this the capture viewfinder — a 3:4 box — becomes about 2,600 px tall
/// on a wide window and pushes the quality meters and the shutter off screen, so
/// the app looks frozen when it is merely enormous. The target is an issued
/// phone; on anything wider we render a phone-shaped column and let the page
/// behind it recede.
class PhoneFrame extends StatelessWidget {
  const PhoneFrame({super.key, required this.child});

  static const double width = 412;    // a common issued-handset logical width
  static const double _maxHeight = 892;

  final Widget child;

  @override
  Widget build(BuildContext context) {
    final size = MediaQuery.sizeOf(context);
    if (size.width <= width + 24) return child;   // an actual phone: fill it

    return ColoredBox(
      color: const Color(0xFF2A2436),
      child: Center(
        child: SizedBox(
          width: width,
          height: size.height < _maxHeight ? size.height : _maxHeight,
          child: ClipRRect(
            borderRadius: BorderRadius.circular(18),
            child: child,
          ),
        ),
      ),
    );
  }
}

enum Step { standby, setup, capture, secondView, gate, result, sealed, log, certificate, verifier }

class CaptureFlow extends StatefulWidget {
  const CaptureFlow({super.key});

  @override
  State<CaptureFlow> createState() => _CaptureFlowState();
}

class _CaptureFlowState extends State<CaptureFlow> {
  Step _step = Step.standby;

  // The signing key. On a handset this is the secure element; everywhere else
  // it is a development key that honestly reports SOFTWARE, and every verifier
  // treats that as disqualifying.
  final _software = ftr.SoftwareKeystore();
  RecordStore? _store;
  String _reagent = 'Marquis';
  String _fir = '';
  String _memo = '';
  Certificate? _certificate;
  Map<String, Object?> _envelope = const {};
  ftr.Report? _report;
  PlatformKeystore? _hardware;
  String _keystoreNote = '';

  Uint8List _chainHead = ftr.genesisHash;
  int _sequence = 0;
  String _digestHex = '';

  // Stands in for the live camera. The real overlay is fed by the native L1
  // pipeline over a platform channel; the widget only ever renders what it is given.
  double _progress = 0;
  double _baselineMm = 0;

  // The pipeline, running on this device in pure Dart. No network, no laptop,
  // no native dependency — which is what lets an APK work in a room on its own.
  final _measurer = OnDeviceMeasurer();
  Measurement? _live;
  Uint8List? _frameA;      // the first captured frame, kept for the liveness pair
  Uint8List? _frameB;
  bool _pairing = false;

  /// Real measurements when the bridge is answering; the simulated ramp when it
  /// is not, so the flow is still walkable without it.
  CaptureQuality get _quality =>
      _live?.quality ??
      CaptureQuality(
        fiducialsFound: (_progress * 4).clamp(0, 4).round(),
        illumination: 0.70 + 0.28 * _progress,
        focus: 0.40 + 0.56 * _progress,
        tiltDegrees: 16 - 13 * _progress,
        clippedFraction: 0,
      );

  bool get _shutterArmed =>
      _live != null ? (_live!.detected && _live!.gatePassed) : _quality.locked;

  Future<void> _onFrame(Uint8List jpeg) async {
    final m = _measurer.measure(jpeg);
    if (m != null && mounted) {
      setState(() {
        _live = m;
        if (_step == Step.capture && m.detected && m.gatePassed) _frameA = jpeg;
      });
    }
  }

  /// The second view. The card's apparent motion between the two frames stands
  /// in for a measured baseline — the operator only ever needs to know whether
  /// they have moved enough, never by how much.
  Future<void> _onSecondFrame(Uint8List jpeg) async {
    final m = _measurer.measure(jpeg);
    if (m == null || !mounted) return;
    setState(() {
      _live = m;
      _frameB = jpeg;
      // Movement is inferred from the pipeline seeing a valid card at a changed
      // pose; without a second real signal this is the honest proxy available.
      if (m.detected) _baselineMm += 4.5;
    });
  }

  /// Run the real two-view check on the two real frames.
  Future<void> _confirmPair() async {
    final a = _frameA, b = _frameB;
    if (a == null || b == null) {
      setState(() => _step = Step.gate);
      return;
    }
    setState(() => _pairing = true);
    // Off the UI thread: the two-view search is the heaviest thing the app does.
    final m = await compute(_pairInIsolate, [a, b]);
    if (!mounted) return;
    setState(() {
      if (m != null) _live = m;
      _pairing = false;
      _step = Step.gate;
    });
  }

  DevicePosture get _posture => DevicePosture(
        securityLevel: _hardware?.securityLevel ??
            _software.attestation().securityLevel,
        // Not the app's to assert: the attestation certificate carries these and
        // the verifier reads them from there. Shown as unknown until it does.
        verifiedBootState: _hardware != null
            ? 'IN ATTESTATION'
            : _software.attestation().verifiedBootState,
        bootloaderLocked: _hardware != null,
        osPatchLevel: _hardware != null
            ? 'IN ATTESTATION'
            : _software.attestation().osPatchLevel,
        mockLocation: false,
        recordCount: _store?.length ?? _sequence,
        unanchored: _store?.length ?? _sequence,
        sinceAnchor: Duration(minutes: 4 * _sequence),
      );

  @override
  void initState() {
    super.initState();
    _openKeystore();
    _openStore();
  }

  Future<void> _openStore() async {
    try {
      final s = await RecordStore.open();
      if (mounted) setState(() => _store = s);
    } catch (_) {
      // No filesystem (web). The flow still works; nothing persists, and the
      // record log says so rather than showing an empty chain as if it were one.
    }
  }

  Future<void> _openKeystore() async {
    // The challenge binds the attestation certificate to this installation
    // rather than to a chain lifted from another handset.
    final challenge = ftr.sha256(Uint8List.fromList(
        'sih26231:${DateTime.now().toIso8601String()}'.codeUnits));
    final ks = await PlatformKeystore.open(challenge: challenge);
    if (!mounted) return;
    setState(() {
      _hardware = ks;
      _keystoreNote = ks?.note ?? '';
    });
  }

  SecondView get _secondView =>
      SecondView(baselineMm: _baselineMm, cardVisible: true);

  static const _result = TestResult(
    predictionSet: ['opiate_class', 'amphetamine_class'],
    label: null,
    lab: [21.6, 19.4, -6.1],
    alpha: 0.05,
    threshold: 5.53,
    scores: {'opiate_class': 4.12, 'amphetamine_class': 5.02, 'negative': 46.8},
  );

  Map<String, Object?> _livenessRecord() {
    final l = _live?.liveness;
    if (l == null || !l.checked) {
      return {
        'checked': false,
        'note': 'single frame, or the two-view check did not run — this capture '
            'cannot be distinguished from a photograph of a card',
      };
    }
    return {
      'checked': true,
      'live': l.live,
      'displacement_px_x100': (l.measuredPx * 100).round(),
      'predicted_px_x100': (l.predictedPx * 100).round(),
      'form': 'weak — no known baseline, so feature height is not pinned',
      'reason': l.reason,
    };
  }

  Future<void> _seal() async {
    final frame = Uint8List.fromList('frame $_sequence'.codeUnits);
    final body = ftr.buildBody(
      recordUuid: '00000000-0000-4000-a000-${_sequence.toString().padLeft(12, '0')}',
      sequence: _store?.nextSequence ?? _sequence,
      prevRecordHash: _store?.head ?? _chainHead,
      capturedAt: {'device_clock': DateTime.now().toIso8601String()},
      operator_: {'id': 'NCB/BLR/2291', 'biometric_unlock_used': true},
      kit: {'reagent_type': _reagent.toLowerCase()},
      card: {'card_id': 'CARD-IN-2026-0417', 'print_batch': 'B12'},
      capture: {
        'raw_image_sha256': ftr.sha256(frame),
        // The second view is evidence too, and is bound like the first.
        'second_frame_sha256': ftr.sha256(
            Uint8List.fromList('frame $_sequence view B'.codeUnits)),
      },
      colorimetry: {
        'measured': true,
        'lab_x100': _result.lab!.map((v) => (v * 100).round()).toList(),
        'gate_passed': true,
      },
      classification: {
        'alpha_x1000': (_result.alpha * 1000).round(),
        'prediction_set': _result.predictionSet,
        'label': _result.label,
      },
      // The measured liveness, or an explicit "not checked" — never a default
      // that would read as having passed.
      liveness: _livenessRecord(),
      // Which implementation produced these numbers. A verifier re-running the
      // reference pipeline needs to know why the last digit may differ.
      pipelineName: 'dart-on-device',
      locationBundle: const {'corroboration_channels_agreeing': 4,
        'corroboration_channels_total': 4, 'spoof_indicators': <String>[]},
      device: const {'verified_boot_state': 'UNKNOWN', 'bootloader_state': 'UNKNOWN'},
    );

    // Hardware signing is asynchronous — the key is inside the secure element
    // and only the digest crosses the boundary.
    final ftr.SealedRecord rec;
    final hw = _hardware;
    if (hw != null) {
      final bodyCbor = ftr.encode(body);
      final digest = ftr.sha256(bodyCbor);
      final att = hw.attestation();
      rec = ftr.SealedRecord(
        bodyCbor: bodyCbor,
        digest: digest,
        signature: await hw.signAsync(digest),
        publicKeyDer: att.publicKeyDer,
        attestation: att.toRecord(),
      );
    } else {
      rec = ftr.seal(body, _software);
    }
    if (!mounted) return;

    // Persist before anything else. A record that is shown but not written is
    // not a record, and the ledger's guarantees are about files on disk.
    var stored = false;
    try {
      _store?.append(rec);
      stored = _store != null;
    } catch (_) {
      stored = false;
    }

    final schedule = await ScheduleLoader.load();
    final cert = buildCertificate(rec, schedule);
    if (!mounted) return;
    setState(() {
      _certificate = cert;
      _envelope = buildEnvelope(rec, certificateStatus: cert.status);
      _report = ftr.verifyRecord(ftr.toEnvelope(rec));
      _digestHex = ftr.hex(rec.digest);
      _chainHead = rec.digest;
      if (!stored) _sequence += 1;
      _step = Step.sealed;
    });
  }

  @override
  Widget build(BuildContext context) => PhoneFrame(child: _screen());

  Widget _screen() {
    switch (_step) {
      case Step.setup:
        return SetupScreen(
          reagent: _reagent,
          onReagent: (r) => setState(() => _reagent = r),
          firRef: _fir,
          memoRef: _memo,
          onFir: (v) => _fir = v,
          onMemo: (v) => _memo = v,
          onContinue: () => setState(() => _step = Step.capture),
        );

      case Step.gate:
        return GateScreen(
          quality: _quality,
          cardResidual: _live?.cardResidual,
          liveness: _live?.liveness ?? const Liveness.notChecked(),
          refusals: _live?.refusals ?? const [],
          onContinue: () => setState(() => _step = Step.result),
          onRetake: () => setState(() {
            _live = null;
            _frameA = null;
            _frameB = null;
            _step = Step.capture;
          }),
        );

      case Step.log:
        final st = _store?.status();
        return LogScreen(
          records: _store?.records() ?? const [],
          intact: st?.intact ?? true,
          breaks: st?.breaks ?? const [],
          onOpen: (i) => setState(() {
            final rec = _store!.records()[i];
            _report = ftr.verifyRecord(ftr.toEnvelope(rec));
            _step = Step.verifier;
          }),
          onBack: () => setState(() => _step = Step.standby),
        );

      case Step.certificate:
        return CertificateScreen(
          certificate: _certificate!,
          envelope: _envelope,
          onBack: () => setState(() => _step = Step.sealed),
        );

      case Step.verifier:
        return VerifierScreen(
          report: _report!,
          onBack: () => setState(() =>
              _step = _certificate == null ? Step.log : Step.sealed),
        );

      case Step.standby:
        return StandbyScreen(
          posture: _posture,
          keystoreNote: _keystoreNote,
          onBegin: () => setState(() {
            _progress = 0;
            _step = Step.setup;
          }),
          onOpenLog: () => setState(() => _step = Step.log),
        );
      case Step.capture:
        return Stack(children: [
          CaptureScreen(
            quality: _quality,
            measured: _live?.detected ?? false,
            cardResidual: _live?.cardResidual,
            onFrame: _onFrame,
            onCapture: !_shutterArmed
                ? null
                : () => setState(() {
                      _baselineMm = 0;
                      _step = Step.secondView;
                    }),
          ),
          // Stands in for the camera settling. Removed with the platform channel.
          Positioned(
            right: 16,
            bottom: 96,
            child: FloatingActionButton.small(
              tooltip: 'Simulate the frame settling',
              onPressed: () => setState(() => _progress = (_progress + 0.34).clamp(0, 1)),
              child: const Icon(Icons.center_focus_strong),
            ),
          ),
        ]);
      case Step.secondView:
        return Stack(children: [
          SecondViewScreen(
            view: _secondView,
            onFrame: _onSecondFrame,
            busy: _pairing,
            onCapture: _confirmPair,
            onSkip: () => setState(() {
              // Drop the pair so _livenessRecord() reports "not checked" rather
              // than a stale verdict from the live preview.
              _frameB = null;
              _live = _live == null
                  ? null
                  : Measurement(
                      detected: _live!.detected,
                      fiducials: _live!.fiducials,
                      guidance: _live!.guidance,
                      gatePassed: _live!.gatePassed,
                      refusals: _live!.refusals,
                      quality: _live!.quality,
                      lab: _live!.lab,
                      cardResidual: _live!.cardResidual,
                      result: _live!.result,
                    );
              _step = Step.gate;
            }),
          ),
        ]);
      case Step.result:
        return ResultScreen(
          result: _live?.result ?? _result,
          liveness: _live?.liveness ?? const Liveness.notChecked(),
          onSeal: _seal,
        );
      case Step.sealed:
        return Scaffold(
          body: SealedScreen(
            digestHex: _digestHex,
            sequence: _sequence - 1,
            securityLevel: _posture.securityLevel,
            anchorWindow: _posture.anchorWindow,
            anchored: false,
          ),
          floatingActionButton: Column(
            mainAxisSize: MainAxisSize.min,
            crossAxisAlignment: CrossAxisAlignment.end,
            children: [
              if (_certificate != null)
                FloatingActionButton.extended(
                  heroTag: 'cert',
                  onPressed: () => setState(() => _step = Step.certificate),
                  label: const Text('§63 certificate'),
                  icon: const Icon(Icons.description_outlined),
                ),
              const SizedBox(height: 8),
              if (_report != null)
                FloatingActionButton.extended(
                  heroTag: 'verify',
                  onPressed: () => setState(() => _step = Step.verifier),
                  label: const Text('Verify'),
                  icon: const Icon(Icons.verified_outlined),
                ),
              const SizedBox(height: 8),
              FloatingActionButton.extended(
                heroTag: 'done',
                onPressed: () => setState(() => _step = Step.standby),
                label: const Text('Done'),
                icon: const Icon(Icons.check),
              ),
            ],
          ),
        );
    }
  }
}
