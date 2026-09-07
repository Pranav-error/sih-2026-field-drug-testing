/// Sealed records: parse an envelope, recompute the digest, check the signature.
///
/// The digest is always recomputed from the body bytes. A verifier that trusts a
/// digest handed to it in the file is not verifying anything, so the envelope
/// deliberately does not carry one.
library;

import 'dart:typed_data';

import 'package:crypto/crypto.dart' as crypto;
import 'package:pointycastle/pointycastle.dart' as pc;
import 'package:pointycastle/ecc/curves/secp256r1.dart';
import 'package:pointycastle/signers/ecdsa_signer.dart';
import 'package:pointycastle/asn1.dart';

import 'canonical_cbor.dart' as cbor;

Uint8List sha256(Uint8List b) => Uint8List.fromList(crypto.sha256.convert(b).bytes);

const int genesisLength = 32;
final Uint8List genesisHash = Uint8List(32);

class SealedRecord {
  final Uint8List bodyCbor;
  final Uint8List digest;
  final Uint8List signature;
  final Uint8List publicKeyDer;
  final Map<Object?, Object?> attestation;

  SealedRecord({
    required this.bodyCbor,
    required this.digest,
    required this.signature,
    required this.publicKeyDer,
    required this.attestation,
  });

  factory SealedRecord.fromEnvelope(Uint8List blob) {
    final e = cbor.decode(blob);
    if (e is! Map) throw cbor.CborError('envelope is not a map');
    for (final k in ['body', 'sig', 'pub', 'att']) {
      if (!e.containsKey(k)) throw cbor.CborError('envelope missing field: $k');
    }
    final body = e['body'];
    if (body is! Uint8List) throw cbor.CborError('envelope body must be a byte string');
    return SealedRecord(
      bodyCbor: body,
      digest: sha256(body), // recomputed, never read from the file
      signature: e['sig'] as Uint8List,
      publicKeyDer: e['pub'] as Uint8List,
      attestation: (e['att'] as Map).cast<Object?, Object?>(),
    );
  }

  Map<Object?, Object?> get body => cbor.decode(bodyCbor) as Map<Object?, Object?>;
  int get sequence => body['sequence'] as int;
  Uint8List get prevRecordHash => body['prev_record_hash'] as Uint8List;

  bool get signatureValid {
    try {
      return _verifyEcdsaP256(publicKeyDer, digest, signature);
    } catch (_) {
      return false;
    }
  }
}

/// Verify an ECDSA-P256 signature over an already-computed digest.
///
/// PointyCastle rather than Python's `cryptography`: different authors, different
/// language, different bignum code. If both say the same signature verifies over
/// the same digest, that agreement means something.
bool _verifyEcdsaP256(Uint8List spkiDer, Uint8List digest, Uint8List sigDer) {
  final params = ECCurve_secp256r1();

  // SubjectPublicKeyInfo: SEQUENCE { AlgorithmIdentifier, BIT STRING point }
  final spki = ASN1Sequence.fromBytes(spkiDer);
  final bitString = spki.elements![1] as ASN1BitString;
  final point = params.curve.decodePoint(bitString.stringValues!);
  if (point == null) return false;
  final pub = pc.ECPublicKey(point, params);

  // ECDSA-Sig-Value: SEQUENCE { INTEGER r, INTEGER s }
  final sigSeq = ASN1Sequence.fromBytes(sigDer);
  final r = (sigSeq.elements![0] as ASN1Integer).integer!;
  final s = (sigSeq.elements![1] as ASN1Integer).integer!;

  final signer = ECDSASigner(null, null)
    ..init(false, pc.PublicKeyParameter<pc.ECPublicKey>(pub));
  return signer.verifySignature(digest, pc.ECSignature(r, s));
}

String hex(Uint8List b) => b.map((x) => x.toRadixString(16).padLeft(2, '0')).join();

bool bytesEqual(Uint8List a, Uint8List b) {
  if (a.length != b.length) return false;
  for (var i = 0; i < a.length; i++) {
    if (a[i] != b[i]) return false;
  }
  return true;
}
