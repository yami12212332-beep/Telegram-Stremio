# Project state — M Searcher bridge + Android APK

Branch: `feature/msearcher-on-demand`
Base: Telegram-Stremio 5.3.0 (`e6024b8`)
Fork: `https://github.com/yami12212332-beep/Telegram-Stremio`

## What works

### M Searcher bridge
- `/stream` fallback for titles missing from the local library.
- Correct source query forms: `S01E01`, `S01E1`, `S01 EP01`, then `S01`.
- Episode parsing and strict filtering; a different episode is never returned.
- Movie and episode result pagination (up to 5 pages).
- Direct-file replies (single match, no buttons) are handled.
- Page-aware playback: candidates remember their result page; the shared
  message is navigated before clicking, with label and full-page fallbacks.
- Pending/resolved play requests persist in MongoDB (`ms_requests`, 2h TTL),
  so a restart no longer breaks a selected stream.
- Prefetch is capped by `EXTERNAL_PREFETCH_LIMIT` (0-5, default 1).
- Hourly orphan sweep removes staging messages no library entry references.
- Settings card: Admin → Settings → M Searcher Bridge.
- `/ms/resolve` mirrors the `/stream` subscription-group check.
- `EXTERNAL_VARIANTS=0` exposes every available source; max results 1-100.
- Multi-host Atlas URIs are supported: `DATABASE` accepts `;` or `,`.

### Android
- Kotlin app + Chaquopy (CPython 3.11) runs the existing Python server on the phone.
- Foreground service, wake lock, notification, readiness probe of `/login`.
- Native setup screen writes `config.env`; WebView opens the admin UI.
- In-app **View Log** reads `filesDir/app/server.log`.
- Startup errors are re-raised and logged instead of becoming `CancelledError`.
- Vendored pure-Python `pymongo`/`bson`/`gridfs`/`motor`; local `pyaes` wheel.
- Pydantic 1 / FastAPI 0.99 for Android (avoids native `pydantic-core`).
- Uvicorn falls back to asyncio/h11 when uvloop/httptools are absent.
- arm64 debug APK, ~52 MB.
- **TgCrypto 1.2.5** native AES bundled; without it Pyrogram falls back to
  pure-Python AES and streams at roughly 0.1 MB/s.

## Android build (new machine)

Prerequisites:
- JDK 17
- Android SDK platform 35 + build-tools 35.0.0
- Gradle 8.9
- Python 3.11 for Chaquopy (`buildPython`)

```bash
cd android
cp local.properties.example local.properties
# edit local.properties: sdk.dir and TS_BUILD_PYTHON
export JAVA_HOME=/path/to/jdk-17
export ANDROID_HOME=/path/to/Android/Sdk
gradle :app:assembleDebug
```

APK: `android/app/build/outputs/apk/debug/app-debug.apk`

`android/local.properties` is git-ignored. The repo contains **no credentials**.
To prefill the setup screen, add `TS_*` keys there (see
`android/local.properties.example`), or enter them manually in the app.

Note: `android/gradlew` is not included; install Gradle 8.9 or run the wrapper
task if your network allows it.

## Atlas

One free M0 cluster, two databases, standard (non-SRV) URIs:

```
mongodb://USER:PASS@host-00.xxxxx.mongodb.net:27017,host-01.xxxxx.mongodb.net:27017,host-02.xxxxx.mongodb.net:27017/ts_tracking?replicaSet=atlas-xxxxx-shard-0&authSource=admin&tls=true&retryWrites=true&w=majority
mongodb://USER:PASS@host-00.xxxxx.mongodb.net:27017,host-01.xxxxx.mongodb.net:27017,host-02.xxxxx.mongodb.net:27017/ts_storage?replicaSet=atlas-xxxxx-shard-0&authSource=admin&tls=true&retryWrites=true&w=majority
```

On Android, the app writes both URIs separated by `;` because the standard URI
contains commas. `Backend/config.py` accepts both separators.

## First run on Android

1. Fill API ID/hash, bot token, owner ID, both Mongo URIs, source bot, staging
   channel; set Base URL to `http://127.0.0.1:8000` (same phone) or the phone's
   LAN IP (Nuvio on another device).
2. Start; wait for “Server ready on port 8000”.
3. Open Admin → `admin`/`admin` → change password.
4. Settings → Telegram User Session → connect the userbot.
5. Tokens → copy the manifest URL into Nuvio/Stremio.
6. Make the bot an admin in the staging channel.

## Test status

- P0 core: search, buttons, click, copy, `/dl`, indexing, idempotent replay: pass.
- Episode matching: pass (VisionQuest S01E01, HOTD S03E02; Heart Beat E01 absent).
- Movie pagination: Baasha 39 results / 4 pages, 37-38 unique options.
- Page-aware playback: The Dark Knight page-4/page-2 picks resolve.
- Persistence: unresolved link after restart works; resolved link returns 307.
- Prefetch cap: S03E05 copied exactly 1 file.
- Staging sweep: 28 scanned, 11 orphans deleted, 17 referenced kept.
- >2 GB: a 2.9 GB copy succeeded on the test account.
- `noforwards` / restricted content: not tested.
- Android: admin panel opens on-device; Nuvio playback confirmed after bundling
  TgCrypto. The native AES module removed the 0.1 MB/s bottleneck.

Last verified: 2026-11-04.

## Known issues / next work

1. **Built-in player** — the APK is server-only. Add a catalog browser + libVLC
   player for on-device playback without Nuvio.
2. **Dedupe / duplicate-protection** — replace mode may delete a variant while a
   player holds its `/dl` link.
3. **First `/stream` latency** — large movies can take ~10-15s (page collection
   plus page reset). Cache/lazy-load or avoid returning to page 1.
4. **Tamil/quality inference** — label-only; infer from filename/size when absent.
5. **Tests/CI** — offline logic tests exist; add fake-userbot and endpoint tests.
6. **Android runtime** — Stop kills the process (Chaquopy limitation); session is
   stored in Atlas (obfuscated, not encrypted); arm64 only; disable battery
   optimization.
7. **Security** — previously committed test credentials were removed from the
   branch. Rotate the bot token, Atlas password and API hash if they were exposed.

## Local server (development)

```bash
uv sync
cp sample_config.env config.env
# fill API_ID, API_HASH, BOT_TOKEN, OWNER_ID, DATABASE
.venv/bin/python -m Backend
```

Local test environment used two MongoDB containers on ports 27017/27018, but
any 2 URIs work. `config.env` is git-ignored.
