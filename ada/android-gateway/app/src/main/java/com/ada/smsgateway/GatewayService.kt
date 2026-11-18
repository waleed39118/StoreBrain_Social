package com.ada.smsgateway

import android.app.Notification
import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.PendingIntent
import android.app.Service
import android.content.Context
import android.content.Intent
import android.content.pm.ServiceInfo
import android.os.Build
import android.os.IBinder
import android.os.PowerManager
import androidx.core.app.NotificationCompat
import androidx.core.app.ServiceCompat
import androidx.core.content.ContextCompat
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.Job
import kotlinx.coroutines.SupervisorJob
import kotlinx.coroutines.cancel
import kotlinx.coroutines.delay
import kotlinx.coroutines.isActive
import kotlinx.coroutines.launch

/**
 * Foreground service that long-polls the Ada server and sends queued SMS from this SIM.
 *
 * Safety rails (protect the SIM even if the server were compromised):
 *  - only recipients from the pairing allow-list (the owner's number) are ever texted;
 *  - local cap of [MAX_PER_HOUR] messages per hour;
 *  - HTTPS only, system CAs only, no redirects.
 */
class GatewayService : Service() {
    private val scope = CoroutineScope(SupervisorJob() + Dispatchers.IO)
    private var loop: Job? = null
    private var wakeLock: PowerManager.WakeLock? = null
    private val sentTimes = ArrayDeque<Long>()
    private lateinit var store: SecureStore

    override fun onBind(intent: Intent?): IBinder? = null

    override fun onCreate() {
        super.onCreate()
        store = SecureStore(this)
        createChannel()
    }

    override fun onStartCommand(intent: Intent?, flags: Int, startId: Int): Int {
        if (intent?.action == ACTION_STOP) {
            stopEverything()
            return START_NOT_STICKY
        }
        val type = if (Build.VERSION.SDK_INT >= 34) ServiceInfo.FOREGROUND_SERVICE_TYPE_REMOTE_MESSAGING else 0
        ServiceCompat.startForeground(this, NOTIF_ID, notification(getString(R.string.status_running)), type)
        val cfg = store.load()
        if (cfg == null) {
            store.recordStatus("error", getString(R.string.error_not_paired))
            stopEverything()
            return START_NOT_STICKY
        }
        store.running = true
        if (wakeLock == null) {
            // Dedicated gateway phone: keep the CPU awake so OTPs go out instantly.
            wakeLock = (getSystemService(Context.POWER_SERVICE) as PowerManager)
                .newWakeLock(PowerManager.PARTIAL_WAKE_LOCK, "ada:gateway").apply { acquire() }
        }
        if (loop?.isActive != true) loop = scope.launch { run(cfg) }
        return START_STICKY
    }

    private suspend fun run(cfg: GatewayConfig) {
        val client = GatewayClient(cfg)
        val sender = SmsSender(this)
        var backoff = 2_000L
        while (scope.isActive) {
            try {
                val batch = client.claim()
                store.recordStatus("online")
                for (msg in batch) {
                    val error = when {
                        !Pairing.isValidRecipient(msg.phone) -> "invalid recipient"
                        msg.phone !in cfg.allowed -> "recipient not in allow-list"
                        !allowRate() -> "local hourly limit reached"
                        else -> sender.send(msg.phone, msg.body)
                    }
                    client.ack(msg.id, error == null, error)
                    store.recordStatus("online", error, sentDelta = if (error == null) 1 else 0)
                }
                backoff = 2_000L
            } catch (e: AuthException) {
                store.recordStatus("error", getString(R.string.error_token))
                updateNotification(getString(R.string.error_token))
                delay(60_000)
            } catch (e: Exception) {
                store.recordStatus("offline", e.message ?: e.javaClass.simpleName)
                delay(backoff)
                backoff = (backoff * 2).coerceAtMost(60_000)
            }
        }
    }

    private fun allowRate(): Boolean {
        val now = System.currentTimeMillis()
        while (sentTimes.isNotEmpty() && now - sentTimes.first() > 3_600_000) sentTimes.removeFirst()
        if (sentTimes.size >= MAX_PER_HOUR) return false
        sentTimes.addLast(now)
        return true
    }

    private fun stopEverything() {
        store.running = false
        store.recordStatus("stopped")
        loop?.cancel()
        wakeLock?.let { if (it.isHeld) it.release() }
        wakeLock = null
        ServiceCompat.stopForeground(this, ServiceCompat.STOP_FOREGROUND_REMOVE)
        stopSelf()
    }

    override fun onDestroy() {
        scope.cancel()
        wakeLock?.let { if (it.isHeld) it.release() }
        super.onDestroy()
    }

    private fun createChannel() {
        val nm = getSystemService(NotificationManager::class.java)
        nm.createNotificationChannel(
            NotificationChannel(CHANNEL, getString(R.string.channel_name), NotificationManager.IMPORTANCE_LOW))
    }

    private fun notification(text: String): Notification {
        val open = PendingIntent.getActivity(this, 0, Intent(this, MainActivity::class.java),
            PendingIntent.FLAG_IMMUTABLE)
        return NotificationCompat.Builder(this, CHANNEL)
            .setSmallIcon(R.drawable.ic_stat_gateway)
            .setContentTitle(getString(R.string.app_name))
            .setContentText(text)
            .setOngoing(true)
            .setContentIntent(open)
            .build()
    }

    private fun updateNotification(text: String) =
        getSystemService(NotificationManager::class.java).notify(NOTIF_ID, notification(text))

    companion object {
        private const val CHANNEL = "gateway"
        private const val NOTIF_ID = 1
        private const val MAX_PER_HOUR = 30
        const val ACTION_STOP = "com.ada.smsgateway.STOP"

        fun start(context: Context) =
            ContextCompat.startForegroundService(context, Intent(context, GatewayService::class.java))

        fun stop(context: Context) =
            context.startService(Intent(context, GatewayService::class.java).setAction(ACTION_STOP))
    }
}
