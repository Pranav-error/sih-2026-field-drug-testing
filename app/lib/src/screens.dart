/// The screens, from docs/DESIGN.md. Presentation only — every value shown here
/// arrives from the record layer, and none is computed in a widget.
library;

import 'dart:typed_data';

import 'package:flutter/material.dart';

import 'models.dart';
import 'tokens.dart';
import 'viewfinder.dart';
import 'widgets.dart';

/// Screen 01 — the device states its own trustworthiness before it is used.
///
/// Opens on a posture report, not a camera. The first question any later
/// challenge asks is not what the strip looked like; it is what kind of machine
/// was holding the camera.
class StandbyScreen extends StatelessWidget {
  const StandbyScreen({
    super.key,
    required this.posture,
    this.onBegin,
    this.cardId,
    this.bridgeEndpoint,
    this.bridgeReachable,
    this.onEditBridge,
    this.keystoreNote,
    this.onOpenLog,
  });

  final DevicePosture posture;
  final VoidCallback? onBegin;
  final VoidCallback? onOpenLog;

  /// Why the hardware guarantee is weaker than requested, when it is — for
  /// instance a handset with no discrete secure element falling back to the TEE.
  final String? keystoreNote;

  /// Retained so the web build can still point at a bridge; the handset build
  /// measures on-device and leaves these null.
  /// The card the operator actually entered, not a constant. A standby screen
  /// naming a card that is not the one in the officer's hand is a small lie
  /// that gets read as a device capability.
  final String? cardId;

  final String? bridgeEndpoint;
  final bool? bridgeReachable;
  final VoidCallback? onEditBridge;

  @override
  Widget build(BuildContext context) {
    // The chip and the warning key off whether the KEY is in hardware, which
    // the app can answer. Whether the DEVICE is trustworthy is a separate
    // question, answered from the attestation certificate by the verifier.
    final hw = posture.hardwareBacked;
    return AppScaffold(
      title: 'Ready',
      chip: StateChip(
        posture.securityLevel,
        colour: hw ? Tokens.negative : Tokens.abstain,
        soft: hw ? Tokens.negativeSoft : Tokens.abstainSoft,
      ),
      body: [
        Panel(title: 'Device posture', children: [
          Measured('Signing key', posture.securityLevel,
              tone: hw ? Tokens.negative : Tokens.abstain),
          Measured('Verified boot', posture.verifiedBootState,
              tone: posture.verifiedBootState == 'GREEN' ? Tokens.negative : Tokens.abstain),
          Measured(
              'Bootloader',
              posture.bootloaderLocked == null
                  ? 'IN ATTESTATION'
                  : (posture.bootloaderLocked! ? 'LOCKED' : 'UNLOCKED'),
              tone: posture.bootloaderLocked == true
                  ? Tokens.negative
                  : Tokens.abstain),
          Measured('OS patch level', posture.osPatchLevel),
          Measured(
              'Mock location',
              posture.mockLocation == null
                  ? 'Not checked yet'
                  : (posture.mockLocation! ? 'ON' : 'Off'),
              tone: posture.mockLocation == false
                  ? Tokens.negative
                  : Tokens.abstain),
        ]),
        if (keystoreNote != null && keystoreNote!.isNotEmpty)
          PresumptiveNotice(detail: keystoreNote!),
        if (keystoreNote != null && keystoreNote!.isNotEmpty)
          const SizedBox(height: 12),
        if (posture.usesSoftwareKey)
          const PresumptiveNotice(
            detail: 'This build signs with a software key. Records it produces are '
                'for development only and will fail verification. They must never be '
                'presented as evidence.',
          ),
        if (posture.securityLevelUnknown)
          const PresumptiveNotice(
            detail: 'Android did not report what backs this signing key. That is '
                'not the same as a software key, and it is not a pass either — '
                'the attestation certificate shipped with each record is '
                'authoritative, and the verifier reads the level from there.',
          ),
        if (posture.hardwareBacked && !posture.evidenceGrade)
          const PresumptiveNotice(
            detail: 'The key is in secure hardware. Whether this device booted '
                'unmodified is not the app\'s to assert — it is inside the '
                'attestation certificate, which ships with every record. The '
                'verifier reads it there, and fails a record that claims more '
                'than its certificate attests.',
          ),
        const SizedBox(height: 12),
        Panel(title: 'Measurement pipeline', children: [
          const Measured('Runs', 'On this device', tone: Tokens.negative),
          const Measured('Network required', 'None', tone: Tokens.negative),
          Measured('Reference card', cardId ?? 'Not set',
              tone: cardId == null ? Tokens.abstain : null),
          const SizedBox(height: 6),
          const Text(
            'Fiducial detection, the illumination fit, the colour transform and '
            'the abstention threshold all run here, in Dart. Corner detection is '
            'coarser than the reference implementation, and every record says so.',
            style: TextStyle(fontSize: 11, height: 1.4, color: Tokens.muted),
          ),
        ]),
        Panel(title: 'Record chain', tint: true, children: [
          Measured('Records on device', '${posture.recordCount}'),
          Measured('Awaiting anchor', '${posture.unanchored}',
              tone: posture.unanchored > 0 ? Tokens.abstain : Tokens.negative),
          // The open window is the honest limit of what the chain proves, so it
          // sits on the home screen rather than in a settings pane.
          Measured('Open window', posture.anchorWindow,
              tone: posture.unanchored > 0 ? Tokens.abstain : Tokens.muted),
        ]),
      ],
      footer: [
        PrimaryButton('Begin field test', onPressed: onBegin),
        const SizedBox(height: 8),
        if (onOpenLog != null) ...[
          PrimaryButton.ghost('Open record log', onPressed: onOpenLog),
          const SizedBox(height: 8),
        ],
        const Text(
          'Presumptive testing only. Results are not confirmatory and do not '
          'replace laboratory analysis.',
          textAlign: TextAlign.center,
          style: TextStyle(fontSize: 11.5, height: 1.4, color: Tokens.muted),
        ),
      ],
    );
  }
}

