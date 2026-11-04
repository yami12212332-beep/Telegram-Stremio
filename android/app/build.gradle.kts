plugins {
    id("com.android.application")
    id("org.jetbrains.kotlin.android")
    id("com.chaquo.python")
}

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
        // UV-managed CPython 3.11, used only at build time by Chaquopy's pip.
        buildPython("/home/yami/.local/share/uv/python/cpython-3.11.15-linux-x86_64-gnu/bin/python3.11")

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
