/// The screens `DESIGN.md` specifies that the capture spine did not cover:
/// setup (02), the quality gate (04), the record log (07), the certificate (08)
/// and the verifier report (09).
///
/// The last one is the reason the whole system is worth anything, and it can run
/// here because `verifier.dart` was deliberately kept free of `dart:io` — the
/// same verifier a court would run, running inside the app that made the record.
library;

import 'package:flutter/material.dart';
import 'package:ftr_verify/ftr_verify.dart' as ftr;

import 'certificate.dart';
import 'screens.dart';

import 'models.dart';
import 'tokens.dart';
import 'widgets.dart';

// --------------------------------------------------------------------------- //
// 02 — setup
// --------------------------------------------------------------------------- //

/// Where kit-agnosticism is actually implemented: the reagent is **declared by
/// the operator**, never read from a vendor's serialised pouch. That single
/// choice is what the problem statement requires and what separates this from
/// the shipping commercial product.
class SetupScreen extends StatelessWidget {
  const SetupScreen({
    super.key,
    required this.reagent,
    required this.onReagent,
    required this.firRef,
    required this.memoRef,
    required this.onFir,
    required this.onMemo,
    this.onContinue,
  });

  final String reagent;
  final ValueChanged<String> onReagent;
  final String firRef;
  final String memoRef;
  final ValueChanged<String> onFir;
  final ValueChanged<String> onMemo;
  final VoidCallback? onContinue;

  static const reagents = ['Marquis', 'Mecke', 'Scott', 'Simon'];

  @override
  Widget build(BuildContext context) {
    return AppScaffold(
      title: 'New test',
      chip: const StateChip('Step 1 of 4'),
      body: [
        Panel(title: 'Reagent', children: [
          Wrap(
            spacing: 6,
            runSpacing: 6,
            children: reagents.map((r) {
              final on = r == reagent;
              return GestureDetector(
                onTap: () => onReagent(r),
                child: Container(
                  padding: const EdgeInsets.symmetric(horizontal: 13, vertical: 9),
                  decoration: BoxDecoration(
                    color: on ? Tokens.accentSoft : Tokens.surface,
                    border: Border.all(color: on ? Tokens.accent : Tokens.rule),
                    borderRadius: BorderRadius.circular(4),
                  ),
                  child: Text(r,
                      style: TextStyle(
                          fontSize: 13,
                          fontWeight: on ? FontWeight.w600 : FontWeight.w400,
                          color: on ? Tokens.accent : Tokens.ink2)),
                ),
              );
            }).toList(),
          ),
          const SizedBox(height: 8),
          const Text(
            'Declared by you, not read from the kit. The system works with '
            'whatever reagent the department already buys — no serialised pouch, '
            'no vendor lock-in.',
            style: TextStyle(fontSize: 11.5, height: 1.4, color: Tokens.muted),
          ),
        ]),
        Panel(title: 'Link to case', tint: true, children: [
          _Field(label: 'FIR reference', value: firRef, onChanged: onFir,
              hint: '142/2026 PS Kadugodi'),
          const SizedBox(height: 8),
          _Field(label: 'Seizure memo', value: memoRef, onChanged: onMemo,
              hint: 'SM-2026-0913-07'),
          const SizedBox(height: 8),
          const Text(
            'Both optional. A record with neither is valid but flagged as '
            'orphaned — demanding an FIR number at 2 a.m. only produces invented '
            'ones.',
            style: TextStyle(fontSize: 11.5, height: 1.4, color: Tokens.muted),
          ),
        ]),
      ],
      footer: [PrimaryButton('Open camera', onPressed: onContinue)],
    );
  }
}

class _Field extends StatelessWidget {
  const _Field({required this.label, required this.value,
      required this.onChanged, required this.hint});

  final String label;
  final String value;
  final ValueChanged<String> onChanged;
  final String hint;

  @override
  Widget build(BuildContext context) {
    return Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
      Text(label, style: const TextStyle(fontSize: 12, color: Tokens.muted)),
      const SizedBox(height: 4),
      TextFormField(
        initialValue: value,
        onChanged: onChanged,
        style: Tokens.monoStyle(size: 13),
        decoration: InputDecoration(
          hintText: hint,
          isDense: true,
          contentPadding: const EdgeInsets.symmetric(horizontal: 9, vertical: 9),
          border: const OutlineInputBorder(),
        ),
      ),
    ]);
  }
}

