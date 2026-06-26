"""
Auth middleware. All protected routes use @require_auth.
Role-specific routes use @require_role("admin") etc.

Supabase issues JWTs that are verified using the JWT_SECRET (your Supabase JWT secret).
The decoded payload contains the user's UUID as 'sub' and role in app_metadata.
"""

import jwt
from functools import wraps
from flask import request, g, current_app, abort
from app.db import get_db, SupabaseError


def _decode_token(token: str) -> dict:
    try:
        # 🔍 DEBUG: Print what's being used
        print(f"🔍 JWT_SECRET loaded: {current_app.config['JWT_SECRET'][:20]}...")
        print(f"🔍 JWT_ALGORITHM: {current_app.config.get('JWT_ALGORITHM', 'NOT SET')}")
        
        # 🔍 DEBUG: Decode the header to see what alg is in the token
        import jwt
        header = jwt.get_unverified_header(token)
        print(f"🔍 Token alg: {header.get('alg')}")
        print(f"🔍 Token kid: {header.get('kid')}")
        
        payload = jwt.decode(
            token,
            current_app.config["JWT_SECRET"],
            algorithms=[current_app.config["JWT_ALGORITHM"]],
            options={"verify_aud": False},
        )
        return payload
    except jwt.ExpiredSignatureError:
        abort(401, "Token has expired")
    except jwt.InvalidTokenError as e:
        print(f"🔍 JWT Error: {e}")  # 🔍 Debug
        abort(401, f"Invalid token: {e}")
        
def _get_token_from_header() -> str:
    auth_header = request.headers.get("Authorization", "")
    if not auth_header.startswith("Bearer "):
        abort(401, "Missing or malformed Authorization header")
    return auth_header.split(" ", 1)[1]


def require_auth(f):
    """Verify Supabase JWT and load user profile into g.user and g.user_id."""
    @wraps(f)
    def decorated(*args, **kwargs):
        token = _get_token_from_header()
        payload = _decode_token(token)
        g.user_id = payload.get("sub")
        g.jwt_token = token
        g.jwt_payload = payload

        db = get_db()
        try:
            profile = (
                db.table("profiles")
                .select("id,full_name,role,is_active,phone,date_of_birth,referral_code,referred_by")
                .eq("id", g.user_id)
                .single()
                .execute()
            )
        except SupabaseError as e:
            abort(401, "User profile not found")

        if not profile.get("is_active", True):
            abort(403, "Account is deactivated")

        g.user = profile
        g.user_role = profile.get("role", "student")
        return f(*args, **kwargs)
    return decorated


def require_role(*roles):
    """Require one of the given roles. Must be used after @require_auth."""
    def decorator(f):
        @wraps(f)
        def decorated(*args, **kwargs):
            token = _get_token_from_header()
            payload = _decode_token(token)
            g.user_id = payload.get("sub")
            g.jwt_token = token
            g.jwt_payload = payload

            db = get_db()
            try:
                profile = (
                    db.table("profiles")
                    .select("id,full_name,role,is_active")
                    .eq("id", g.user_id)
                    .single()
                    .execute()
                )
            except SupabaseError:
                abort(401, "User profile not found")

            if not profile.get("is_active", True):
                abort(403, "Account is deactivated")

            if profile.get("role") not in roles:
                abort(403, f"Requires one of roles: {', '.join(roles)}")

            g.user = profile
            g.user_role = profile.get("role")
            return f(*args, **kwargs)
        return decorated
    return decorator


def optional_auth(f):
    """Try to load user from JWT if present, but don't fail if missing (for guest flows)."""
    @wraps(f)
    def decorated(*args, **kwargs):
        auth_header = request.headers.get("Authorization", "")
        g.user_id = None
        g.user = None
        g.user_role = None
        g.jwt_token = None

        if auth_header.startswith("Bearer "):
            token = auth_header.split(" ", 1)[1]
            try:
                payload = _decode_token(token)
                g.user_id = payload.get("sub")
                g.jwt_token = token
                db = get_db()
                try:
                    profile = (
                        db.table("profiles")
                        .select("id,full_name,role,is_active")
                        .eq("id", g.user_id)
                        .single()
                        .execute()
                    )
                    g.user = profile
                    g.user_role = profile.get("role", "student")
                except SupabaseError:
                    g.user_id = None
            except Exception:
                pass

        return f(*args, **kwargs)
    return decorated
                