/// Screen 03 — the guidance overlay is a measurement instrument.
///
/// The shutter arms only when the frame is measurable. A bad frame produces a
/// confident wrong answer in exactly the conditions where that does most damage.
class CaptureScreen extends StatelessWidget {
  const CaptureScreen({
    super.key,
    required this.quality,
    this.onCapture,
    this.onFrame,
    this.measured = false,
    this.cardResidual,
  });

  final CaptureQuality quality;
  final VoidCallback? onCapture;
  final Future<void> Function(Uint8List)? onFrame;

  /// True once the real pipeline is answering, so the panel can stop saying the
  /// numbers are placeholders — because they no longer are.
  final bool measured;
  final double? cardResidual;

  @override
  Widget build(BuildContext context) {
    // When a real measurement is present the caller has already applied the
    // pipeline's own gate, so an armed shutter is signalled by onCapture being
    // non-null. Duplicating the thresholds here would let the UI and the record
    // disagree about whether a frame was usable.
    final locked = measured ? onCapture != null : quality.locked;
    return AppScaffold(
      title: 'Frame the card',
      step: 1,
      chip: StateChip(locked ? 'Locked' : 'Aligning',
          colour: locked ? Tokens.negative : Tokens.abstain,
          soft: locked ? Tokens.negativeSoft : Tokens.abstainSoft),
      body: [
        Viewfinder(guidance: quality.guidance, locked: locked, onFrame: onFrame),
        const SizedBox(height: 12),
        Panel(
            title: measured
                ? 'Live capture quality — measured'
                : 'Capture quality — not yet measured',
            children: [
          Measured('Fiducial lock', '${quality.fiducialsFound}/4',
              tone: quality.fiducialsFound == 4 ? Tokens.negative : Tokens.abstain),
          Measured('Illumination', '${(quality.illumination * 100).round()}%',
              limit: '85%'),
          Measured('Focus', quality.focus.toStringAsFixed(2), limit: '0.85'),
          Measured('Card angle', '${quality.tiltDegrees.round()}°', limit: '25°'),
          Measured('Clipped', '${(quality.clippedFraction * 100).toStringAsFixed(1)}%',
              limit: '2.0%'),
          if (measured && cardResidual != null)
            Measured('Card residual', '${cardResidual!.toStringAsFixed(2)} dE',
                limit: '3.00',
                tone: cardResidual! <= 3 ? Tokens.negative : Tokens.positive),
          const SizedBox(height: 6),
          // Rule 8 again: never let a live picture imply a live measurement.
          Text(
            measured
                ? 'These are real measurements of the frame in front of the '
                    'camera, from the same pipeline the verifier re-runs.'
                : 'The camera is live, but these figures are placeholders. Start '
                    'the measure bridge to get real ones.',
            style: TextStyle(
                fontSize: 11, height: 1.4,
                color: measured ? Tokens.muted : Tokens.abstain),
          ),
        ]),
      ],
      footer: [
        PrimaryButton(locked ? 'Capture frame' : 'Hold steady…',
            onPressed: locked ? onCapture : null),
        const SizedBox(height: 8),
        const Text('The card and the reaction well must be in one frame, on one '
            'plane, under one light.',
            textAlign: TextAlign.center,
            style: TextStyle(fontSize: 11.5, height: 1.4, color: Tokens.muted)),
      ],
    );
  }
}

