# M Searcher → Nuvio on-demand — implementation handoff

Status: **vertical slice implemented, not yet runtime-tested against the real source bot.**
Branch: `feature/msearcher-on-demand`
Base: `e6024b8` (Telegram-Stremio 5.3.0)
Commit: `feat: on-demand M Searcher bridge for missing titles`

---

## 1. What this adds

A fallback source for titles that are **not in the Telegram-Stremio library**.
Nuvio/Stremio asks for streams; the addon searches a third-party Telegram
file-search bot (M Searcher) through your own **user session**, offers the
source bot's file buttons as Nuvio stream options, and on first play copies the
chosen file into a staging channel you control.

Why a user session: Telegram does not let one bot read another bot's messages.
A bot token cannot query M Searcher directly.

```
Nuvio / Stremio
   │  /stream/{type}/{imdb}.json
   ▼
Telegram-Stremio addon
   │  search (userbot → M Searcher DM)
   │  result buttons → stream options
   ▼
GET /ms/resolve/{token}/{request_id}
   │  click button → receive document
   │  copy_message → staging channel
   ▼
302 → /dl/{token}/{encoded}/{name}
   │  existing streamer
   ▼
Player
```

The staging copy is also picked up by the normal receiver and indexed, so later
plays come from the local library.

---

## 2. Files changed

| File | Change |
|---|---|
| `Backend/helper/external_search.py` | **New.** Userbot adapter: query, parse inline buttons, click, copy, cache, request registry, prefetch. |
| `Backend/fastapi/routes/stremio_routes.py` | Appends external stream options to `/stream` for titles with no local streams (or when `external_always` is on). |
| `Backend/fastapi/routes/stream_routes.py` | New `/ms/resolve/{token}/{request_id}` endpoint; resolves, copies, redirects to `/dl`. |
| `Backend/pyrofork/plugins/receiver.py` | Treats `staging_channel` as an indexable channel (receive, edit, delete handlers). |
| `Backend/config.py` | `EXTERNAL_*` env fields. |
| `Backend/helper/settings_manager.py` | Defaults + typed properties for the bridge settings. |
| `Backend/fastapi/routes/api_routes.py` | Validation/coercion for the new settings (API, not UI yet). |
| `Backend/__main__.py` | Startup config check and staging-channel reachability warning. |
| `sample_config.env` | Documented env block. |
| `docs/msearcher.md` | Setup and operations guide. |

---

## 3. Configuration

Add to `config.env`:

```env
EXTERNAL_SEARCH="true"
EXTERNAL_BOT="MSearcherBot"          # username, no @
STAGING_CHANNEL="-1001234567890"     # private channel

EXTERNAL_TAMIL_FIRST="true"          # prefer Tamil labels
EXTERNAL_PREFETCH="false"            # copy offered files immediately
EXTERNAL_ALWAYS="false"              # also for titles already local
EXTERNAL_TIMEOUT="8"                 # seconds, 3-30
EXTERNAL_MAX_RESULTS="6"             # options, 1-20
EXTERNAL_VARIANTS="1"                # copies per quality, 1-3
```

Staging channel requirements:

- Private **channel** (not a group).
- Your user account can post.
- `StreamBot` is an administrator/member so it receives the post and can stream it.
- `BASE_URL` is set to the public addon URL.

There is **no Settings-page card yet**; use `config.env` (or POST the keys to the
settings API). Existing databases merge the env defaults because the keys are
missing from `_DEFAULTS`.

---

## 4. Testing done

Environment: Termux, Python 3.14, no app dependencies/Pyrogram installed in the clone.

| Check | Result |
|---|---|
| `python -m py_compile` on all modified files | ✅ |
| `python -m compileall -q Backend` | ✅ |
| `git diff --check` | ✅ |
| Pure logic test with stubs: `build_query`, `parse_candidate`, `select_candidates`, `register`/`get_request` | ✅ |
| Sample labels from the screenshots (`《1.67 GB》 … 1080p`, `《700.76 MB》 … 720p`) parse | ✅ |
| Page/nav labels (`Next`, `Previous`, `Page 3/313`) are ignored | ✅ |
| Tamil candidate wins the 1080p slot over a non-Tamil 1080p | ✅ |
| Real M Searcher query / button click / copy | ❌ not run |
| Nuvio playback and redirect | ❌ not run |
| 2 GB copy / `noforwards` / FloodWait behavior | ❌ not run |

