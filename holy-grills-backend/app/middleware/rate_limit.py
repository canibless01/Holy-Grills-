"""
Simple in-memory rate limiter. In production, swap for Redis-backed limiter.

Accepts either hard-coded integers or Flask config key strings so limits can
be changed via environment variables without touching route code.

Usage:
    @rate_limit(max_requests=20, window_seconds=900)           # hard-coded
    @rate_limit("RATE_LIMIT_LOGIN_REQUESTS", "RATE_LIMIT_LOGIN_WINDOW")  # config-backed
"""

import time
from collections import defaultdict
from functools import wraps
from flask import request, jsonify, g, current_app
from app.messages import MSG


_request_counts: dict[str, list] = defaultdict(list)


def rate_limit(max_requests, window_seconds=60):
    """
    Limit a route to max_requests per window_seconds per IP (or user_id if
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

            # Unbounded dict otherwise grows forever (one entry per endpoint+user/IP
            # ever seen) since this limiter has no Redis TTL to expire it for us.
            if len(_request_counts) > 10_000:
                for stale_key in [k for k, v in _request_counts.items() if not v or v[-1] < now - 86400]:
                    _request_counts.pop(stale_key, None)

            timestamps = _request_counts[bucket_key]
            cutoff = now - _win
            timestamps[:] = [t for t in timestamps if t > cutoff]

            if len(timestamps) >= _max:
                retry_after = max(1, int(timestamps[0] + _win - now) + 1)
                resp = jsonify({
                    "error": MSG.RATE_LIMIT_EXCEEDED,
                    "detail": MSG.RATE_LIMIT_DETAIL.format(max=_max, window=int(_win)),
                    "retry_after": retry_after,
                })
                resp.status_code = 429
                resp.headers["Retry-After"] = str(retry_after)
                return resp

            timestamps.append(now)
            return f(*args, **kwargs)
        return decorated
    return decorator
