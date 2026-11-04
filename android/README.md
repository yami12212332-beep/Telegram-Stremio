# Telegram-Stremio Android (on-device server)

This is a **server-only** Android wrapper around the existing Python app. The
phone runs FastAPI, Pyrogram, StreamBot and the M Searcher bridge; MongoDB stays
in a free Atlas cluster.

## Build

```bash
# JDK 17 and Android SDK 35 are required.
export JAVA_HOME=/home/yami/android/jdk-17.0.21+9
export ANDROID_HOME=/home/yami/android/sdk
export GRADLE_USER_HOME=/home/yami/android/.gradle
./gradle-8.9/bin/gradle :app:assembleDebug
```

APK: `app/build/outputs/apk/debug/app-debug.apk`

## Install

```bash
adb install -r app/build/outputs/apk/debug/app-debug.apk
```

Or copy the APK to the phone and allow "install unknown apps".

## Atlas

Create one free M0 cluster and **two databases** on it. Put the database name in
the URI path so the app can keep tracking and storage separate:

```
mongodb+srv://USER:PASS@cluster0.xxxxx.mongodb.net/ts_tracking?retryWrites=true&w=majority
mongodb+srv://USER:PASS@cluster0.xxxxx.mongodb.net/ts_storage?retryWrites=true&w=majority
```

Allow `0.0.0.0/0` in Network Access (the phone IP changes), or restrict it later.

If the `mongodb+srv://` form fails on Android (DNS resolver difference), use
Atlas's standard connection string instead, e.g.:

```
mongodb://USER:PASS@host-00.xxxxx.mongodb.net:27017,host-01.xxxxx.mongodb.net:27017,host-02.xxxxx.mongodb.net:27017/ts_tracking?replicaSet=atlas-xxxxx-shard-0&authSource=admin&tls=true&retryWrites=true&w=majority
```

Open **View Log** in the app if startup fails; it shows the Python traceback.

## First run

1. Fill API ID/hash, bot token, owner user ID, both Mongo URIs, source bot
   (`M1searcherbot`) and staging channel.
2. Tap **Save & Start Server** and grant the notification permission.
3. Tap **Open Admin / Telegram Login** → log in with `admin`/`admin` (change it
   in Settings) → Telegram User Session → connect the userbot.
4. The addon URL is shown on the admin dashboard. Add it to Nuvio/Stremio.
5. For Nuvio on another device, set **Base URL** to `http://<phone-LAN-IP>:8000`
   before starting.

## Notes

- The server runs in a foreground service with a wake lock; disable battery
  optimization for the app if Android kills it.
- **Stop Server** kills the app process, because Chaquopy cannot unload Python
  in-process.
- The Telegram user session is stored in the Atlas tracking database (obfuscated
  by the existing `encode_string`, not encrypted). Use a dedicated account and a
  strong Atlas password.
- The APK is arm64 only and ~39 MB.
- This build omits `tgcrypto`, `rapidfuzz` (pure-Python fallback), `zstandard`
  (optional), `uvloop` and `httptools` (uvicorn falls back to asyncio/h11).