/// Screen 03b — the second view.
///
/// The screen most likely to be cut by someone who does not know why it exists.
/// A quality print passes every colour check; what it cannot fake is depth. This
/// asks the operator to move a few centimetres, without explaining stereo
/// geometry to somebody standing in the sun wearing gloves.
class SecondViewScreen extends StatelessWidget {
  const SecondViewScreen({
    super.key,
    required this.view,
    this.onCapture,
    this.onFrame,
    this.onSkip,
    this.busy = false,
  });

  final SecondView view;
  final VoidCallback? onCapture;
  final Future<void> Function(Uint8List)? onFrame;

  /// Proceed on the first frame alone. Offered because field conditions are not
  /// negotiable with software — but the record then says a liveness check was
  /// not performed, and the verifier reports that it cannot be distinguished
  /// from a photograph of a card. Skipping is allowed; hiding it is not.
  final VoidCallback? onSkip;

  /// True while the two-view check is running on the pair.
  final bool busy;

  @override
  Widget build(BuildContext context) {
    return AppScaffold(
      title: 'Second view',
      step: 2,
      chip: StateChip(view.ready ? 'Far enough' : 'Keep moving',
          colour: view.ready ? Tokens.negative : Tokens.abstain,
          soft: view.ready ? Tokens.negativeSoft : Tokens.abstainSoft),
      body: [
        // Without this the second viewfinder is indistinguishable from the
        // first, and taking a frame reads as having gone backwards.
        Container(
          width: double.infinity,
          margin: const EdgeInsets.only(bottom: 10),
          padding: const EdgeInsets.fromLTRB(11, 9, 11, 10),
          decoration: BoxDecoration(
            color: Tokens.negativeSoft,
            border: Border.all(color: Tokens.negative),
            borderRadius: BorderRadius.circular(5),
          ),
          child: Row(children: [
            const Icon(Icons.check_circle, size: 17, color: Tokens.negative),
            const SizedBox(width: 8),
            Expanded(
              child: RichText(
                text: const TextSpan(
                  style: TextStyle(fontSize: 12.5, height: 1.4, color: Tokens.ink2),
                  children: [
                    TextSpan(
                        text: 'First frame captured. ',
                        style: TextStyle(
                            fontWeight: FontWeight.w700, color: Tokens.negative)),
                    TextSpan(text: 'Now move a few centimetres and take a second '
                        'one — that is what proves the card was really there.'),
                  ],
                ),
              ),
            ),
          ]),
        ),
        Viewfinder(guidance: view.guidance, locked: view.ready, onFrame: onFrame),
        const SizedBox(height: 12),
        Panel(title: 'Movement', children: [
          // Deliberately not a number in millimetres: the operator cannot act on
          // "24 mm", only on "far enough".
          ClipRRect(
            borderRadius: BorderRadius.circular(2),
            child: LinearProgressIndicator(
              value: view.progress,
              minHeight: 5,
              backgroundColor: Tokens.ruleSoft,
              valueColor: AlwaysStoppedAnimation(
                  view.ready ? Tokens.negative : Tokens.abstain),
            ),
          ),
          const SizedBox(height: 8),
          Measured('Card in frame', view.cardVisible ? 'Yes' : 'No',
              tone: view.cardVisible ? Tokens.negative : Tokens.abstain),
          Measured('Moved far enough', view.ready ? 'Yes' : 'Not yet',
              tone: view.ready ? Tokens.negative : Tokens.abstain),
        ]),
        const PresumptiveNotice(
          detail: 'Two views from slightly different positions prove the card was '
              'physically present. A photograph of a card is flat, and cannot '
              'produce this — at any print quality.',
        ),
      ],
      footer: [
        PrimaryButton(
            busy
                ? 'Checking both frames…'
                : (view.ready ? 'Capture second frame' : 'Move a little further'),
            onPressed: (view.ready && !busy) ? onCapture : null),
        const SizedBox(height: 8),
        if (onSkip != null)
          PrimaryButton.ghost('Continue with one frame only',
              onPressed: busy ? null : onSkip),
        const SizedBox(height: 8),
        Text(
          onSkip == null
              ? 'Both frames are hashed into the record. The second one is '
                  'evidence too.'
              : 'Both frames are hashed into the record. Continuing with one '
                  'records that no liveness check was performed — the result '
                  'cannot then be told apart from a photograph of a card.',
          textAlign: TextAlign.center,
          style: const TextStyle(fontSize: 11.5, height: 1.4, color: Tokens.muted),
        ),
      ],
    );
  }
}

