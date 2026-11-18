package com.ada.smsgateway

import org.json.JSONObject

/** Parses the pairing code shown by the Ada owner app (QR or copy/paste). */
object Pairing {
    private val E164 = Regex("^\\+[1-9]\\d{7,14}$")

    fun parse(text: String): GatewayConfig {
        val o = JSONObject(text.trim())
        require(o.optString("ada") == "sms-gateway") { "Not an Ada pairing code" }
        val url = o.getString("url").trimEnd('/')
        require(url.startsWith("https://")) { "Server must use HTTPS" }
        val token = o.getString("token")
        require(token.length >= 32) { "Invalid token" }
        val allow = o.optJSONArray("allow")
        val allowed = buildSet {
            if (allow != null) for (i in 0 until allow.length()) {
                val p = allow.getString(i)
                if (E164.matches(p)) add(p)
            }
        }
        require(allowed.isNotEmpty()) { "Pairing code has no allowed recipients" }
        return GatewayConfig(url, token, allowed)
    }

    fun isValidRecipient(phone: String) = E164.matches(phone)
}
