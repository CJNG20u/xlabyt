"""Per-person YouTube accounts without logins.

Each browser can upload its own cookies.txt (Settings). It is stored on the server under a random
id that lives in an httpOnly cookie, and that person's Home, Subscriptions, History, Watch later and
Shorts feed come from their own account. A browser can also choose Guest mode (no account at all).
Browsers that do neither use the server's cookies.txt, unless SHARE_SERVER_ACCOUNT=false.

Playback itself still uses the server's cookies.txt only as a fallback for bot checks, like before.
"""
import contextvars
import os
import re
import secrets
from hashlib import sha1

ACCOUNTS_PATH = os.path.abspath(os.environ.get('ACCOUNTS_PATH', './accounts'))
SHARE_SERVER_ACCOUNT = os.environ.get('SHARE_SERVER_ACCOUNT', 'true').lower() == 'true'
UID_COOKIE = 'xlabyt_uid'
MODE_COOKIE = 'xlabyt_mode'  # 'guest' or empty
MAX_COOKIES_BYTES = 1024 * 1024
_UID = re.compile(r'^[a-f0-9]{32}$')

# cookies.txt path for the request being handled (None = no account)
current = contextvars.ContextVar('xlabyt_cookiefile', default=None)
current_source = contextvars.ContextVar('xlabyt_cookie_source', default='none')


def _user_file(uid: str | None) -> str | None:
    if not uid or not _UID.match(uid): return None
    return os.path.join(ACCOUNTS_PATH, f'{uid}.txt')


def resolve(request, server_cookies: str | None):
    """Pick the cookies for this request and store them in the context vars."""
    uid = request.cookies.get(UID_COOKIE)
    path = _user_file(uid)
    if path and os.path.exists(path):
        current.set(path); current_source.set('own')
    elif request.cookies.get(MODE_COOKIE) == 'guest':
        current.set(None); current_source.set('guest')
    elif SHARE_SERVER_ACCOUNT and server_cookies:
        current.set(server_cookies); current_source.set('server')
    else:
        current.set(None); current_source.set('none')


def cache_key() -> str:
    """Short id of the account in use, so cached feeds never leak between people."""
    path = current.get()
    return sha1(path.encode()).hexdigest()[:10] if path else 'anon'


def validate(data: bytes) -> str:
    if len(data) > MAX_COOKIES_BYTES: raise ValueError('File is too big for a cookies.txt')
    try: text = data.decode('utf-8')
    except UnicodeDecodeError: raise ValueError('Not a text file')
    lines = [l for l in text.splitlines() if l.strip() and not l.startswith('#') or l.startswith('#HttpOnly_')]
    yt = [l for l in lines if 'youtube.com' in l.split('\t')[0] and len(l.split('\t')) >= 7]
    if not yt: raise ValueError('No youtube.com cookies found. Export cookies.txt (Netscape format) while signed in to YouTube.')
    if not text.startswith('# Netscape') and not text.startswith('# HTTP Cookie File'):
        text = '# Netscape HTTP Cookie File\n' + text
    return text


def save(uid: str | None, data: bytes) -> str:
    text = validate(data)
    if not uid or not _UID.match(uid): uid = secrets.token_hex(16)
    os.makedirs(ACCOUNTS_PATH, exist_ok=True)
    path = _user_file(uid)
    tmp = path + '.tmp'
    with open(os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600), 'w') as f:
        f.write(text)
    os.replace(tmp, path)
    return uid


def remove(uid: str | None):
    path = _user_file(uid)
    if path and os.path.exists(path): os.remove(path)
