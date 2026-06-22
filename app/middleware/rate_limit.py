"""
Simple in-memory rate limiter. In production, swap for Redis-backed limiter.
"""

import time
from collections import defaultdict
from functools import wraps
from flask import request, abort, g


_request_counts: dict[str, list] = defaultdict(list)


def rate_limit(max_requests: int, window_seconds: int = 60):
    """Limit a route to max_requests per window_seconds per IP (or user_id if authenticated)."""
    def decorator(f):
        @wraps(f)
        def decorated(*args, **kwargs):
            now = time.time()
            key = getattr(g, "user_id", None) or request.remote_addr
            bucket_key = f"{request.endpoint}:{key}"

            timestamps = _request_counts[bucket_key]
            cutoff = now - window_seconds
            timestamps[:] = [t for t in timestamps if t > cutoff]

            if len(timestamps) >= max_requests:
                abort(429, f"Rate limit exceeded: {max_requests} requests per {window_seconds}s")

            timestamps.append(now)
            return f(*args, **kwargs)
        return decorated
    return decorator
