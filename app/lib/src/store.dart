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

  static Future<RecordStore> open() async {
    final base = await getApplicationDocumentsDirectory();
    final dir = Directory('${base.path}/ftr-chain');
    if (!dir.existsSync()) dir.createSync(recursive: true);
    return RecordStore._(dir);
  }

  String get path => _dir.path;

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

  List<ftr.SealedRecord> records() => _files
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
    return file;
  }

  /// Replay the chain and report every defect rather than the first.
  ({bool intact, List<String> breaks}) status() {
    final breaks = <String>[];
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
      prev = r.digest;
    }
    return (intact: breaks.isEmpty, breaks: breaks);
  }
}
