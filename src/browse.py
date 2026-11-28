"""YouTube-style browsing: search results, home/subscription feeds, channels and playlists.

Everything is fetched with yt-dlp's flat extraction (no per-video requests), so a page of
24 results comes back in roughly the time of one YouTube page load.
"""
import re
import time
from threading import Lock
from urllib.parse import quote_plus, urlparse

from main import *
from addons import YTDLP, get_global_cookies_file, pprint_exc


PAGE_SIZE = 24
CACHE_TTL = int(os.environ.get('BROWSE_CACHE_TTL', '600'))

_cache: dict[str, tuple[float, list]] = {}
_cache_lock = Lock()
_inflight: dict[str, Lock] = {}

# The server runs 4 worker processes and each had its own in-memory cache, so going back to a page
# usually landed on a worker that had never seen it and re-ran yt-dlp. Results are also kept on disk
# so every worker shares them.
_DISK_CACHE = os.path.join(data_path, '_browse_cache')


def _disk_path(key: str) -> str:
    from hashlib import sha1
    return os.path.join(_DISK_CACHE, sha1(key.encode()).hexdigest() + '.json')


def _disk_get(key: str, ttl: int):
    import json
    path = _disk_path(key)
    try:
        if time.time() - os.path.getmtime(path) >= ttl: return None
        with open(path) as f: return json.load(f)
    except Exception:
        return None


def _disk_put(key: str, value):
    import json
    try:
        os.makedirs(_DISK_CACHE, exist_ok=True)
        with open(os.path.join(_DISK_CACHE, 'keepalive'), 'w') as f: f.write(str(int(time.time())))
        path = _disk_path(key)
        tmp = f'{path}.{os.getpid()}.tmp'
        with open(tmp, 'w') as f: json.dump(value, f)
        os.replace(tmp, path)
        if hash(path) % 50 == 0:  # now and then, drop entries older than any TTL we use
            for name in os.listdir(_DISK_CACHE):
                full = os.path.join(_DISK_CACHE, name)
                if name.endswith('.json') and time.time() - os.path.getmtime(full) > 3 * 3600: os.remove(full)
    except Exception as e:
        print(f'[browse] disk cache write failed: {e}')


def _flat_opts(start: int, end: int, cookies: bool):
    opts = {
        'quiet': True,
        'skip_download': True,
        'extract_flat': 'in_playlist',
        'playlist_items': f'{start}-{end}',
        'lazy_playlist': True,
    }
    opts.update(ydl_global_opts)
    opts.pop('playlistend', None)
    opts.pop('noplaylist', None)
    if cookies and (c := get_global_cookies_file(True)):
        opts['cookiefile'] = c
        opts['mark_watched'] = False
    return opts


def _thumb(entry: dict) -> str:
    vid = entry.get('id') or ''
    if _is_youtube_video(entry) and vid:
        return f'https://i.ytimg.com/vi/{vid}/mqdefault.jpg'
    thumbs = entry.get('thumbnails') or []
    if thumbs:
        best = sorted(thumbs, key=lambda t: (t.get('width') or 0))
        # pick a mid-sized thumbnail if available, otherwise the largest
        mid = [t for t in best if 200 <= (t.get('width') or 0) <= 720]
        return (mid[-1] if mid else best[-1]).get('url') or ''
    return entry.get('thumbnail') or ''


def _is_youtube_video(entry: dict) -> bool:
    return (entry.get('ie_key') or '').lower() in ('youtube', '') and len(entry.get('id') or '') == 11


def _kind(entry: dict) -> str:
    url = entry.get('url') or ''
    ie = (entry.get('ie_key') or '').lower()
    if ie == 'youtubetab' or entry.get('_type') == 'playlist':
        path = urlparse(url).path
        if path.startswith('/playlist') or 'list=' in url:
            return 'playlist'
        return 'channel'
    if '/shorts/' in url:
        return 'short'
    return 'video'


def _video_url(entry: dict) -> str:
    url = entry.get('url') or entry.get('webpage_url') or ''
    if _is_youtube_video(entry):
        return f'https://www.youtube.com/watch?v={entry["id"]}'
    if url and not url.startswith('http'):
        return f'https://www.youtube.com/watch?v={url}'
    return url


def _abs(url: str) -> str:
    return 'https:' + url if url and url.startswith('//') else (url or '')