// --------------------------------------------------------------------------- //
// 04 — the quality gate, reported before any result
// --------------------------------------------------------------------------- //

/// Both gates report **before** the result is revealed. Order matters: an
/// operator who has already seen "positive" will rationalise a poor calibration
/// score; one who sees the score first reads it honestly.
class GateScreen extends StatelessWidget {
  const GateScreen({
    super.key,
    required this.quality,
    required this.cardResidual,
    required this.liveness,
    required this.refusals,
    this.onContinue,
    this.onRetake,
  });

  final CaptureQuality quality;
  final double? cardResidual;
  final Liveness liveness;
  final List<String> refusals;
  final VoidCallback? onContinue;
  final VoidCallback? onRetake;

  @override
  Widget build(BuildContext context) {
    final ok = refusals.isEmpty;
    return AppScaffold(
      title: 'Frame accepted',
      chip: StateChip(ok ? 'Gate passed' : 'Refused',
          colour: ok ? Tokens.negative : Tokens.abstain,
          soft: ok ? Tokens.negativeSoft : Tokens.abstainSoft),
      body: [
        Panel(title: 'Normalisation report', children: [
          Measured('Fiducials resolved', '${quality.fiducialsFound} / 4',
              tone: quality.fiducialsFound == 4 ? Tokens.negative : Tokens.abstain),
          if (cardResidual != null)
            Measured('Residual on card patches',
                '${cardResidual!.toStringAsFixed(2)} dE', limit: '3.00',
                tone: cardResidual! <= 3 ? Tokens.negative : Tokens.positive),
          Measured('Card angle', '${quality.tiltDegrees.round()}°', limit: '25°'),
          Measured('Illumination', '${(quality.illumination * 100).round()}%'),
          Measured('Focus', quality.focus.toStringAsFixed(2)),
          Measured('Clipped',
              '${(quality.clippedFraction * 100).toStringAsFixed(1)}%', limit: '3.0%'),
        ]),
        Panel(title: 'Liveness', tint: true, children: [
          if (!liveness.checked)
            const Measured('Two-view check', 'NOT RUN', tone: Tokens.abstain)
          else ...[
            Measured('Parallax at the tab',
                '${liveness.measuredPx.toStringAsFixed(1)} px',
                limit: '${liveness.predictedPx.toStringAsFixed(1)} px floor',
                tone: liveness.live ? Tokens.negative : Tokens.positive),
            Measured('Physically present', liveness.live ? 'Yes' : 'NO — scene was flat',
                tone: liveness.live ? Tokens.negative : Tokens.positive),
          ],
        ]),
        if (!ok)
          Panel(title: 'Why this frame was refused', children: [
            for (final r in refusals)
              Padding(
                padding: const EdgeInsets.only(bottom: 5),
                child: Text('· $r',
                    style: const TextStyle(
                        fontSize: 12, height: 1.4, color: Tokens.ink2)),
              ),
          ]),
        const PresumptiveNotice(
          detail: 'Corrections applied to this frame are recorded, not hidden. '
              'Correction is not concealment — the verifier re-derives them from '
              'the raw frame.',
        ),
      ],
      footer: [
        PrimaryButton(ok ? 'Read result' : 'Seal the refusal',
            onPressed: onContinue),
        const SizedBox(height: 8),
        // Offered at equal weight: no dark pattern pushing toward proceeding.
        PrimaryButton.ghost('Retake frame', onPressed: onRetake),
      ],
    );
  }
}

// --------------------------------------------------------------------------- //
// 07 — the record log
// --------------------------------------------------------------------------- //

/// Append-only, and it keeps the results nobody wanted. `withdraw` exists;
/// `delete` does not — annotation is the honest primitive for a store where
/// removal forks the chain.
class LogScreen extends StatelessWidget {
  const LogScreen({
    super.key,
    required this.records,
    required this.intact,
    required this.breaks,
    this.onOpen,
    this.onBack,
  });

