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

        var strongBox = true
        var note = ""
        if (!ks.containsAlias(ALIAS)) {
            try {
                generate(challenge, useStrongBox = true)
            } catch (e: StrongBoxUnavailableException) {
                // Not an error: many issued handsets have no discrete secure
                // element. Fall back, and let the record carry the weaker level.
                strongBox = false
                note = "StrongBox unavailable on this device; the key was " +
                    "generated in the TEE, which is a weaker guarantee."
                generate(challenge, useStrongBox = false)
            } catch (e: Exception) {
                strongBox = false
                note = "StrongBox generation failed (${e.javaClass.simpleName}); " +
                    "the key was generated in the TEE."
                generate(challenge, useStrongBox = false)
            }
        }

        val entry = ks.getEntry(ALIAS, null) as KeyStore.PrivateKeyEntry
        val chain = entry.certificateChain.map {
            Base64.encodeToString(it.encoded, Base64.NO_WRAP)
        }
        return Attested(
            securityLevel = reportedLevel(entry.privateKey),
            strongBoxRequested = strongBox,
            certChain = chain,
            publicKeyDer = Base64.encodeToString(
                entry.certificate.publicKey.encoded, Base64.NO_WRAP),
            note = note,
        )
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

    /** Sign a digest with the hardware key. The key never leaves the element. */
    fun sign(digest: ByteArray): ByteArray {
        val entry = keyStore().getEntry(ALIAS, null) as KeyStore.PrivateKeyEntry
        // NONEwithECDSA: the digest IS the artefact, so it is signed directly
        // rather than re-hashed into something the verifier would have to
        // reproduce. Matches the Prehashed path on the Python side.
        return Signature.getInstance("NONEwithECDSA").run {
            initSign(entry.privateKey)
            update(digest)
            sign()
        }
    }
}
