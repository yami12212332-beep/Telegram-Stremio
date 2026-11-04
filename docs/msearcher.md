# M Searcher bridge

Optional on-demand source for titles that are not in your Telegram-Stremio library.
It drives a third-party Telegram file-search bot through **your own user session**
(the same session used by Global Search) and copies the chosen file into a staging
channel you control.

> Telegram does not let one bot read another bot's messages. This feature therefore
> requires the `Userbot` session; a bot token cannot be used for the source bot.

## What it does

1. Nuvio/Stremio asks the addon for streams of a title.
2. If the title has no local streams (or `EXTERNAL_ALWAYS=true`), the addon asks the
   source bot for `title year SxxExx`.
3. The source bot's file buttons become stream options in Nuvio:
   `🌐 1080p · Tamil`, `🌐 720p`, etc.
4. On the first play, the userbot presses that button, waits for the file, and copies
   it into `STAGING_CHANNEL` (server-side; no download to the VPS).
5. The player is redirected to the normal `/dl/...` stream. The copy is also indexed
   by the existing receiver, so later plays are instant.

## Prerequisites

- **Telegram user session** connected in Settings → Telegram User Session.
- A **private channel** used only for staging.
  - Add your main bot (`StreamBot`) as an administrator/member; it streams and indexes
    the copied files.
  - Add your user account (the session) as a member with permission to post.
- The source bot's **username** (without `@`).
- `BASE_URL` set to the public URL of the addon (as for any stream link).

## Configuration

Add to `config.env` and restart:

```env
EXTERNAL_SEARCH="true"
EXTERNAL_BOT="YourSourceBot"
STAGING_CHANNEL="-1001234567890"

# Prefer Tamil-labelled results (does not hide other languages).
EXTERNAL_TAMIL_FIRST="true"

# Copy the offered candidates in the background on the first stream request.
# Costs Telegram API calls and channel messages; leave false to copy on play only.
EXTERNAL_PREFETCH="false"

# Show external options even when the title already has local streams.
# Off by default to avoid duplicate copies.
EXTERNAL_ALWAYS="false"

# Seconds to wait for the source bot (3-30).
EXTERNAL_TIMEOUT="8"

# Number of stream options (1-20) and copies per quality (1-3).
EXTERNAL_MAX_RESULTS="6"
EXTERNAL_VARIANTS="1"
```

Existing databases pick these values up as defaults; saving the Settings page also
persists them. There is no dedicated web form yet — use `config.env`.

## First test

1. Set `EXTERNAL_SEARCH=true`, `EXTERNAL_BOT`, `STAGING_CHANNEL`, and restart.
2. Check the log for `[MSEARCH] enabled`.
3. In Nuvio, open a title that is **not** in your library and request streams.
4. You should see `🌐 ...` options. The first play may take a few seconds while the
   file is copied; later plays use the indexed copy.

If no options appear, check the log for `[MSEARCH]` warnings. Common causes:

- The userbot session is not connected.
- The source bot does not answer with inline file buttons.
- The source bot uses URL buttons instead of callback buttons (unsupported).
- The file is protected (`noforwards`); `copy_message` fails.
- The userbot is not allowed to post in the staging channel.

## Limitations

- The source bot is third-party: it can change its UI, rate-limit, or ban the account.
- `FLOOD_WAIT` is surfaced as HTTP 503 with `Retry-After`; players usually retry.
- Tamil is detected from the button label only. If the label has no language, the
  option is shown without a Tamil tag.
- Per-file Telegram limits still apply: 2 GB for free accounts, 4 GB with Premium.
- The bridge is a fallback by default. With `EXTERNAL_ALWAYS=false`, a title that
  already has local streams will not show external options.
- Only IMDb-based titles are supported (Kitsu/anime IDs are skipped).
