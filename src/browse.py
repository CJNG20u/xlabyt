"""YouTube-style browsing: search results, home/subscription feeds, channels and playlists.

Everything is fetched with yt-dlp's flat extraction (no per-video requests), so a page of
24 results comes back in roughly the time of one YouTube page load.
"""
import re
import time
from threading import Lock
from urllib.parse import urlparse

from main import *
from addons import YTDLP, get_global_cookies_file, pprint_exc


PAGE_SIZE = 24
CACHE_TTL = int(os.environ.get('BROWSE_CACHE_TTL', '600'))

_cache: dict[str, tuple[float, list]] = {}
_cache_lock = Lock()


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


def _search_source(query: str, page: int) -> str:
    # ytsearchN returns the first N results; request enough to cover the page we want.
    return f'ytsearch{page * PAGE_SIZE}:{query}'


def _channel_source(url: str, tab: str) -> str:
    url = url.rstrip('/')
    for t in ('/videos', '/shorts', '/streams', '/playlists', '/featured', '/live'):
        if url.endswith(t):
            url = url[: -len(t)]
    return f'{url}/{tab}'


def has_cookies() -> bool:
    return bool(get_global_cookies_file(True))


def browse(kind: str, page: int = 1, q: str = '', url: str = '', tab: str = 'videos') -> dict:
    page = max(1, min(page, 20))
    if kind == 'search':
        if not q: return {'items': [], 'has_more': False}
        data = _fetch(_search_source(q, page), page, cookies=False)
        return data | {'title': q}
    if kind == 'home':
        return _fetch(':ytrec', page, cookies=True) | {'title': 'Home'}
    if kind == 'subscriptions':
        return _fetch(':ytsubs', page, cookies=True) | {'title': 'Subscriptions'}
    if kind == 'history':
        return _fetch(':ythistory', page, cookies=True) | {'title': 'History'}
    if kind == 'watchlater':
        return _fetch(':ytwatchlater', page, cookies=True) | {'title': 'Watch later'}
    if kind == 'shorts':
        # Shorts discovery: search results narrowed to shorts (vertical, up to 3 minutes)
        data = _fetch(_search_source(f'{q} #shorts' if q else '#shorts', page), page, cookies=False)
        items = [it | {'kind': 'short'} for it in data['items']
                 if it['kind'] == 'short' or (it['kind'] == 'video' and it.get('duration') and 0 < it['duration'] <= 180 and not it.get('live'))]
        return data | {'items': items, 'title': 'Shorts'}
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
    value = fn()
    with _cache_lock:
        _cache[key] = (now, value)
    return value


def related(url: str, title: str = '') -> dict:
    """YouTube's own "Up next" isn't exposed by yt-dlp, so use the video's auto-generated
    mix (the same source YouTube autoplay draws from), topped up with a title search."""
    vid = youtube_id(url)

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
                add(_fetch(_search_source(title, 1), 1, cookies=False)['items'])
            except Exception as e:
                pprint_exc(e)
        return {'items': items[:30]}

    return _cached(f'related|{vid or url}', build)


def _page_details(url: str) -> dict:
    """Fast-path metadata skips the watch page, so likes / upload date / subscribers are missing.
    Fetch them separately (android_vr, no JS challenges) without holding up playback."""
    def build():
        opts = {'quiet': True, 'skip_download': True, 'extractor_retries': 0, 'socket_timeout': 6,
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


def comments(url: str, sort: str = 'top') -> dict:
    sort = 'new' if sort == 'new' else 'top'

    def build():
        opts = {
            'quiet': True,
            'skip_download': True,
            'getcomments': True,
            # max total, max top-level threads, max replies total, max replies per thread
            'extractor_args': {'youtube': {'max_comments': ['150', '50', '100', '5'], 'comment_sort': [sort]}},
        }
        opts.update(ydl_global_opts)
        info = YTDLP.get_info(url, opts) or {}
        threads, by_id = [], {}
        for c in info.get('comments') or []:
            item = {
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
                'replies': [],
            }
            parent = c.get('parent') or 'root'
            if parent == 'root':
                by_id[c.get('id')] = item
                threads.append(item)
            elif parent in by_id:
                by_id[parent]['replies'].append(item)
        return {'count': info.get('comment_count'), 'comments': threads}

    return _cached(f'comments|{sort}|{url}', build, ttl=1800)


_prefetching: set[str] = set()
_prefetch_lock = Lock()
MAX_PREFETCH = int(os.environ.get('MAX_PREFETCH', '3'))


def prefetch(url: str) -> bool:
    """Start resolving a video in the background (hover / touch / up next), like xlab-player's prefetch."""
    from addons import check_media, get_meta
    from threading import Thread
    if not url or check_media(url, 'meta'): return False
    with _prefetch_lock:
        if url in _prefetching or len(_prefetching) >= MAX_PREFETCH: return False
        _prefetching.add(url)
    def run():
        try: get_meta(url)
        except Exception as e: print(f'[prefetch] {url}: {e}')
        finally:
            with _prefetch_lock: _prefetching.discard(url)
    Thread(target=run, daemon=True).start()
    return True
