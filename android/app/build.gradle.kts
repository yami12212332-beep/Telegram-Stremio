import java.util.Properties

plugins {
    id("com.android.application")
    id("org.jetbrains.kotlin.android")
    id("com.chaquo.python")
}

// Optional local defaults. android/local.properties is git-ignored, so the
// repository never contains API hashes, bot tokens or Mongo credentials.
val localProperties = Properties().apply {
    val file = rootProject.file("local.properties")
    if (file.exists()) file.inputStream().use { load(it) }
}

fun localDefault(key: String, fallback: String = ""): String =
    (project.findProperty(key) as String?)
        ?: localProperties.getProperty(key)
        ?: System.getenv(key)
        ?: fallback

fun quoted(value: String): String =
    "\"" + value.replace("\\", "\\\\").replace("\"", "\\\"") + "\""

android {
    namespace = "com.yami.telegramstremio"
    compileSdk = 35

    defaultConfig {
        applicationId = "com.yami.telegramstremio"
        minSdk = 26
        targetSdk = 35
        versionCode = 1
        versionName = "0.1.0"

        ndk {
            abiFilters += listOf("arm64-v8a")
        }

        buildConfigField("String", "DEFAULT_API_ID", quoted(localDefault("TS_API_ID")))
        buildConfigField("String", "DEFAULT_API_HASH", quoted(localDefault("TS_API_HASH")))
        buildConfigField("String", "DEFAULT_BOT_TOKEN", quoted(localDefault("TS_BOT_TOKEN")))
        buildConfigField("String", "DEFAULT_OWNER_ID", quoted(localDefault("TS_OWNER_ID")))
        buildConfigField("String", "DEFAULT_TRACKING_URI", quoted(localDefault("TS_TRACKING_URI")))
        buildConfigField("String", "DEFAULT_STORAGE_URI", quoted(localDefault("TS_STORAGE_URI")))
        buildConfigField("String", "DEFAULT_SOURCE_BOT", quoted(localDefault("TS_SOURCE_BOT", "M1searcherbot")))
        buildConfigField("String", "DEFAULT_STAGING", quoted(localDefault("TS_STAGING")))
        buildConfigField("String", "DEFAULT_PORT", quoted(localDefault("TS_PORT", "8000")))
        buildConfigField("String", "DEFAULT_BASE_URL", quoted(localDefault("TS_BASE_URL", "http://127.0.0.1:8000")))
    }

    buildTypes {
        release {
            isMinifyEnabled = false
            proguardFiles(getDefaultProguardFile("proguard-android-optimize.txt"), "proguard-rules.pro")
        }
    }

    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_17
        targetCompatibility = JavaVersion.VERSION_17
    }

    kotlinOptions {
        jvmTarget = "17"
    }

    buildFeatures {
        buildConfig = true
    }
}

chaquopy {
    defaultConfig {
        version = "3.11"
        // Set TS_BUILD_PYTHON in android/local.properties or the environment
        // if python3.11 is not on PATH.
        buildPython(localDefault("TS_BUILD_PYTHON", "python3.11"))

        pip {
            // FastAPI 0.99 + Pydantic 1 avoids the native pydantic-core build.
            install("fastapi==0.99.1")
            install("pydantic==1.10.15")
            install("starlette==0.27.0")
            install("uvicorn==0.23.2")
            install("dnspython==2.6.1")
            install("pyrofork==2.3.61")
            install("wheels/pyaes-1.6.1-py3-none-any.whl")
            install("python-dotenv==1.0.1")
            install("aiofiles==23.2.1")
            install("httpx==0.27.2")
            install("jinja2==3.1.4")
            install("python-multipart==0.0.9")
            install("itsdangerous==2.2.0")
            install("guessit==3.8.0")
            install("parse-torrent-title==2.8.2")
            install("pytz==2024.2")
            install("themoviedb==1.0.2")
            install("requests==2.32.3")
            install("certifi==2024.8.30")
        }
    }
}

// Copy the Python server into assets before the APK is assembled.
val copyBackend = tasks.register<Sync>("copyBackend") {
    from(rootProject.file("../Backend")) {
        into("Backend")
        exclude("**/__pycache__/**", "**/*.pyc")
    }
    into(layout.projectDirectory.dir("src/main/assets/backend"))
}

tasks.named("preBuild") {
    dependsOn(copyBackend)
}

dependencies {
    implementation("androidx.core:core-ktx:1.13.1")
    implementation("androidx.appcompat:appcompat:1.7.0")
    implementation("com.google.android.material:material:1.12.0")
    implementation("androidx.constraintlayout:constraintlayout:2.1.4")
}
