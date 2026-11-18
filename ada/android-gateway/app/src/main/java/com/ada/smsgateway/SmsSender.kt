package com.ada.smsgateway

import android.app.Activity
import android.app.PendingIntent
import android.content.BroadcastReceiver
import android.content.Context
import android.content.Intent
import android.content.IntentFilter
import android.os.Build
import android.telephony.SmsManager
import androidx.core.content.ContextCompat
import kotlinx.coroutines.CompletableDeferred
import kotlinx.coroutines.withTimeoutOrNull
import java.util.concurrent.atomic.AtomicInteger

/** Sends one (possibly multi-part) SMS and suspends until the radio reports the result. */
class SmsSender(private val context: Context) {
    private val requestCodes = AtomicInteger(1)

    @Suppress("DEPRECATION")
    private fun smsManager(): SmsManager =
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.S) context.getSystemService(SmsManager::class.java)
        else SmsManager.getDefault()

    /** Returns null on success, or an error description. */
    suspend fun send(phone: String, body: String): String? {
        val manager = smsManager()
        val parts = manager.divideMessage(body)            // Arabic = UCS-2, 70 chars/part
        val action = "com.ada.smsgateway.SENT.${System.nanoTime()}"
        val remaining = AtomicInteger(parts.size)
        val result = CompletableDeferred<String?>()

        val receiver = object : BroadcastReceiver() {
            override fun onReceive(ctx: Context, intent: Intent) {
                if (resultCode != Activity.RESULT_OK) {
                    result.complete("radio error $resultCode")
                } else if (remaining.decrementAndGet() == 0) {
                    result.complete(null)
                }
            }
        }
        ContextCompat.registerReceiver(context, receiver, IntentFilter(action),
            ContextCompat.RECEIVER_NOT_EXPORTED)
        try {
            val intents = ArrayList(parts.map {
                PendingIntent.getBroadcast(context, requestCodes.getAndIncrement(),
                    Intent(action).setPackage(context.packageName),
                    PendingIntent.FLAG_IMMUTABLE or PendingIntent.FLAG_ONE_SHOT)
            })
            manager.sendMultipartTextMessage(phone, null, parts, intents, null)
            return withTimeoutOrNull(60_000) { result.await() } ?: "timeout waiting for radio"
        } catch (e: SecurityException) {
            return "SMS permission missing"
        } catch (e: Exception) {
            return e.javaClass.simpleName
        } finally {
            runCatching { context.unregisterReceiver(receiver) }
        }
    }
}