/// Screen 05 — a prediction set, not a percentage.
///
/// An abstention is rendered with the same weight as a call, never as an error
/// or a prompt to retry until the answer improves.
class ResultScreen extends StatelessWidget {
  const ResultScreen({super.key, required this.result, this.onSeal,
      this.liveness = const Liveness.notChecked(),
      this.refusals = const [],
      this.guidance,
      this.onRetake,
      this.sealError});

  /// Null when the frame produced no measurement at all.
  ///
  /// It used to fall back to a hardcoded constant, so a failed scan rendered as
  /// a plausible inconclusive reading and there was no way to tell a working
  /// capture from a broken one. The constant was also arithmetically impossible
  /// — it claimed a point 4.12 from one locus and 5.02 from another that are
  /// 30.20 apart.
  final TestResult? result;

  /// What the pipeline refused on, when there is no result.
  final List<String> refusals;

  /// What the operator should do about it.
  final String? guidance;

  final VoidCallback? onSeal;
  final Liveness liveness;

  /// Why the last seal attempt failed, if it did. Shown rather than swallowed.
  final String? sealError;

  final VoidCallback? onRetake;

  @override
  Widget build(BuildContext context) {
    final r = result;
    if (r == null) return _noMeasurement(context);
    return _measured(context, r);
  }

  /// No result is a refusal, not a result. Nothing here may be sealed: there is
  /// no measurement to seal, and the previous behaviour put a canned one into
  /// the record.
  Widget _noMeasurement(BuildContext context) => AppScaffold(
        title: 'No measurement',
        chip: const StateChip('Refused',
            colour: Tokens.abstain, soft: Tokens.abstainSoft),
        body: [
          Panel(title: 'This frame produced no reading', children: [
            const Text(
              'The pipeline did not return a measurement, so there is nothing to '
              'classify and nothing to seal. This is not an inconclusive result — '
              'it is the absence of one.',
              style: TextStyle(fontSize: 12.5, height: 1.5, color: Tokens.ink2),
            ),
            if (guidance != null && guidance!.isNotEmpty) ...[
              const SizedBox(height: 8),
              Measured('What to do', guidance!),
            ],
          ]),
          if (refusals.isNotEmpty)
            Panel(title: 'Refused on', children: [
              for (final r in refusals)
                Text('· $r',
                    style: const TextStyle(
                        fontSize: 12, height: 1.5, color: Tokens.abstain)),
            ]),
          const PresumptiveNotice(
            detail: 'Presumptive only. This is a screening indication, not '
                'confirmation of identity or quantity. Laboratory analysis under '
                'NDPS procedure remains required.',
          ),
        ],
        footer: [PrimaryButton('Retake the frame', onPressed: onRetake)],
      );

