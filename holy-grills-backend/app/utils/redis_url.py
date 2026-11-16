"""Redis connection strings: accept what dashboards hand out, and say so clearly.

`redis.Redis.from_url()` only accepts `redis://`, `rediss://` or `unix:` and otherwise
raises

    ValueError: Redis URL must specify one of the following schemes
                (redis://, rediss://, unix://)

Railway's Connect tab offers the public proxy as a bare `host:port`
(e.g. `roundhouse.proxy.rlwy.net:12345`), so pasting that into `REDIS_URL` produced
exactly that error even though the host and port were correct. The same is true of
`REDIS_HOST`/`REDIS_PORT` style values, or a URL copied out of another provider's
"endpoint" field.

`normalize_redis_url()` repairs the recoverable shapes and returns "" for anything that
is not a Redis URL at all, so callers can report "misconfigured" instead of an opaque
library error. Nothing here guesses credentials: only the scheme is added.

Both helpers are pure (environment is read by the caller) so they can be used from
`app.config` at import time without pulling in the app.
"""
import logging
import re

logger = logging.getLogger(__name__)

_REDIS_SCHEMES = ("redis://", "rediss://", "unix:")
# host[:port][/db] — the shape copied from a dashboard's endpoint field.
_BARE_HOST = re.compile(r"^[A-Za-z0-9_][A-Za-z0-9._\-]*(:\d{1,5})?(/\d{0,2})?$")


def _clean(raw) -> str:
    """Trim whitespace and any quotes a dashboard paste leaves behind."""
    if raw is None:
        return ""
    return str(raw).strip().strip("'\"").strip()


def normalize_redis_url(raw) -> str:
    """A URL `redis.from_url()` will accept, or "" if `raw` is not a Redis URL."""
    value = _clean(raw)
    if not value:
        return ""
    low = value.lower()
    if low.startswith(_REDIS_SCHEMES):
        return value
    if "://" in low:
        # An explicit but wrong scheme is a mistake we can repair for http(s), which is
        # how some hosts publish a TLS proxy endpoint. Anything else (amqp://, postgres://)
        # is not a Redis URL and must not be silently rewritten.
        for prefix, scheme in (("https://", "rediss://"), ("http://", "redis://")):
            if low.startswith(prefix):
                repaired = scheme + value[len(prefix):].rstrip("/")
                logger.warning("redis: %s:// endpoint rewritten as %s://", prefix[:-3], scheme[:-3])
                return repaired
        return ""
    if _BARE_HOST.match(value):
        logger.warning("redis: REDIS_URL had no scheme (host:port); using it as redis://%s", value)
        return "redis://" + value
    return ""


def normalize_broker_url(raw) -> str:
    """Like `normalize_redis_url`, but leaves a deliberate non-Redis broker alone.

    Celery can be pointed at RabbitMQ, SQS or anything else kombu supports, so an
    `amqp://` value must pass through untouched. Only scheme-less values are treated as
    Redis host:port, which is the Railway paste case.
    """
    value = _clean(raw)
    if not value:
        return ""
    low = value.lower()
    if "://" in low and not low.startswith(_REDIS_SCHEMES):
        return value
    return normalize_redis_url(value)
