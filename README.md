<h1 align="center">xlab-yt</h1>

<p align="center">
  <img src="src/static/favicon.svg" width="128" alt="xlab-yt logo">
</p>

<p align="center"><b>YouTube, played from your own server.</b></p>

<p align="center"><a href="#install">Install</a> · <a href="#key-features">Features</a> · <a href="#your-youtube-account-optional">YouTube account</a> · <a href="#install-on-your-phone-pwa">Phone app</a> · <a href="#uninstall">Uninstall</a></p>

Self-hosted YouTube web app & PWA for iOS, Android and PC: a YouTube-style home, search, channels and watch page, with videos streamed through your server by yt-dlp. No ads, SponsorBlock skipping, background playback on your phone, and optional sign-in with your own YouTube account.


[![Docker image](https://github.com/CJNG20u/xlabyt/actions/workflows/docker-publish.yml/badge.svg)](https://github.com/CJNG20u/xlabyt/pkgs/container/xlabyt)

🐳 **Docker image:** `ghcr.io/cjng20u/xlabyt:latest` (amd64 + arm64)

```bash
docker pull ghcr.io/cjng20u/xlabyt:latest
```

## Why xlab-yt?

The YouTube app and website are built around ads, autoplay rabbit holes and features locked behind Premium. Other front ends either break every time YouTube changes something or make you paste a link for every video.

**xlab-yt** keeps the YouTube layout you already know and changes what happens underneath:
- **Streams through your server:** videos are fetched and played by [yt-dlp](https://github.com/yt-dlp/yt-dlp) on your server, so there are no ads and no YouTube player scripts on your devices. Only thumbnails load straight from YouTube's image servers.
- **Keeps working:** yt-dlp updates itself every day inside the container, so YouTube changes are usually fixed before you notice them.
- **Premium-style playback for free:** background and lock-screen playback on your phone, downloads, loop, and automatic SponsorBlock skipping.
- **Your choice of account:** follow channels with no Google account at all, or mount your own `cookies.txt` to get your real Home feed and Subscriptions.
- **One small container:** no database, no login to manage, and the same install as every other xlab app.

---

## Key Features

- **YouTube-style Home & Search**: Infinite-scroll search results, channel pages (Videos / Shorts / Live / Playlists) and playlists. Paste any link into the search bar to play it.
- **Shorts**: Full-screen vertical feed under Home: swipe or use the arrow keys, tap to pause, mute, loop. Upcoming Shorts are downloaded by the server and buffered in the page ahead of time, so swiping to the next one is instant. With your `cookies.txt` the feed is built from your account: Shorts from your subscriptions plus Shorts on the topics YouTube recommends to you; without it, from channels you follow and what you played. Tapping a Short anywhere opens it in the feed.
- **Watch Page**: Full-width player with title, channel and subscribers, likes, an expandable description with clickable timestamps, and read-only comments (top / newest, with replies).
- **Up Next & Autoplay**: Recommendations from the video's YouTube mix, topped up with related search results, plus a 5-second autoplay countdown you can cancel.
- **Following Without an Account**: Follow channels from their page; their newest uploads fill your Home page. Saved in your browser.
- **Your YouTube Account (optional)**: Mount `cookies.txt` for your real Home recommendations, Subscriptions, History and Watch later.
- **Player**: Quality switching, livestreams, subtitles, chapters, seek previews, SponsorBlock auto-skip, loop, picture-in-picture, background playback and downloads.
- **Installable Mobile & Desktop PWA**: Home-screen app for Android, iOS/iPadOS and desktop, with notch-safe layout, a back button in standalone mode, and **Share → xlab-yt** from the YouTube app on Android.
- **Fast Start Engine**: The xlab-player resolve engine: YouTube links are resolved with the `android_vr` client and a cached `visitor_data` token (no JavaScript challenge solving), with automatic fallback to standard yt-dlp. Videos are resolved ahead of time while they're on screen (Home, search, channels, Up next) through a background queue, so tapping one starts playback immediately; taps and hovers jump the queue.
- **Any yt-dlp Site**: Besides YouTube, paste a link from any site yt-dlp supports and play it in the same player.

---

### Prerequisites

- Docker & Docker Compose v2
- For the phone app: an **HTTPS** address (Caddy, Nginx or a Cloudflare Tunnel in front of port `5000`)

## Install

Every xlab app installs and updates the same way: one folder, one `docker-compose.yml`, one `.env`.

```bash
mkdir -p /opt/xlab-yt && cd /opt/xlab-yt
curl -fsSLO https://raw.githubusercontent.com/CJNG20u/xlabyt/main/docker-compose.yml
curl -fsSL https://raw.githubusercontent.com/CJNG20u/xlabyt/main/.env.example -o .env
docker compose up -d
```

Open `http://<host-ip>:5000`. Search for something, or paste a video link.

Everything in `.env` is optional: app name and accent color, playback quality, SponsorBlock categories, proxies.

## Update

```bash
cd /opt/xlab-yt
docker compose pull && docker compose up -d
```

Images are built automatically for `linux/amd64` and `linux/arm64`. `:latest` follows `main`; every release also gets its version tag and `:stable` (for example `:v1.0.0`), so you can pin one with `image: ghcr.io/cjng20u/xlabyt:v1.0.0`.

## Build from source

```bash
git clone https://github.com/CJNG20u/xlabyt.git
cd xlabyt
cp .env.example .env
docker compose -f docker-compose.yml -f docker-compose.build.yml up -d --build
```

---

## Your YouTube Account (optional)

Without an account, use **Follow** on channel pages. To get your real Home feed, Subscriptions, History and Watch later, give xlab-yt your YouTube cookies:

1. On your PC, install a cookies.txt exporter (**Get cookies.txt LOCALLY** for Chrome/Edge, **cookies.txt** for Firefox) and allow it in private windows.
2. Open a **private window**, sign in to youtube.com, then go to `youtube.com/robots.txt` in the same tab.
3. Export the cookies for youtube.com as `cookies.txt`, then **close the private window without signing out**.
4. Copy the file next to `docker-compose.yml` **before** enabling it:

```bash
scp cookies.txt user@your-server:/opt/xlab-yt/cookies.txt
```

5. Uncomment the `volumes` lines in `docker-compose.yml`:

```yaml
    volumes:
      - ./cookies.txt:/app/cookies.txt
```

6. Restart and check:

```bash
docker compose up -d
docker exec xlab-yt head -1 /app/cookies.txt   # should print "# Netscape HTTP Cookie File"
```

The "No cookies.txt found" note in the side menu disappears and Home shows your recommendations.

> ⚠️ If `cookies.txt` doesn't exist when the container starts, Docker creates an empty **folder** with that name. Fix: `docker compose down && rm -rf cookies.txt`, copy the real file, start again.

> 🔐 `cookies.txt` can sign in to your Google account. Keep it only on the server and **never commit it to Git**. Cookies expire after a while: if Subscriptions starts asking for your account again, export a fresh file and restart.

---

## Install on your Phone (PWA)

Phones only install web apps over **HTTPS**, so open xlab-yt through your reverse-proxy hostname.

- **Android (Chrome):** tap **Install** on the banner, or ⋮ → *Install app*. Afterwards, share a video from the YouTube app → **xlab-yt** to open it in your player. Long-press the icon for Search, Subscriptions and Following shortcuts.
- **iPhone / iPad (Safari):** tap **Share** → **Add to Home Screen**.

If you installed an older version, remove the icon and add it again to refresh the name, icon and colors.

> 💡 **mTLS / client certificates:** iPhone home-screen apps may not send client certificates even when Safari does. If the installed app can't connect but the website works, exempt the xlab-yt hostname from mTLS and protect it another way (VPN, Cloudflare Access, Authelia).

### HTTPS Reverse Proxy

**Caddy**

```caddy
yt.example.com {
    reverse_proxy 127.0.0.1:5000
}
```

> **Security**: xlab-yt has no built-in login. If you expose it outside your LAN, put it behind a VPN (Tailscale/WireGuard) or reverse-proxy auth (Authelia/Authentik/Cloudflare Access), especially when `cookies.txt` is mounted.

---

## Uninstall

**Server**

```bash
cd /opt/xlab-yt
docker compose down
docker rmi ghcr.io/cjng20u/xlabyt:latest
cd / && rm -rf /opt/xlab-yt        # also deletes your .env and cookies.txt
```

xlab-yt keeps no database. Cached video files live inside the container and are removed with it.

**Phone & browser**

- **Android:** long-press the xlab-yt icon → **Uninstall** (or App info → Uninstall).
- **iPhone / iPad:** long-press the icon → **Remove App** → **Delete from Home Screen**.
- **Desktop browser:** open xlab-yt → address-bar app menu → **Uninstall**.
- Followed channels, Recently played and settings are stored in each browser. To erase them, clear the site data for your xlab-yt address (browser settings → Site settings / Website data).

**YouTube account**

Deleting `cookies.txt` doesn't sign that session out. To revoke it, go to your Google Account → **Security** → **Your devices**, and sign out the session you exported (or just change your password).

---

## Credits

Built on [**YT-DLP Web Player**](https://github.com/Matszwe02/ytdlp_web_player) by [@Matszwe02](https://github.com/Matszwe02), which provides the player, streaming and transcoding engine, and powered by [**yt-dlp**](https://github.com/yt-dlp/yt-dlp) and [**SponsorBlock**](https://sponsor.ajay.app/). Huge thanks to both projects. Go give them a ⭐!

## License

xlab-yt additions © 2026 Ulises Sierra. Because it is built on GPL-2.0 code, the whole project is licensed under the **GNU GPL v2**. See [`LICENSE`](LICENSE).
