# Telegram-Stremio Android (on-device server)

Server-only Android wrapper around the Python app. The phone runs FastAPI,
Pyrogram, StreamBot and the M Searcher bridge; MongoDB stays in Atlas.
Playback is through Nuvio/Stremio for now (built-in libVLC is next).

## Build

Prerequisites:

- JDK 17
- Android SDK platform 35 and build-tools 35.0.0
- Gradle 8.9
- Python 3.11 (`buildPython`)

```bash
cd android
cp local.properties.example local.properties
# edit sdk.dir and TS_BUILD_PYTHON
export JAVA_HOME=/path/to/jdk-17
export ANDROID_HOME=/path/to/Android/Sdk
gradle :app:assembleDebug
```

APK: `app/build/outputs/apk/debug/app-debug.apk` (arm64, ~52 MB)

## Performance

`tgcrypto==1.2.5` is bundled from Chaquopy's Android wheel. Without it, Pyrogram
uses pure-Python AES and streaming drops to roughly 0.1 MB/s. After startup,
**View Log** must not contain `TgCrypto is missing`.

If playback is still slow with TgCrypto active, test on Wi-Fi, try a lower
quality, and check the phone's CPU/decoder support for HEVC.

`local.properties` is git-ignored. The repository contains no credentials.

## Optional prefilled setup

Add any of these to `android/local.properties` before building:

```properties
TS_API_ID=
TS_API_HASH=
TS_BOT_TOKEN=
TS_OWNER_ID=
TS_TRACKING_URI=
TS_STORAGE_URI=
TS_SOURCE_BOT=M1searcherbot
TS_STAGING=
TS_PORT=8000
TS_BASE_URL=http://127.0.0.1:8000
```

They become `BuildConfig` defaults and appear in the setup screen. Leave them
blank to fill the form manually.

## Atlas

Use **standard** connection strings, not `mongodb+srv`, if Android SRV DNS fails:

```
mongodb://USER:PASS@host-00.xxxxx.mongodb.net:27017,host-01.xxxxx.mongodb.net:27017,host-02.xxxxx.mongodb.net:27017/ts_tracking?replicaSet=atlas-xxxxx-shard-0&authSource=admin&tls=true&retryWrites=true&w=majority
```

and the same with `/ts_storage`. The app writes them with `;` between the two
URIs because the standard URI contains commas.

## First run

1. Fill the setup screen and tap **Save & Start Server**.
2. Wait for “Server ready on port 8000”.
3. **Open Admin / Telegram Login** → `admin`/`admin` → change password.
4. Settings → Telegram User Session → connect the userbot.
5. Tokens → copy the manifest URL into Nuvio/Stremio.
6. Add the bot as admin in the staging channel.

For Nuvio on another device, set Base URL to the phone's LAN IP before starting.

## Troubleshooting

- **View Log** shows `filesDir/app/server.log` (Python traceback, `[MSEARCH]`).
- `CancelledError` in older builds was a masked startup error; current builds
  re-raise the real exception and write it to the log.
- **Stop Server** kills the app process because Chaquopy cannot unload Python
  in-process.
- Disable battery optimization for the app; the server runs in a foreground
  service with a wake lock.
- The APK is arm64 only.
- Nuvio's internal mpv may show `[ytdl_hook] youtube-dl failed` on an
  extensionless URL. External stream URLs now end in `/video.mkv`; if the app
  still insists on yt-dlp, play the stream with VLC or another external player.

See `../PROJECT_STATE.md` for the full status and remaining work.
