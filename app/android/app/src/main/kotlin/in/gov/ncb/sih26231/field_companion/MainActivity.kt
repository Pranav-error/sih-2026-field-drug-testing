package `in`.gov.ncb.sih26231.field_companion

import android.util.Base64
import io.flutter.embedding.android.FlutterActivity
import io.flutter.embedding.engine.FlutterEngine
import io.flutter.plugin.common.MethodChannel

class MainActivity : FlutterActivity() {
    private val channel = "in.gov.ncb.sih26231/keystore"

    override fun configureFlutterEngine(engine: FlutterEngine) {
        super.configureFlutterEngine(engine)
        MethodChannel(engine.dartExecutor.binaryMessenger, channel)
            .setMethodCallHandler { call, result ->
                try {
                    when (call.method) {
                        "prepare" -> {
                            val challenge = Base64.decode(
                                call.argument<String>("challenge") ?: "", Base64.NO_WRAP)
                            val force = call.argument<Boolean>("regenerate") ?: false
                            val a = HardwareKeystore.prepare(challenge, force)
                            result.success(mapOf(
                                "securityLevel" to a.securityLevel,
                                "strongBox" to a.strongBoxRequested,
                                "certChain" to a.certChain,
                                "publicKeyDer" to a.publicKeyDer,
                                "note" to a.note,
                            ))
                        }
                        "sign" -> {
                            val digest = Base64.decode(
                                call.argument<String>("digest") ?: "", Base64.NO_WRAP)
                            result.success(Base64.encodeToString(
                                HardwareKeystore.sign(digest), Base64.NO_WRAP))
                        }
                        else -> result.notImplemented()
                    }
                } catch (e: Exception) {
                    // Surfaced to Dart rather than swallowed: a keystore failure
                    // must make the app say its records are not evidence, never
                    // fall back to something weaker without saying so.
                    result.error("keystore", e.message, e.javaClass.simpleName)
                }
            }
    }
}