  Widget _measured(BuildContext context, TestResult result) {
    final outcome = result.outcome;
    final setText =
        result.predictionSet.isEmpty ? '∅' : result.predictionSet.join(', ');

    return AppScaffold(
      title: 'Result',
      chip: StateChip('Presumptive', colour: outcome.colour, soft: outcome.soft),
      body: [
        Container(
          width: double.infinity,
          padding: const EdgeInsets.fromLTRB(13, 12, 13, 13),
          decoration: BoxDecoration(
            color: outcome.soft,
            border: Border.all(color: outcome.colour),
            borderRadius: BorderRadius.circular(6),
          ),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Text('OUTCOME',
                  style: Tokens.monoStyle(
                      size: 10, weight: FontWeight.w600, colour: outcome.colour, spacing: 1.2)),
              const SizedBox(height: 5),
              Text(outcome.label,
                  style: TextStyle(
                      fontSize: 21, fontWeight: FontWeight.w700, color: outcome.colour)),
              const SizedBox(height: 5),
              Text('prediction set = { $setText }', style: Tokens.monoStyle()),
              const SizedBox(height: 6),
              Text(result.reason,
                  style: const TextStyle(fontSize: 12.5, height: 1.4, color: Tokens.ink2)),
            ],
          ),
        ),
        const SizedBox(height: 12),
        Panel(title: 'Measurement', tint: true, children: [
          if (result.lab != null)
            Measured('Lab*',
                result.lab!.map((v) => v.toStringAsFixed(1)).join('  ')),
          Measured('Risk level α', result.alpha.toStringAsFixed(2),
              limit: 'coverage ≥ ${((1 - result.alpha) * 100).round()}%'),
          Measured('Threshold', '${result.threshold.toStringAsFixed(2)} dE'),
          for (final e in result.scores.entries)
            Measured('  ΔE to ${e.key}', e.value.toStringAsFixed(2),
                tone: e.value <= result.threshold ? Tokens.ink : Tokens.muted),
        ]),
        Panel(title: 'Liveness', tint: true, children: [
          if (!liveness.checked)
            Measured('Two-view check', 'NOT RUN', tone: Tokens.abstain)
          else ...[
            Measured('Parallax measured', '${liveness.measuredPx.toStringAsFixed(1)} px',
                limit: '${liveness.predictedPx.toStringAsFixed(1)} px predicted',
                tone: liveness.live ? Tokens.negative : Tokens.positive),
            Measured('Physically present', liveness.live ? 'Yes' : 'NO — scene was flat',
                tone: liveness.live ? Tokens.negative : Tokens.positive),
          ],
          const SizedBox(height: 4),
          Text(
            liveness.checked
                ? (liveness.live
                    ? 'The scene had depth. A print or a screen gives zero parallax.'
                    : liveness.reason)
                : liveness.reason,
            style: const TextStyle(fontSize: 11.5, height: 1.4, color: Tokens.muted),
          ),
        ]),
        const PresumptiveNotice(),
      ],
      footer: [
        if (sealError != null) ...[
          Container(
            width: double.infinity,
            padding: const EdgeInsets.fromLTRB(10, 8, 10, 9),
            margin: const EdgeInsets.only(bottom: 8),
            decoration: BoxDecoration(
              color: Tokens.positiveSoft,
              border: Border.all(color: Tokens.positive),
              borderRadius: BorderRadius.circular(4),
            ),
            child: Text('Could not seal: $sealError',
                style: const TextStyle(
                    fontSize: 11.5, height: 1.4, color: Tokens.positive)),
          ),
        ],
        PrimaryButton('Seal record', onPressed: onSeal),
        const SizedBox(height: 8),
        const Text(
          'Sealing is irreversible. The result is written to the chain exactly as '
          'shown, including an inconclusive outcome.',
          textAlign: TextAlign.center,
          style: TextStyle(fontSize: 11.5, height: 1.4, color: Tokens.muted),
        ),
      ],
    );
  }
}

/// Screen 06 — the screen that states the limits of its own proof.
class SealedScreen extends StatelessWidget {
  const SealedScreen({
    super.key,
    required this.digestHex,
    required this.sequence,
    required this.securityLevel,
    required this.anchorWindow,
    required this.anchored,
    this.stored = false,
    this.storeError,
    this.frameError,
  });

  final String digestHex;
  final int sequence;
  final String securityLevel;
  final String anchorWindow;
  final bool anchored;

  /// Whether the record reached storage. A record that is shown but not written
  /// is not a record, so the screen must not imply it was kept.
  final bool stored;

  /// Why the write failed, when it did. A record that is not on disk is not in
  /// the chain, and an officer who cannot see the reason cannot fix it.
  final String? storeError;

  /// The record reached the chain but its frames did not. Reported separately,
  /// because it does not mean the record was lost.
  final String? frameError;

