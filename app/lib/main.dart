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
import 'package:device_info_plus/device_info_plus.dart';

import 'src/certificate.dart';
import 'package:share_plus/share_plus.dart';
import 'src/handoff.dart';
import 'src/location.dart';
import 'src/platform_keystore.dart';
import 'src/screens_extra.dart';
import 'src/store.dart';

import 'package:flutter/foundation.dart';
import 'package:flutter/material.dart';
import 'package:ftr_verify/ftr_verify.dart' as ftr;

import 'src/models.dart';
import 'src/record_id.dart';
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

enum Step {
  standby, setup, capture, secondView, gate, result, sealed, log, certificate,
  verifier, handoff,
}

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
  String _operatorId = '';
  Map<String, Object?> _deviceInfo = const {};
  String _cardId = 'CARD-IN-2026-0417';
  String _printBatch = 'B12';
  String _fir = '';
  String _memo = '';
  Certificate? _certificate;
  Map<String, Object?> _envelope = const {};

  BundleResult? _bundle;
  bool _exporting = false;
  String? _exportError;
  ftr.Report? _report;
  String? _sealError;
  bool _storedOk = false;
  String? _storeError;

  /// The record is in the chain but its frames are not beside it. A separate
  /// failure from the record write, and it must not read as the same one.
  String? _frameError;

  /// Set the first time a real position is read. Stays null before that: "off"
  /// is a finding, and claiming it before looking is a fabricated value.
  bool? _mockLocationSeen;
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
        // Not the app's to assert — same reason as verified boot above. It is
        // inside the attestation certificate, which ships with every record.
        bootloaderLocked: null,
        osPatchLevel: _hardware != null
            ? 'IN ATTESTATION'
            : _software.attestation().osPatchLevel,
        // Null until a position has actually been read, which needs the
        // permission prompt and so does not happen at launch.
        mockLocation: _mockLocationSeen,
        recordCount: _store?.length ?? _sequence,
        unanchored: _store?.unanchored ?? _sequence,
        lastAnchorAt: _store?.lastAnchorAt,
      );

  @override
  void initState() {
    super.initState();
    _openKeystore();
    _openStore();
    _readDevice();
  }

  /// Make and model for the §63 certificate, which asks for them by name.
  ///
  /// Serial number and IMEI are **not** readable without privileged permissions
  /// on any modern Android, so they stay absent and the certificate reports them
  /// as fields the record cannot supply — which is the honest outcome, not a bug.
  Future<void> _readDevice() async {
    try {
      final info = await DeviceInfoPlugin().androidInfo;
      if (!mounted) return;
      setState(() => _deviceInfo = {
            'make_model': '${info.manufacturer} ${info.model}',
            'os_patch_level': '${info.version.securityPatch}',
            'android_release': info.version.release,
            'hardware': info.hardware,
          });
    } catch (_) {
      // Not Android, or the plugin is unavailable. The certificate then names
      // make and model as missing rather than inventing them.
    }
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
      // A hardware keystore that failed says why. Falling back to a
      // development key silently is how an operator ends up unable to explain
      // a SOFTWARE record in court.
      _keystoreNote = ks?.note ?? PlatformKeystore.lastFailure ?? '';
    });
  }

  SecondView get _secondView =>
      SecondView(baselineMm: _baselineMm, cardVisible: true);

  // The hardcoded `_result` that used to live here is gone. It was shown
  // whenever the real measurement produced nothing, so a failed scan rendered
  // as a plausible inconclusive reading — and it was arithmetically impossible
  // besides, claiming a point 4.12 from one locus and 5.02 from another that
  // are 30.20 apart. There is no fallback now: no measurement is a refusal.

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
    try {
      await _sealInner();
    } catch (e) {
      // Never silent. A seal that fails and says nothing is indistinguishable
      // from a seal that worked, which is the worst possible failure mode for
      // something whose entire job is producing trustworthy records.
      if (!mounted) return;
      setState(() => _sealError = '$e');
    }
  }

  Future<void> _sealInner() async {
    // No fallback. Sealing a canned result would put a measurement into the
    // record that no camera produced — the one thing an evidentiary record must
    // never do.
    //
    // But a refusal IS sealable, and must be. A frame the instrument would not
    // read is evidence too, and letting an operator retake until they like the
    // answer — with the rejected frames leaving no trace — is precisely the
    // attack the ledger exists to stop. Removing the canned fallback took this
    // with it for one build: the gate offered "Seal the refusal" and the next
    // screen had only a Retake button.
    final shown = _live?.result;
    // Read the position at the moment of sealing, not at app start.
    final fix = await LocationReader.read();
    // Now the standby screen can stop saying "not checked yet" about a thing
    // that has been checked.
    _mockLocationSeen = fix.mocked;
    final frame = _frameA;
    if (frame == null) {
      throw StateError('no captured frame to seal — capture one first');
    }
    final body = ftr.buildBody(
      recordUuid: newRecordUuid(),
      sequence: _store?.nextSequence ?? _sequence,
      prevRecordHash: _store?.head ?? _chainHead,
      // UTC with an explicit Z, plus the offset the handset was set to.
      // A bare local ISO string carries no zone at all: a record made at 07:06
      // IST reads as 07:06 in whatever zone the reader assumes. The timestamp
      // is only a claim either way — an ambiguous claim is strictly worse.
      capturedAt: {
        'device_clock': DateTime.now().toUtc().toIso8601String(),
        'device_utc_offset_minutes': DateTime.now().timeZoneOffset.inMinutes,
      },
      operator_: {
        if (_operatorId.isNotEmpty) 'id': _operatorId,
        // FALSE would be a lie if we claimed otherwise: the signing key is not
        // created with setUserAuthenticationRequired, so nothing gates its use
        // behind a fingerprint. Asserting a biometric that never happened is
        // exactly the kind of claim this project exists to refuse.
        'biometric_unlock_used': false,
        'identified': _operatorId.isNotEmpty,
      },
      kit: {'reagent_type': _reagent.toLowerCase()},
      card: {'card_id': _cardId, 'print_batch': _printBatch},
      capture: {
        'raw_image_sha256': ftr.sha256(frame),
        // The second view is evidence too, and is bound like the first.
        if (_frameB != null) 'second_frame_sha256': ftr.sha256(_frameB!),
      },
      // What was actually measured on this frame. Sealing the fallback constant
      // would have produced a record that did not match the screen above it —
      // the one thing an evidentiary record must never do.
      colorimetry: {
        'measured': _live?.detected ?? false,
        if (shown?.lab != null)
          'lab_x100': shown!.lab!.map((v) => (v * 100).round()).toList(),
        if (_live?.cardResidual != null)
          'card_residual_x1000': (_live!.cardResidual! * 1000).round(),
        'gate_passed': _live?.gatePassed ?? false,
        'refusals': _live?.refusals ?? const <String>[],
      },
      // A refusal carries no classification, and says so rather than carrying
      // an empty one that reads like a negative result.
      classification: shown == null
          ? const {'measured': false}
          : {
              'measured': true,
              'alpha_x1000': (shown.alpha * 1000).round(),
              'threshold_x1000': (shown.threshold * 1000).round(),
              'prediction_set': shown.predictionSet,
              'label': shown.label,
              'scores_x1000': {
                for (final e in shown.scores.entries)
                  e.key: (e.value * 1000).round(),
              },
            },
      // The measured liveness, or an explicit "not checked" — never a default
      // that would read as having passed.
      liveness: _livenessRecord(),
      // Which implementation produced these numbers. A verifier re-running the
      // reference pipeline needs to know why the last digit may differ.
      pipelineName: 'dart-on-device',
      // A real fix, or an explicit statement that there is none. Never four
      // invented channels agreeing about a position nobody read.
      locationBundle: fix.toRecord(),
      // Verified boot and bootloader state are deliberately absent: they live in
      // the attestation certificate, and the app must not assert them.
      device: {..._deviceInfo, 'state_source': 'attestation certificate'},
    );

    // Hardware signing is asynchronous — the key is inside the secure element
    // and only the digest crosses the boundary.
    final ftr.SealedRecord rec;
    final hw = _hardware;
    if (hw != null) {
      final bodyCbor = ftr.encode(body);
      final att = hw.attestation();
      rec = ftr.SealedRecord(
        bodyCbor: bodyCbor,
        digest: ftr.sha256(bodyCbor),
        // The body, not the digest: the secure element hashes it itself.
        signature: await hw.signBody(bodyCbor),
        publicKeyDer: att.publicKeyDer,
        attestation: att.toRecord(),
      );
    } else {
      rec = ftr.seal(body, _software);
    }
    // Persist BEFORE the mounted check. A `return` here used to drop a record
    // that was already signed: background the app in the window between the
    // secure element returning a signature and the write, and the record was
    // gone with nothing said. Whether this widget is still on screen has no
    // bearing on whether a sealed record belongs in the ledger.
    var stored = false;
    String? storeError;
    String? frameError;
    try {
      if (_store != null) {
        _store!.append(rec);
        // The append is what puts the record in the chain, so `stored` is true
        // from here. The frames are a separate failure: they can fail on their
        // own, and reporting "NO — memory only" about a record that IS in the
        // chain is the more dangerous error — an officer would re-run a test
        // that already sealed.
        stored = true;
        try {
          _store!.writeFrames(rec.sequence, frameA: frame, frameB: _frameB);
        } catch (e) {
          frameError = '$e';
        }
      }
    } catch (e) {
      // The reason must reach the screen. "NO — memory only" with no cause is
      // the same silence that let the seal failure vanish: an officer cannot
      // act on it, and neither can anyone reading the log afterwards.
      stored = false;
      storeError = '$e';
    }
    if (!mounted) return;

    final schedule = await ScheduleLoader.load();
    final cert = buildCertificate(rec, schedule);
    if (!mounted) return;
    setState(() {
      _certificate = cert;
      _envelope = buildEnvelope(rec, certificateStatus: cert.status);
      _report = ftr.verifyRecord(ftr.toEnvelope(rec));
      _sealError = null;
      _storedOk = stored;
      _storeError = storeError;
      _frameError = frameError;
      _digestHex = ftr.hex(rec.digest);
      _chainHead = rec.digest;
      if (!stored) _sequence += 1;
      _step = Step.sealed;
    });
  }

  @override
  Widget build(BuildContext context) => PhoneFrame(child: _screen());

  /// Write the bundle. Errors surface on the screen rather than vanishing —
  /// a handoff that silently did nothing is worse than one that failed loudly.
  Future<void> _export() async {
    final store = _store;
    if (store == null) {
      setState(() => _exportError = 'No filesystem on this platform.');
      return;
    }
    setState(() {
      _exporting = true;
      _exportError = null;
    });
    try {
      final schedule = await ScheduleLoader.load();
      final res = await exportChain(store,
          certificateFor: (rec) => buildCertificate(rec, schedule));
      if (mounted) setState(() => _bundle = res);
    } catch (e) {
      if (mounted) setState(() => _exportError = '$e');
    } finally {
      if (mounted) setState(() => _exporting = false);
    }
  }

  Future<void> _shareBundle() async {
    final b = _bundle;
    if (b == null) return;
    try {
      await SharePlus.instance.share(ShareParams(
        files: b.files.map((f) => XFile(f.path)).toList(),
        subject: 'Field Test Record handoff — ${b.files.length} file(s)',
      ));
    } catch (e) {
      if (mounted) setState(() => _exportError = 'Share failed: $e');
    }
  }

  Widget _screen() {
    switch (_step) {
      case Step.setup:
        return SetupScreen(
          reagent: _reagent,
          onReagent: (r) => setState(() => _reagent = r),
          operatorId: _operatorId,
          onOperator: (v) => _operatorId = v,
          cardId: _cardId,
          onCardId: (v) => _cardId = v,
          printBatch: _printBatch,
          onPrintBatch: (v) => _printBatch = v,
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
          storePath: _store?.path ?? 'no filesystem on this platform',
          bytesUsed: _store?.bytesUsed ?? 0,
          onOpen: (i) => setState(() {
            final rec = _store!.records()[i];
            _report = ftr.verifyRecord(ftr.toEnvelope(rec));
            _step = Step.verifier;
          }),
          onBack: () => setState(() => _step = Step.standby),
        );

      case Step.handoff:
        return HandoffScreen(
          recordCount: _store?.length ?? 0,
          unanchored: _store?.unanchored ?? 0,
          lastAnchor: _store?.lastAnchor,
          result: _bundle,
          busy: _exporting,
          error: _exportError,
          onExport: _export,
          onShare: _shareBundle,
          onBack: () => setState(() => _step = Step.log),
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
          cardId: _cardId.isEmpty ? null : _cardId,
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
          result: _live?.result,
          refusals: _live?.refusals ?? const ['no frame was measured'],
          guidance: _live?.guidance,
          liveness: _live?.liveness ?? const Liveness.notChecked(),
          sealError: _sealError,
          onSeal: _seal,
          onRetake: () => setState(() {
            _frameA = null;
            _frameB = null;
            _live = null;
            _step = Step.capture;
          }),
        );
      case Step.sealed:
        return Scaffold(
          body: SealedScreen(
            stored: _storedOk,
            storeError: _storeError,
            frameError: _frameError,
            digestHex: _digestHex,
            // The store owns sequencing once it exists; _sequence is only the
            // in-memory fallback for a platform with no filesystem.
            sequence: (_store?.length ?? _sequence) - 1,
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
