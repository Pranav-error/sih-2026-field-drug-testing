/// Sealing — the app side of L4.
///
/// The verifier can check a record it did not make; this is what makes one. It
/// exists in Dart because the app is where sealing actually happens, and because
/// a format only one implementation can *write* is not a format.
///
/// The keystore here is a development key held in memory or on disk, and it says
/// so: `securityLevel = "SOFTWARE"`, which both verifiers treat as a failure. On
/// Android the same interface is backed by
/// `KeyGenParameterSpec.Builder(...).setIsStrongBoxBacked(true)` with
/// `setAttestationChallenge(digest)`, over a platform channel; nothing above this
/// class needs to know which one it is holding. Shipping a Dart class that could
/// *claim* StrongBox would destroy the only thing the record is for, so this one
/// cannot.
library;

import 'dart:math';
import 'dart:typed_data';

import 'package:pointycastle/pointycastle.dart' as pc;
import 'package:pointycastle/ecc/curves/secp256r1.dart';
import 'package:pointycastle/key_generators/ec_key_generator.dart';
import 'package:pointycastle/random/fortuna_random.dart';
import 'package:pointycastle/signers/ecdsa_signer.dart';
import 'package:pointycastle/asn1.dart';

import 'canonical_cbor.dart' as cbor;
import 'record.dart';

const int schemaVersion = 1;

/// What a keystore asserts about the key that produced a signature.
class Attestation {
  final String securityLevel;      // SOFTWARE | TEE | STRONGBOX
  final String verifiedBootState;  // GREEN | YELLOW | ORANGE | RED | UNKNOWN
  final bool bootloaderLocked;
  final String osPatchLevel;
  final bool keyExportable;
  final Uint8List publicKeyDer;
  final List<Uint8List> certChain;

  const Attestation({
    required this.securityLevel,
    required this.verifiedBootState,
    required this.bootloaderLocked,
    required this.osPatchLevel,
    required this.keyExportable,
    required this.publicKeyDer,
    required this.certChain,
  });

  Map<String, Object?> toRecord() => {
        'security_level': securityLevel,
        // The chain itself, not a count. A verifier must be able to walk it to a
        // hardware root and read verified-boot state from the certificate rather
        // than taking the app's word for either.
        if (certChain.isNotEmpty) 'cert_chain': certChain,
        'verified_boot_state': verifiedBootState,
        'bootloader_locked': bootloaderLocked,
        'os_patch_level': osPatchLevel,
        'key_exportable': keyExportable,
        'public_key_sha256': sha256(publicKeyDer),
        'cert_chain_len': certChain.length,
      };
}

/// The interface the app and the platform keystore agree on.
abstract class Keystore {
  Uint8List sign(Uint8List digest);
  Attestation attestation();
  Uint8List get publicKeyDer;
}

/// Development keystore. P-256 in memory, honestly labelled SOFTWARE.
class SoftwareKeystore implements Keystore {
  late final pc.ECPrivateKey _priv;
  late final pc.ECPublicKey _pub;
  final pc.SecureRandom _random;

  SoftwareKeystore._(this._priv, this._pub, this._random);

  factory SoftwareKeystore({int? seed}) {
    final rnd = FortunaRandom();
    final r = Random(seed ?? DateTime.now().microsecondsSinceEpoch);
    rnd.seed(pc.KeyParameter(
        Uint8List.fromList(List<int>.generate(32, (_) => r.nextInt(256)))));

    final gen = ECKeyGenerator()
      ..init(pc.ParametersWithRandom(pc.ECKeyGeneratorParameters(ECCurve_secp256r1()), rnd));
    final pair = gen.generateKeyPair();
    return SoftwareKeystore._(
        pair.privateKey as pc.ECPrivateKey, pair.publicKey as pc.ECPublicKey, rnd);
  }

  @override
  Uint8List get publicKeyDer {
    // SubjectPublicKeyInfo for id-ecPublicKey / prime256v1, so the Python side
    // parses it with a stock loader rather than anything bespoke.
    final algorithm = ASN1Sequence()
      ..add(ASN1ObjectIdentifier.fromIdentifierString('1.2.840.10045.2.1'))
      ..add(ASN1ObjectIdentifier.fromIdentifierString('1.2.840.10045.3.1.7'));
    final point = _pub.Q!.getEncoded(false);
    final spki = ASN1Sequence()
      ..add(algorithm)
      ..add(ASN1BitString(stringValues: point));
    return spki.encode();
  }