  @override
  Widget build(BuildContext context) {
    return AppScaffold(
      title: 'Record sealed',
      chip: const StateChip('Signed', colour: Tokens.negative, soft: Tokens.negativeSoft),
      body: [
        Panel(title: 'Field Test Record #$sequence', children: [
          const Measured('Encoding', 'Canonical CBOR'),
          const Measured('Algorithm', 'SHA-256'),
          const SizedBox(height: 6),
          SelectableText(
            digestHex,
            style: Tokens.monoStyle(size: 11.5, colour: Tokens.ink2).copyWith(height: 1.5),
          ),
        ]),
        Panel(title: 'Storage', children: [
          Measured('Written to the ledger', stored ? 'Yes' : 'NO — memory only',
              tone: stored ? Tokens.negative : Tokens.abstain),
          if (!stored && storeError != null) ...[
            const SizedBox(height: 4),
            Text(storeError!,
                style: Tokens.monoStyle(size: 10, colour: Tokens.negative)),
            const SizedBox(height: 2),
            const Text(
              'This record exists only in memory. It is not in the chain, and '
              'closing the app loses it.',
              style: TextStyle(fontSize: 11, height: 1.4, color: Tokens.muted),
            ),
          ],
          if (stored && frameError != null) ...[
            const SizedBox(height: 4),
            const Measured('Frames beside the record', 'NOT WRITTEN',
                tone: Tokens.abstain),
            Text(frameError!,
                style: Tokens.monoStyle(size: 10, colour: Tokens.abstain)),
            const SizedBox(height: 2),
            const Text(
              'The record is sealed and in the chain. Its image hashes name '
              'files that are not on this device, so the verifier cannot re-check '
              'them from here.',
              style: TextStyle(fontSize: 11, height: 1.4, color: Tokens.muted),
            ),
          ],
        ]),
        Panel(title: 'Signature', children: [
          Measured('Key', securityLevel,
              tone: securityLevel == 'SOFTWARE' ? Tokens.abstain : Tokens.negative),
          // Was 'Fingerprint'. The record directly above carries
          // biometric_unlock_used: false, because the key is created without
          // setUserAuthenticationRequired — nothing gates its use. The screen
          // asserting a fingerprint that never happened is the same false claim
          // that was removed from the record itself.
          const Measured('Use authorised by', 'Nothing', tone: Tokens.abstain),
          const SizedBox(height: 4),
          const Text(
            'The key is not gated on user authentication, so no fingerprint or '
            'PIN was required to sign. The record says so too, and both '
            'verifiers state it.',
            style: TextStyle(fontSize: 11, height: 1.4, color: Tokens.muted),
          ),
        ]),
        PresumptiveNotice(
          detail: anchored
              ? 'This record is anchored. Its position in the ledger is externally witnessed.'
              : 'This record proves it was created no earlier than record #${sequence - 1} '
                  'and no later than the next anchor ($anchorWindow open). It does not '
                  'prove the wall-clock time, and it does not claim to.',
        ),
      ],
      footer: const [
        Text('Presumptive field test. Not confirmatory.',
            textAlign: TextAlign.center,
            style: TextStyle(fontSize: 11.5, color: Tokens.muted)),
      ],
    );
  }
}

/// The chrome every screen shares: app bar with a state chip, a scrolling body,
/// and a fixed footer holding the primary action within thumb reach.
class AppScaffold extends StatelessWidget {
  const AppScaffold({
    super.key,
    required this.title,
    required this.chip,
    required this.body,
    this.footer = const [],
    this.step,
  });

  final String title;
  final Widget chip;
  final List<Widget> body;
  final List<Widget> footer;

  /// Which of the two capture frames this is, when it is one of them.
  final int? step;

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: Tokens.ground,
      appBar: AppBar(
        backgroundColor: Tokens.surface,
        surfaceTintColor: Colors.transparent,
        // Flexible, because the app bar also carries a state chip and a step
        // counter: an unconstrained Row here overflows on a narrow handset.
        title: Row(children: [
          Flexible(
            child: Text(title,
                overflow: TextOverflow.ellipsis,
                style: const TextStyle(
                    fontSize: 16, fontWeight: FontWeight.w600, color: Tokens.ink)),
          ),
          if (step != null) ...[
            const SizedBox(width: 7),
            Text('$step/2', style: Tokens.monoStyle(
                size: 11, weight: FontWeight.w600, colour: Tokens.muted)),
          ],
        ]),
        actions: [Padding(padding: const EdgeInsets.only(right: 14), child: Center(child: chip))],
        bottom: const PreferredSize(
          preferredSize: Size.fromHeight(1),
          child: Divider(height: 1, color: Tokens.ruleSoft),
        ),
      ),
      body: SafeArea(
        child: Column(
          children: [
            Expanded(
              child: SingleChildScrollView(
                padding: const EdgeInsets.fromLTRB(14, 14, 14, 8),
                child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: body),
              ),
            ),
            if (footer.isNotEmpty)
              Container(
                width: double.infinity,
                padding: const EdgeInsets.fromLTRB(14, 11, 14, 14),
                decoration: const BoxDecoration(
                  color: Tokens.surface,
                  border: Border(top: BorderSide(color: Tokens.ruleSoft)),
                ),
                child: Column(children: footer),
              ),
          ],
        ),
      ),
    );
  }
}
