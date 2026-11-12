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
EXTERNAL_BOT="M1searcherbot"          # username of the source bot, no @
STAGING_CHANNEL="-1001234567890"     # private channel

EXTERNAL_TAMIL_FIRST="true"          # prefer Tamil labels
EXTERNAL_PREFETCH="false"            # copy offered files immediately
EXTERNAL_PREFETCH_LIMIT="1"          # max candidates prefetch may copy, 0-5
EXTERNAL_ALWAYS="true"              # also for titles already local
EXTERNAL_TIMEOUT="8"                 # seconds, 3-30
EXTERNAL_MAX_RESULTS="50"            # options, 1-100
EXTERNAL_VARIANTS="0"                # 0 = every source, or cap per quality
```

Staging channel requirements:

- Private **channel** (not a group).
- Your user account can post.
- `StreamBot` is an administrator/member so it receives the post and can stream it.
- `BASE_URL` is set to the public addon URL.

The bridge is configured in **Admin → Settings → M Searcher Bridge**, or from
`config.env` (the settings API accepts the same keys). Existing databases merge
the env defaults for keys missing from `_DEFAULTS`.

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

### P0 run 1 — live bot, 2026-11-04

Session: `@me_h_i` (Telethon session from the local `TelegramSteamBot` checkout).
The addon itself was not started; this validated the bot side only.

| Step | Result |
|---|---|
| Resolve configured bot | ❌ `MSearcherBot` does not exist; real username is **`@M1searcherbot`** ("M Searcher bot") |
| Query format | ❌ `House of the Dragon 2026 S03E02` → "No results"; ✅ `House of the Dragon 2026 S03 EP02` → 4 buttons |
| Reply shape | ✅ multi-result queries return one message with inline callback buttons |
| Single-result queries | ⚠️ the bot sometimes sends the **file directly, with no buttons** (observed for `Dragon`, `Thevar magan`) |
| Button labels | ✅ `《1.67 GB》… 1080p S03EP02`; ⚠️ other results use `[3.52 GB] …` and `1080` without `p` |
| Ignored buttons | ✅ ad button `😍 New Dating BoT 😘`, `📚 Page 1/3`, `Next ⏩` are dropped by the parser |
| Click → file | ✅ clicked `《1.87 GB》… 1080p S03EP08`; document arrived in **1.4s**, 2,008,525,192 bytes, `noforwards=False` |
| Pagination | ⚠️ `House of the Dragon S03` returned 26 results across 3 pages; only page 1 is parsed |
| Staging copy | ✅ created private `Telegram-Stremio Staging` (`-1003752379719`); 1.87 GiB copied in **0.1s** with no forward header |
| `/ms/resolve` → `/dl` | ✅ 307 in ~3s; `/dl` returned 200 (HEAD), 206 range, correct `content-length`/`content-type` |
| Receiver indexing | ✅ staged copies indexed into `tv` (`S03E02`: 1080p, 720p, 480p); second `/stream` served local `/dl` streams |
| Idempotent play | ✅ same `/ms/resolve` URL redirects again in 0.01s without a second copy |
| Restart | ✅ pending request IDs become 404 (expected, in-memory registry) |
| Restricted content (>2 GB) | ❌ not tested |

Fixes applied from run 1:

- `build_query` emits `SxxExx` (and the old spaced form as a fallback) and omits
  the year for episodes, because the source index year can differ.
- `search_best` tries progressively broader movie queries and stops early on
  "No results" instead of waiting out the timeout.
- `_SIZE_RE` accepts `[...]` / `【...】` as well as `《...》` / `<...>`.
- `_QUALITY_RE` accepts `1080` as well as `1080p`, normalized to `1080p`.
- A direct file reply (single match) becomes a synthetic candidate with no
  callback data; `prepare_request` copies that message without clicking.
- **`message.click` axis bug**: Pyrogram takes `(x, y)` = `(column, row)`; the
  bridge passed `(row, col)`, so every non-zero row failed.
- `/ms/` now returns a JSON 401 instead of redirecting to `/login`.

### P0 run 2 — series episodes and all sources, 2026-11-04

| Check | Result |
|---|---|
| Exact episode query | ⚠️ bots index either `S01E01` (VisionQuest) or `S01 EP01` (House of the Dragon); one form alone misses half the shows |
| Season fallback | ❌ `VisionQuest S01 EP01` → no results, then `VisionQuest S01` returned page 1 (E04-E07); the bridge played the **wrong episode** |
| Episode filtering | ✅ candidates now carry parsed season/episode; different episodes are never offered |
| Episode pagination | ✅ bounded walk (max 5 pages) of `S01E1`-style results; matches are cached |
| VisionQuest S01E01 | ✅ 3 sources (`1.44GB`, `426.63MB`, `267.96MB`), all the same episode |
| House of the Dragon S03E02 | ✅ falls through `S03E02` → `S03E2` → `S03 EP02`, then returns 3 sources |
| Heart Beat S01E01 | ✅ no options returned — the source's `S01E1` result set ends at E10 on page 4, so E01 is genuinely absent |
| All sources | ✅ `EXTERNAL_VARIANTS=0` + `EXTERNAL_MAX_RESULTS=50`; Dorothy now exposes 10 options instead of 3 |
| Stream grouping | ✅ `bingeGroup` is unique per request so players do not collapse variants |

### P0 run 3 — movie pagination, 2026-11-04

| Check | Result |
|---|---|
| Bot header | `Baasha 1995` → `Total Results: 39`, `Page 1/4` (10+10+10+9 file buttons) |
| Old behaviour | ❌ only page 1 parsed → 10 options, the other 29 never fetched |
| Movie pagination | ✅ walks all `Next` pages and aggregates; 38 unique buttons after dropping one duplicate |
| Display cap | ✅ raised from 20 to 50 (API accepts 1-100) so the full result set is exposed |

Fix: `search_all` now collects every page for movie searches (max 5 pages) before
`select_candidates` applies the display cap.

Fixes applied from this run:

- Parse `SxxExx`, `Sxx EPxx` and `EPxx` from labels into `Candidate.season/episode`.
- `build_episode_queries` tries `S01E01`, `S01E1`, `S01 EP01`, then `S01`.
- `search_episode` filters by the requested episode and pages through episode-specific
  results (max 5 pages) instead of accepting whatever page 1 returned.
- `select_candidates` refuses to return a different episode than requested.
- `EXTERNAL_VARIANTS=0` means every available source; `EXTERNAL_MAX_RESULTS` default 50.
- Stream names fall back to the file size when the label has no quality token.

### P0 run 4 — page-aware playback, 2026-11-04

| Check | Result |
|---|---|
| Symptom | `/ms/resolve` returned 502 `The M Searcher result list changed` for every multi-page movie |
| Cause 1 | the result header says `Total Pages : 3/11`, but the parser only matched `Page 3/11`, so every candidate was tagged **page 1** |
| Cause 2 | callback data is page-state-bound; clicking a page-1 button while the message sat on page 5 fails with `DATA_INVALID` |
| Page parsing | ✅ `_PAGE_RE` accepts `Total Pages : x/y` and `Page x/y` |
| Page tracking | ✅ each candidate stores the page it was parsed from |
| Resolve | ✅ navigates to that page before clicking; falls back to a label match, then a full page scan |
| The Dark Knight | ✅ 48 options; page-4 pick copied + returned 200 in 9.3s, page-2 pick in 4.4s |
| Shared message | ✅ a page lock serializes navigation/clicks across concurrent resolves |
| Timeouts | ✅ `/ms/resolve` allows 40-80s when navigation is required |

Fixes applied from this run:

- `Candidate.page` / `ExternalRequest.page`; `register` persists the page.
- `_collect_pages` leaves the message on page 1 after collecting (best effort).
- `_click_and_wait` navigates to the stored page, then matches by callback data
  or normalized label before clicking.
- `find_button`/`_find_button_across_pages` tolerate callback re-encryption and
  page reordering.

### P0 run 5 — prefetch, cleanup, settings UI, 2026-11-04

| Check | Result |
|---|---|
| Prefetch storm risk | ❌ prefetch copied every selected option (up to 48) |
| Prefetch cap | ✅ `EXTERNAL_PREFETCH_LIMIT` (0-5, default 1); S03E05 prefetch copied exactly **1** file |
| Staging growth | ❌ orphaned/replaced copies stayed forever |
| Orphan sweep | ✅ `cleanup_orphans` scanned 28 staging messages, kept 17 referenced, deleted 11 orphans |
| Sweep schedule | ✅ starts 5 min after boot, then every 6 hours |
| Settings card | ✅ Admin → Settings → M Searcher Bridge; all bridge fields save and re-render |
| PATCH validation | ✅ invalid staging channel returns 400 |
| Prefetch toggle | ✅ enabled for the test, then disabled again |

### P0 run 6 — persisted requests + security parity, 2026-11-04

| Check | Result |
|---|---|
| Unresolved link across restart | ✅ registered S03E06, restarted, then resolved the saved URL — copied and streamed in 7.2s |
| Resolved link across restart | ✅ restarted again; same URL returned 307 in **0.006s** with no second copy |
| Peer cache | ✅ source bot peer is re-resolved before loading a post-restart message |
| TTL | ✅ `ms_requests.expires_at` index auto-drops entries after 2h |
| `/ms/resolve` access | ✅ mirrors the `/stream` subscription-group membership check |

Fix: pending requests are mirrored to `ms_requests`, resolved state is written
back, and `get_request`/`register` load from Mongo when the in-memory map is cold.

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
- Server restart between `/stream` and play → pending link still works (persisted).

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

1. **Remaining P0 edges** — restricted/`noforwards` files and >2 GB on a free
   account still need a live check.
2. **Settings page card** — ✅ added under Admin → Settings → M Searcher Bridge.
3. **Pagination** — ✅ movies walk up to 5 pages, episode searches up to 5 pages.
   Season-wide series fallbacks still parse page 1 only.
4. **Dedupe / duplicate-protection interaction** — if `external_always` is on and
   the same file is already indexed, the receiver may delete the copy while the
   player holds a direct `/dl` link. Detect and redirect to the existing stream, or
   skip external options for known files.
5. **Prefetch hardening** — ✅ capped by `EXTERNAL_PREFETCH_LIMIT` (0-5, default 1).
   Still to do: cancel on title change and persist state across restarts.
6. **Staging cleanup** — ✅ hourly orphan sweep; still to do: a retention policy for
   *referenced* copies (replace mode keeps one per quality).
7. **Tamil detection** — currently label-only. If the label lacks language, inspect
   the file caption after click (costs a copy) or tag manually.
8. **Tests** — add the fake-userbot suite and endpoint tests to CI.
8. **Security parity** — ✅ `/ms/resolve` now mirrors the `/stream` subscription
   group membership check.
9. **Observability** — counters for searches/copies/failures, admin status card.
10. **Legal review** — third-party source + redistribution/ToS risk.

---

## 7. Known limitations

- External options are shown beside local streams by default; with
  `EXTERNAL_ALWAYS=false` a title with any local stream hides them.
- Tamil is detected from the **button label only**.
- Only IMDb IDs; Kitsu/anime IDs are skipped.
- Request state is persisted in Mongo for 2 hours; pending links survive restarts.
  Page navigation is serialized per process, so multiple uvicorn workers could
  race on the same result message (the app normally runs a single worker).
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
