/// The signing key, in the phone's secure element.
///
/// Implements the same `Keystore` interface as the development key, so nothing
/// above this class knows or cares which one it is holding — which is the whole
/// point of that interface existing.
///
/// What it reports is deliberately narrow. It says which security level Android
/// claims backs the key, and it ships the attestation certificate chain raw. It
/// does **not** report verified-boot state or bootloader status, because those
/// live inside the attestation certificate and a verifier taking the app's word
/// for them would be trusting exactly the software whose integrity is in
/// question. The verifier parses the chain itself.
library;

import 'dart:convert';

import 'package:flutter/services.dart';
import 'package:ftr_verify/ftr_verify.dart' as ftr;

class PlatformKeystore implements ftr.Keystore {
  PlatformKeystore._(this._level, this._chain, this._publicKeyDer, this.note);

  static const _channel = MethodChannel('in.gov.ncb.sih26231/keystore');

  final String _level;
  final List<Uint8List> _chain;
  final Uint8List _publicKeyDer;

  /// Why the guarantee is weaker than asked for, when it is. Empty otherwise.
  final String note;

  /// Prepare the key, generating it in the secure element on first run.
  ///
  /// [challenge] becomes the attestation challenge, which binds the certificate
  /// to a value this installation chose rather than one the device picked — that
  /// is what stops a chain being lifted from another handset.
  ///
  /// Returns null when there is no hardware keystore at all, so the caller can
  /// fall back to a development key **and say so**, rather than silently
  /// producing records that look stronger than they are.
  static Future<PlatformKeystore?> open({Uint8List? challenge}) async {
    try {
      final res = await _channel.invokeMapMethod<String, dynamic>('prepare', {
        'challenge': base64Encode(
            challenge ?? Uint8List.fromList(DateTime.now().toIso8601String().codeUnits)),
        'regenerate': false,
      });
      if (res == null) return null;
      final chain = (res['certChain'] as List)
          .map((c) => base64Decode(c as String))
          .toList();
      return PlatformKeystore._(
        res['securityLevel'] as String? ?? 'UNKNOWN',
        chain,
        base64Decode(res['publicKeyDer'] as String),
        res['note'] as String? ?? '',
      );
    } on PlatformException {
      return null;
    } on MissingPluginException {
      return null;   // web, or a platform with no keystore channel
    }
  }

  @override
  Uint8List get publicKeyDer => _publicKeyDer;

  @override
  Uint8List sign(Uint8List digest) {
    throw UnsupportedError(
        'the hardware key signs asynchronously — use signAsync');
  }

  /// The real signing path. The key never leaves the secure element.
  ///
  /// Takes the record **body**, not its digest. The key is generated with
  /// `setDigests(DIGEST_SHA256)` and Android enforces that list, so asking the
  /// keystore for `NONEwithECDSA` over a pre-computed digest throws — which is
  /// what made the seal button silently do nothing. Signing the body with
  /// `SHA256withECDSA` produces a signature over SHA-256(body), which *is* the
  /// digest, and is exactly what both verifiers check.
  Future<Uint8List> signBody(Uint8List body) async {
    final sig = await _channel.invokeMethod<String>(
        'sign', {'body': base64Encode(body)});
    if (sig == null) throw StateError('the keystore returned no signature');
    return base64Decode(sig);
  }

  @override
  ftr.Attestation attestation() => ftr.Attestation(
        securityLevel: _level,
        // Not ours to assert. The attestation certificate carries them, and the
        // verifier reads them from there.
        verifiedBootState: 'IN_ATTESTATION',
        bootloaderLocked: false,
        osPatchLevel: 'IN_ATTESTATION',
        keyExportable: false,
        publicKeyDer: _publicKeyDer,
        certChain: _chain,
      );

  /// True when this key is worth presenting as evidence.
  bool get evidenceGrade => _level == 'STRONGBOX' || _level == 'TEE';

  String get securityLevel => _level;
  int get chainLength => _chain.length;
}
