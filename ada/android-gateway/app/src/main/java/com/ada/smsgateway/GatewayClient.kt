package com.ada.smsgateway

import android.os.Build
import org.json.JSONArray
import org.json.JSONObject
import java.io.IOException
import java.net.URL
import javax.net.ssl.HttpsURLConnection

data class OutgoingSms(val id: Long, val phone: String, val body: String)

class AuthException : IOException("Gateway token rejected (re-pair the phone)")

/** Minimal HTTPS client for the Ada gateway protocol (claim -> send -> ack). */
class GatewayClient(private val cfg: GatewayConfig) {
    private val device = "${Build.MANUFACTURER} ${Build.MODEL} / app ${BuildConfig.VERSION_NAME}"

    fun claim(waitSec: Int = 25, limit: Int = 10): List<OutgoingSms> {
        val body = post("/api/v1/sms-gateway/claim?wait=$waitSec&limit=$limit", null,
            readTimeoutMs = (waitSec + 15) * 1000)
        val arr = JSONArray(body)
        return List(arr.length()) { i ->
            val o = arr.getJSONObject(i)
            OutgoingSms(o.getLong("id"), o.getString("phone"), o.getString("body"))
        }
    }

    fun ack(id: Long, ok: Boolean, error: String?) {
        val payload = JSONObject().put("ok", ok).apply { if (error != null) put("error", error.take(200)) }
        post("/api/v1/sms-gateway/$id/ack", payload.toString(), readTimeoutMs = 15_000)
    }

    private fun post(path: String, json: String?, readTimeoutMs: Int): String {
        val conn = URL(cfg.url + path).openConnection() as HttpsURLConnection
        try {
            conn.requestMethod = "POST"
            conn.connectTimeout = 15_000
            conn.readTimeout = readTimeoutMs
            conn.instanceFollowRedirects = false          // never leak the token to another host
            conn.setRequestProperty("X-Gateway-Token", cfg.token)
            conn.setRequestProperty("X-Gateway-Device", device)
            conn.setRequestProperty("Accept", "application/json")
            conn.doOutput = true
            val bytes = (json ?: "").toByteArray(Charsets.UTF_8)
            if (json != null) conn.setRequestProperty("Content-Type", "application/json")
            conn.setFixedLengthStreamingMode(bytes.size)
            conn.outputStream.use { it.write(bytes) }
            val code = conn.responseCode
            if (code == 401) throw AuthException()
            if (code == 409) return ""                    // ack for an already-finalised message
            if (code !in 200..299) throw IOException("Server error $code")
            return conn.inputStream.bufferedReader(Charsets.UTF_8).use { it.readText() }
        } finally {
            conn.disconnect()
        }
    }
}