  final List<ftr.SealedRecord> records;
  final bool intact;
  final List<String> breaks;
  final ValueChanged<int>? onOpen;
  final VoidCallback? onBack;

  @override
  Widget build(BuildContext context) {
    return AppScaffold(
      title: 'Record log',
      chip: StateChip(intact ? 'Chain intact' : 'Chain broken',
          colour: intact ? Tokens.negative : Tokens.positive,
          soft: intact ? Tokens.negativeSoft : Tokens.positiveSoft),
      body: [
        Panel(title: 'Chain integrity', tint: true, children: [
          Measured('Records on device', '${records.length}'),
          Measured('Gaps or forks', intact ? 'None' : '${breaks.length}',
              tone: intact ? Tokens.negative : Tokens.positive),
          for (final b in breaks)
            Padding(
              padding: const EdgeInsets.only(top: 4),
              child: Text('· $b',
                  style: const TextStyle(fontSize: 11.5, color: Tokens.positive)),
            ),
        ]),
        if (records.isEmpty)
          const Panel(title: 'Empty', children: [
            Text('No records sealed on this device yet.',
                style: TextStyle(fontSize: 12.5, color: Tokens.muted)),
          ])
        else
          Panel(title: 'Records', children: [
            for (var i = records.length - 1; i >= 0; i--)
              _LogRow(rec: records[i], onTap: onOpen == null ? null : () => onOpen!(i)),
          ]),
      ],
      footer: [
        PrimaryButton.ghost('Back', onPressed: onBack),
        const SizedBox(height: 8),
        const Text('Records cannot be deleted. A withdrawn test is annotated and '
            'stays in the chain.',
            textAlign: TextAlign.center,
            style: TextStyle(fontSize: 11.5, height: 1.4, color: Tokens.muted)),
      ],
    );
  }
}

class _LogRow extends StatelessWidget {
  const _LogRow({required this.rec, this.onTap});

  final ftr.SealedRecord rec;
  final VoidCallback? onTap;

  @override
  Widget build(BuildContext context) {
    final body = rec.body;
    final cls = (body['classification'] as Map?) ?? const {};
    final live = (body['liveness'] as Map?) ?? const {};
    final set = ((cls['prediction_set'] as List?) ?? const []).cast<String>();
    final outcome = Outcome.fromPredictionSet(set);
    final flat = live['checked'] == true && live['live'] != true;

    return InkWell(
      onTap: onTap,
      child: Padding(
        padding: const EdgeInsets.symmetric(vertical: 7),
        child: Row(crossAxisAlignment: CrossAxisAlignment.start, children: [
          // A 3px severity stripe, scannable at arm's length — always doubled by
          // the text label, never colour alone.
          Container(width: 3, height: 34,
              decoration: BoxDecoration(
                  color: outcome.colour,
                  borderRadius: BorderRadius.circular(2))),
          const SizedBox(width: 9),
          Expanded(
            child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
              Text('#${body['sequence']} · ${outcome.label}',
                  style: const TextStyle(
                      fontSize: 13, fontWeight: FontWeight.w600, color: Tokens.ink)),
              Text('${(body['kit'] as Map?)?['reagent_type'] ?? 'unknown'} · '
                  '${ftr.hex(rec.digest).substring(0, 12)}…',
                  style: Tokens.monoStyle(size: 10.5, colour: Tokens.muted)),
              if (flat)
                const Text('Liveness failed — the scene was flat',
                    style: TextStyle(fontSize: 11, color: Tokens.positive)),
              if (live['checked'] != true)
                const Text('No liveness check performed',
                    style: TextStyle(fontSize: 11, color: Tokens.abstain)),
            ]),
          ),
          const Icon(Icons.chevron_right, size: 18, color: Tokens.muted),
        ]),
      ),
    );
  }
}

// --------------------------------------------------------------------------- //
// 08 — the statutory certificate
// --------------------------------------------------------------------------- //

