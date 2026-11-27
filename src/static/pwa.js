// PWA helpers shared by the browse and watch pages (xlab-yt)
(() => {
    const standalone = matchMedia('(display-mode: standalone)').matches || navigator.standalone === true;
    const ua = navigator.userAgent;
    const isIOS = /iphone|ipad|ipod/i.test(ua) || (/macintosh/i.test(ua) && navigator.maxTouchPoints > 1);
    const isIOSSafari = isIOS && /safari/i.test(ua) && !/crios|fxios|edgios|opt\//i.test(ua);
    document.documentElement.classList.toggle('pwa-standalone', standalone);
    document.documentElement.classList.toggle('pwa-ios', isIOS);

    if ('serviceWorker' in navigator && isSecureContext) {
        navigator.serviceWorker.register('/sw.js', {scope: '/'}).catch(() => {});
    }

    const css = document.createElement('style');
    css.textContent = `
        .pwa-banner { position: fixed; left: 50%; transform: translateX(-50%); z-index: 300;
            bottom: calc(16px + env(safe-area-inset-bottom, 0px)); width: min(440px, calc(100vw - 24px));
            background: #212121; color: #f1f1f1; border-radius: 14px; padding: 14px 14px 14px 16px;
            box-shadow: 0 6px 28px rgba(0,0,0,.6); display: flex; gap: 12px; align-items: center;
            font: 14px/1.4 Roboto, "Segoe UI", Arial, sans-serif; animation: pwa-up .25s ease-out; }
        .pwa-banner img { width: 44px; height: 44px; border-radius: 10px; flex-shrink: 0; }
        .pwa-banner div { flex: 1; min-width: 0; }
        .pwa-banner b { display: block; font-size: 15px; }
        .pwa-banner small { color: #aaa; }
        .pwa-banner .ios-share { display: inline-block; vertical-align: -2px; width: 14px; height: 16px; }
        .pwa-banner button { border: 0; border-radius: 18px; padding: 8px 14px; font: inherit; font-weight: 600; cursor: pointer; flex-shrink: 0; }
        .pwa-banner .go { background: #f1f1f1; color: #0f0f0f; }
        .pwa-banner .x { background: none; color: #aaa; padding: 8px; }
        @keyframes pwa-up { from { opacity: 0; transform: translate(-50%, 20px); } }
        .pwa-back { display: none; }
        html.pwa-standalone .pwa-back { display: inline-flex; }`;
    document.head.appendChild(css);

    const DISMISS_KEY = 'xlabyt.installDismissed';
    const dismissed = () => { try { return Date.now() - (+localStorage.getItem(DISMISS_KEY) || 0) < 14 * 864e5; } catch { return false; } };
    const dismiss = () => { try { localStorage.setItem(DISMISS_KEY, Date.now()); } catch {} };
    const shareIcon = '<svg class="ios-share" viewBox="0 0 14 16" fill="none" stroke="#3ea6ff" stroke-width="1.5"><path d="M7 1v9M3.5 4.5 7 1l3.5 3.5M4 7H2v8h10V7h-2"/></svg>';

    function banner(html, onGo) {
        if (document.querySelector('.pwa-banner')) return;
        const el = document.createElement('div');
        el.className = 'pwa-banner';
        el.innerHTML = `<img src="/icon-192.png" alt="">${html}<button class="x" aria-label="Dismiss">✕</button>`;
        el.querySelector('.x').onclick = () => { dismiss(); el.remove(); };
        if (onGo) el.querySelector('.go').onclick = () => { el.remove(); onGo(); };
        document.body.appendChild(el);
    }

    // Android / desktop Chrome & Edge: real install prompt
    let deferred = null;
    window.addEventListener('beforeinstallprompt', e => {
        e.preventDefault();
        deferred = e;
        document.querySelectorAll('[data-pwa-install]').forEach(b => b.hidden = false);
        if (!dismissed() && matchMedia('(max-width: 1000px)').matches) {
            banner(`<div><b>Install ${document.title.split(' - ').pop()}</b><small>Full-screen app on your home screen, open shared YouTube links in it.</small></div>
                    <button class="go">Install</button>`, install);
        }
    });
    async function install() {
        if (!deferred) return;
        deferred.prompt();
        const choice = await deferred.userChoice.catch(() => null);
        if (choice && choice.outcome !== 'accepted') dismiss();
        deferred = null;
        document.querySelectorAll('[data-pwa-install]').forEach(b => b.hidden = true);
    }
    window.addEventListener('appinstalled', () => document.querySelector('.pwa-banner')?.remove());
    window.xlabInstall = () => {
        if (deferred) return install();
        if (isIOS) return iosHelp(true);
        alert(isSecureContext ? 'Use your browser menu → "Install app" / "Add to Home screen".'
                              : 'Installing needs HTTPS. Open this app through your HTTPS address (e.g. your Caddy / Cloudflare hostname).');
    };

    // iOS Safari has no install prompt; explain Share → Add to Home Screen
    function iosHelp(force) {
        if (standalone || (!force && dismissed())) return;
        if (!isIOSSafari) {
            banner('<div><b>Install on iPhone</b><small>Open this page in <b style="display:inline;font-size:inherit">Safari</b>, then Share → Add to Home Screen.</small></div>');
            return;
        }
        banner(`<div><b>Install this app</b><small>Tap ${shareIcon} <b style="display:inline;font-size:inherit">Share</b>, then <b style="display:inline;font-size:inherit">Add to Home Screen</b>.</small></div>`);
    }
    if (isIOS && !standalone && document.body.dataset.pwaHome !== undefined) setTimeout(() => iosHelp(false), 2500);

    // Installed app: no browser chrome, so offer a back button
    window.xlabBack = () => {
        if (history.length > 1) history.back();
        else location.href = '/';
    };
    if (isIOS && !standalone) document.querySelectorAll('[data-pwa-install]').forEach(b => b.hidden = false);
})();
