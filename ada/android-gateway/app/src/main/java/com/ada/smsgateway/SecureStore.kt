package com.ada.smsgateway

import android.content.Context
import android.content.SharedPreferences
import android.security.keystore.KeyGenParameterSpec
import android.security.keystore.KeyProperties
import android.util.Base64
import java.security.KeyStore
import javax.crypto.Cipher
import javax.crypto.KeyGenerator
import javax.crypto.SecretKey
import javax.crypto.spec.GCMParameterSpec

/** Gateway configuration. The token is encrypted with a non-exportable Android Keystore key. */
data class GatewayConfig(val url: String, val token: String, val allowed: Set<String>)

class SecureStore(context: Context) {
    private val prefs: SharedPreferences =
        context.applicationContext.getSharedPreferences("ada_gateway", Context.MODE_PRIVATE)

    fun load(): GatewayConfig? {
        val url = prefs.getString(K_URL, null) ?: return null
        val enc = prefs.getString(K_TOKEN, null) ?: return null
        val token = runCatching { decrypt(enc) }.getOrNull() ?: return null
        val allowed = prefs.getStringSet(K_ALLOWED, emptySet()).orEmpty()
        return GatewayConfig(url, token, allowed)
    }

    fun save(cfg: GatewayConfig) {
        prefs.edit()
            .putString(K_URL, cfg.url)
            .putString(K_TOKEN, encrypt(cfg.token))
            .putStringSet(K_ALLOWED, cfg.allowed)
            .apply()
    }

    fun clear() = prefs.edit().clear().apply()

    // ---- status shared between service and UI ----
    var running: Boolean
        get() = prefs.getBoolean(K_RUNNING, false)
        set(v) = prefs.edit().putBoolean(K_RUNNING, v).apply()

    fun recordStatus(state: String, error: String? = null, sentDelta: Int = 0) {
        prefs.edit()
            .putString(K_STATE, state)
            .putString(K_ERROR, error)
            .putLong(K_LAST_POLL, System.currentTimeMillis())
            .putInt(K_SENT, prefs.getInt(K_SENT, 0) + sentDelta)
            .apply()
    }

    fun state(): String = prefs.getString(K_STATE, "stopped") ?: "stopped"
    fun lastError(): String? = prefs.getString(K_ERROR, null)
    fun lastPoll(): Long = prefs.getLong(K_LAST_POLL, 0)
    fun sentCount(): Int = prefs.getInt(K_SENT, 0)
    fun registerListener(l: SharedPreferences.OnSharedPreferenceChangeListener) =
        prefs.registerOnSharedPreferenceChangeListener(l)
    fun unregisterListener(l: SharedPreferences.OnSharedPreferenceChangeListener) =
        prefs.unregisterOnSharedPreferenceChangeListener(l)

    // ---- AES-256-GCM with Keystore-held key ----
    private fun key(): SecretKey {
        val ks = KeyStore.getInstance("AndroidKeyStore").apply { load(null) }
        (ks.getEntry(ALIAS, null) as? KeyStore.SecretKeyEntry)?.let { return it.secretKey }
        val gen = KeyGenerator.getInstance(KeyProperties.KEY_ALGORITHM_AES, "AndroidKeyStore")
        gen.init(
            KeyGenParameterSpec.Builder(ALIAS, KeyProperties.PURPOSE_ENCRYPT or KeyProperties.PURPOSE_DECRYPT)
                .setBlockModes(KeyProperties.BLOCK_MODE_GCM)
                .setEncryptionPaddings(KeyProperties.ENCRYPTION_PADDING_NONE)
                .setKeySize(256)
                .build()
        )
        return gen.generateKey()
    }

    private fun encrypt(plain: String): String {
        val c = Cipher.getInstance("AES/GCM/NoPadding")
        c.init(Cipher.ENCRYPT_MODE, key())
        val out = c.iv + c.doFinal(plain.toByteArray(Charsets.UTF_8))
        return Base64.encodeToString(out, Base64.NO_WRAP)
    }

    private fun decrypt(enc: String): String {
        val raw = Base64.decode(enc, Base64.NO_WRAP)
        val c = Cipher.getInstance("AES/GCM/NoPadding")
        c.init(Cipher.DECRYPT_MODE, key(), GCMParameterSpec(128, raw, 0, 12))
        return String(c.doFinal(raw, 12, raw.size - 12), Charsets.UTF_8)
    }

    companion object {
        private const val ALIAS = "ada_gateway_key"
        private const val K_URL = "url"
        private const val K_TOKEN = "token"
        private const val K_ALLOWED = "allowed"
        private const val K_RUNNING = "running"
        private const val K_STATE = "state"
        private const val K_ERROR = "error"
        private const val K_LAST_POLL = "last_poll"
        private const val K_SENT = "sent"
    }
}