def _simplify(entry: dict) -> dict | None:
    if not entry: return None
    kind = _kind(entry)
    if kind in ('video', 'short') and not (entry.get('id') or entry.get('url')): return None
    channel_url = entry.get('channel_url') or entry.get('uploader_url') or ''
    if not channel_url and entry.get('channel_id'):
        channel_url = f'https://www.youtube.com/channel/{entry["channel_id"]}'
    return {
        'kind': kind,
        'id': entry.get('id'),
        'url': _video_url(entry) if kind in ('video', 'short') else entry.get('url'),
        'title': entry.get('title') or '',
        'thumb': _abs(_thumb(entry)),
        'duration': entry.get('duration'),
        'views': entry.get('view_count'),
        'live': entry.get('live_status') == 'is_live' or entry.get('is_live') or False,
        'channel': entry.get('channel') or entry.get('uploader') or '',
        'channel_url': channel_url,
        'timestamp': entry.get('timestamp') or entry.get('release_timestamp'),
        'upload_date': entry.get('upload_date'),
        'count': entry.get('playlist_count'),
    }


def _fetch(source: str, page: int, cookies: bool) -> dict:
    key = f'{source}|{page}|{cookies}'
    now = time.time()
    with _cache_lock:
        hit = _cache.get(key)
        if hit and now - hit[0] < CACHE_TTL:
            return hit[1]
    if (disk := _disk_get(key, CACHE_TTL)) is not None:
        with _cache_lock: _cache[key] = (now, disk)
        return disk

    start = (page - 1) * PAGE_SIZE + 1
    end = page * PAGE_SIZE
    info = YTDLP.get_info(source, _flat_opts(start, end, cookies)) or {}
    entries = [e for e in (_simplify(e) for e in (info.get('entries') or [])) if e]

    result = {
        'title': info.get('title') or info.get('channel') or '',
        'channel': info.get('channel') or info.get('uploader') or '',
        'channel_url': info.get('channel_url') or info.get('uploader_url') or '',
        'avatar': _abs(_channel_avatar(info)),
        'banner': _abs(_channel_banner(info)),
        'subscribers': info.get('channel_follower_count'),
        'items': entries,
        'has_more': len(entries) >= PAGE_SIZE,
    }
    _disk_put(key, result)
    with _cache_lock:
        _cache[key] = (now, result)
        if len(_cache) > 500:
            for k in sorted(_cache, key=lambda k: _cache[k][0])[:100]:
                _cache.pop(k, None)
    return result


def _channel_avatar(info: dict) -> str:
    for t in info.get('thumbnails') or []:
        if (t.get('id') or '') in ('avatar_uncropped', 'avatar') or (t.get('width') and t.get('width') == t.get('height')):
            return t.get('url') or ''
    return ''


def _channel_banner(info: dict) -> str:
    for t in info.get('thumbnails') or []:
        if 'banner' in (t.get('id') or ''):
            return t.get('url') or ''
    return ''


SEARCH_BUCKET = 96  # results per YouTube search call; pages are sliced from it


SHORTS_FILTER = 'EgIQCQ%253D%253D'  # YouTube search filter "Type: Shorts" (as it appears in results URLs)


def _search_page(query: str, page: int, cookies: bool = False, sp: str | None = None) -> dict:
    """ytsearchN always starts from the first result, so fetching page 5 used to re-run pages 1-4.
    Fetch 96 results at a time (cached) and slice pages out of them."""
    per_bucket = SEARCH_BUCKET // PAGE_SIZE
    bucket = (page - 1) // per_bucket + 1
    n = bucket * SEARCH_BUCKET
    def build():
        start = (bucket - 1) * SEARCH_BUCKET + 1
        # ytsearch always applies YouTube's "Videos only" filter; other filters need a results URL
        source = f'https://www.youtube.com/results?search_query={quote_plus(query)}&sp={sp}' if sp else f'ytsearch{n}:{query}'
        info = YTDLP.get_info(source, _flat_opts(start, n, cookies)) or {}
        return [e for e in (_simplify(x) for x in (info.get('entries') or [])) if e]
    items = _cached(f'search|{query}|{bucket}|{cookies}|{sp}', build)
    offset = ((page - 1) % per_bucket) * PAGE_SIZE
    chunk = items[offset:offset + PAGE_SIZE]
    more = len(chunk) >= PAGE_SIZE or (offset + PAGE_SIZE >= len(items) and len(items) >= SEARCH_BUCKET)
    return {'title': query, 'channel': '', 'channel_url': '', 'avatar': '', 'banner': '', 'subscribers': None,
            'items': chunk, 'has_more': more}


