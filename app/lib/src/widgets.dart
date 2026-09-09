/// Shared presentation pieces, each enforcing one rule from docs/DESIGN.md.
library;

import 'package:flutter/material.dart';

import 'tokens.dart';

/// A measured quantity. Always mono, always with its label, optionally with the
/// threshold it is being judged against — a figure without its threshold invites
/// the reader to invent one.
class Measured extends StatelessWidget {
  const Measured(this.label, this.value, {super.key, this.limit, this.tone});

  final String label;
  final String value;
  final String? limit;
  final Color? tone;

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.symmetric(vertical: 3),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.baseline,
        textBaseline: TextBaseline.alphabetic,
        children: [
          Expanded(
            child: Text(label,
                style: const TextStyle(fontSize: 13, color: Tokens.muted)),
          ),
          Text(value,
              style: Tokens.monoStyle(colour: tone ?? Tokens.ink)),
          if (limit != null)
            Text('  / $limit', style: Tokens.monoStyle(colour: Tokens.muted)),
        ],
      ),
    );
  }
}

/// A state chip. Colour is always doubled by the text label — sunlight, cheap
/// screens, and colour vision all make colour-only state unreadable.
class StateChip extends StatelessWidget {
  const StateChip(this.text, {super.key, this.colour = Tokens.accent, this.soft});

  final String text;
  final Color colour;
  final Color? soft;

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 7, vertical: 3),
      decoration: BoxDecoration(
        color: soft ?? Tokens.accentSoft,
        border: Border.all(color: colour),
        borderRadius: BorderRadius.circular(3),
      ),
      child: Text(text.toUpperCase(),
          style: Tokens.monoStyle(
              size: 10, weight: FontWeight.w600, colour: colour, spacing: 0.8)),
    );
  }
}

class Panel extends StatelessWidget {
  const Panel({super.key, required this.title, required this.children, this.tint = false});

  final String title;
  final List<Widget> children;
  final bool tint;

  @override
  Widget build(BuildContext context) {
    return Container(
      width: double.infinity,
      margin: const EdgeInsets.only(bottom: 12),
      padding: const EdgeInsets.fromLTRB(13, 11, 13, 12),
      decoration: BoxDecoration(
        color: tint ? Tokens.surface2 : Tokens.surface,
        border: Border.all(color: Tokens.rule),
        borderRadius: BorderRadius.circular(6),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(title.toUpperCase(),
              style: Tokens.monoStyle(
                  size: 10, weight: FontWeight.w600, colour: Tokens.muted, spacing: 1.2)),
          const SizedBox(height: 8),
          ...children,
        ],
      ),
    );
  }
}

/// The standing reminder. Present on every screen that shows or seals a result,
/// so there is no state in which a user forgets what class of claim this is.
class PresumptiveNotice extends StatelessWidget {
  const PresumptiveNotice({super.key, this.detail});

  final String? detail;

  static const text =
      'Presumptive only. This is a screening indication, not confirmation of '
      'identity or quantity. Laboratory analysis under NDPS procedure remains required.';

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.fromLTRB(11, 9, 11, 10),
      decoration: const BoxDecoration(
        color: Tokens.accentSoft,
        border: Border(left: BorderSide(color: Tokens.accent, width: 3)),
      ),
      child: Text(detail ?? text,
          style: const TextStyle(fontSize: 12, height: 1.45, color: Tokens.ink2)),
    );
  }
}

/// Primary action. Disabled state is a real state: a blocked shutter is a rude
/// interaction and the correct one.
class PrimaryButton extends StatelessWidget {
  const PrimaryButton(this.label, {super.key, this.onPressed, this.tone})
      : ghosted = false;

  /// A secondary action, offered at lower visual weight but never hidden. Used
  /// where a rule can be stepped around and the record notes that it was.
  const PrimaryButton.ghost(this.label, {super.key, this.onPressed})
      : tone = null,
        ghosted = true;

  final String label;
  final VoidCallback? onPressed;
  final Color? tone;
  final bool ghosted;

  @override
  Widget build(BuildContext context) {
    final enabled = onPressed != null;
    if (ghosted) {
      return SizedBox(
        width: double.infinity,
        height: Tokens.touchTarget,
        child: OutlinedButton(
          onPressed: onPressed,
          style: OutlinedButton.styleFrom(
            foregroundColor: enabled ? Tokens.ink2 : Tokens.muted,
            side: const BorderSide(color: Tokens.rule),
            shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(5)),
          ),
          child: Text(label,
              style: const TextStyle(fontSize: 14, fontWeight: FontWeight.w500)),
        ),
      );
    }
    return SizedBox(
      width: double.infinity,
      height: Tokens.touchTarget,
      child: FilledButton(
        onPressed: onPressed,
        style: FilledButton.styleFrom(
          backgroundColor: enabled ? (tone ?? Tokens.accent) : Tokens.rule,
          foregroundColor: enabled ? Colors.white : Tokens.muted,
          shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(5)),
        ),
        child: Text(label,
            style: const TextStyle(fontSize: 15, fontWeight: FontWeight.w600)),
      ),
    );
  }
}
