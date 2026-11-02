"""
Health check route — GET /api/health

Returns the API version, uptime status, and live connectivity checks for
every external dependency (Supabase, Redis).  Designed to be polled by
load balancers, uptime monitors, and deployment pipelines.

Response shape:
    {
        "status": "ok" | "degraded",
        "api": "<APP_NAME from config>",
        "version": "1.0.0",
        "checks": {
            "supabase":      "connected" | "error:<status>" | "unreachable:<msg>",   # PostgREST (database)
            "supabase_auth": "connected" | "error:<status>" | "unreachable:<msg>",   # GoTrue (auth)
            "redis":         "connected" | "error:<msg>"    | "not_configured"
        }
    }

HTTP 200 is returned whether status is "ok" or "degraded" — callers must
inspect the "status" field.  A 503 is only returned when the health handler
itself crashes, which should never happen in practice.
"""

import os

import requests as _req
from flask import Blueprint, jsonify, current_app
from app.messages import MSG

health_bp = Blueprint("health", __name__)


def _detail(exc, kind: str = "unreachable") -> str:
    """Reason for a failed check, without leaking internals to the public.

    `/api/health` is unauthenticated, and driver messages carry hostnames, ports and
    occasionally credentials from the URL. In production only the failure class is
    reported; DEBUG/TESTING keeps the full text because a developer is reading it.
    """
    if current_app.config.get("DEBUG") or current_app.config.get("TESTING"):
        return f"{kind}:{str(exc)[:80]}"
    text = str(exc).lower()
    if "refused" in text:
        return f"{kind}:connection_refused"
    if "name or service not known" in text or "nodename nor servname" in text:
        return f"{kind}:dns_failure"
    if "timed out" in text or "timeout" in text:
        return f"{kind}:timeout"
    return f"{kind}:error"


@health_bp.route("/health")
def health():
    """
    API health check — connectivity to Supabase and Redis.
    ---
    tags: [Health]
    security: []
    responses:
      200:
        description: Health status (inspect 'status' field — may be 'ok' or 'degraded')
        schema:
          properties:
            status:  {type: string, example: ok}
            api:     {type: string, example: "My App", description: "APP_NAME from config"}
            version: {type: string, example: "1.0.0"}
            checks:  {type: object}
    """
    checks: dict = {}

    # ── Supabase ──────────────────────────────────────────────────────────────
    try:
        url = os.environ.get("SUPABASE_URL", "").rstrip("/")
        key = os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "")
        r = _req.get(
            f"{url}/rest/v1/profiles?select=id&limit=1",
            headers={"apikey": key, "Authorization": f"Bearer {key}"},
            timeout=5,
        )
        checks["supabase"] = MSG.HEALTH_CONNECTED if r.status_code < 400 else f"error:{r.status_code}"
    except Exception as exc:
        checks["supabase"] = _detail(exc)

    # ── Supabase Auth ─────────────────────────────────────────────────────────
    # Same project, different service: PostgREST can be up while GoTrue (auth) is
    # not, and every login/register/refresh goes through GoTrue.  Reported
    # separately so a deploy can tell "database down" from "auth down".
    try:
        url = os.environ.get("SUPABASE_URL", "").rstrip("/")
        key = os.environ.get("SUPABASE_ANON_KEY") or os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "")
        r = _req.get(f"{url}/auth/v1/health", headers={"apikey": key}, timeout=5)
        checks["supabase_auth"] = MSG.HEALTH_CONNECTED if r.status_code < 400 else f"error:{r.status_code}"
    except Exception as exc:
        checks["supabase_auth"] = _detail(exc)

    # ── Redis ─────────────────────────────────────────────────────────────────
    # Normalised first: redis-py rejects anything without redis:// | rediss:// | unix:
    # with a long library ValueError, and a bare host:port (what Railway's Connect tab
    # shows for the public proxy) is the usual cause. Repairing it here means the check
    # reports whether Redis actually answers, not how the string was pasted.
    from app.utils.redis_url import normalize_redis_url
    raw_redis = os.environ.get("REDIS_URL", "")
    redis_url = normalize_redis_url(raw_redis)
    if redis_url:
        try:
            import redis as _redis
            client = _redis.from_url(redis_url, socket_connect_timeout=3)
            client.ping()
            checks["redis"] = MSG.HEALTH_CONNECTED
        except Exception as exc:
            checks["redis"] = _detail(exc, "error")
    elif raw_redis.strip():
        # Set, but nothing usable: say so instead of reporting "not configured".
        checks["redis"] = "error:invalid_url_missing_redis_scheme"
    else:
        checks["redis"] = MSG.HEALTH_NOT_CONFIGURED

    overall = MSG.HEALTH_OK if all(
        v in (MSG.HEALTH_CONNECTED, MSG.HEALTH_NOT_CONFIGURED) for v in checks.values()
    ) else MSG.HEALTH_DEGRADED

    return jsonify({
        "status": overall,
        "api": current_app.config.get("APP_NAME", "Holy Grills"),
        "version": MSG.API_VERSION,
        "checks": checks,
    }), 200
