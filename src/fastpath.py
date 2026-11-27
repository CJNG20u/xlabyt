"""Fast YouTube resolve path, ported from xlab-player's `android-vr-fast` strategy.

yt-dlp's default YouTube clients have to download the web player and solve its JavaScript
challenges (through Deno) before any stream URL is usable, which costs several seconds per
video. The android_vr client returns ready-to-use stream URLs without that step, and with
`player_skip=webpage,configs` plus a cached `visitor_data` token yt-dlp makes a single API
call. Typical lookups drop from ~4-8 s to ~1 s.

The fast path is always a first attempt only: anything it can't handle (age-restricted,
members-only, bot checks, a stream URL that fails its first probe) falls back to the normal
yt-dlp extraction. Repeated bot checks switch it off for 30 minutes, like xlab-player does.
"""
import json
import os
import re
import time
from threading import Lock

import requests

ENABLED = os.environ.get('FAST_PATH', 'true').lower() == 'true'
VISITOR_DATA_URL = 'https://www.youtube.com/sw.js_data'
VISITOR_DATA_TTL = 3600
VISITOR_DATA_COOLDOWN = 60
BOT_FAILURE_THRESHOLD = 3
AUTO_DISABLE_SECONDS = 30 * 60

_YT_ID = re.compile(r'(?:v=|youtu\.be/|/shorts/|/live/|/embed/)([A-Za-z0-9_-]{11})')
_lock = Lock()
_visitor = {'value': None, 'valid_until': 0.0, 'retry_at': 0.0}
_bot = {'failures': 0, 'disabled_until': 0.0}


def youtube_id(url: str) -> str | None:
    m = _YT_ID.search(url or '')
    return m.group(1) if m else None


def _parse_visitor_data(text: str) -> str | None:
    body = text.lstrip()
    if body.startswith(")]}'"):
        body = body.split('\n', 1)[1] if '\n' in body else ''
    try:
        def walk(node):
            if isinstance(node, str) and 20 < len(node) <= 160 and re.fullmatch(r'(?:Cg|Ch|Cs)[A-Za-z0-9_%-]+', node):
                return node
            if isinstance(node, list):
                for child in node:
                    if (found := walk(child)): return found
            return None
        if (found := walk(json.loads(body))): return found
    except Exception:
        pass
    m = re.search(r'"(C[a-zA-Z0-9_%-]{20,140})"', text)
    return m.group(1) if m else None


def visitor_data(proxy: str | None = None) -> str | None:
    now = time.time()
    with _lock:
        if now < _visitor['retry_at']: return None
        if _visitor['value'] and now < _visitor['valid_until']: return _visitor['value']
    value = None
    try:
        r = requests.get(VISITOR_DATA_URL, headers={'User-Agent': 'Mozilla/5.0', 'Accept': '*/*'}, timeout=5,
                         proxies={'http': proxy, 'https': proxy} if proxy else None)
        if r.ok: value = _parse_visitor_data(r.text[:256 * 1024])
    except Exception as e:
        print(f'[fast-path] visitor_data fetch failed: {e}')
    with _lock:
        if value:
            _visitor.update(value=value, valid_until=time.time() + VISITOR_DATA_TTL, retry_at=0.0)
        else:
            _visitor.update(value=None, valid_until=0.0, retry_at=time.time() + VISITOR_DATA_COOLDOWN)
    return value


def reject_visitor_data(value: str | None):
    with _lock:
        if value and _visitor['value'] == value:
            _visitor.update(value=None, valid_until=0.0, retry_at=time.time() + VISITOR_DATA_COOLDOWN)


def available(url: str) -> bool:
    if not ENABLED or not youtube_id(url): return False
    with _lock:
        if _bot['disabled_until'] and time.time() < _bot['disabled_until']: return False
        if _bot['disabled_until']:
            _bot.update(failures=0, disabled_until=0.0)
            print('[fast-path] auto-disable expired, re-enabling')
    return True


def options(proxy: str | None = None) -> tuple[dict, str | None]:
    """yt-dlp options for the fast attempt and the visitor token they use."""
    vd = visitor_data(proxy)
    args = {'player_client': ['android_vr']}
    if vd:
        args['player_skip'] = ['webpage', 'configs']
        args['visitor_data'] = [vd]
    return {'extractor_args': {'youtube': args}, 'socket_timeout': 6, 'extractor_retries': 0}, vd


def usable(info: dict) -> bool:
    formats = [f for f in (info.get('formats') or []) if f.get('url')]
    return bool(formats) and not info.get('is_live') and any((f.get('vcodec') or 'none') != 'none' for f in formats)


def success():
    with _lock:
        _bot['failures'] = 0


def failure(error: Exception | str, vd: str | None = None):
    msg = str(error).lower()
    bot = 'confirm you' in msg or 'not a bot' in msg or 'bot' in msg and 'sign in' in msg
    if bot or 'visitor' in msg: reject_visitor_data(vd)
    with _lock:
        if bot:
            _bot['failures'] += 1
            if _bot['failures'] >= BOT_FAILURE_THRESHOLD and not _bot['disabled_until']:
                _bot['disabled_until'] = time.time() + AUTO_DISABLE_SECONDS
                print(f'[fast-path] {BOT_FAILURE_THRESHOLD} bot checks in a row; disabling fast path for 30 minutes')
        else:
            _bot['failures'] = 0
    print(f'[fast-path] falling back to normal extraction: {str(error).splitlines()[0][:200] if str(error) else error}')
