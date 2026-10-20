"""Small fixed-window rate limiter backed by Django's cache."""
import hashlib

from django.core.cache import cache


def _key(scope: str, ident: str) -> str:
    return f"throttle:{scope}:{hashlib.sha256(ident.encode()).hexdigest()[:32]}"


def is_blocked(scope: str, ident: str, limit: int) -> bool:
    return cache.get(_key(scope, ident), 0) >= limit


def register_hit(scope: str, ident: str, window_seconds: int) -> int:
    key = _key(scope, ident)
    if cache.add(key, 1, timeout=window_seconds):
        return 1
    try:
        return cache.incr(key)
    except ValueError:  # key expired between add() and incr()
        cache.set(key, 1, timeout=window_seconds)
        return 1


def reset(scope: str, ident: str) -> None:
    cache.delete(_key(scope, ident))
