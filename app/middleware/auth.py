"""
Auth middleware. All protected routes use @require_auth.
Role-specific routes use @require_role("admin") etc.

Supabase issues JWTs that are verified using the JWT_SECRET (your Supabase JWT secret).
The decoded payload contains the user's UUID as 'sub' and role in app_metadata.
"""

from functools import wraps
from flask import request, g, abort
from app.db import get_db, SupabaseError
from app.constants import ADMIN_ROLES
from app.messages import MSG


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
        abort(403, description=MSG.ORDER_ACCESS_DENIED)


def fetch_or_403(db, table, record_id, select="*", not_found_msg=None):
    record = None
    try:
        record = db.table(table).select(select).eq("id", record_id).single().execute()
    except Exception:
        pass
    if record:
        return record, None

    from flask import jsonify
    try:
        from app.db import get_db
        exists = get_db().table(table).select("id").eq("id", record_id).single().execute()
        if exists:
            return None, (jsonify({"error": "You don't have permission to access this resource"}), 403)
    except Exception:
        pass

    return None, (jsonify({"error": not_found_msg or "Not found"}), 404)


def update_or_403(db, table, record_id, patch):
    result = db.table(table).eq("id", record_id).update(patch).execute()
    from flask import jsonify
    if not result or (isinstance(result, list) and len(result) == 0):
        return None, (jsonify({"error": "Update not permitted or record not found"}), 403)
    return result, None

def _resolve_default_campus(db, user_role: str = None):
    """
    Shared helper — call from require_auth / require_role / optional_auth
    wherever g.campus_id needs a fallback. Never assigns a default to super_admin.
    """
    if user_role == "super_admin":
        return None
    default = db.table("campuses").select("id").eq("is_active", True).order("created_at").limit(1).execute()
    return default[0]["id"] if (default and isinstance(default, list) and len(default) > 0) else None

def _get_token_from_header() -> str:
    auth_header = request.headers.get("Authorization", "")
    if not auth_header.startswith("Bearer "):
        abort(401, "Missing or malformed Authorization header")
    parts = auth_header.split(" ", 1)
    if len(parts) < 2 or not parts[1].strip():
        abort(401, "Missing or malformed Authorization header")
    return parts[1].strip()

def require_auth(f):
    """Decorator to require Supabase JWT authentication. Sets g.user, g.user_id, g.jwt_token, g.campus_id."""
    @wraps(f)
    def decorated(*args, **kwargs):
        token = _get_token_from_header()
        db = get_db()

        try:
            auth_user = db.auth_get_user(token)

            g.user_id = auth_user["id"]
            g.jwt_token = token
            g.jwt_payload = auth_user

        except SupabaseError:
            abort(401, "Invalid token")

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
        except SupabaseError:
            abort(401, "User profile not found")

        if not profile.get("is_active", True):
            abort(403, "Account is deactivated")

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
            token = _get_token_from_header()
            db = get_db()

            try:
                auth_user = db.auth_get_user(token)
                g.user_id = auth_user["id"]
                g.jwt_token = token
                g.jwt_payload = auth_user
            except SupabaseError:
                abort(401, "Invalid token")

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
            except SupabaseError:
                abort(401, "User profile not found")

            if not profile:
                abort(401, "User profile not found")

            if not profile.get("is_active", True):
                abort(403, "Account is deactivated")

            allowed_roles = set()
            for r in roles:
                if r == "admin":
                    allowed_roles.update(ADMIN_ROLES)
                else:
                    allowed_roles.add(r)

            if profile.get("role") not in allowed_roles:
                abort(403, f"Requires one of roles: {', '.join(roles)}")

            g.user = profile
            g.user_role = profile.get("role")
            g.campus_id = profile.get("campus_id")
            if not g.campus_id:
                g.campus_id = _resolve_default_campus(db, g.user_role)
            return f(*args, **kwargs)
        return decorated
    return decorator


def optional_auth(f):
    """Try to load user from JWT if present, but don't fail if missing (for guest flows)."""
    @wraps(f)
    def decorated(*args, **kwargs):
        auth_header = request.headers.get("Authorization")
        g.user_id = None
        g.user = None
        g.user_role = None
        g.jwt_token = None
        g.jwt_payload = None

        if auth_header is not None:
            # An Authorization header is supplied. We must parse and validate it.
            if not auth_header.startswith("Bearer "):
                abort(401, "Malformed Bearer header")

            parts = auth_header.split(" ", 1)
            if len(parts) < 2 or not parts[1].strip():
                abort(401, "Malformed Bearer header")

            token = parts[1].strip()
            db = get_db()
            try:
                auth_user = db.auth_get_user(token)
            except Exception:
                # Any invalid or expired token must produce a 401 error instead of silently becoming guest
                abort(401, "Invalid or expired token")

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
            except SupabaseError:
                abort(401, "User profile not found")

            if not profile:
                abort(401, "User profile not found")

            if not profile.get("is_active", True):
                abort(403, "Account is deactivated")

            g.user = profile
            g.user_role = profile.get("role", "student")
            g.campus_id = profile.get("campus_id")
            if not g.campus_id:
                g.campus_id = _resolve_default_campus(db, g.user_role)

        return f(*args, **kwargs)
    return decorated