/// BSA 2023 §63, Part A pre-populated from the sealed record.
///
/// Every field a human must attest is rendered blank and marked in amber. An
/// auto-filled signature line is a forgery mechanism, and an auto-filled oath is
/// worse — the Schedule's declarations begin "I do hereby solemnly affirm".
class CertificateScreen extends StatelessWidget {
  const CertificateScreen({
    super.key,
    required this.certificate,
    required this.envelope,
    this.onBack,
  });

  final Certificate certificate;
  final Map<String, Object?> envelope;
  final VoidCallback? onBack;

  @override
  Widget build(BuildContext context) {
    final c = certificate;
    return AppScaffold(
      title: 'BSA §63 certificate',
      chip: StateChip(c.isDraft ? 'Draft' : 'Ready',
          colour: c.isDraft ? Tokens.abstain : Tokens.negative,
          soft: c.isDraft ? Tokens.abstainSoft : Tokens.negativeSoft),
      body: [
        if (c.isDraft)
          const PresumptiveNotice(
            detail: 'DRAFT — NOT FOR FILING. The field labels are transcribed '
                'from a bare-Act repository, not the official Gazette. The '
                'computed values below are correct and come from the signed '
                'record; only the provenance of the LABELS is provisional.',
          ),
        if (c.isDraft) const SizedBox(height: 12),
        for (final part in c.parts)
          Panel(
            title: '${part['title']}  ${part['subtitle']}',
            children: [
              for (final item in (part['items'] as List).cast<Map<String, dynamic>>())
                _CertItem(item: item, values: c.values),
            ],
          ),
        if (c.missingFromRecord.isNotEmpty)
          Panel(title: 'Statutory fields the record cannot supply', children: [
            for (final m in c.missingFromRecord)
              Text('· $m',
                  style: const TextStyle(
                      fontSize: 12, height: 1.5, color: Tokens.abstain)),
            const SizedBox(height: 5),
            const Text('These must be completed by hand, or the record schema '
                'extended.',
                style: TextStyle(fontSize: 11.5, height: 1.4, color: Tokens.muted)),
          ]),
        Panel(title: 'eSakshya / CCTNS-2.0 envelope', tint: true, children: [
          Measured('System of record', '${envelope['system_of_record']}'),
          Measured('FIR reference',
              '${(envelope['routing'] as Map)['fir_reference'] ?? '— not linked'}'),
          Measured('Seizure memo',
              '${(envelope['routing'] as Map)['seizure_memo_ref'] ?? '— not linked'}'),
          const SizedBox(height: 5),
          const Text('Provisional field names: no published ingest specification '
              'has been found. CCTNS-2.0 stays the system of record — no parallel '
              'evidence store is built.',
              style: TextStyle(fontSize: 11.5, height: 1.4, color: Tokens.muted)),
        ]),
      ],
      footer: [
        PrimaryButton.ghost('Back', onPressed: onBack),
        const SizedBox(height: 8),
        Text('${c.blanks.length} fields await a human signatory. The app computes '
            'the hash and the algorithm; it does not sign for anyone.',
            textAlign: TextAlign.center,
            style: const TextStyle(fontSize: 11.5, height: 1.4, color: Tokens.muted)),
      ],
    );
  }
}

class _CertItem extends StatelessWidget {
  const _CertItem({required this.item, required this.values});

  final Map<String, dynamic> item;
  final Map<String, String> values;