  @override
  Uint8List sign(Uint8List digest) {
    final signer = ECDSASigner(null, null)
      ..init(true, pc.ParametersWithRandom(pc.PrivateKeyParameter<pc.ECPrivateKey>(_priv), _random));
    final sig = signer.generateSignature(digest) as pc.ECSignature;

    // Low-S normalisation. Both (r, s) and (r, n-s) verify, so leaving it high
    // would make an identical record produce signatures that differ in a way no
    // reader could explain. Nothing depends on it; it costs nothing to be tidy.
    final n = ECCurve_secp256r1().n;
    final s = sig.s.compareTo(n >> 1) > 0 ? n - sig.s : sig.s;

    return (ASN1Sequence()
          ..add(ASN1Integer(sig.r))
          ..add(ASN1Integer(s)))
        .encode();
  }

  @override
  Attestation attestation() => Attestation(
        securityLevel: 'SOFTWARE',
        verifiedBootState: 'UNKNOWN',
        bootloaderLocked: false,
        osPatchLevel: '1970-01-01',
        keyExportable: true, // it is a key in memory. say so.
        publicKeyDer: publicKeyDer,
        certChain: const [],
      );
}

/// Build the canonical body of a Field Test Record.
///
/// `sequence` is inside the signed body so a record cannot be silently relocated
/// in the chain: moving it changes the digest, which breaks the signature.
Map<String, Object?> buildBody({
  required String recordUuid,
  required int sequence,
  required Uint8List prevRecordHash,
  required Map<String, Object?> capturedAt,
  required Map<String, Object?> operator_,
  required Map<String, Object?> kit,
  required Map<String, Object?> card,
  required Map<String, Object?> capture,
  required Map<String, Object?> colorimetry,
  required Map<String, Object?> classification,
  Map<String, Object?> liveness = const {'checked': false},
  String pipelineName = 'reference',
  required Map<String, Object?> locationBundle,
  required Map<String, Object?> device,
  Map<String, Object?> ndps = const {},
  List<String> omitted = const [],
}) {
  if (prevRecordHash.length != 32) {
    throw ArgumentError('prev_record_hash must be 32 bytes');
  }
  if (sequence < 0) throw ArgumentError('sequence must be non-negative');
  return {
    'schema_version': schemaVersion,
    'record_uuid': recordUuid,
    'sequence': sequence,
    'prev_record_hash': prevRecordHash,
    'captured_at': capturedAt,
    'operator': operator_,
    'kit': kit,
    'card': card,
    'capture': capture,
    'colorimetry': colorimetry,
    // Peer of colorimetry and classification: whether the scene was physically
    // present is a finding about the test, not a property of an image file.
    'liveness': liveness,
    // Which implementation measured this. The on-device Dart pipeline uses
    // coarser corner detection than the reference, so a verifier re-deriving
    // the result knows what tolerance to expect.
    'pipeline': pipelineName,
    'classification': classification,
    'location_bundle': locationBundle,
    'device': device,
    'ndps': ndps,
    'omitted': [...omitted]..sort(),
  };
}

/// Encode, hash and sign. This is the irreversible step the UI warns about.
SealedRecord seal(Map<String, Object?> body, Keystore keystore) {
  final bodyCbor = cbor.encode(body);
  final digest = sha256(bodyCbor);
  final att = keystore.attestation();
  return SealedRecord(
    bodyCbor: bodyCbor,
    digest: digest,
    signature: keystore.sign(digest),
    publicKeyDer: att.publicKeyDer,
    attestation: att.toRecord(),
  );
}

/// Serialise a sealed record into the envelope both verifiers read.
///
/// Deliberately carries no digest: a verifier that trusts a supplied digest is
/// not verifying anything.
Uint8List toEnvelope(SealedRecord rec) => cbor.encode({
      'v': schemaVersion,
      'body': rec.bodyCbor,
      'sig': rec.signature,
      'pub': rec.publicKeyDer,
      'att': rec.attestation,
    });
