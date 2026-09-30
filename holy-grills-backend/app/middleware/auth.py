"""
Auth middleware. All protected routes use @require_auth.
Role-specific routes use @require_role("admin") etc.

Tokens are verified by calling Supabase Auth (auth_get_user). The user's role and
campus are read from the profiles table.
"""

import requests
from functools import wraps
from flask import request, g, abort
from app.db import get_db, SupabaseError
from app.constants import ADMIN_ROLES
from app.messages import MSG
from app.utils.logger import get_logger

logger = get_logger(__name__)


def _abort_on_auth_failure(exc, message):
    """401 only when Supabase rejected the credentials/profile (a real 4xx, not 429);
    503 when Supabase is unreachable or erroring (429/5xx/network failure) so an
    infrastructure blip doesn't silently log the user out."""
    status = getattr(exc, "status_code", None)
    if isinstance(exc, SupabaseError) and status is not None and 400 <= status < 500 and status != 429:
        abort(401, message)
    logger.error("Supabase unavailable during auth: %s", exc)
    abort(503, MSG.SERVICE_UNAVAILABLE)


def resolve_scoped_campus_id(requested_campus_id=None):
    """
    For super_admin: requested value (or None = all campuses).
    For everyone else: always their assigned campus (g.campus_id) — requested value is ignored.
    """
    if getattr(g, "user_role", None) == "super_admin":
        return requested_campus_id
    return getattr(g, "campus_id", None)


def assert_owns_campus(record_campus_id):
    """
    Raise 403 if a non-super_admin attempts to access/mutate a record belonging to a different campus.
    """
    if getattr(g, "user_role", None) == "super_admin":
        return
    user_campus_id = getattr(g, "campus_id", None)
    if record_campus_id and record_campus_id != user_campus_id:
        abort(403, description=MSG.RESOURCE_ACCESS_DENIED)


def fetch_or_403(db, table, record_id, select="*", not_found_msg=None):
    """Return (record, None) or (None, error_response). An unknown id and another
    campus's id both give 404 (no existence leak — relies on RLS to filter rows the
    caller can't see); a database failure gives 503 instead of a false "not found"."""
    from flask import jsonify
    from app.utils.validators import validate_uuid

    not_found = (jsonify({"error": not_found_msg or MSG.RESOURCE_NOT_FOUND}), 404)
    if not validate_uuid(str(record_id)):
        return None, not_found
    try:
        record = db.table(table).select(select).eq("id", record_id).single().execute()
    except (SupabaseError, requests.RequestException) as e:
        from app.utils.admin_helpers import db_error_response
        return None, db_error_response(e, f"fetch {table}")
    return (record, None) if record else (None, not_found)


def update_or_403(db, table, record_id, patch):
    """Update one row by id. Returns (rows, None) or (None, error_response)."""
    from flask import jsonify
    try:
        result = db.table(table).eq("id", record_id).update(patch).execute()
    except (SupabaseError, requests.RequestException) as e:
        from app.utils.admin_helpers import db_error_response
        return None, db_error_response(e, f"update {table}")
    if not result or (isinstance(result, list) and len(result) == 0):
        return None, (jsonify({"error": MSG.UPDATE_NOT_PERMITTED}), 403)
    return result, None


def _resolve_default_campus(db, user_role: str = None):
    """
    Shared helper — call from require_auth / require_role / optional_auth
    wherever g.campus_id needs a fallback. Never assigns a default to super_admin.
    Prioritizes designated default campus (is_default=True) before falling back to first active campus.
    """
    if user_role == "super_admin":
        return None
    default = (
        db.table("campuses")
        .select("id")
        .eq("is_active", True)
        .eq("is_default", True)
        .order("created_at")
        .limit(1)
        .execute()
    )
    if default and isinstance(default, list) and len(default) > 0:
        return default[0]["id"]
    fallback = db.table("campuses").select("id").eq("is_active", True).order("created_at").limit(1).execute()
    return fallback[0]["id"] if (fallback and isinstance(fallback, list) and len(fallback) > 0) else None


def _get_token_from_header() -> str:
    auth_header = request.headers.get("Authorization", "")
    if not auth_header.startswith("Bearer "):
        abort(401, MSG.SESSION_MALFORMED)
    parts = auth_header.split(" ", 1)
    if len(parts) < 2 or not parts[1].strip():
        abort(401, MSG.SESSION_MALFORMED)
    return parts[1].strip()