  @override
  Widget build(BuildContext context) {
    final kind = item['kind'] as String;
    final key = item['key'] as String;
    final filled = values[key];

    Widget blank(String what) => Text(what,
        style: const TextStyle(
            fontSize: 11.5, fontStyle: FontStyle.italic, color: Tokens.abstain));

    return Padding(
      padding: const EdgeInsets.only(bottom: 9),
      child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
        if (kind == 'prose')
          Text('${item['text']}',
              style: const TextStyle(fontSize: 11.5, height: 1.45, color: Tokens.ink2))
        else if (kind == 'hash') ...[
          Text('${item['text']}',
              style: const TextStyle(fontSize: 11.5, height: 1.45, color: Tokens.ink2)),
          const SizedBox(height: 4),
          if (filled != null)
            SelectableText(filled, style: Tokens.monoStyle(size: 11)),
          Text('[${values['hash_value__algorithm'] == 'SHA256' ? 'X' : ' '}] SHA256   '
              '[ ] SHA1   [ ] MD5   [ ] Other',
              style: Tokens.monoStyle(size: 10.5, colour: Tokens.ink2)),
        ] else if (kind == 'checkboxes') ...[
          Wrap(spacing: 8, children: [
            for (final o in (item['options'] as List).cast<String>())
              Text('[${filled == o ? 'X' : ' '}] $o',
                  style: Tokens.monoStyle(size: 10.5, colour: Tokens.ink2)),
          ]),
        ] else if (kind == 'signature' || kind == 'datetimeplace') ...[
          Text('${item['label']}',
              style: const TextStyle(fontSize: 11.5, color: Tokens.muted)),
          blank('▢ to be completed by hand'),
        ] else ...[
          Text('${item['label']}',
              style: const TextStyle(fontSize: 11.5, color: Tokens.muted)),
          if (filled != null)
            Text(filled, style: Tokens.monoStyle(size: 11.5))
          else
            blank('▢ blank'),
        ],
      ]),
    );
  }
}

// --------------------------------------------------------------------------- //
// 09 — the verifier report
// --------------------------------------------------------------------------- //

/// The independent verifier, running inside the app that made the record.
///
/// Possible because `verifier.dart` was kept free of `dart:io`. It is the same
/// code a court would run, and it reports what it **cannot** prove at the same
/// visual weight as what it can — because a tool that only ever prints VALID
/// teaches courts to over-trust it, which is worse than the status quo.
class VerifierScreen extends StatelessWidget {
  const VerifierScreen({super.key, required this.report, this.onBack});

  final ftr.Report report;
  final VoidCallback? onBack;

  @override
  Widget build(BuildContext context) {
    return AppScaffold(
      title: 'Verifier report',
      chip: StateChip(report.ok ? 'Verified' : 'Failed',
          colour: report.ok ? Tokens.negative : Tokens.positive,
          soft: report.ok ? Tokens.negativeSoft : Tokens.positiveSoft),
      body: [
        if (report.failures.isNotEmpty)
          _Bucket(title: 'FAILED', items: report.failures, colour: Tokens.positive),
        _Bucket(title: 'PROVEN', items: report.proven, colour: Tokens.negative),
        _Bucket(title: 'ASSERTED, NOT PROVEN', items: report.asserted,
            colour: Tokens.abstain),
        _Bucket(title: 'UNVERIFIABLE FROM THIS BUNDLE', items: report.unverifiable,
            colour: Tokens.muted),
        if (report.ok)
          const PresumptiveNotice(
            detail: 'A verified record is not a true result. It is an unaltered one.',
          ),
      ],
      footer: [
        PrimaryButton.ghost('Back', onPressed: onBack),
        const SizedBox(height: 8),
        const Text('This verifier trusts nothing, including this app. It runs '
            'offline and re-derives every claim it can.',
            textAlign: TextAlign.center,
            style: TextStyle(fontSize: 11.5, height: 1.4, color: Tokens.muted)),
      ],
    );
  }
}

class _Bucket extends StatelessWidget {
  const _Bucket({required this.title, required this.items, required this.colour});

  final String title;
  final List<String> items;
  final Color colour;

  @override
  Widget build(BuildContext context) {
    if (items.isEmpty) return const SizedBox.shrink();
    return Container(
      width: double.infinity,
      margin: const EdgeInsets.only(bottom: 12),
      padding: const EdgeInsets.fromLTRB(11, 9, 11, 11),
      decoration: BoxDecoration(
        color: Tokens.surface,
        border: Border(left: BorderSide(color: colour, width: 3)),
      ),
      child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
        Text(title,
            style: Tokens.monoStyle(
                size: 10, weight: FontWeight.w600, colour: colour, spacing: 1.2)),
        const SizedBox(height: 7),
        for (final i in items)
          Padding(
            padding: const EdgeInsets.only(bottom: 6),
            child: Text(i,
                style: const TextStyle(
                    fontSize: 11.5, height: 1.45, color: Tokens.ink2)),
          ),
      ]),
    );
  }
}
