/// Where sealed records actually live.
///
/// Until this existed the app built a record, showed its digest, and dropped it —
/// which made the ledger, the certificate and the verifier report impossible, and
/// made "append-only" a claim about code that never wrote anything.
///
/// A **directory of files**, mirroring `core/ftr/chain.py::Chain`, and for the
/// same reason: appending must never rewrite an existing byte, so a partial write
/// can lose at most the record being made and never one already sealed.
library;

import 'dart:io';
import 'dart:typed_data';

import 'package:ftr_verify/ftr_verify.dart' as ftr;
import 'package:path_provider/path_provider.dart';

class RecordStore {
  RecordStore._(this._dir);

  final Directory _dir;

  /// Open a store rooted at a directory of your choosing.
  ///
  /// Exists so the ledger and the handoff bundle can be exercised in a test
  /// without a platform channel. The export path shipping without ever having
  /// run once is exactly how the seal button reached a handset doing nothing.
  static RecordStore at(Directory dir) {
    if (!dir.existsSync()) dir.createSync(recursive: true);
    return RecordStore._(dir);
  }

  static Future<RecordStore> open() async {
    final base = await getApplicationDocumentsDirectory();
    final dir = Directory('${base.path}/ftr-chain');
    if (!dir.existsSync()) dir.createSync(recursive: true);
    return RecordStore._(dir);
  }

  String get path => _dir.path;

  /// Where bundles are written — a **sibling** of the ledger, never inside it.
  ///
  /// Exports are derived, deletable and re-creatable; the ledger is none of
  /// those. Nesting them would put mutable files under the directory whose
  /// whole contract is that nothing in it changes, and would make "clear
  /// exports" a command that walks the evidence directory.
  Directory get exportRoot {
    final d = Directory('${_dir.parent.path}/ftr-export');
    if (!d.existsSync()) d.createSync(recursive: true);
    return d;
  }

  List<File> get _files => _dir
      .listSync()
      .whereType<File>()
      .where((f) => f.path.endsWith('.ftr'))
      .toList()
    ..sort((a, b) => a.path.compareTo(b.path));

  int get length => _files.length;

  /// Digest of the last record, or the genesis hash on an empty chain.
  Uint8List get head {
    final files = _files;
    if (files.isEmpty) return ftr.genesisHash;
    return ftr.SealedRecord.fromEnvelope(files.last.readAsBytesSync()).digest;
  }

  int get nextSequence => _files.length;

  // -- anchoring ---------------------------------------------------------- //
  //
  // The signature proves who sealed a record and the chain proves the order they
  // were sealed in. Neither proves *when*: a handset can only assert its own
  // clock, and a handset with no network cannot be told otherwise. What an
  // anchor does is bound the window in which a timestamp could have been
  // fabricated — before the anchor the ordering is witnessed by someone outside
  // this device, after it the window is open. So the honest thing is not to hide
  // the window but to report how wide it is, which is what [unanchored] does.

  File get _anchorFile => File('${_dir.path}/ANCHOR');

  /// `<sequence>` on the first line, `<iso8601 utc>` on the second.
  ///
  /// Two lines rather than JSON so a person looking at the file with `cat`
  /// understands it, and so a file written by an older build (sequence only)
  /// still parses.
  List<String> get _anchorLines => _anchorFile.existsSync()
      ? _anchorFile.readAsStringSync().trim().split('\n')
      : const [];

  /// Sequence witnessed by something outside this handset, or null if none is.
  int? get lastAnchor {
    final l = _anchorLines;
    return l.isEmpty ? null : int.tryParse(l.first.trim());
  }

  /// When that witnessing happened, or null if it never did.
  ///
  /// The device's own clock, so it is a claim like every other timestamp here —
  /// but a claim bounded by the export it records, which is the point of
  /// anchoring at all.
  DateTime? get lastAnchorAt {
    final l = _anchorLines;
    if (l.length < 2) return null;
    return DateTime.tryParse(l[1].trim())?.toUtc();
  }

  /// How many sealed records have never been witnessed outside this device.
  int get unanchored {
    final a = lastAnchor;
    return a == null ? length : (length - (a + 1)).clamp(0, length);
  }

  /// Record that the chain was witnessed up to [sequence].
  ///
  /// Exporting a bundle is what witnesses it here: the bundle leaves the handset
  /// and lands somewhere this app cannot reach, so any later rewrite of those
  /// records is contradicted by a copy the app does not control. That is a
  /// weaker anchor than a countersigning service and it is labelled as such
  /// everywhere it is reported — but it is real, and it needs no network.
  void anchor(int sequence) => _anchorFile.writeAsStringSync(
      '$sequence\n${DateTime.now().toUtc().toIso8601String()}\n');

  List<ftr.SealedRecord> records() => _cachedRecords ??= _readRecords();

