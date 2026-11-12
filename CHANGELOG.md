# Changelog

All notable changes to the M Searcher bridge and the Android on-device server.

## 2026-11-12

- External stream URLs now end in `/video.mkv`, e.g.
  `/ms/resolve/<token>/<id>/video.mkv`. Nuvio's mpv/ytdl_hook was seeing an
  extensionless URL and trying to launch `youtube-dl`, producing
  `[ytdl_hook] youtube-dl failed: not found or not enough permissions`.
- `/ms/resolve` now **streams the file directly** (`200`/`206` with
  `video/x-matroska`) instead of returning a `307` redirect to `/dl`.
  Nuvio's internal mpv mishandles the redirect: the direct local `/dl` URL
  played, but the external redirect triggered ytdl_hook. The old
  `/ms/resolve/<token>/<id>` URL still works.
- Workaround if Nuvio's internal player still insists on yt-dlp: use VLC or
  another external player.
- `EXTERNAL_ALWAYS` now defaults to **true**: bot results are shown beside the
  local library instead of disappearing as soon as one local copy exists. Set it
  to false in Admin → Settings → M Searcher Bridge if you want fallback-only
  behavior.

## 2026-11-04

### Android on-device server — working

- Kotlin app + Chaquopy CPython 3.11 runs the existing FastAPI/Pyrogram server
  on the phone.
- Foreground service, wake lock, notification, and a `/login` readiness probe.
- Native setup screen writes `config.env`; WebView opens the admin UI.
- In-app **View Log** reads `filesDir/app/server.log`.
- Startup errors are re-raised and logged instead of being masked as
  `CancelledError`.
- **TgCrypto 1.2.5** bundled from Chaquopy's arm64 wheel. This fixes the
  pure-Python AES bottleneck that capped streams at roughly 0.1 MB/s.
- Atlas support: standard multi-host URIs work; `DATABASE` accepts `;` or `,`.
- Build defaults come from git-ignored `android/local.properties` (`TS_*` keys).
  The repository contains no credentials.
- Prefilled test APK works on-device; admin panel opens and Nuvio playback is
  confirmed.

### M Searcher bridge

- On-demand fallback for titles missing from the Telegram-Stremio library.
- Source query forms: `S01E01`, `S01E1`, `S01 EP01`, then `S01`.
- Episode parsing + strict filtering; a different episode is never played.
- Movie and episode result pagination (up to 5 pages).
- Single-match direct-file replies handled without a button.
- Page-aware playback: candidates remember the result page, navigate before
  clicking, and fall back to label matching or a full page scan.
- Pending/resolved `/ms/resolve` requests persist in MongoDB with a 2h TTL.
- Prefetch capped by `EXTERNAL_PREFETCH_LIMIT` (0-5, default 1).
- Hourly staging orphan sweep; only unreferenced messages are deleted.
- Settings card for every bridge field.
- `/ms/resolve` mirrors the `/stream` subscription-group check.
- `EXTERNAL_VARIANTS=0` exposes every source; max options 1-100.

### Fixes worth remembering

- Pyrogram `message.click` takes `(column, row)`, not `(row, column)`.
- Result callback data is page-bound and re-encrypted on re-render; match by
  normalized label when needed.
- Result headers use `Total Pages : x/y`, not `Page x/y`.
- `DATABASE` must not split multi-host Atlas URIs on their internal commas.
- Pure-Python AES is the first thing to check when Android streaming is slow.
