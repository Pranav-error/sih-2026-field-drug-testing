/// The one contract in this app that no test can execute.
///
/// `HardwareKeystore` needs a secure element, so it runs only on a handset —
/// and the seal path has now been broken twice by the same mismatch:
///
///   the key is generated with `setDigests(DIGEST_SHA256)`, Android enforces
///   that list at use time, and the signer asked for `NONEwithECDSA`.
///
/// Both times it reached a real device as
/// `PlatformException(keystore, InvalidKeyException)`. The second time, the fix
/// had been applied to the Dart and to `MainActivity` but not to the Kotlin
/// that actually signs — it analysed clean, compiled clean, and failed on
/// hardware.
///
/// So this reads the Kotlin source and checks the two halves agree. A source
/// grep is a poor substitute for running the code; it is a great deal better
/// than finding out from a photograph of a phone.
library;

import 'dart:io';

import 'package:flutter_test/flutter_test.dart';

void main() {
  final file = File('android/app/src/main/kotlin/in/gov/ncb/sih26231/'
      'field_companion/HardwareKeystore.kt');

  late String src;

  setUpAll(() {
    expect(file.existsSync(), isTrue,
        reason: 'HardwareKeystore.kt moved — update this test with it');
    src = file.readAsStringSync();
  });

  test('the key is generated for SHA-256 and nothing else', () {
    expect(src, contains('setDigests(KeyProperties.DIGEST_SHA256)'));
    expect(src.contains('DIGEST_NONE'), isFalse,
        reason: 'if DIGEST_NONE is ever added, this whole test needs rethinking');
  });

  test('the signer asks for the algorithm the key actually authorises', () {
    // The failure mode: Signature.getInstance("NONEwithECDSA") against a key
    // whose authorisation list holds only SHA-256.
    expect(src, contains('Signature.getInstance("SHA256withECDSA")'));
    expect(src.contains('NONEwithECDSA"'), isFalse,
        reason: 'NONEwithECDSA against a SHA256-only key throws '
            'InvalidKeyException at signing time, on the handset, with no '
            'compile-time or analyzer warning anywhere');
  });

  test('sign takes the body, because SHA256withECDSA hashes what it is given',
      () {
    // Signing the *digest* with SHA256withECDSA would produce a signature over
    // SHA-256(digest) — a valid signature over the wrong thing, which every
    // verifier would then correctly reject. Worse than the crash: it seals.
    expect(src, contains('fun sign(body: ByteArray)'));
    expect(src.contains('fun sign(digest: ByteArray)'), isFalse);
    expect(src, contains('update(body)'));
  });

  test('the security-level explanation survives a restart', () {
    // note was only set inside the `if (!containsAlias)` branch, so a handset
    // that fell back to the TEE explained itself once and was silent on every
    // later launch. The level stayed honest; the reason did not.
    expect(src, contains('if (note.isEmpty() && level != "STRONGBOX")'));
    expect(src, contains('val level = reportedLevel(entry.privateKey)'));
  });

  test('MainActivity passes the body under that name', () {
    final main = File('android/app/src/main/kotlin/in/gov/ncb/sih26231/'
        'field_companion/MainActivity.kt');
    expect(main.existsSync(), isTrue);
    final m = main.readAsStringSync();
    expect(m, contains('call.argument<String>("body")'));
    expect(m, contains('HardwareKeystore.sign(body)'));
  });

  test('the Dart side sends "body", and refuses the digest-shaped call', () {
    final dart = File('lib/src/platform_keystore.dart').readAsStringSync();
    expect(dart, contains("'sign', {'body': base64Encode(body)}"));
    // The synchronous Keystore.sign(digest) must stay unimplemented rather than
    // quietly doing something plausible.
    expect(dart, contains('UnsupportedError'));
  });
}
