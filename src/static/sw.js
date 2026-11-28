// xlab-yt service worker
// - pages: network first (so updates show immediately), cached copy / offline page when offline
// - static assets, icons, player library: stale-while-revalidate
// - API, video streams, downloads: never touched
const VERSION = 'xlab-yt-v12';
const STATIC_CACHE = VERSION + '-static';
const PAGE_CACHE = VERSION + '-pages';
const PRECACHE = ['/', '/static/fontawesome/css/all.min.css', '/static/style.css', '/static/watch-page.css',
                  '/static/watch-page.js', '/favicon.svg', '/icon-192.png'];

const OFFLINE_HTML = `<!DOCTYPE html><html><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
<meta name="theme-color" content="#0f0f0f"><title>Offline</title>
<style>body{margin:0;min-height:100vh;display:flex;align-items:center;justify-content:center;background:#0f0f0f;color:#f1f1f1;
font-family:Roboto,Arial,sans-serif;text-align:center;padding:24px;box-sizing:border-box}
img{width:96px;height:96px;margin-bottom:16px}button{margin-top:20px;padding:10px 22px;border:0;border-radius:20px;
background:#f1f1f1;color:#0f0f0f;font:inherit;font-weight:600}</style></head>
<body><div><img src="/icon-192.png" alt=""><h2>You're offline</h2><p style="color:#aaa">Can't reach your server right now.</p>
<button onclick="location.reload()">Retry</button></div></body></html>`;

self.addEventListener('install', event => {
    event.waitUntil(caches.open(STATIC_CACHE).then(c => c.addAll(PRECACHE).catch(() => {})).then(() => self.skipWaiting()));
});

self.addEventListener('activate', event => {
    event.waitUntil((async () => {
        for (const key of await caches.keys()) if (!key.startsWith(VERSION)) await caches.delete(key);
        await self.clients.claim();
    })());
});

function isStatic(url) {
    if (url.origin === 'https://cdn.jsdelivr.net') return true;
    if (url.origin !== self.location.origin) return false;
    return url.pathname.startsWith('/static/') || /^\/(favicon|icon-)/.test(url.pathname) || url.pathname === '/manifest.json';
}

async function staleWhileRevalidate(request) {
    const cache = await caches.open(STATIC_CACHE);
    const cached = await cache.match(request);
    const network = fetch(request).then(res => {
        if (res && (res.ok || res.type === 'opaque')) cache.put(request, res.clone());
        return res;
    }).catch(() => cached);
    return cached || network;
}

async function networkFirstPage(request) {
    const cache = await caches.open(PAGE_CACHE);
    try {
        const res = await fetch(request);
        if (res.ok) cache.put(request, res.clone());
        return res;
    } catch {
        const cached = await cache.match(request) || await caches.match('/', {ignoreSearch: true});
        return cached || new Response(OFFLINE_HTML, {headers: {'Content-Type': 'text/html; charset=utf-8'}});
    }
}

self.addEventListener('fetch', event => {
    const req = event.request;
    if (req.method !== 'GET') return;
    const url = new URL(req.url);

    if (req.mode === 'navigate' && url.origin === self.location.origin) {
        // only the home page is cached for offline; watch pages would just pile up
        if (url.pathname === '/' || url.pathname === '/browse') event.respondWith(networkFirstPage(req));
        else event.respondWith(fetch(req).catch(() => new Response(OFFLINE_HTML, {headers: {'Content-Type': 'text/html; charset=utf-8'}})));
        return;
    }
    if (isStatic(url)) event.respondWith(staleWhileRevalidate(req));
});
