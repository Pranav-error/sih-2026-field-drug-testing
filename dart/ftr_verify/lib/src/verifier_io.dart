/// The chain verifier — the half that reads a directory.
///
/// Split from `verifier.dart` so the record verifier stays free of `dart:io` and
/// can run in a browser and inside the Flutter app. Everything here needs a
/// filesystem by nature: a chain is a directory of sealed records.
library;

import 'dart:io';

import 'record.dart';
import 'verifier.dart';

Report verifyChain(Directory root) {
  final r = Report();
  final files = root
      .listSync()
      .whereType<File>()
      .where((f) => f.path.endsWith('.ftr'))
      .toList()
    ..sort((a, b) => a.path.compareTo(b.path));

  if (files.isEmpty) {
    r.failures.add('No records found in ${root.path}.');
    return r;
  }

  var bad = 0;
  final records = <SealedRecord>[];
  // Per-record findings, counted rather than repeated. Forty copies of one caveat
  // would bury the record that differs, which is the opposite of what a reader needs.
  final seen = <String, int>{};
  for (final f in files) {
    final sub = verifyRecord(f.readAsBytesSync());
    if (!sub.ok) {
      bad++;
      for (final x in sub.failures) {
        r.failures.add('record ${_stem(f.path)}: $x');
      }
    }
    for (final item in sub.asserted) {
      seen[item] = (seen[item] ?? 0) + 1;
    }
    try {
      records.add(SealedRecord.fromEnvelope(f.readAsBytesSync()));
    } catch (_) {}
  }
  if (bad == 0) {
    r.proven.add('All ${files.length} records individually verify: canonical, hashed '
        'and signed.');
  }

  final n = files.length;
  final keys = seen.keys.toList()
    ..sort((a, b) {
      final c = seen[b]!.compareTo(seen[a]!);
      return c != 0 ? c : a.compareTo(b);
    });
  for (final item in keys) {
    final count = seen[item]!;
    final scope = count == n ? 'every record' : '$count of $n records';
    r.asserted.add('[$scope] $item');
  }

  var prev = genesisHash;
  var genesisSeen = 0;
  final breaks = <String>[];
  for (var i = 0; i < records.length; i++) {
    final rec = records[i];
    if (rec.sequence != i) {
      breaks.add('chain break at #$i [bad_sequence]: file carries sequence ${rec.sequence}');
    }
    if (bytesEqual(rec.prevRecordHash, genesisHash)) {
      genesisSeen++;
      if (genesisSeen > 1) {
        breaks.add('chain break at #${rec.sequence} [duplicate_genesis]: a second '
            'record claims to be first on this device');
      }
    }
    if (!bytesEqual(rec.prevRecordHash, prev)) {
      breaks.add('chain break at #${rec.sequence} [${i > 0 ? 'gap' : 'fork'}]: chains to '
          '${hex(rec.prevRecordHash).substring(0, 16)}…, expected ${hex(prev).substring(0, 16)}…');
    }
    prev = rec.digest;
  }

  if (breaks.isEmpty) {
    r.proven.add('The chain replays from genesis to record #${records.length - 1} with '
        'no gap and no fork: no record was reordered, removed from the middle, or '
        'inserted after the fact.');
  } else {
    r.failures.addAll(breaks);
  }

  final anchorFile = File('${root.path}/ANCHOR');
  final anchor = anchorFile.existsSync() ? int.tryParse(anchorFile.readAsStringSync().trim()) : null;
  if (anchor == null) {
    r.asserted.add('This chain has never been anchored. All ${records.length} records '
        'could have been produced at any time; the ledger fixes their order, not their date.');
  } else {
    final unanchored = records.length - (anchor + 1);
    if (unanchored > 0) {
      r.asserted.add('$unanchored record(s) after #$anchor are unanchored. Each proves '
          'only that it was made after the record before it and before the next anchor.');
    } else {
      r.proven.add('Every record is anchored up to #$anchor.');
    }
  }

  r.unverifiable.add('Whether records were removed from the *head* of the chain. '
      'Truncation is detectable only against an external anchor, never from the files alone.');
  return r;
}

String _stem(String path) {
  final base = path.split(Platform.pathSeparator).last;
  return base.endsWith('.ftr') ? base.substring(0, base.length - 4) : base;
}
