package com.yami.telegramstremio

import android.annotation.SuppressLint
import android.os.Bundle
import android.webkit.WebResourceError
import android.webkit.WebResourceRequest
import android.webkit.WebView
import android.webkit.WebViewClient
import androidx.activity.OnBackPressedCallback
import androidx.appcompat.app.AppCompatActivity

class WebActivity : AppCompatActivity() {

    private lateinit var webView: WebView

    @SuppressLint("SetJavaScriptEnabled")
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)

        webView = WebView(this)
        setContentView(webView)
        webView.settings.apply {
            javaScriptEnabled = true
            domStorageEnabled = true
            useWideViewPort = true
            loadWithOverviewMode = true
            allowFileAccess = false
            allowContentAccess = false
        }
        webView.webViewClient = object : WebViewClient() {
            override fun onReceivedError(
                view: WebView,
                request: WebResourceRequest,
                error: WebResourceError
            ) {
                if (!request.isForMainFrame) return
                val url = request.url.toString()
                val jsUrl = url.replace("\\", "\\\\").replace("'", "\\'")
                val html = """
                    <html><body style="font-family:sans-serif;padding:24px;background:#0f172a;color:#e2e8f0">
                    <h3>Server not reachable</h3>
                    <p style="word-break:break-all">$url</p>
                    <p>${error.description}</p>
                    <p>Wait for the notification to say "Server ready", then retry.</p>
                    <button onclick="location.href='$jsUrl'"
                        style="padding:12px 20px;font-size:16px;border-radius:8px;border:0">Retry</button>
                    </body></html>
                """.trimIndent()
                view.loadDataWithBaseURL(url, html, "text/html", "UTF-8", null)
            }
        }
        webView.loadUrl(intent.getStringExtra("url") ?: "http://127.0.0.1:8000/")

        onBackPressedDispatcher.addCallback(this, object : OnBackPressedCallback(true) {
            override fun handleOnBackPressed() {
                if (webView.canGoBack()) webView.goBack() else finish()
            }
        })
    }
}
