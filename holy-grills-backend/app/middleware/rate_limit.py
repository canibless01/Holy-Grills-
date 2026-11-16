"""Rate limiting that survives more than one worker and one deploy.

Counters live in Redis when `REDIS_URL` is configured, so a limit means the same thing
across gunicorn workers, Railway services and restarts. Without Redis the original
in-process store is used unchanged, which keeps local development, the test suite and a
Redis outage working exactly as before.

Accepts either hard-coded integers or Flask config key strings so limits can be changed
via environment variables without touching route code.

Usage:
    @rate_limit(max_requests=20, window_seconds=900)           # hard-coded
    @rate_limit("RATE_LIMIT_LOGIN_REQUESTS", "RATE_LIMIT_LOGIN_WINDOW")  # config-backed
"""

import time
from collections import defaultdict
from functools import wraps

from flask import request, jsonify, g, current_app

from app.messages import MSG
from app.utils.redis_url import normalize_redis_url

# Fallback store, used when Redis is not configured or cannot be reached.
_request_counts: dict[str, list] = defaultdict(list)

# A single shared client per process; None means "do not try again just yet".
_client = None
_client_checked = False
_client_retry_after = 0.0
_REDIS_RETRY_SECONDS = 60


def _redis():
    """Shared Redis client, or None when unavailable.

    Only uses Redis when REDIS_URL is explicitly set: an implicit localhost default
    would make every request pay a failed connect before falling back.
    """
    global _client, _client_checked, _client_retry_after

    import os
    url = normalize_redis_url(os.environ.get("REDIS_URL"))
    if not url:
        return None

    now = time.time()
    if _client is not None:
        return _client
    if _client_checked and now < _client_retry_after:
        return None
    _client_checked = True
    try:
        import redis as _redis_module
        client = _redis_module.from_url(
            url,
            socket_connect_timeout=0.5,
            socket_timeout=0.5,
            decode_responses=True,
        )
        client.ping()
        _client = client
        return _client
    except Exception:                                             # noqa: BLE001
        _client_retry_after = now + _REDIS_RETRY_SECONDS
        current_app.logger.warning(
            "rate limit: Redis unavailable (%s) — counting in-process; limits are "
            "per-worker until it recovers", url.split("@")[-1])
        return None


def reset_redis_client():
    """Forget the cached client (used by tests and after a config change)."""
    global _client, _client_checked, _client_retry_after
    _client = None
    _client_checked = False
    _client_retry_after = 0.0


def _redis_count(bucket_key: str, window: float) -> int:
    """Increment and return the count for the current fixed window.

    A fixed window (rather than a sorted set) keeps the cost to one INCR+EXPIRE for the
    common case; the worst case is a burst spanning a window boundary, which allows up to
    2x the limit for one instant — acceptable for brute-force and abuse limits.
    """
    client = _redis()
    if client is None:
        return -1
    slot = int(time.time() // max(1, window))
    key = f"hg:rl:{bucket_key}:{slot}"
    try:
        pipe = client.pipeline()
        pipe.incr(key, 1)
        pipe.expire(key, int(window) + 1)
        count, _ = pipe.execute()
        return int(count)
    except Exception:                                             # noqa: BLE001
        current_app.logger.warning("rate limit: Redis counter failed — falling back in-process")
        reset_redis_client()
        return -1


def _memory_count(bucket_key: str, window: float, now: float) -> int:
    if len(_request_counts) > 10_000:
        for stale_key in [k for k, v in _request_counts.items() if not v or v[-1] < now - 86400]:
            _request_counts.pop(stale_key, None)
    timestamps = _request_counts[bucket_key]
    cutoff = now - window
    timestamps[:] = [t for t in timestamps if t > cutoff]
    timestamps.append(now)
    return len(timestamps)


def rate_limit(max_requests, window_seconds=60):
    """Limit a route to max_requests per window_seconds per IP (or user_id if
    authenticated).

    Both parameters can be:
      - an int  → used as-is
      - a str   → treated as a Flask config key looked up at request time
    """
    def decorator(f):
        @wraps(f)
        def decorated(*args, **kwargs):
            if request.method == "OPTIONS":
                return "", 200
            # Resolve values — look up config keys at request time so env var
            # changes take effect after a restart without code edits.
            _max = (
                current_app.config.get(max_requests, 10)
                if isinstance(max_requests, str)
                else max_requests
            )
            _win = (
                current_app.config.get(window_seconds, 60)
                if isinstance(window_seconds, str)
                else window_seconds
            )

            now = time.time()
            key = getattr(g, "user_id", None) or request.remote_addr
            bucket_key = f"{request.endpoint}:{key}"

            count = _redis_count(bucket_key, _win)
            from_redis = count >= 0
            if not from_redis:
                count = _memory_count(bucket_key, _win, now)

            if count > _max:
                if from_redis:
                    retry_after = max(1, int(_win - (now % _win)) + 1)
                else:
                    timestamps = _request_counts.get(bucket_key) or []
                    oldest = timestamps[-_max] if len(timestamps) >= _max else now
                    retry_after = max(1, int(oldest + _win - now) + 1)
                resp = jsonify({
                    "error": MSG.RATE_LIMIT_EXCEEDED,
                    "detail": MSG.RATE_LIMIT_DETAIL.format(max=_max, window=int(_win)),
                    "retry_after": retry_after,
                })
                resp.status_code = 429
                resp.headers["Retry-After"] = str(retry_after)
                return resp
            return f(*args, **kwargs)
        return decorated
    return decorator
