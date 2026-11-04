package com.yami.telegramstremio

import android.Manifest
import android.content.Intent
import android.content.pm.PackageManager
import android.os.Build
import android.os.Bundle
import android.os.Handler
import android.os.Looper
import android.widget.Button
import android.widget.CheckBox
import android.widget.EditText
import android.widget.TextView
import android.widget.Toast
import androidx.appcompat.app.AppCompatActivity
import androidx.core.app.ActivityCompat
import androidx.core.content.ContextCompat

class MainActivity : AppCompatActivity() {

    private lateinit var store: ConfigStore
    private lateinit var status: TextView

    private lateinit var apiId: EditText
    private lateinit var apiHash: EditText
    private lateinit var botToken: EditText
    private lateinit var ownerId: EditText
    private lateinit var trackingUri: EditText
    private lateinit var storageUri: EditText
    private lateinit var sourceBot: EditText
    private lateinit var staging: EditText
    private lateinit var port: EditText
    private lateinit var baseUrl: EditText
    private lateinit var externalSearch: CheckBox

    private val handler = Handler(Looper.getMainLooper())
    private val ticker = object : Runnable {
        override fun run() {
            refreshStatus()
            handler.postDelayed(this, 1500)
        }
    }

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContentView(R.layout.activity_main)
        store = ConfigStore(this)

        status = findViewById(R.id.tv_status)
        apiId = findViewById(R.id.et_api_id)
        apiHash = findViewById(R.id.et_api_hash)
        botToken = findViewById(R.id.et_bot_token)
        ownerId = findViewById(R.id.et_owner_id)
        trackingUri = findViewById(R.id.et_tracking_uri)
        storageUri = findViewById(R.id.et_storage_uri)
        sourceBot = findViewById(R.id.et_source_bot)
        staging = findViewById(R.id.et_staging_channel)
        port = findViewById(R.id.et_port)
        baseUrl = findViewById(R.id.et_base_url)
        externalSearch = findViewById(R.id.cb_external_search)

        loadFields()

        findViewById<Button>(R.id.btn_start).setOnClickListener { startServer() }
        findViewById<Button>(R.id.btn_stop).setOnClickListener { stopServer() }
        findViewById<Button>(R.id.btn_web).setOnClickListener { openWebUi() }

        requestNotificationPermission()
    }

    override fun onResume() {
        super.onResume()
        handler.removeCallbacks(ticker)
        handler.post(ticker)
    }

    override fun onPause() {
        handler.removeCallbacks(ticker)
        super.onPause()
    }

    private fun loadFields() {
        apiId.setText(store.apiId)
        apiHash.setText(store.apiHash)
        botToken.setText(store.botToken)
        ownerId.setText(store.ownerId)
        trackingUri.setText(store.trackingUri)
        storageUri.setText(store.storageUri)
        sourceBot.setText(store.externalBot)
        staging.setText(store.stagingChannel)
        port.setText(store.port)
        baseUrl.setText(store.baseUrl)
        externalSearch.isChecked = store.externalSearch
    }

    private fun saveFields() {
        store.apiId = apiId.text.toString().trim()
        store.apiHash = apiHash.text.toString().trim()
        store.botToken = botToken.text.toString().trim()
        store.ownerId = ownerId.text.toString().trim()
        store.trackingUri = trackingUri.text.toString().trim()
        store.storageUri = storageUri.text.toString().trim()
        store.externalBot = sourceBot.text.toString().trim().removePrefix("@")
        store.stagingChannel = staging.text.toString().trim()
        store.port = port.text.toString().trim().ifBlank { "8000" }
        store.baseUrl = baseUrl.text.toString().trim().ifBlank { "http://127.0.0.1:8000" }
        store.externalSearch = externalSearch.isChecked
    }

    private fun startServer() {
        saveFields()
        if (!store.isConfigured()) {
            toast("Fill API ID/hash, bot token, owner ID and both Mongo URIs first.")
            return
        }
        if (store.baseUrl.contains("127.0.0.1") || store.baseUrl.contains("localhost")) {
            toast("Tip: for Nuvio on another device, use this phone's LAN IP as Base URL.")
        }
        val intent = Intent(this, ServerService::class.java)
            .setAction(ServerService.ACTION_START)
        ContextCompat.startForegroundService(this, intent)
        toast("Starting the server…")
        refreshStatus()
    }

    private fun stopServer() {
        val intent = Intent(this, ServerService::class.java)
            .setAction(ServerService.ACTION_STOP)
        startService(intent)
    }

    private fun openWebUi() {
        val p = store.port.ifBlank { "8000" }
        startActivity(
            Intent(this, WebActivity::class.java)
                .putExtra("url", "http://127.0.0.1:$p/admin/settings")
        )
    }

    private fun refreshStatus() {
        status.text = if (ServerService.isRunning) {
            "● ${ServerService.lastMessage}"
        } else {
            "○ ${ServerService.lastMessage}"
        }
    }

    private fun requestNotificationPermission() {
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.TIRAMISU &&
            ContextCompat.checkSelfPermission(this, Manifest.permission.POST_NOTIFICATIONS) !=
            PackageManager.PERMISSION_GRANTED
        ) {
            ActivityCompat.requestPermissions(
                this, arrayOf(Manifest.permission.POST_NOTIFICATIONS), 100
            )
        }
    }

    private fun toast(message: String) {
        Toast.makeText(this, message, Toast.LENGTH_LONG).show()
    }
}