  List<ftr.SealedRecord> _readRecords() => _files
      .map((f) => ftr.SealedRecord.fromEnvelope(f.readAsBytesSync()))
      .toList();

  /// Write the frames a record refers to, beside it.
  ///
  /// Without this the record carries `raw_image_sha256` for an image that exists
  /// nowhere, so the verifier's strongest image check — *"the supplied frame
  /// hashes to the value in the record"* — could never be run. A hash of a file
  /// nobody kept proves nothing.
  void writeFrames(int sequence, {Uint8List? frameA, Uint8List? frameB}) {
    final stem = sequence.toString().padLeft(6, '0');
    if (frameA != null) {
      File('${_dir.path}/$stem.a.jpg').writeAsBytesSync(frameA);
    }
    if (frameB != null) {
      File('${_dir.path}/$stem.b.jpg').writeAsBytesSync(frameB);
    }
  }

  /// The frames belonging to a record, if they were kept.
  ({Uint8List? a, Uint8List? b}) frames(int sequence) {
    final stem = sequence.toString().padLeft(6, '0');
    final fa = File('${_dir.path}/$stem.a.jpg');
    final fb = File('${_dir.path}/$stem.b.jpg');
    return (
      a: fa.existsSync() ? fa.readAsBytesSync() : null,
      b: fb.existsSync() ? fb.readAsBytesSync() : null,
    );
  }

  /// Bytes on disk, so the log can say what the ledger is costing.
  int get bytesUsed => _dir
      .listSync()
      .whereType<File>()
      .fold<int>(0, (n, f) => n + f.lengthSync());

  /// Write a sealed record. Refuses to overwrite, and refuses a record that does
  /// not chain — the same two guards the Python `Chain.append` applies.
  File append(ftr.SealedRecord rec) {
    if (rec.sequence != nextSequence) {
      throw StateError('sequence ${rec.sequence} is not the next slot '
          '($nextSequence)');
    }
    if (!ftr.bytesEqual(rec.prevRecordHash, head)) {
      throw StateError('record does not chain to the current head');
    }
    final name = rec.sequence.toString().padLeft(6, '0');
    final file = File('${_dir.path}/$name.ftr');
    if (file.existsSync()) {
      throw StateError('$name.ftr already exists; records are never rewritten');
    }
    file.writeAsBytesSync(ftr.toEnvelope(rec));
    refresh();
    return file;
  }

  // -- replay, computed once ---------------------------------------------- //
  //
  // status() ECDSA-verifies every record, measured at ~4.4 ms each on a
  // developer machine and several times that on a handset. The log screen
  // called it on every rebuild, alongside a second full parse from records() —
  // so a ledger of 200 records blocked the main thread for seconds each time a
  // widget rebuilt, and the design targets ten thousand.
  //
  // Only append() and anchor() change what is on disk, and both go through this
  // class, so the cache is invalidated exactly where the truth changes. A
  // stale-cache bug here would be a chain break the log fails to show, so
  // nothing else may clear it: refresh() exists for a caller that has reason to
  // believe the directory changed underneath us.

  List<ftr.SealedRecord>? _cachedRecords;
  ({bool intact, List<String> breaks})? _cachedStatus;

  /// Drop the cached replay. Cheap; the next read recomputes.
  void refresh() {
    _cachedRecords = null;
    _cachedStatus = null;
  }

  /// Replay the chain and report every defect rather than the first.
  ({bool intact, List<String> breaks}) status() =>
      _cachedStatus ??= _replay();

  ({bool intact, List<String> breaks}) _replay() {
    final breaks = <String>[];
    List<int>? deviceKey;
    var prev = ftr.genesisHash;
    final recs = records();
    for (var i = 0; i < recs.length; i++) {
      final r = recs[i];
      if (r.sequence != i) {
        breaks.add('#$i carries sequence ${r.sequence}');
      }
      if (!ftr.bytesEqual(r.prevRecordHash, prev)) {
        breaks.add('#${r.sequence} chains to the wrong record — a gap or a fork');
      }
      if (!r.signatureValid) {
        breaks.add('#${r.sequence} signature does not verify');
      }
      // One chain, one signing key. Two devices' records interleaved into one
      // directory would each verify individually while the sequence they imply
      // never happened, so the key fingerprint is checked across the chain and
      // not only within a record.
      // Byte lists, so compare contents: `!=` on two Uint8Lists is identity
      // and would silently never fire.
      final key = r.attestation['public_key_sha256'];
      if (key is List<int>) {
        if (deviceKey == null) {
          deviceKey = key;
        } else if (!ftr.bytesEqual(
            Uint8List.fromList(key), Uint8List.fromList(deviceKey))) {
          breaks.add('#${r.sequence} was sealed by a different key than the '
              'records before it — two devices in one chain');
        }
      }
      prev = r.digest;
    }
    return (intact: breaks.isEmpty, breaks: breaks);
  }
}
