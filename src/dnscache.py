"""Process-wide DNS cache.

The Docker image is Alpine (musl), which has no local DNS cache: every request to
googlevideo.com / i.ytimg.com / youtube.com did a fresh DNS lookup. Video playback makes
many range requests per video, so those lookups added up. This caches successful
socket.getaddrinfo() results for DNS_CACHE_TTL seconds (default 300, 0 = off).
It covers requests, urllib and yt-dlp's Python networking.
"""
import os
import socket
import threading
import time

TTL = int(os.environ.get('DNS_CACHE_TTL', '300'))
MAX_ENTRIES = 2048

_orig_getaddrinfo = socket.getaddrinfo
_cache: dict[tuple, tuple[float, list]] = {}
_lock = threading.Lock()


def _cached_getaddrinfo(host, port, family=0, type=0, proto=0, flags=0):
    key = (host, port, family, type, proto, flags)
    now = time.monotonic()
    with _lock:
        hit = _cache.get(key)
        if hit and hit[0] > now:
            return hit[1]
    result = _orig_getaddrinfo(host, port, family, type, proto, flags)
    with _lock:
        if len(_cache) >= MAX_ENTRIES:
            for k in [k for k, v in _cache.items() if v[0] <= now] or list(_cache)[:MAX_ENTRIES // 4]:
                _cache.pop(k, None)
        _cache[key] = (now + TTL, result)
    return result


def install():
    if TTL > 0 and socket.getaddrinfo is _orig_getaddrinfo:
        socket.getaddrinfo = _cached_getaddrinfo
        print(f'DNS cache enabled ({TTL}s)')


install()