def _search_source(query: str, page: int) -> str:
    return f'ytsearch{page * PAGE_SIZE}:{query}'


def _channel_source(url: str, tab: str) -> str:
    url = url.rstrip('/')
    for t in ('/videos', '/shorts', '/streams', '/playlists', '/featured', '/live'):
        if url.endswith(t):
            url = url[: -len(t)]
    return f'{url}/{tab}'


def has_cookies() -> bool:
    return bool(get_global_cookies_file(True))


def browse(kind: str, page: int = 1, q: str = '', url: str = '', tab: str = 'videos', hints: list | None = None) -> dict:
    page = max(1, min(page, 20))
    if kind == 'search':
        if not q: return {'items': [], 'has_more': False}
        return _search_page(q, page)
    if kind == 'home':
        return _fetch(':ytrec', page, cookies=True) | {'title': 'Home'}
    if kind == 'subscriptions':
        return _fetch(':ytsubs', page, cookies=True) | {'title': 'Subscriptions'}
    if kind == 'history':
        return _fetch(':ythistory', page, cookies=True) | {'title': 'History'}
    if kind == 'watchlater':
        return _fetch(':ytwatchlater', page, cookies=True) | {'title': 'Watch later'}
    if kind == 'shorts':
        return shorts_feed(page, q, hints)
    if kind == 'channel':
        if tab not in ('videos', 'shorts', 'streams', 'playlists'): tab = 'videos'
        return _fetch(_channel_source(url, tab), page, cookies=False)
    if kind == 'playlist':
        return _fetch(url, page, cookies=False)
    raise ValueError(f'Unknown browse kind: {kind}')


# ---------------------------------------------------------------------------
# Watch page: recommendations, details, comments
# ---------------------------------------------------------------------------

_YT_ID = re.compile(r'(?:v=|youtu\.be/|/shorts/|/live/|/embed/)([A-Za-z0-9_-]{11})')


def youtube_id(url: str) -> str | None:
    m = _YT_ID.search(url or '')
    return m.group(1) if m else None


def _cached(key: str, fn, ttl: int = CACHE_TTL):
    now = time.time()
    with _cache_lock:
        hit = _cache.get(key)
        if hit and now - hit[0] < ttl:
            return hit[1]
    if (disk := _disk_get(key, ttl)) is not None:
        with _cache_lock: _cache[key] = (now, disk)
        return disk
    with _cache_lock:  # same thing already loading in this process (e.g. a warm-up): wait for it instead
        lock = _inflight.setdefault(key, Lock())
    with lock:
        with _cache_lock:
            hit = _cache.get(key)
        if hit and time.time() - hit[0] < ttl: return hit[1]
        try:
            value = fn()
            _disk_put(key, value)
            with _cache_lock: _cache[key] = (time.time(), value)
            return value
        finally:
            with _cache_lock: _inflight.pop(key, None)


def related(url: str, title: str = '') -> dict:
    """YouTube's own "Up next" isn't exposed by yt-dlp, so use the video's auto-generated
    mix (the same source YouTube autoplay draws from), topped up with a title search."""
    vid = youtube_id(url)
    # before the video's details arrive the page only knows the app name; searching for that
    # filled "Up next" with videos about xlab. Use the real title from the resolved meta instead.
    if not title or title.strip().lower() == app_title.strip().lower():
        title = ''
        try:
            from addons import get_meta
            title = (get_meta(url, force=True) or {}).get('title') or ''
        except Exception:
            pass

    def build():
        items, seen = [], {vid}
        def add(entries):
            for it in entries:
                if it['kind'] not in ('video', 'short') or it['id'] in seen: continue
                seen.add(it['id']); items.append(it)
        if vid:
            try:
                info = YTDLP.get_info(f'https://www.youtube.com/watch?v={vid}&list=RD{vid}', _flat_opts(1, 30, cookies=False)) or {}
                add([e for e in (_simplify(x) for x in (info.get('entries') or [])) if e])
            except Exception as e:
                pprint_exc(e)
        if len(items) < 16 and title:
            try:
                add(_search_page(title, 1)['items'])
            except Exception as e:
                pprint_exc(e)
        if not items: raise RuntimeError('no recommendations found')  # don't cache an empty list
        return {'items': items[:30]}

    try:
        return _cached(f'related2|{vid or url}', build)
    except RuntimeError:
        return {'items': []}


