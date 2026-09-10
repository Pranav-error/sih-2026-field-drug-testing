package `in`.gov.ncb.sih26231.field_companion

import android.os.Build
import android.security.keystore.KeyGenParameterSpec
import android.security.keystore.KeyInfo
import android.security.keystore.KeyProperties
import android.security.keystore.StrongBoxUnavailableException
import android.util.Base64
import java.security.KeyFactory
import java.security.KeyStore
import java.security.PrivateKey
import java.security.Signature
import java.security.spec.ECGenParameterSpec

/**
 * The signing key, generated inside the secure element and never exported.
 *
 * This is what converts *an app claims it signed this* into *this device's secure
 * hardware signed this, and here is a certificate chain to a root you already
 * trust.* Without it a Field Test Record is a file someone made; with it the
 * record can be checked years later, without the handset in evidence.
 *
 * Two things this class deliberately does **not** do.
 *
 * It does not report verified boot state or bootloader status. Those live inside
 * the attestation certificate's Android extension, and a verifier that took the
 * app's word for them would be trusting exactly the software whose integrity is
 * in question. The chain is shipped raw; the verifier reads them itself.
 *
 * It does not pretend StrongBox is present when it is not. If the discrete
 * secure element is unavailable the key is generated in the TEE instead, and the
 * weaker guarantee is reported honestly and recorded — never quietly upgraded.
 */
object HardwareKeystore {
    private const val ALIAS = "sih26231.ftr.signing"

    /** Set when an unusable key was replaced, so the app can say so. */
    @JvmStatic var regenerated = false
    @JvmStatic var regenerationNote = ""
    private var lastChallenge: ByteArray? = null
    private const val PROVIDER = "AndroidKeyStore"

    /** Result of preparing a key: what backs it, and the attestation chain. */
    data class Attested(
        val securityLevel: String,
        val strongBoxRequested: Boolean,
        val certChain: List<String>,
        val publicKeyDer: String,
        val note: String,
    )

    private fun keyStore(): KeyStore =
        KeyStore.getInstance(PROVIDER).apply { load(null) }

    /**
     * Generate the key if it does not exist, and report what actually backs it.
     *
     * [challenge] becomes the attestation challenge, which binds the certificate
     * to a value the caller chose rather than one the device picked. That is what
     * stops a chain being replayed from another device.
     */
    fun prepare(challenge: ByteArray, forceRegenerate: Boolean = false): Attested {
        val ks = keyStore()
        if (forceRegenerate && ks.containsAlias(ALIAS)) ks.deleteEntry(ALIAS)

        lastChallenge = challenge
        var strongBox = true
        var note = ""
        if (!ks.containsAlias(ALIAS)) {
            strongBox = generateBestAvailable(challenge)
            if (!strongBox) {
                note = "StrongBox unavailable on this device; the key was " +
                    "generated in the TEE, which is a weaker guarantee."
            }
        }
        if (regenerated) note = regenerationNote

        val entry = ks.getEntry(ALIAS, null) as KeyStore.PrivateKeyEntry
        val chain = entry.certificateChain.map {
            Base64.encodeToString(it.encoded, Base64.NO_WRAP)
        }
        val level = reportedLevel(entry.privateKey)

        // The note above is only set on the run that generates the key. Every
        // later launch takes the `containsAlias` branch, so a handset that fell
        // back to the TEE explained itself once and then went quiet about it
        // forever. The level stayed honest; the reason for it did not survive a
        // restart. Derive it from what actually backs the key instead.
        if (note.isEmpty() && level != "STRONGBOX") {
            note = when (level) {
                "TEE" -> "This key lives in the TEE, not in a discrete secure " +
                    "element. StrongBox is either unavailable on this handset or " +
                    "was unavailable when the key was created."
                "SOFTWARE" -> "This key is NOT in secure hardware. Records signed " +
                    "with it will fail verification and must never be presented " +
                    "as evidence."
                else -> "Android did not report what backs this key. The " +
                    "attestation certificate shipped with each record is " +
                    "authoritative."
            }
        }

        return Attested(
            securityLevel = level,
            strongBoxRequested = strongBox,
            certChain = chain,
            publicKeyDer = Base64.encodeToString(
                entry.certificate.publicKey.encoded, Base64.NO_WRAP),
            note = note,
        )
    }

