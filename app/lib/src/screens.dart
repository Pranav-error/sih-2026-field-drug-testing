/// The screens, from docs/DESIGN.md. Presentation only — every value shown here
/// arrives from the record layer, and none is computed in a widget.
library;

import 'package:flutter/material.dart';

import 'models.dart';
import 'tokens.dart';
import 'widgets.dart';

/// Screen 01 — the device states its own trustworthiness before it is used.
///
/// Opens on a posture report, not a camera. The first question any later
/// challenge asks is not what the strip looked like; it is what kind of machine
/// was holding the camera.
class StandbyScreen extends StatelessWidget {
  const StandbyScreen({super.key, required this.posture, this.onBegin});

  final DevicePosture posture;
  final VoidCallback? onBegin;

  @override
  Widget build(BuildContext context) {
    final hw = posture.evidenceGrade;
    return _Scaffold(
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
          Measured('Bootloader', posture.bootloaderLocked ? 'LOCKED' : 'UNLOCKED',
              tone: posture.bootloaderLocked ? Tokens.negative : Tokens.abstain),
          Measured('OS patch level', posture.osPatchLevel),
          Measured('Mock location', posture.mockLocation ? 'ON' : 'Off',
              tone: posture.mockLocation ? Tokens.abstain : Tokens.negative),
        ]),
        if (!hw)
          const PresumptiveNotice(
            detail: 'This build signs with a software key. Records it produces are '
                'for development only and will fail verification. They must never be '
                'presented as evidence.',
          ),
        const SizedBox(height: 12),
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
  const CaptureScreen({super.key, required this.quality, this.onCapture});

  final CaptureQuality quality;
  final VoidCallback? onCapture;

  @override
  Widget build(BuildContext context) {
    final locked = quality.locked;
    return _Scaffold(
      title: 'Frame the card',
      chip: StateChip(locked ? 'Locked' : 'Aligning',
          colour: locked ? Tokens.negative : Tokens.abstain,
          soft: locked ? Tokens.negativeSoft : Tokens.abstainSoft),
      body: [
        AspectRatio(
          aspectRatio: 3 / 4,
          child: Container(
            decoration: BoxDecoration(
              color: const Color(0xFF16131F),
              borderRadius: BorderRadius.circular(6),
            ),
            alignment: Alignment.bottomLeft,
            padding: const EdgeInsets.all(10),
            child: Container(
              padding: const EdgeInsets.all(9),
              decoration: BoxDecoration(
                color: Colors.black.withValues(alpha: 0.82),
                borderRadius: BorderRadius.circular(4),
              ),
              child: Text(quality.guidance,
                  style: const TextStyle(color: Color(0xFFEDEAF4), fontSize: 12.5)),
            ),
          ),
        ),
        const SizedBox(height: 12),
        Panel(title: 'Live capture quality', children: [
          Measured('Fiducial lock', '${quality.fiducialsFound}/4',
              tone: quality.fiducialsFound == 4 ? Tokens.negative : Tokens.abstain),
          Measured('Illumination', '${(quality.illumination * 100).round()}%',
              limit: '85%'),
          Measured('Focus', quality.focus.toStringAsFixed(2), limit: '0.85'),
          Measured('Card angle', '${quality.tiltDegrees.round()}°', limit: '25°'),
          Measured('Clipped', '${(quality.clippedFraction * 100).toStringAsFixed(1)}%',
              limit: '2.0%'),
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
  const SecondViewScreen({super.key, required this.view, this.onCapture});

  final SecondView view;
  final VoidCallback? onCapture;

  @override
  Widget build(BuildContext context) {
    return _Scaffold(
      title: 'Second view',
      chip: StateChip(view.ready ? 'Far enough' : 'Keep moving',
          colour: view.ready ? Tokens.negative : Tokens.abstain,
          soft: view.ready ? Tokens.negativeSoft : Tokens.abstainSoft),
      body: [
        AspectRatio(
          aspectRatio: 3 / 4,
          child: Container(
            decoration: BoxDecoration(
              color: const Color(0xFF16131F),
              borderRadius: BorderRadius.circular(6),
            ),
            alignment: Alignment.bottomLeft,
            padding: const EdgeInsets.all(10),
            child: Container(
              padding: const EdgeInsets.all(9),
              decoration: BoxDecoration(
                color: Colors.black.withValues(alpha: 0.82),
                borderRadius: BorderRadius.circular(4),
              ),
              child: Text(view.guidance,
                  style: const TextStyle(color: Color(0xFFEDEAF4), fontSize: 12.5)),
            ),
          ),
        ),
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
        PrimaryButton(view.ready ? 'Capture second frame' : 'Move a little further',
            onPressed: view.ready ? onCapture : null),
        const SizedBox(height: 8),
        const Text('Both frames are hashed into the record. The second one is '
            'evidence too.',
            textAlign: TextAlign.center,
            style: TextStyle(fontSize: 11.5, height: 1.4, color: Tokens.muted)),
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
      this.liveness = const Liveness.notChecked()});

  final TestResult result;
  final VoidCallback? onSeal;
  final Liveness liveness;

  @override
  Widget build(BuildContext context) {
    final outcome = result.outcome;
    final setText =
        result.predictionSet.isEmpty ? '∅' : result.predictionSet.join(', ');

    return _Scaffold(
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
  });

  final String digestHex;
  final int sequence;
  final String securityLevel;
  final String anchorWindow;
  final bool anchored;

  @override
  Widget build(BuildContext context) {
    return _Scaffold(
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
        Panel(title: 'Signature', children: [
          Measured('Key', securityLevel,
              tone: securityLevel == 'SOFTWARE' ? Tokens.abstain : Tokens.negative),
          const Measured('Use authorised by', 'Fingerprint'),
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

class _Scaffold extends StatelessWidget {
  const _Scaffold({
    required this.title,
    required this.chip,
    required this.body,
    this.footer = const [],
  });

  final String title;
  final Widget chip;
  final List<Widget> body;
  final List<Widget> footer;

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: Tokens.ground,
      appBar: AppBar(
        backgroundColor: Tokens.surface,
        surfaceTintColor: Colors.transparent,
        title: Text(title,
            style: const TextStyle(
                fontSize: 16, fontWeight: FontWeight.w600, color: Tokens.ink)),
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