def _page_details(url: str) -> dict:
    """Fast-path metadata skips the watch page, so likes / upload date / subscribers are missing.
    Fetch them separately (android_vr, no JS challenges) without holding up playback."""
    def build():
        opts = {'quiet': True, 'skip_download': True, 'extractor_retries': 0, 'socket_timeout': 6,
                'ignore_no_formats_error': True,
                'extractor_args': {'youtube': {'player_client': ['android_vr']}}}
        opts.update({k: v for k, v in ydl_global_opts.items() if k not in ('extractor_args',)})
        info = YTDLP.get_info(url, opts, fallback=False) or {}
        keys = ('like_count', 'upload_date', 'timestamp', 'release_timestamp', 'channel_follower_count', 'comment_count',
                'channel_is_verified', 'channel_url', 'uploader_url', 'tags', 'concurrent_view_count', 'view_count', 'description')
        return {k: info.get(k) for k in keys if info.get(k) is not None}
    return _cached(f'pagedetails|{url}', build, ttl=3600)


def details(meta: dict) -> dict:
    if meta.get('_fast_path') and not meta.get('upload_date') and meta.get('original_url'):
        try:
            extra = _page_details(meta['original_url'])
            meta = meta | {k: v for k, v in extra.items() if k != 'timestamp'}
        except Exception as e:
            pprint_exc(e)
    channel_url = meta.get('channel_url') or meta.get('uploader_url') or ''
    if not channel_url and meta.get('channel_id'):
        channel_url = f'https://www.youtube.com/channel/{meta["channel_id"]}'
    return {
        'title': meta.get('title') or '',
        'channel': meta.get('channel') or meta.get('uploader') or '',
        'channel_url': channel_url,
        'verified': bool(meta.get('channel_is_verified')),
        'subscribers': meta.get('channel_follower_count'),
        'views': meta.get('view_count'),
        'watching': meta.get('concurrent_view_count'),
        'likes': meta.get('like_count'),
        'comment_count': meta.get('comment_count'),
        'timestamp': meta.get('timestamp') or meta.get('release_timestamp'),
        'upload_date': meta.get('upload_date'),
        'live': meta.get('live_status') == 'is_live' or bool(meta.get('is_live')),
        'description': meta.get('description') or '',
        'tags': (meta.get('tags') or [])[:12],
        'is_youtube': (meta.get('extractor_key') or meta.get('extractor') or '').lower().startswith('youtube'),
    }


# (max total, max top-level threads, max replies total, max replies per thread)
_COMMENT_LIMITS = {
    'quick': ['25', '20', '0', '0'],     # first screen: one or two requests, no reply threads
    'full': ['150', '50', '100', '5'],   # every thread with replies costs YouTube an extra request each
}


def comments(url: str, sort: str = 'top', full: bool = False) -> dict:
    sort = 'new' if sort == 'new' else 'top'
    depth = 'full' if full else 'quick'
    if not full:  # a finished full load already has everything the quick one would
        with _cache_lock:
            hit = _cache.get(f'comments|full|{sort}|{url}')
        if hit and time.time() - hit[0] < 1800: return hit[1]

    def build():
        opts = {
            'quiet': True,
            'skip_download': True,
            'getcomments': True,
            'extractor_retries': 0,
            'socket_timeout': 8,
            'ignore_no_formats_error': True,  # we only want the comments, not playable formats
        }
        opts.update(ydl_global_opts)
        # comments come from the watch page itself; the android_vr client skips downloading and
        # solving YouTube's player JavaScript, which used to be most of the wait
        opts['extractor_args'] = {'youtube': {'max_comments': _COMMENT_LIMITS[depth], 'comment_sort': [sort],
                                              'player_client': ['android_vr']}}
        info = YTDLP.get_info(url, opts) or {}
        threads, by_id = [], {}
        for c in info.get('comments') or []:
            item = {
                'id': c.get('id'),
                'author': c.get('author') or '',
                'avatar': c.get('author_thumbnail') or '',
                'author_url': c.get('author_url') or '',
                'text': c.get('text') or '',
                'likes': c.get('like_count'),
                'timestamp': c.get('timestamp'),
                'time_text': c.get('_time_text') or '',
                'pinned': bool(c.get('is_pinned')),
                'hearted': bool(c.get('is_favorited')),
                'is_uploader': bool(c.get('author_is_uploader')),
                'verified': bool(c.get('author_is_verified')),
                'reply_count': c.get('reply_count'),
                'replies': [],
            }
            parent = c.get('parent') or 'root'
            if parent == 'root':
                by_id[c.get('id')] = item
                threads.append(item)
            elif parent in by_id:
                by_id[parent]['replies'].append(item)
        return {'count': info.get('comment_count'), 'comments': threads, 'full': full}

    return _cached(f'comments|{depth}|{sort}|{url}', build, ttl=1800)