The code is intentionally defensive: failures are logged with `[MSEARCH]` and the
addon still returns local streams/donation instead of breaking `/stream`.

---

## 5. Test plan (next)

### P0 — validate the source bot (do this first)

1. From the userbot account, send `House of the Dragon 2026 S03E02`.
2. Confirm the reply is **one message with inline callback buttons** and that the
   labels include size + quality (+ Tamil when applicable).
3. Press one button; confirm a document/video arrives **in the same chat**.
4. Copy it to the staging channel and time it (1 GB+).
5. Confirm the copy plays via `/dl` and is indexed (check Media Management).
6. Repeat with a title that has `restrict saving content`; record the failure.
7. Check a >2 GB file on a free account.

If step 2 or 3 fails, adjust `external_search.py` before spending time on Nuvio.

### Integration without real Telegram

- Add a fake `Userbot`/message factory to exercise `search_candidates`,
  `_click_and_wait`, `_copy_to_staging`.
- Test `/stream` with `external_search=true` and a fake adapter: local hit,
  local miss, timeout, `ExternalSearchBusy`, no candidates.
- Test `/ms/resolve`: valid token, expired token, wrong token, expired request,
  resolved request (idempotent redirect), copy failure.
- Test receiver staging: valid file, duplicate, edit, delete.

### Manual Nuvio

- Title not in library → options appear; first play copies; second play local.
- `EXTERNAL_ALWAYS=true` → external options appear beside local ones.
- `EXTERNAL_VARIANTS=3` → up to 3 options per quality.
- `EXTERNAL_PREFETCH=true` → first play is fast / no duplicate copies.
- Tamil label present/absent.
- Token expired / data limit / subscription expired.
- Server restart between `/stream` and play → 404 with a clear message.

### Edge cases

- Source bot uses URL buttons (unsupported).
- Source bot sends a text error ("join channel").
- Source bot deletes or edits the result message after caching.
- `FLOOD_WAIT` during search/click/copy.
- Staging channel not accessible to `StreamBot`.
- Caption/filename that metadata cannot parse (direct stream should still work).
- Duplicate protection enabled.

---

## 6. What still needs doing (prioritized)

1. **P0 validation** (above) — determines whether the whole approach survives.
2. **Settings page card** — toggle, bot username, staging channel, Tamil/prefetch/
   variants/timeouts. API validation exists, UI does not.
3. **Pagination** — source results have pages; currently only the first result
   message is parsed.
4. **Dedupe / duplicate-protection interaction** — if `external_always` is on and
   the same file is already indexed, the receiver may delete the copy while the
   player holds a direct `/dl` link. Detect and redirect to the existing stream, or
   skip external options for known files.
5. **Prefetch hardening** — queue width, cancel on title change, avoid copying all
   variants for every `/stream` call, persist state across restarts.
6. **Tamil detection** — currently label-only. If the label lacks language, inspect
   the file caption after click (costs a copy) or tag manually.
7. **Tests** — add the fake-userbot suite and endpoint tests to CI.
8. **Security parity** — `/ms/resolve` checks token expiry/limits but not
   subscription group membership; mirror the `/stream` checks.
9. **Observability** — counters for searches/copies/failures, admin status card.
10. **Legal review** — third-party source + redistribution/ToS risk.

---

## 7. Known limitations

- External options are a **fallback**; with `EXTERNAL_ALWAYS=false` a title with
  any local stream will not show them.
- Tamil is detected from the **button label only**.
- Only IMDb IDs; Kitsu/anime IDs are skipped.
- Request state is in memory; a restart invalidates pending `/ms/resolve` URLs.
- Single-process design; multiple uvicorn workers would not share `_REQUESTS`.
- `noforwards`/protected content blocks copying.
- 2 GB per file on free accounts; 4 GB with Premium.
- The source bot is third-party and can change UI/rate-limit/ban at any time.
- No bulk import; only the selected file is copied.

---

## 8. Rollback

Set `EXTERNAL_SEARCH="false"` and restart. The staging receiver code is dormant
unless `staging_channel` is set; existing local streams are unaffected. To remove
the feature entirely, revert the commit.

---

## 9. Apply / push

Patch: `msearcher-on-demand.patch` (format-patch, one commit).

```bash
git am msearcher-on-demand.patch
# or
git apply msearcher-on-demand.patch
```

Push to your fork:

```bash
git remote add fork https://github.com/<you>/Telegram-Stremio.git
git push -u fork feature/msearcher-on-demand
```