def require_auth(f):
    """Decorator to require Supabase JWT authentication.
    Sets g.user, g.user_id, g.user_role, g.jwt_token, g.jwt_payload, g.campus_id."""
    @wraps(f)
    def decorated(*args, **kwargs):
        if request.method == "OPTIONS":
            return "", 200
        token = _get_token_from_header()
        db = get_db()

        try:
            auth_user = db.auth_get_user(token)

            g.user_id = auth_user["id"]
            g.jwt_token = token
            g.jwt_payload = auth_user

        except (SupabaseError, requests.RequestException) as e:
            _abort_on_auth_failure(e, MSG.SESSION_INVALID)

        try:
            profile = (
                db.table("profiles")
                .select(
                    "id,full_name,role,is_active,"
                    "phone,date_of_birth,referral_code,referred_by,"
                    "campus_id"
                )
                .eq("id", g.user_id)
                .single()
                .execute()
            )
        except (SupabaseError, requests.RequestException) as e:
            _abort_on_auth_failure(e, MSG.PROFILE_NOT_FOUND)

        if not profile:
            abort(401, MSG.PROFILE_NOT_FOUND)

        if not profile.get("is_active", True):
            abort(403, MSG.ACCOUNT_DEACTIVATED)

        g.user = profile
        g.user_role = profile.get("role", "student")
        g.campus_id = profile.get("campus_id")
        if not g.campus_id:
            g.campus_id = _resolve_default_campus(db, g.user_role)

        return f(*args, **kwargs)

    return decorated


def require_role(*roles):
    """Require one of the given roles. Verifies token via Supabase API."""
    def decorator(f):
        @wraps(f)
        def decorated(*args, **kwargs):
            if request.method == "OPTIONS":
                return "", 200
            token = _get_token_from_header()
            db = get_db()

            try:
                auth_user = db.auth_get_user(token)
                g.user_id = auth_user["id"]
                g.jwt_token = token
                g.jwt_payload = auth_user
            except (SupabaseError, requests.RequestException) as e:
                _abort_on_auth_failure(e, MSG.SESSION_INVALID)

            try:
                profile = (
                    db.table("profiles")
                    .select(
                        "id,full_name,role,is_active,"
                        "phone,date_of_birth,referral_code,referred_by,"
                        "campus_id"
                    )
                    .eq("id", g.user_id)
                    .single()
                    .execute()
                )
            except (SupabaseError, requests.RequestException) as e:
                _abort_on_auth_failure(e, MSG.PROFILE_NOT_FOUND)

            if not profile:
                abort(401, MSG.PROFILE_NOT_FOUND)

            if not profile.get("is_active", True):
                abort(403, MSG.ACCOUNT_DEACTIVATED)

            allowed_roles = set()
            for r in roles:
                if r == "admin":
                    allowed_roles.update(ADMIN_ROLES)
                else:
                    allowed_roles.add(r)

            if profile.get("role") not in allowed_roles:
                abort(403, MSG.ROLE_NOT_PERMITTED)

            g.user = profile
            g.user_role = profile.get("role")
            g.campus_id = profile.get("campus_id")
            # Campus-scoped staff must have a campus — silently defaulting them would show an
            # empty dashboard (RLS already scopes them to nothing) instead of a clear error.
            if not g.campus_id and g.user_role in ("admin", "kitchen", "rider"):
                abort(403, MSG.ACCOUNT_NO_CAMPUS)
            if not g.campus_id:
                g.campus_id = _resolve_default_campus(db, g.user_role)
            return f(*args, **kwargs)
        return decorated
    return decorator


def optional_auth(f):
    """Try to load user from JWT if present. Guests (no Authorization header) pass
    through as guests; a supplied but invalid/expired token is 401; a deactivated
    account is 403."""
    @wraps(f)
    def decorated(*args, **kwargs):
        if request.method == "OPTIONS":
            return "", 200
        auth_header = request.headers.get("Authorization")
        g.user_id = None
        g.user = None
        g.user_role = None
        g.jwt_token = None
        g.jwt_payload = None

        if auth_header is not None:
            # An Authorization header is supplied. We must parse and validate it.
            if not auth_header.startswith("Bearer "):
                abort(401, MSG.SESSION_MALFORMED)

            parts = auth_header.split(" ", 1)
            if len(parts) < 2 or not parts[1].strip():
                abort(401, MSG.SESSION_MALFORMED)

            token = parts[1].strip()
            db = get_db()
            try:
                auth_user = db.auth_get_user(token)
            except (SupabaseError, requests.RequestException) as e:
                # Any invalid or expired token must produce a 401 (or 503 if Supabase itself
                # is down) instead of silently becoming guest.
                _abort_on_auth_failure(e, MSG.SESSION_INVALID)

            g.user_id = auth_user["id"]
            g.jwt_token = token
            g.jwt_payload = auth_user

            try:
                profile = (
                    db.table("profiles")
                    .select(
                        "id,full_name,role,is_active,"
                        "phone,date_of_birth,referral_code,referred_by,"
                        "campus_id"
                    )
                    .eq("id", g.user_id)
                    .single()
                    .execute()
                )
            except (SupabaseError, requests.RequestException) as e:
                _abort_on_auth_failure(e, MSG.PROFILE_NOT_FOUND)

            if not profile:
                abort(401, MSG.PROFILE_NOT_FOUND)

            if not profile.get("is_active", True):
                abort(403, MSG.ACCOUNT_DEACTIVATED)

            g.user = profile
            g.user_role = profile.get("role", "student")
            g.campus_id = profile.get("campus_id")
            if not g.campus_id:
                g.campus_id = _resolve_default_campus(db, g.user_role)

        return f(*args, **kwargs)
    return decorated