    /** Generate in StrongBox, falling back to the TEE. True if StrongBox. */
    private fun generateBestAvailable(challenge: ByteArray): Boolean {
        return try {
            generate(challenge, useStrongBox = true)
            true
        } catch (e: StrongBoxUnavailableException) {
            // Not an error: many issued handsets have no discrete secure
            // element. Fall back, and let the record carry the weaker level.
            generate(challenge, useStrongBox = false)
            false
        } catch (e: Exception) {
            generate(challenge, useStrongBox = false)
            false
        }
    }

    private fun generate(challenge: ByteArray, useStrongBox: Boolean) {
        val generator = java.security.KeyPairGenerator.getInstance(
            KeyProperties.KEY_ALGORITHM_EC, PROVIDER)
        val spec = KeyGenParameterSpec.Builder(ALIAS, KeyProperties.PURPOSE_SIGN)
            .setAlgorithmParameterSpec(ECGenParameterSpec("secp256r1"))
            .setDigests(KeyProperties.DIGEST_SHA256)
            // The challenge is what ties the attestation to this installation
            // rather than to a chain lifted from another device.
            .setAttestationChallenge(challenge)
            .apply { if (useStrongBox) setIsStrongBoxBacked(true) }
            .build()
        generator.initialize(spec)
        generator.generateKeyPair()
    }

    /**
     * What Android says backs the key.
     *
     * Only a hint: it is the app asking the platform, and the authoritative
     * answer is in the attestation certificate that the verifier parses. Shown to
     * the operator so the standby screen can be honest before any record exists.
     */
    private fun reportedLevel(key: PrivateKey): String {
        return try {
            val factory = KeyFactory.getInstance(key.algorithm, PROVIDER)
            val info = factory.getKeySpec(key, KeyInfo::class.java) as KeyInfo
            if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.S) {
                when (info.securityLevel) {
                    KeyProperties.SECURITY_LEVEL_STRONGBOX -> "STRONGBOX"
                    KeyProperties.SECURITY_LEVEL_TRUSTED_ENVIRONMENT -> "TEE"
                    KeyProperties.SECURITY_LEVEL_SOFTWARE -> "SOFTWARE"
                    else -> "UNKNOWN"
                }
            } else {
                @Suppress("DEPRECATION")
                if (info.isInsideSecureHardware) "TEE" else "SOFTWARE"
            }
        } catch (e: Exception) {
            "UNKNOWN"
        }
    }

    /**
     * Sign the record **body** with the hardware key. It never leaves the element.
     *
     * The body, not its digest. The key is generated with
     * `setDigests(DIGEST_SHA256)` and Android enforces that list at use time, so
     * asking for `NONEwithECDSA` over a pre-computed digest throws
     * `InvalidKeyException` — which is exactly what reached a handset as
     * *"Could not seal: PlatformException(keystore, InvalidKeyException)"*.
     *
     * `SHA256withECDSA` over the body produces a signature over SHA-256(body),
     * and SHA-256(body) *is* the record digest. So this is the same signature
     * the Prehashed path on the Python side produces, and both verifiers check
     * it unchanged. Nothing above this line had to move.
     */
    fun sign(body: ByteArray): ByteArray {
        try {
            return signWith(ALIAS, body)
        } catch (e: java.security.InvalidKeyException) {
            // A key left by an older build whose parameters no longer match how
            // this build signs. Until now the only cure was uninstalling the
            // app, which also destroyed the ledger — so every fix shipped with
            // "delete it first", and testers stopped being able to carry records
            // across builds.
            //
            // Regenerating is safe here and nowhere else: this key signs future
            // records, it does not decrypt past ones. Records already sealed
            // carry their own public key and attestation chain, so they keep
            // verifying against the key that signed them. What is lost is the
            // continuity claim that one device signed the whole chain — and the
            // chain check reports that itself, as a foreign_key break, rather
            // than it passing silently.
            regenerated = true
            regenerationNote = "The signing key was replaced: the previous one " +
                "was created by an older build and this build cannot sign with " +
                "it (${e.javaClass.simpleName}). Records sealed before this " +
                "point still verify, but the chain now spans two keys and the " +
                "verifier reports that."
            keyStore().deleteEntry(ALIAS)
            generateBestAvailable(lastChallenge ?: ByteArray(32))
            return signWith(ALIAS, body)
        }
    }

    private fun signWith(alias: String, body: ByteArray): ByteArray {
        val entry = keyStore().getEntry(alias, null) as KeyStore.PrivateKeyEntry
        return Signature.getInstance("SHA256withECDSA").run {
            initSign(entry.privateKey)
            update(body)
            sign()
        }
    }
}
