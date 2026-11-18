package com.ada.smsgateway

import android.Manifest
import android.annotation.SuppressLint
import android.content.Intent
import android.content.SharedPreferences
import android.content.pm.PackageManager
import android.net.Uri
import android.os.Build
import android.os.Bundle
import android.os.PowerManager
import android.provider.Settings
import android.text.format.DateUtils
import android.widget.Button
import android.widget.EditText
import android.widget.TextView
import android.widget.Toast
import androidx.activity.result.contract.ActivityResultContracts
import androidx.appcompat.app.AlertDialog
import androidx.appcompat.app.AppCompatActivity
import androidx.core.content.ContextCompat
import com.journeyapps.barcodescanner.ScanContract
import com.journeyapps.barcodescanner.ScanOptions

class MainActivity : AppCompatActivity() {
    private lateinit var store: SecureStore
    private lateinit var statusText: TextView
    private lateinit var detailText: TextView
    private lateinit var serverText: TextView
    private lateinit var toggle: Button

    private val listener = SharedPreferences.OnSharedPreferenceChangeListener { _, _ -> runOnUiThread { render() } }

    private val permissions = registerForActivityResult(ActivityResultContracts.RequestMultiplePermissions()) { res ->
        if (res[Manifest.permission.SEND_SMS] == true) startGateway()
        else toast(getString(R.string.need_sms_permission))
    }

    private val scanner = registerForActivityResult(ScanContract()) { result ->
        result.contents?.let { applyPairing(it) }
    }

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContentView(R.layout.activity_main)
        store = SecureStore(this)
        statusText = findViewById(R.id.status)
        detailText = findViewById(R.id.detail)
        serverText = findViewById(R.id.server)
        toggle = findViewById(R.id.toggle)

        findViewById<Button>(R.id.scan).setOnClickListener {
            scanner.launch(ScanOptions().setDesiredBarcodeFormats(ScanOptions.QR_CODE)
                .setPrompt(getString(R.string.scan_prompt)).setBeepEnabled(false).setOrientationLocked(false))
        }
        findViewById<Button>(R.id.paste).setOnClickListener { showPasteDialog() }
        findViewById<Button>(R.id.battery).setOnClickListener { requestBatteryExemption() }
        toggle.setOnClickListener {
            if (store.running) GatewayService.stop(this) else ensurePermissionsAndStart()
        }
        render()
    }

    override fun onResume() { super.onResume(); store.registerListener(listener); render() }
    override fun onPause() { store.unregisterListener(listener); super.onPause() }

    private fun applyPairing(text: String) {
        try {
            val cfg = Pairing.parse(text)
            store.save(cfg)
            toast(getString(R.string.paired_ok))
            if (store.running) GatewayService.stop(this)
            ensurePermissionsAndStart()
        } catch (e: Exception) {
            toast(getString(R.string.paired_fail) + ": " + (e.message ?: ""))
        }
        render()
    }

    private fun showPasteDialog() {
        val input = EditText(this).apply { hint = getString(R.string.paste_hint); minLines = 3 }
        AlertDialog.Builder(this)
            .setTitle(R.string.paste_title)
            .setView(input)
            .setPositiveButton(R.string.save) { _, _ -> applyPairing(input.text.toString()) }
            .setNegativeButton(android.R.string.cancel, null)
            .show()
    }

    private fun ensurePermissionsAndStart() {
        if (store.load() == null) { toast(getString(R.string.error_not_paired)); return }
        val needed = buildList {
            add(Manifest.permission.SEND_SMS)
            if (Build.VERSION.SDK_INT >= 33) add(Manifest.permission.POST_NOTIFICATIONS)
        }.filter { ContextCompat.checkSelfPermission(this, it) != PackageManager.PERMISSION_GRANTED }
        if (needed.isEmpty()) startGateway() else permissions.launch(needed.toTypedArray())
    }

    private fun startGateway() {
        GatewayService.start(this)
        render()
    }

    @SuppressLint("BatteryLife")
    private fun requestBatteryExemption() {
        val pm = getSystemService(PowerManager::class.java)
        if (pm.isIgnoringBatteryOptimizations(packageName)) { toast(getString(R.string.battery_ok)); return }
        startActivity(Intent(Settings.ACTION_REQUEST_IGNORE_BATTERY_OPTIMIZATIONS)
            .setData(Uri.parse("package:$packageName")))
    }

    private fun render() {
        val cfg = store.load()
        serverText.text = cfg?.let { getString(R.string.server_fmt, it.url, it.allowed.joinToString()) }
            ?: getString(R.string.error_not_paired)
        val label = when (store.state()) {
            "online" -> getString(R.string.state_online)
            "offline" -> getString(R.string.state_offline)
            "error" -> getString(R.string.state_error)
            else -> getString(R.string.state_stopped)
        }
        statusText.text = label
        val last = store.lastPoll()
        val ago = if (last > 0) DateUtils.getRelativeTimeSpanString(last) else "—"
        detailText.text = getString(R.string.detail_fmt, store.sentCount(), ago, store.lastError() ?: "—")
        toggle.text = getString(if (store.running) R.string.stop else R.string.start)
    }

    private fun toast(s: String) = Toast.makeText(this, s, Toast.LENGTH_LONG).show()
}
