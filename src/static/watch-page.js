// YouTube-style watch page: details, description, Up next and read-only comments (xlab-yt)
(() => {
    try { for (const k of ['follows', 'recent', 'autoplay', 'installDismissed']) { const o = localStorage.getItem('ytweb.' + k); if (o !== null && localStorage.getItem('xlabyt.' + k) === null) localStorage.setItem('xlabyt.' + k, o); } } catch {}
    const $ = id => document.getElementById(id);
    const metaEl = $('yt-meta');
    if (!metaEl) return;

    const params = new URLSearchParams(location.search);
    const videoUrl = params.get('url') || params.get('v') || metaEl.dataset.url;
    if (!videoUrl) return;
    const enc = encodeURIComponent(videoUrl);
    let pageTitle = metaEl.dataset.title || '';
    let related = [];

const prefetched = new Set();
    function prefetch(url) {
        if (!url || prefetched.has(url)) return;
        prefetched.add(url);
        fetch('/api/prefetch?url=' + encodeURIComponent(url), {method: 'POST', keepalive: true}).catch(() => {});
    }
    const esc = s => String(s ?? '').replace(/[&<>"']/g, c => ({'&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'}[c]));
    const store = {
        get(k, d) { try { return JSON.parse(localStorage.getItem(k)) ?? d; } catch { return d; } },
        set(k, v) { try { localStorage.setItem(k, JSON.stringify(v)); } catch {} },
    };

    function fmtNum(n) {
        if (n == null) return '';
        if (n >= 1e9) return (n / 1e9).toFixed(1).replace(/\.0$/, '') + 'B';
        if (n >= 1e6) return (n / 1e6).toFixed(1).replace(/\.0$/, '') + 'M';
        if (n >= 1e3) return (n / 1e3).toFixed(n >= 1e4 ? 0 : 1).replace(/\.0$/, '') + 'K';
        return String(n);
    }
    function fmtDur(s) {
        if (!s) return '';
        s = Math.round(s);
        const h = Math.floor(s / 3600), m = Math.floor(s % 3600 / 60), sec = s % 60;
        return (h ? h + ':' + String(m).padStart(2, '0') : m) + ':' + String(sec).padStart(2, '0');
    }
    function ago(ts, uploadDate) {
        let t = ts;
        if (!t && uploadDate) t = Date.UTC(+uploadDate.slice(0, 4), +uploadDate.slice(4, 6) - 1, +uploadDate.slice(6, 8)) / 1000;
        if (!t) return '';
        const s = Date.now() / 1000 - t;
        for (const [u, n] of [[31536000, 'year'], [2592000, 'month'], [604800, 'week'], [86400, 'day'], [3600, 'hour'], [60, 'minute']])
            if (s >= u) { const v = Math.floor(s / u); return `${v} ${n}${v > 1 ? 's' : ''} ago`; }
        return 'just now';
    }
    const watchHref = url => '/watch?url=' + encodeURIComponent(url);
    const channelHref = url => '/#/channel?url=' + encodeURIComponent(url);

    // Escape, then turn URLs into links and timestamps into seek links
    function richText(text) {
        let html = esc(text);
        html = html.replace(/https?:\/\/[^\s<]+/g, u => {
            const raw = u.replace(/&amp;/g, '&');
            const yt = /(?:youtube\.com\/(?:watch|shorts|live)|youtu\.be\/)/i.test(raw);
            return yt ? `<a href="${watchHref(raw)}">${u}</a>` : `<a href="${u}" target="_blank" rel="noopener noreferrer">${u}</a>`;
        });
        html = html.replace(/(^|[\s(])((?:\d{1,2}:)?\d{1,2}:\d{2})(?=$|[\s),.])/gm, (m, pre, ts) => {
            const secs = ts.split(':').reduce((a, b) => a * 60 + +b, 0);
            return `${pre}<a href="#" data-seek="${secs}">${ts}</a>`;
        });
        return html;
    }
    document.addEventListener('click', e => {
        const a = e.target.closest('[data-seek]');
        if (!a) return;
        e.preventDefault();
        try { player.currentTime = +a.dataset.seek; player.play?.(); scrollTo({top: 0, behavior: 'smooth'}); } catch {}
    });

    function avatarHtml(src, name) {
        return src ? `<img src="${esc(src)}" referrerpolicy="no-referrer" loading="lazy" alt="">` : esc((name || '?').trim().charAt(0).toUpperCase());
    }

    /* ---------- details ---------- */
    fetch(`/api/details?url=${enc}`).then(r => r.ok ? r.json() : null).then(d => {
        if (!d) return;
        pageTitle = d.title || pageTitle;
        document.querySelector('.yt-title').textContent = d.title;
        $('yt-chan-name').textContent = d.channel;
        $('yt-subs').textContent = d.subscribers ? fmtNum(d.subscribers) + ' subscribers' : '';
        $('yt-avatar').innerHTML = avatarHtml('', d.channel);
        if (d.channel_url) {
            $('yt-chan').href = channelHref(d.channel_url);
            // channel avatar isn't in the video's metadata; the channel page call has it (and is cached)
            fetch('/api/browse?' + new URLSearchParams({kind: 'channel', url: d.channel_url, tab: 'videos'}))
                .then(r => r.ok ? r.json() : null)
                .then(c => { if (c && c.avatar) $('yt-avatar').innerHTML = avatarHtml(c.avatar, d.channel); })
                .catch(() => {});
        }
        if (d.likes != null) { $('yt-likes').hidden = false; $('yt-likes').querySelector('span').textContent = fmtNum(d.likes); }

        const head = [
            d.live ? (d.watching ? fmtNum(d.watching) + ' watching now' : 'Live') : (d.views != null ? Number(d.views).toLocaleString() + ' views' : ''),
            d.live ? '' : ago(d.timestamp, d.upload_date),
        ].filter(Boolean).join('  ');
        const tags = (d.tags || []).slice(0, 3).map(t => `<span class="tag">#${esc(t.replace(/\s+/g, ''))}</span>`).join('');
        $('yt-desc-head').innerHTML = esc(head) + tags;
        $('yt-desc-body').innerHTML = richText(d.description) || '<i>No description</i>';
        $('yt-desc').hidden = false;
        if (d.comment_count != null) $('yt-comment-count').textContent = Number(d.comment_count).toLocaleString() + ' Comments';

        loadRelated();
        if (d.is_youtube) setupComments();
    }).catch(() => loadRelated());

    const desc = $('yt-desc');
    desc.addEventListener('click', e => {
        if (e.target.closest('a')) return;
        if (desc.classList.contains('collapsed')) { desc.classList.remove('collapsed'); $('yt-desc-toggle').textContent = 'Show less'; }
        else if (e.target.id === 'yt-desc-toggle') { desc.classList.add('collapsed'); $('yt-desc-toggle').textContent = '...more'; }
    });

    $('yt-share').addEventListener('click', async () => {
        const link = location.origin + '/watch?url=' + enc;
        try {
            if (navigator.share) await navigator.share({title: pageTitle, url: link});
            else { await navigator.clipboard.writeText(link); $('yt-share').lastChild.textContent = 'Copied!'; setTimeout(() => $('yt-share').lastChild.textContent = 'Share', 2000); }
        } catch {}
    });

    /* ---------- up next ---------- */
    const relEl = $('yt-related');
    relEl.innerHTML = Array.from({length: 8}, () => `<div class="yt-rel yt-skel"><div class="yt-rel-thumb"></div><div class="yt-rel-info" style="flex:1"><div class="yt-skel-line" style="width:90%"></div><div class="yt-skel-line" style="width:60%"></div></div></div>`).join('');

    let relatedLoaded = false;
    function loadRelated() {
        if (relatedLoaded) return;
        relatedLoaded = true;
        fetch(`/api/related?url=${enc}&title=${encodeURIComponent(pageTitle)}`).then(r => r.json()).then(d => {
            related = d.items || [];
            relEl.innerHTML = related.length ? related.map(relCard).join('') : '<div class="yt-empty">No recommendations for this video.</div>';
            // the autoplay pick is resolved while this video plays, so it starts right away
            if (related[0]) setTimeout(() => prefetch(related[0].url), 3000);
        }).catch(() => { relEl.innerHTML = '<div class="yt-empty">Could not load recommendations.</div>'; });
    }
    setTimeout(loadRelated, 4000); // don't wait forever on details

    function relCard(it, i) {
        const badge = it.live ? '<span class="yt-badge live">LIVE</span>' : (it.duration ? `<span class="yt-badge">${fmtDur(it.duration)}</span>` : '');
        const sub = [it.views != null ? fmtNum(it.views) + ' views' : '', ago(it.timestamp, it.upload_date)].filter(Boolean).join(' · ');
        return `<a class="yt-rel" href="${watchHref(it.url)}" data-idx="${i}">
            <div class="yt-rel-thumb">${it.thumb ? `<img src="${esc(it.thumb)}" referrerpolicy="no-referrer" loading="lazy" alt="">` : ''}${badge}</div>
            <div class="yt-rel-info"><p class="yt-rel-title">${esc(it.title)}</p>
            <div class="yt-rel-sub">${esc(it.channel)}${it.channel && sub ? '<br>' : ''}${esc(sub)}</div></div></a>`;
    }
    function remember(it) {
        const r = store.get('xlabyt.recent', []).filter(x => x.url !== it.url);
        r.unshift(it);
        store.set('xlabyt.recent', r.slice(0, 200));
    }
    let relHover = null;
    relEl.addEventListener('pointerover', e => {
        const a = e.target.closest('[data-idx]');
        if (!a || e.pointerType !== 'mouse') return;
        clearTimeout(relHover);
        relHover = setTimeout(() => prefetch(related[a.dataset.idx]?.url), 120);
    });
    relEl.addEventListener('pointerout', () => clearTimeout(relHover));
    relEl.addEventListener('pointerdown', e => { const a = e.target.closest('[data-idx]'); if (a) prefetch(related[a.dataset.idx]?.url); }, {passive: true});
    relEl.addEventListener('click', e => {
        const a = e.target.closest('[data-idx]');
        if (a && related[a.dataset.idx]) remember(related[a.dataset.idx]);
    });

    /* ---------- autoplay next ---------- */
    const auto = $('yt-autoplay');
    auto.checked = store.get('xlabyt.autoplay', true);
    auto.addEventListener('change', () => store.set('xlabyt.autoplay', auto.checked));

    let countdown = null;
    function cancelNext() { clearInterval(countdown); countdown = null; $('yt-upnext-toast').hidden = true; }
    function playNext() {
        if (!auto.checked || (typeof repeatMode !== 'undefined' && repeatMode)) return;
        const next = related[0];
        if (!next || countdown) return;
        let left = 5;
        const toast = $('yt-upnext-toast');
        toast.innerHTML = `<span>Up next in <b id="yt-cd">${left}</b>: ${esc(next.title)}</span>
            <button class="yt-pill" id="yt-cancel">Cancel</button><button class="yt-pill" id="yt-now">Play now</button>`;
        toast.hidden = false;
        const go = () => { cancelNext(); remember(next); location.href = watchHref(next.url); };
        $('yt-cancel').onclick = cancelNext;
        $('yt-now').onclick = go;
        countdown = setInterval(() => { if (--left <= 0) go(); else $('yt-cd').textContent = left; }, 1000);
    }
    // script.js creates `player` asynchronously; attach once it exists
    const waitPlayer = setInterval(() => {
        if (typeof player === 'undefined' || !player || !player.addEventListener) return;
        clearInterval(waitPlayer);
        player.addEventListener('ended', playNext);
        player.addEventListener('play', cancelNext);
    }, 300);

    /* ---------- comments (read-only) ---------- */
    const listEl = $('yt-comment-list');
    let commentsStarted = false;
    function setupComments() {
        $('yt-comments').hidden = false;
        // load once the comments come near the viewport, like YouTube
        const io = new IntersectionObserver(es => {
            if (es[0].isIntersecting && !commentsStarted) { commentsStarted = true; io.disconnect(); loadComments('top'); }
        }, {rootMargin: '400px'});
        io.observe($('yt-comments'));
        $('yt-comment-sort').addEventListener('change', e => loadComments(e.target.value));
    }
    function loadComments(sort) {
        listEl.innerHTML = '<div class="yt-loading"><div class="yt-spinner"></div></div>';
        fetch(`/api/comments?url=${enc}&sort=${sort}`).then(r => r.json()).then(d => {
            const cs = d.comments || [];
            if (d.count != null) $('yt-comment-count').textContent = Number(d.count).toLocaleString() + ' Comments';
            listEl.innerHTML = cs.length ? cs.map(c => commentHtml(c, false)).join('')
                : `<div class="yt-empty">${d.error ? 'Could not load comments: ' + esc(d.error) : 'No comments.'}</div>`;
            listEl.querySelectorAll('.yt-comment-text').forEach(t => {
                const clamped = t.clientHeight;
                t.classList.remove('clamp');
                const full = t.clientHeight;
                t.classList.add('clamp');
                if (full > clamped + 4) {
                    const b = document.createElement('button');
                    b.className = 'yt-more'; b.textContent = 'Read more';
                    b.onclick = () => { const open = t.classList.toggle('clamp'); b.textContent = open ? 'Read more' : 'Show less'; };
                    t.after(b);
                }
            });
        }).catch(() => { listEl.innerHTML = '<div class="yt-empty">Could not load comments.</div>'; });
    }
    function commentHtml(c, isReply) {
        const author = `<span class="${c.is_uploader ? 'owner' : ''}">${esc(c.author)}${c.verified ? ' <i class="fa-solid fa-circle-check" style="font-size:11px"></i>' : ''}</span>`;
        const replies = c.replies && c.replies.length ? `
            <button class="yt-replies-toggle" onclick="const r=this.nextElementSibling; r.hidden=!r.hidden; this.firstChild.className = r.hidden ? 'fa-solid fa-chevron-down' : 'fa-solid fa-chevron-up';"><i class="fa-solid fa-chevron-down"></i> ${c.replies.length} ${c.replies.length === 1 ? 'reply' : 'replies'}</button>
            <div class="yt-replies" hidden>${c.replies.map(r => commentHtml(r, true)).join('')}</div>` : '';
        return `<div class="yt-comment ${isReply ? 'yt-reply' : ''}">
            <span class="yt-avatar">${avatarHtml(c.avatar, c.author)}</span>
            <div class="yt-comment-body">
                ${c.pinned ? '<div class="yt-comment-pinned"><i class="fa-solid fa-thumbtack"></i> Pinned</div>' : ''}
                <div class="yt-comment-author">${author}<time>${esc(c.time_text || ago(c.timestamp))}</time></div>
                <div class="yt-comment-text clamp">${richText(c.text)}</div>
                <div class="yt-comment-foot"><span><i class="fa-regular fa-thumbs-up"></i> ${c.likes ? fmtNum(c.likes) : ''}</span>${c.hearted ? '<i class="fa-solid fa-heart heart" title="Hearted by creator"></i>' : ''}</div>
                ${replies}
            </div></div>`;
    }
})();
