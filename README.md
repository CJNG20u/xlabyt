<div align="center">
  <img src="src/static/favicon.svg" width="120px" />

# xlab-yt

### Self-hosted YouTube front end, powered by yt-dlp

Self-hosted YT web player that works on iOS, Android and PC: browse, search and watch YouTube from your own server, no ads, no tracking.

</div>

## Features

- **YouTube-style home** – search with infinite scroll, channel pages (Videos / Shorts / Live / Playlists), playlists
- **Watch page** – video player, title and channel, likes, expandable description with clickable timestamps, read-only comments with replies
- **Up next** – recommendations from the video's YouTube mix, with an autoplay countdown
- **Following** – follow channels without a Google account; their newest uploads fill your home page
- **Your YouTube account (optional)** – mount `cookies.txt` to get your real Home feed, Subscriptions, History and Watch later
- **Installable app (PWA)** for Android and iPhone, with "Share to xlab-yt" from the YouTube app on Android
- Player: quality switching, livestreams, SponsorBlock skipping, subtitles, chapters, seek previews, background playback, loop, downloads
- yt-dlp updates itself daily, and any site yt-dlp supports can still be played by pasting its link
- Docker images for `amd64` and `arm64` (Raspberry Pi)

## Run it

```yaml
# compose.yml
services:
    xlab-yt:
        container_name: xlab-yt
        image: ghcr.io/cjng20u/xlabyt:latest
        restart: unless-stopped
        ports:
            - 5000:5000
        # volumes:
        #     - ./cookies.txt:/app/cookies.txt   # optional, see below
        # env_file:
        #     - .env                             # optional, see src/example.env
```

```
docker compose up -d
```

Open `http://<server>:5000`. To update: `docker compose pull && docker compose up -d`.

To build from source instead: clone the repo, switch `compose.yml` to the `build:` block, then run `docker compose up -d --build`.

### Your YouTube account (optional)

Export your YouTube cookies in Netscape format (e.g. with a "Get cookies.txt" browser extension, while signed in to youtube.com), save the file as `cookies.txt` and mount it at `/app/cookies.txt`. Home then shows your recommendations, and Subscriptions, History and Watch later work. Without cookies, use **Follow** on channel pages.

### Install on your phone

Phones only install web apps over **HTTPS**, so put xlab-yt behind a reverse proxy (Caddy, Nginx, Cloudflare Tunnel…).

- **Android (Chrome):** tap **Install** on the banner, or ⋮ → *Install app*. Then share a video from the YouTube app → *xlab-yt*.
- **iPhone / iPad (Safari):** Share → *Add to Home Screen*.

## Configuration

All options are environment variables. Copy `src/example.env` to `.env`, uncomment what you want, and enable `env_file` in `compose.yml`. Useful ones:

| Variable | Default | |
|---|---|---|
| `APP_TITLE` | `xlab-yt` | Name shown in the app and on the home screen |
| `THEME_COLOR` | `#fa233b` | Accent and logo color |
| `DEFAULT_QUALITY` / `MAX_QUALITY` | `720` / `2160` | Playback quality |
| `AUTOSKIP_SB_SEGMENTS` | – | SponsorBlock categories to skip, e.g. `sponsor,selfpromo,intro` |
| `PROXIES` | `local` | Proxies to try in order, e.g. `local,http://10.0.0.5:8888` |
| `BROWSE_CACHE_TTL` | `600` | Seconds to cache search / feed / channel results |

For NVIDIA hardware transcoding, install the NVIDIA Container Toolkit, use `Dockerfile.hwaccel` and `gpus: all` (see the comments in `compose.yml`).

## Releases

Every push to `main` publishes `ghcr.io/cjng20u/xlabyt:latest`. Publishing a GitHub release (e.g. `v1.0.0`) also tags `:v1.0.0` and `:stable`, and builds the desktop app (Windows / Linux) as release assets.

## Credits & license

xlab-yt is based on [YT-DLP Web Player](https://github.com/Matszwe02/ytdlp_web_player) by Matszwe02, which provides the player, streaming and transcoding engine. xlab-yt additions © 2026 Ulises Sierra. Because it is built on GPL-2.0 code, the whole project is licensed under the **GNU GPL v2** (see `LICENSE`).