def warm_comments(url: str, delay: float = 4):
    """Start loading the first comments in the background when a watch page opens, after the
    video has had a head start, so they're usually ready by the time you scroll down."""
    def run():
        time.sleep(delay)
        try: comments(url, 'top')
        except Exception as e: print(f'[comments] warm-up failed: {str(e)[:200]}')
    if youtube_id(url): Thread(target=run, daemon=True).start()


from collections import deque
from threading import Condition, Thread

# per worker process. Every resolve can start a Deno JS-solver, so keep this small on small servers
MAX_PREFETCH = int(os.environ.get('MAX_PREFETCH', '1'))
MAX_SHORT_PREFETCH = int(os.environ.get('MAX_SHORT_PREFETCH', '1'))
# resolve videos just because they scrolled into view (off by default: on a home feed that meant
# dozens of background resolves and a maxed-out CPU). Hover, tap and Up next still prefetch.
PREFETCH_VISIBLE = os.environ.get('PREFETCH_VISIBLE', 'false').lower() == 'true'
_QUEUE_LIMIT = {'': 24, 'short': 10}


class _PrefetchQueue:
    """Background resolving / downloading, like xlab-player's prefetch. Regular videos run newest-first
    (what's on screen now matters most); Shorts run in feed order. High priority (tap, hover, up next)
    jumps the queue. Old entries are dropped when the queue is full."""
    def __init__(self, media: str, workers: int):
        self.media, self.workers = media, workers
        self.q, self.keys, self.active = deque(), set(), set()
        self.cv = Condition()
        self.started = False

    def _work(self, url: str):
        from addons import MediaDownloader, get_meta
        started = time.time()
        try:
            if self.media == 'short':
                MediaDownloader(url, 'short').run()
                print(f'[shorts] ready in {time.time() - started:.1f}s: {url}')
            else:
                get_meta(url)
                print(f'[prefetch] resolved in {time.time() - started:.1f}s: {url}')
        except Exception as e:
            print(f'[prefetch] {url}: {e}')

    def _loop(self):
        while True:
            with self.cv:
                while not self.q: self.cv.wait()
                url = self.q.popleft()
                self.keys.discard(url); self.active.add(url)
            try: self._work(url)
            finally:
                with self.cv: self.active.discard(url)

    def add(self, url: str, high: bool = False) -> bool:
        with self.cv:
            if not self.started:
                for _ in range(self.workers): Thread(target=self._loop, daemon=True).start()
                self.started = True
            if url in self.active: return True
            if url in self.keys:
                if high:  # move to the front
                    self.q.remove(url); self.q.appendleft(url)
                return True
            newest_first = self.media != 'short'
            if high or newest_first: self.q.appendleft(url)
            else: self.q.append(url)
            self.keys.add(url)
            limit = _QUEUE_LIMIT.get(self.media, 24)
            while len(self.q) > limit:  # drop the stalest
                old = self.q.pop() if newest_first else self.q.popleft()
                self.keys.discard(old)
            self.cv.notify()
            return True


_queues = {'': _PrefetchQueue('', MAX_PREFETCH), 'short': _PrefetchQueue('short', MAX_SHORT_PREFETCH)}


def prefetch(url: str, media: str = '', high: bool = False):
    """Queue a video for background resolving (media='short': also download the Shorts MP4).
    Returns 'ready' if it is already done, True when queued."""
    from addons import check_media
    if not url: return False
    media = 'short' if media == 'short' else ''
    if check_media(url, 'short' if media else 'meta'): return 'ready'
    if not high and not PREFETCH_VISIBLE and not media: return False
    return _queues[media].add(url, high)


# ---------------------------------------------------------------------------
# Shorts feed built from the user's own account
# ---------------------------------------------------------------------------
SHORTS_CHANNELS_PER_PAGE = 6
SHORTS_PER_CHANNEL = 3


def _shorts_search(query: str, cookies: bool) -> list:
    """YouTube search with the Shorts filter (one batch, real Shorts only)."""
    try:
        data = _search_page(query, 1, cookies=cookies, sp=SHORTS_FILTER)
        return [it | {'kind': 'short'} for it in data['items'] if it['kind'] in ('short', 'video') and not it.get('live')]
    except Exception as e:
        pprint_exc(e)
        return []


