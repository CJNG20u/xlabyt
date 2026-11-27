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
AUTO_DISABLE_SECONDS = 30 * 60

_YT_ID = re.compile(r'(?:v=|youtu\.be/|/shorts/|/live/|/embed/)([A-Za-z0-9_-]{11})')
_lock = Lock()
_visitor = {'value': None, 'valid_until': 0.0, 'retry_at': 0.0}


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


STATE_FILE = None          # set by addons: <DATA_PATH>/fastpath.json, shared by all server processes
FAILURE_THRESHOLD = 2     # any kind of fast-path failure (bot check, refused stream) in a row
BOT_FLAG_SECONDS = 30 * 60


def _read_state() -> dict:
    try:
        with open(STATE_FILE) as f: return json.load(f)
    except Exception: return {}


def _write_state(**changes):
    if not STATE_FILE: return
    state = _read_state() | changes
    tmp = f'{STATE_FILE}.{os.getpid()}.tmp'
    try:
        with open(tmp, 'w') as f: json.dump(state, f)
        os.replace(tmp, STATE_FILE)
    except Exception as e:
        print(f'[fast-path] could not save state: {e}')


def bot_flagged() -> bool:
    """YouTube showed this server a bot check recently: lookups should go straight to cookies."""
    return time.time() < float(_read_state().get('bot_until') or 0)


def flag_bot(error) -> bool:
    msg = str(error).lower()
    if not ('confirm you' in msg or 'not a bot' in msg or ('bot' in msg and 'sign in' in msg)): return False
    if not bot_flagged():
        print('[fast-path] YouTube bot check: using cookies first for the next 30 minutes (if cookies.txt is mounted)')
    _write_state(bot_until=time.time() + BOT_FLAG_SECONDS)
    return True


def available(url: str) -> bool:
    if not ENABLED or not youtube_id(url): return False
    state = _read_state()
    until = float(state.get('disabled_until') or 0)
    if until and time.time() < until: return False
    if until:
        _write_state(disabled_until=0, failures=0)
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
    if int(_read_state().get('failures') or 0): _write_state(failures=0)


def failure(error, vd: str | None = None):
    bot = flag_bot(error)
    if bot or 'visitor' in str(error).lower(): reject_visitor_data(vd)
    failures = int(_read_state().get('failures') or 0) + 1
    if failures >= FAILURE_THRESHOLD:
        _write_state(failures=0, disabled_until=time.time() + AUTO_DISABLE_SECONDS)
        print(f'[fast-path] failed {failures} times in a row; disabling fast path for 30 minutes')
    else:
        _write_state(failures=failures)
    print(f'[fast-path] falling back to normal extraction: {str(error).splitlines()[0][:200] if str(error) else error}')
