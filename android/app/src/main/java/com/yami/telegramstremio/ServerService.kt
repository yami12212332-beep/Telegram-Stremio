package com.yami.telegramstremio

import android.app.Notification
import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.PendingIntent
import android.app.Service
import android.content.Intent
import android.content.pm.ServiceInfo
import android.os.Build
import android.os.IBinder
import android.os.PowerManager
import android.util.Log
import androidx.core.app.NotificationCompat
import androidx.core.app.ServiceCompat
import com.chaquo.python.Python
import com.chaquo.python.android.AndroidPlatform
import java.io.File

class ServerService : Service() {

    companion object {
        private const val TAG = "TS-Server"
        private const val CHANNEL_ID = "ts_server"
        private const val NOTIFICATION_ID = 1

        const val ACTION_START = "com.yami.telegramstremio.START"
        const val ACTION_STOP = "com.yami.telegramstremio.STOP"

        @Volatile var isRunning: Boolean = false
            private set

        @Volatile var lastMessage: String = "Stopped"
            private set
    }

    private var wakeLock: PowerManager.WakeLock? = null
    private var pythonThread: Thread? = null

    override fun onBind(intent: Intent?): IBinder? = null

    override fun onCreate() {
        super.onCreate()
        createChannel()
    }

    override fun onStartCommand(intent: Intent?, flags: Int, startId: Int): Int {
        when (intent?.action) {
            ACTION_STOP -> {
                stopServer()
                return START_NOT_STICKY
            }
            else -> startServer()
        }
        return START_STICKY
    }

    private fun startServer() {
        createChannel()
        ServiceCompat.startForeground(
            this,
            NOTIFICATION_ID,
            notification("Starting server…"),
            if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.Q) {
                ServiceInfo.FOREGROUND_SERVICE_TYPE_DATA_SYNC
            } else {
                0
            }
        )

        val power = getSystemService(POWER_SERVICE) as PowerManager
        if (wakeLock == null) {
            wakeLock = power.newWakeLock(PowerManager.PARTIAL_WAKE_LOCK, "ts:server").apply {
                setReferenceCounted(false)
                acquire()
            }
        }

        if (isRunning) {
            notify("Server is already running")
            return
        }

        isRunning = true
        lastMessage = "Starting…"

        val appDir = File(filesDir, "app")
        try {
            copyAssets("backend", appDir)
            ConfigStore(this).writeEnv(appDir)
        } catch (t: Throwable) {
            fail("Could not extract backend: ${t.message}", t)
            return
        }

        pythonThread = Thread({
            try {
                if (!Python.isStarted()) {
                    Python.start(AndroidPlatform(applicationContext))
                }
                notify("Starting Python…")
                val port = ConfigStore(applicationContext).port
                notify("Server running on port $port — open Admin")
                Python.getInstance()
                    .getModule("bootstrap")
                    .callAttr("start", appDir.absolutePath)
            } catch (t: Throwable) {
                fail("Python failed: ${t.message ?: t.javaClass.simpleName}", t)
            }
        }, "ts-python").apply { start() }
    }

    private fun stopServer() {
        lastMessage = "Stopped"
        isRunning = false
        releaseLock()
        stopForeground(STOP_FOREGROUND_REMOVE)
        stopSelf()
        // Chaquopy cannot unload Python in-process; finishing the process is the
        // only reliable stop. The UI restarts the app for a clean start.
        android.os.Process.killProcess(android.os.Process.myPid())
    }

    private fun fail(message: String, t: Throwable? = null) {
        lastMessage = message
        isRunning = false
        Log.e(TAG, message, t)
        notify(message)
        releaseLock()
    }

    private fun releaseLock() {
        wakeLock?.let {
            if (it.isHeld) it.release()
        }
        wakeLock = null
    }

    private fun copyAssets(assetPath: String, dest: File) {
        val children = assets.list(assetPath).orEmpty()
        if (children.isEmpty()) {
            dest.parentFile?.mkdirs()
            assets.open(assetPath).use { input ->
                dest.outputStream().use { output -> input.copyTo(output) }
            }
            return
        }
        dest.mkdirs()
        for (child in children) {
            copyAssets("$assetPath/$child", File(dest, child))
        }
    }

    private fun createChannel() {
        if (Build.VERSION.SDK_INT < Build.VERSION_CODES.O) return
        val manager = getSystemService(NotificationManager::class.java)
        if (manager.getNotificationChannel(CHANNEL_ID) != null) return
        manager.createNotificationChannel(
            NotificationChannel(
                CHANNEL_ID,
                "Telegram-Stremio server",
                NotificationManager.IMPORTANCE_LOW
            ).apply {
                description = "Keeps the addon and Telegram session running"
                setShowBadge(false)
            }
        )
    }

    private fun notification(text: String): Notification {
        val intent = Intent(this, MainActivity::class.java)
        val pending = PendingIntent.getActivity(
            this, 0, intent,
            PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE
        )
        return NotificationCompat.Builder(this, CHANNEL_ID)
            .setContentTitle("Telegram-Stremio")
            .setContentText(text)
            .setSmallIcon(R.drawable.ic_stat_server)
            .setOngoing(true)
            .setSilent(true)
            .setContentIntent(pending)
            .build()
    }

    private fun notify(text: String) {
        lastMessage = text
        val manager = getSystemService(NotificationManager::class.java)
        manager.notify(NOTIFICATION_ID, notification(text))
    }

    override fun onDestroy() {
        releaseLock()
        super.onDestroy()
    }
}