def _subscribed_channels() -> list:
    """Channels the cookies' account is subscribed to (cached 1 h)."""
    def build():
        info = YTDLP.get_info('https://www.youtube.com/feed/channels', _flat_opts(1, 500, True), fallback=False) or {}
        out = []
        for e in info.get('entries') or []:
            url = e.get('url') or e.get('channel_url') or ''
            if '/channel/' in url or '/@' in url:
                out.append({'url': url, 'name': e.get('title') or e.get('channel') or ''})
        return out
    try:
        return _cached('subs-channels', build, ttl=3600) if has_cookies() else []
    except Exception as e:
        pprint_exc(e)
        return []


def _recommended_titles() -> list:
    """Titles from the account's Home recommendations, used as personal Shorts search terms (cached 30 min)."""
    def build():
        info = YTDLP.get_info(':ytrec', _flat_opts(1, 48, True), fallback=False) or {}
        return [e.get('title') for e in (info.get('entries') or []) if e.get('title')]
    try:
        return _cached('rec-titles', build, ttl=1800) if has_cookies() else []
    except Exception as e:
        pprint_exc(e)
        return []


def _channel_shorts(channel: dict, depth: int) -> list:
    try:
        items = _fetch(_channel_source(channel['url'], 'shorts'), 1, cookies=False)['items']
    except Exception:
        return []
    chunk = items[depth * SHORTS_PER_CHANNEL:(depth + 1) * SHORTS_PER_CHANNEL]
    return [it | {'kind': 'short', 'channel': it.get('channel') or channel['name'], 'channel_url': it.get('channel_url') or channel['url']} for it in chunk]


def _search_term(title: str) -> str:
    # keep the meaningful words of a title: drop hashtags, brackets and punctuation, max 6 words
    t = re.sub(r'[#@]\S+|\(.*?\)|\[.*?\]|[|:!?"\'“”‘’]', ' ', title)
    words = [w for w in t.split() if len(w) > 1][:6]
    return ' '.join(words)


def shorts_feed(page: int, q: str = '', hints: list | None = None) -> dict:
    """One page of the Shorts feed. With cookies: Shorts from subscribed channels (rotating, deeper each
    round) plus Shorts searches seeded by the account's own recommendations. Without cookies: searches
    seeded by the app's followed channels / recently played (hints). A typed query searches just that."""
    from concurrent.futures import ThreadPoolExecutor
    cookies = has_cookies()
    if q:
        data = _search_page(q, page, cookies=cookies, sp=SHORTS_FILTER)
        items = [it | {'kind': 'short'} for it in data['items'] if it['kind'] in ('short', 'video')]
        return {'items': items, 'has_more': data['has_more'] and bool(items), 'title': 'Shorts'}

    jobs, terms = [], []
    subs = _subscribed_channels()
    if subs:
        per = SHORTS_CHANNELS_PER_PAGE
        rounds = max(1, -(-len(subs) // per))
        depth, slot = divmod(page - 1, rounds)
        if depth < 8:
            batch = subs[slot * per:(slot + 1) * per]
            jobs += [('channel', c, depth) for c in batch]
    rec = _recommended_titles()
    seeds = [t for t in (rec or []) if t] + [h for h in (hints or []) if h]
    for k in range(2):  # two personal searches per page, different seeds each page
        if seeds:
            terms.append(_search_term(seeds[((page - 1) * 2 + k) % len(seeds)]))
    if not terms and not jobs:
        terms = ['#shorts']  # nothing personal to go on
    with ThreadPoolExecutor(max_workers=8) as pool:
        chan_results = list(pool.map(lambda j: _channel_shorts(j[1], j[2]), jobs))
        search_results = list(pool.map(lambda t: _shorts_search(t, cookies), [t for t in terms if t]))
    # interleave: subscription shorts and personal discovery
    subs_items = [it for lst in chan_results for it in lst]
    disc_items = [it for lst in search_results for it in lst[:8]]
    mixed = []
    for i in range(max(len(subs_items), len(disc_items))):
        if i < len(subs_items): mixed.append(subs_items[i])
        if i < len(disc_items): mixed.append(disc_items[i])
    more_subs = bool(subs) and (page // max(1, -(-len(subs) // SHORTS_CHANNELS_PER_PAGE))) < 8
    more_seeds = (page * 2) < len(seeds)
    return {'items': mixed, 'has_more': bool(mixed) and (more_subs or more_seeds), 'title': 'Shorts'}
