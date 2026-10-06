"""
Auth routes — register, login, refresh, profile, logout, addresses.
"""
import os
import re
import json
import requests as _req
from datetime import datetime, timezone
from flask import Blueprint, request, jsonify, g, current_app
from app.middleware.auth import require_auth
from app.middleware.rate_limit import rate_limit
from app.services import auth_service, streak_service
from app.utils.retry import with_retry
from app.db import get_db, get_user_client, SupabaseError
from app.messages import MSG
from app.utils.logger import get_logger
from app.utils.upload_urls import is_trusted_upload_url
from app.utils.validators import validate_uuid

logger = get_logger(__name__)

auth_bp = Blueprint("auth", __name__)
users_bp = Blueprint("users", __name__)


def _json_body():
    """Request JSON as a dict, or None when missing / malformed / not an object."""
    data = request.get_json(force=True, silent=True)
    return data if isinstance(data, dict) else None


def _bad_body():
    return jsonify({"error": MSG.REQUEST_BODY_INVALID}), 400


@with_retry()
def _revoke_supabase_sessions(user_id: str):
    """Revoke all Supabase Auth sessions for ANOTHER user (global scope) with the service role.
    Used by admin.py (deactivate_user). Returns the HTTP response, or None when Supabase is not configured.
    A user's OWN sessions are revoked with _revoke_own_sessions (their JWT)."""
    supabase_url = os.environ.get("SUPABASE_URL", "").rstrip("/")
    srk = os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "")
    if not supabase_url or not srk:
        return None
    return _req.post(
        f"{supabase_url}/auth/v1/admin/users/{user_id}/logout",
        headers={
            "apikey": srk,
            "Authorization": f"Bearer {srk}",
            "Content-Type": "application/json",
        },
        json={"scope": "global"},
        timeout=10,
    )


def _revoke_own_sessions(access_token: str) -> bool:
    """Revoke every refresh token / session of the token's owner (documented
    POST /auth/v1/logout?scope=global with the user's own JWT). Returns True on success."""
    supabase_url = os.environ.get("SUPABASE_URL", "").rstrip("/")
    anon_key = os.environ.get("SUPABASE_ANON_KEY", "")
    if not supabase_url or not anon_key or not access_token:
        logger.error("session revoke skipped: SUPABASE_URL / SUPABASE_ANON_KEY / token missing")
        return False
    try:
        resp = _req.post(
            f"{supabase_url}/auth/v1/logout",
            params={"scope": "global"},
            headers={"apikey": anon_key, "Authorization": f"Bearer {access_token}"},
            timeout=10,
        )
    except _req.RequestException as e:
        logger.error("session revoke request failed: %s", e)
        return False
    if resp.status_code not in (200, 204):
        logger.error("session revoke failed: %s %s", resp.status_code, resp.text[:200])
        return False
    return True


def _revoke_all_sessions(user_id: str, access_token: str):
    """Delete the user's device-token rows and revoke all auth sessions.
    Returns (devices_removed, sessions_revoked)."""
    devices_removed = 0
    try:
        removed = get_user_client().table("device_tokens").eq("user_id", user_id).delete()
        devices_removed = len(removed) if isinstance(removed, list) else 0
    except SupabaseError as e:
        logger.error("device_tokens delete failed for %s: %s", user_id, e)
    return devices_removed, _revoke_own_sessions(access_token)


def _streak_checkin(user_id: str) -> None:
    """Best-effort login-streak check-in. Public routes have no g.campus_id, so the
    user's own profile campus is used (login and refresh now behave the same)."""
    try:
        row = get_db().table("profiles").select("campus_id").eq("id", user_id).single().execute()
        streak_service.process_login_streak(user_id, (row or {}).get("campus_id"))
    except Exception as e:
        logger.warning("streak check-in failed for %s: %s", user_id, e)


def _notify_security(user_id: str, notif_type: str) -> None:
    """In-app + email for account-security events (password_changed, welcome_email)."""
    try:
        from app.services.notification_service import send_notification
        send_notification(user_id=user_id, notif_type=notif_type, template_data={}, channels=["in_app", "email"])
    except Exception as e:
        logger.warning("security notification %s failed for %s: %s", notif_type, user_id, e)


def _lock_auth_account(user_id: str) -> bool:
    """After anonymisation: rename the auth email (removes PII, frees the address) and ban logins."""
    supabase_url = os.environ.get("SUPABASE_URL", "").rstrip("/")
    srk = os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "")
    if not supabase_url or not srk:
        logger.error("auth lock skipped for %s: missing SUPABASE_URL / SERVICE_ROLE_KEY", user_id)
        return False
    try:
        resp = _req.put(
            f"{supabase_url}/auth/v1/admin/users/{user_id}",
            headers={"apikey": srk, "Authorization": f"Bearer {srk}", "Content-Type": "application/json"},
            json={"email": f"deleted-{user_id[:8]}@deleted.holygrills.com.ng", "ban_duration": "876000h"},
            timeout=10,
        )
    except _req.RequestException as e:
        logger.error("auth lock request failed for %s: %s", user_id, e)
        return False
    if resp.status_code not in (200, 204):
        logger.error("auth lock failed for %s: %s %s", user_id, resp.status_code, resp.text[:200])
        return False
    return True


@auth_bp.route("/register", methods=["POST"])
@rate_limit("RATE_LIMIT_REGISTER_REQUESTS", "RATE_LIMIT_REGISTER_WINDOW")
def register():
    """
    Register a new student account.
    ---
    tags: [Auth]
    security: []
    parameters:
      - in: body
        name: body
        required: true
        schema:
          required: [email, password, full_name]
          properties:
            email: {type: string}
            password: {type: string, minLength: 8}
            full_name: {type: string}
            phone: {type: string}
            date_of_birth: {type: string, format: date}
            referred_by_code: {type: string}
            department: {type: string, description: "Department name — use name field from GET /api/departments"}
            academic_level: {type: string, description: "Academic level value from GET /api/academic-levels (e.g. 100L, 200L, PG)"}
            nickname: {type: string}
            campus_id: {type: string, description: "Required when more than one campus is active; optional when only one is"}
    responses:
      201:
        description: Registration successful, returns session tokens
      400:
        description: Validation error
    """
    data = _json_body()
    if data is None:
        return _bad_body()

    for field in ("email", "password", "full_name"):
        if not isinstance(data.get(field), str) or not data[field].strip():
            return jsonify({"error": MSG.AUTH_FIELD_REQUIRED.format(field=field)}), 400
    for field in ("phone", "date_of_birth", "referred_by_code", "department",
                  "academic_level", "nickname", "campus_id"):
        if data.get(field) is not None and not isinstance(data[field], str):
            return jsonify({"error": MSG.AUTH_FIELD_INVALID.format(field=field)}), 400

    if len(data["password"]) < 8:
        return jsonify({"error": MSG.AUTH_PASSWORD_TOO_SHORT}), 400

    db = get_db()
    campus_id = (data.get("campus_id") or "").strip() or None
    if campus_id:
        if not validate_uuid(campus_id):
            return jsonify({"error": MSG.INVALID_CAMPUS_ID}), 400
        campus_id = campus_id.lower()
        chosen = db.table("campuses").select("id").eq("id", campus_id).eq("is_active", True).single().execute()
        if not chosen:
            return jsonify({"error": MSG.CAMPUS_NOT_AVAILABLE}), 400
    else:
        # exactly one active campus: default to it; more than one: the student must choose
        active = db.table("campuses").select("id").eq("is_active", True).order("created_at").limit(2).execute() or []
        if len(active) > 1:
            return jsonify({"error": MSG.CAMPUS_REQUIRED}), 400
        campus_id = active[0]["id"] if active else None

    try:
        result = auth_service.register(
            email=data["email"], password=data["password"], full_name=data["full_name"],
            phone=data.get("phone"), date_of_birth=data.get("date_of_birth"),
            referred_by_code=data.get("referred_by_code"), department=data.get("department"),
            academic_level=data.get("academic_level"), campus_id=campus_id, nickname=data.get("nickname"),
        )
    except ValueError as e:
        err_msg = str(e)
        # Anti-enumeration: existing email returns same 200 shape as a new sign-up
        if err_msg == MSG.REGISTER_EMAIL_AMBIGUOUS:
            return jsonify({"status": "check_email", "message": MSG.REGISTER_EMAIL_AMBIGUOUS}), 200
        return jsonify({"error": err_msg}), 400
    except Exception as e:
        logger.exception("register: unexpected failure: %s", e)
        return jsonify({"error": MSG.AUTH_REGISTRATION_FAILED}), 500

    user_id = ((result.get("user") or {}).get("id")) or result.get("id")
    if user_id:
        _notify_security(user_id, "welcome_email")
    # Always return the same ambiguous shape so the response does not reveal whether the email exists
    return jsonify({"status": "check_email", "message": MSG.REGISTER_EMAIL_AMBIGUOUS}), 200


@auth_bp.route("/login", methods=["POST"])
@rate_limit("RATE_LIMIT_LOGIN_REQUESTS", "RATE_LIMIT_LOGIN_WINDOW")
def login():
    """
    Login with email and password.
    ---
    tags: [Auth]
    security: []
    parameters:
      - in: body
        name: body
        required: true
        schema:
          required: [email, password]
          properties:
            email: {type: string}
            password: {type: string}
    responses:
      200:
        description: Login successful, returns access_token and refresh_token
      401:
        description: Invalid credentials
    """
    data = _json_body()
    if (data is None or not isinstance(data.get("email"), str) or not isinstance(data.get("password"), str)
            or not data["email"].strip() or not data["password"]):
        return jsonify({"error": MSG.AUTH_EMAIL_PASSWORD_REQUIRED}), 400

    try:
        result = auth_service.login(data["email"].strip().lower(), data["password"])
    except ValueError:
        return jsonify({"error": MSG.AUTH_LOGIN_FAILED}), 401
    except SupabaseError as e:
        blob = json.dumps(e.details or {}).lower()
        if "email_not_confirmed" in blob or "email not confirmed" in blob:
            # GoTrue only says this after the password was correct -> no account discovery
            return jsonify({"error": MSG.AUTH_EMAIL_NOT_CONFIRMED}), 403
        if e.status_code in (400, 401):
            return jsonify({"error": MSG.AUTH_LOGIN_FAILED}), 401
        logger.error("login: provider error %s: %s", e.status_code, e)
        return jsonify({"error": MSG.AUTH_LOGIN_FAILED}), 500
    except Exception as e:
        logger.exception("login: unexpected failure: %s", e)
        return jsonify({"error": MSG.AUTH_LOGIN_FAILED}), 500

    user_id = (result.get("user") or {}).get("id")
    if user_id:
        try:
            prof = get_db().table("profiles").select("is_active").eq("id", user_id).single().execute()
        except Exception as e:
            prof = None
            logger.warning("login: is_active lookup failed for %s: %s", user_id, e)
        if prof is not None and prof.get("is_active") is False:
            get_db().auth_sign_out(result.get("access_token"), scope="local")   # drop the session just issued
            return jsonify({"error": MSG.ACCOUNT_DEACTIVATED}), 403
        _streak_checkin(user_id)

    result["message"] = MSG.LOGIN_SUCCESS
    return jsonify(result), 200


@auth_bp.route("/refresh", methods=["POST"])
@rate_limit("RATE_LIMIT_REFRESH_REQUESTS", "RATE_LIMIT_REFRESH_WINDOW")
def refresh():
    """
    Silently rotate the access token when it is within the expiry window.

    Pass the current access_token alongside the refresh_token. The server
    checks how much lifetime remains:

    - If MORE than JWT_REFRESH_WINDOW_MINUTES remain → returns
      {rotated: false, access_token: <same>} — no Supabase call made.
    - If LESS than JWT_REFRESH_WINDOW_MINUTES remain, or the token is
      already expired, or access_token is omitted → calls Supabase and
      returns fresh tokens with {rotated: true}.

    This lets the mobile app call this endpoint on every app-foreground
    without hammering Supabase — rotation only happens when necessary.

    Implementation note: the TTL check decodes the token without signature
    verification (we only need the exp claim). Security is enforced by
    Supabase inside auth_refresh, not by this local decode.
    ---
    tags: [Auth]
    security: []
    parameters:
      - in: body
        name: body
        required: true
        schema:
          required: [refresh_token]
          properties:
            refresh_token:
              type: string
              description: Long-lived refresh token from login/register
            access_token:
              type: string
              description: >
                Current access token (optional). When provided the server
                checks remaining TTL and skips rotation if token still has
                plenty of life left.
    responses:
      200:
        description: >
          rotated=false → same access_token returned (still valid);
          rotated=true  → new access_token + refresh_token issued.
      401:
        description: Invalid or expired refresh_token
      429:
        description: Rate limit exceeded
    """
    import jwt as _jwt

    data = _json_body()
    if data is None or not isinstance(data.get("refresh_token"), str) or not data["refresh_token"]:
        return jsonify({"error": MSG.AUTH_REFRESH_TOKEN_REQUIRED}), 400

    access_token = data.get("access_token")
    window_minutes = current_app.config.get("JWT_REFRESH_WINDOW_MINUTES", 5)
    should_rotate = True

    if access_token:
        try:
            # Decode WITHOUT signature verification — we only need the exp claim
            # to decide whether the token needs rotation. The actual security
            # check is performed by Supabase when we call auth_refresh below.
            # Using the JWT_SECRET here would silently fail for tokens signed by
            # a different Supabase JWT secret, causing rotation on every call.
            payload = _jwt.decode(
                access_token,
                algorithms=[current_app.config.get("JWT_ALGORITHM", "HS256")],
                options={
                    "verify_signature": False,
                    "verify_exp": False,
                    "verify_aud": False,
                },
            )
            exp = payload.get("exp", 0)
            seconds_left = exp - datetime.now(timezone.utc).timestamp()
            should_rotate = seconds_left < (window_minutes * 60)
        except Exception:
            # Malformed token — force rotation so Supabase can reject it
            should_rotate = True

    if not should_rotate:
        return jsonify({"rotated": False, "access_token": access_token}), 200

    try:
        result = auth_service.refresh_token(data["refresh_token"])
        result["rotated"] = True
        result["message"] = MSG.SESSION_REFRESHED
        refreshed_user_id = (result.get("user") or {}).get("id")
        if refreshed_user_id:
            _streak_checkin(refreshed_user_id)
        return jsonify(result), 200
    except ValueError as e:
        return jsonify({"error": str(e)}), 401


@auth_bp.route("/me", methods=["GET"])
@require_auth
def me():
    """
    Get authenticated user's full profile including HP balance, tier, and wallet.
    ---
    tags: [Auth]
    responses:
      200:
        description: User profile data
    """
    try:
        user = auth_service.get_current_user(g.jwt_token)
        return jsonify(user), 200
    except Exception as e:
        logger.exception("me: failed for %s: %s", g.user_id, e)
        return jsonify({"error": MSG.AUTH_ME_FAILED}), 500


@auth_bp.route("/profile/photo", methods=["POST"])
@require_auth
def update_profile_photo():
    """Update user profile photo with Cloudinary URL."""
    data = _json_body() or {}
    photo_url = data.get("photo_url")
    if not isinstance(photo_url, str) or not photo_url.strip():
        return jsonify({"error": MSG.PHOTO_URL_REQUIRED}), 400
    photo_url = photo_url.strip()
    if not is_trusted_upload_url(photo_url, f"profile_photos/{g.user_id}"):
        return jsonify({"error": MSG.UPLOAD_URL_INVALID}), 400

    db = get_user_client()
    db.table("profiles").eq("id", g.user_id).update({
        "photo_url": photo_url,
        "updated_at": datetime.now(timezone.utc).isoformat(),
    })
    return jsonify({"photo_url": photo_url, "message": MSG.PROFILE_PHOTO_UPDATED}), 200


@auth_bp.route("/profile", methods=["PATCH"])
@require_auth
def update_profile():
    """
    Update user profile fields.
    ---
    tags: [Auth]
    parameters:
      - in: body
        name: body
        schema:
          properties:
            full_name: {type: string}
            phone: {type: string}
            date_of_birth: {type: string, format: date}
            push_enabled: {type: boolean}
            email_notifications: {type: boolean}
            department: {type: string, description: "Department name — use name field from GET /api/departments"}
            academic_level: {type: string, description: "Academic level value from GET /api/academic-levels (e.g. 100L, 200L, PG)"}
            faculty: {type: string, description: "Faculty — derived automatically from department mapping; do not set manually"}
    responses:
      200:
        description: Profile updated
    """
    data = _json_body()
    if data is None:
        return _bad_body()
    try:
        result = auth_service.update_profile(g.user_id, data)
        result["message"] = MSG.PROFILE_UPDATED
        return jsonify(result), 200
    except ValueError as e:
        return jsonify({"error": str(e)}), 400
    except SupabaseError as e:
        logger.error("update_profile: %s", e)
        return jsonify({"error": MSG.PROFILE_UPDATE_FAILED}), 400


@auth_bp.route("/logout", methods=["POST"])
@require_auth
def logout():
    """
    Logout and invalidate session.
    ---
    tags: [Auth]
    responses:
      200:
        description: Logged out successfully
    """
    if not auth_service.logout(g.jwt_token):
        return jsonify({"error": MSG.LOGOUT_FAILED}), 502
    return jsonify({"message": MSG.LOGGED_OUT}), 200


@auth_bp.route("/addresses", methods=["GET"])
@require_auth
def list_addresses():
    """
    List all saved delivery addresses for the authenticated user.
    ---
    tags: [Auth]
    responses:
      200:
        description: List of saved addresses
    """
    db = get_user_client()
    rows = db.table("user_addresses").select("*").eq("user_id", g.user_id).order("is_default", ascending=False).execute()
    return jsonify(rows), 200


def _clean_coord(value, lo, hi):
    if value is None or value == "":
        return None
    if isinstance(value, bool):
        raise ValueError("coordinate")
    f = float(value)                       # ValueError / TypeError -> caller returns 400
    if not lo <= f <= hi:
        raise ValueError("coordinate range")
    return f


_ADDR_TEXT = ("label", "line1", "line2", "hostel", "city", "state", "landmark")
_ADDR_DELIVERY_TYPES = ("on_campus", "off_campus")


def _clean_ref(value):
    """A uuid reference (gate_id / location_id), or None when absent/blank.

    Returns the sentinel string "__invalid__" for a malformed id so the caller
    can answer 400 rather than letting the database reject the insert.
    """
    if value is None or value == "":
        return None
    if not isinstance(value, str):
        return "__invalid__"
    v = value.strip().lower()
    if not v:
        return None
    return v if validate_uuid(v) else "__invalid__"


def _validate_address_fields(data: dict):
    """Returns (cleaned_dict, error_message|None) for the address keys present in `data`."""
    out = {}
    for k in _ADDR_TEXT:
        if k in data:
            v = data[k]
            if v is not None and not isinstance(v, str):
                return None, MSG.AUTH_FIELD_INVALID.format(field=k)
            if isinstance(v, str) and len(v) > 200:
                return None, MSG.AUTH_FIELD_INVALID.format(field=k)
            out[k] = v.strip() if isinstance(v, str) else v
    # What was saved, so checkout can replay it. `delivery_type` accepts the
    # legacy alias `type` the address form still sends; `gate_id` /
    # `location_id` accept the `delivery_location_id` alias too (the form sends
    # one field that means "hostel on-campus, gate off-campus").
    raw_type = data.get("delivery_type", data.get("type"))
    if raw_type not in (None, ""):
        if raw_type not in _ADDR_DELIVERY_TYPES:
            return None, MSG.AUTH_FIELD_INVALID.format(field="delivery_type")
        out["delivery_type"] = raw_type
    refs = {
        "gate_id": data.get("gate_id"),
        "location_id": data.get("location_id", data.get("delivery_location_id")),
    }
    for key, raw in refs.items():
        if key not in data and "delivery_location_id" not in data:
            continue
        cleaned = _clean_ref(raw)
        if cleaned == "__invalid__":
            return None, MSG.AUTH_FIELD_INVALID.format(field=key)
        out[key] = cleaned
    try:
        if "latitude" in data:
            out["latitude"] = _clean_coord(data["latitude"], -90, 90)
        if "longitude" in data:
            out["longitude"] = _clean_coord(data["longitude"], -180, 180)
    except (TypeError, ValueError):
        return None, MSG.ADDRESS_COORDINATES_INVALID
    return out, None


@auth_bp.route("/addresses", methods=["POST"])
@require_auth
def add_address():
    """
    Save a new delivery address for the authenticated user.
    ---
    tags: [Auth]
    parameters:
      - in: body
        name: body
        required: true
        schema:
          required: [label, address_line, city]
          properties:
            label: {type: string, example: "Home"}
            address_line: {type: string}
            city: {type: string}
            state: {type: string}
            landmark: {type: string}
            latitude: {type: number}
            longitude: {type: number}
            is_default: {type: boolean}
            delivery_type: {type: string, enum: [on_campus, off_campus], description: "What was saved, so checkout can replay it. Alias: type"}
            gate_id: {type: string, description: "Gate an off-campus delivery is met at"}
            location_id: {type: string, description: "Hostel an on-campus delivery goes to. Alias: delivery_location_id"}
    responses:
      201:
        description: Address saved
    """
    db = get_user_client()
    data = _json_body()
    if data is None:
        return _bad_body()
    if "line1" not in data and "address_line" in data:
        data["line1"] = data["address_line"]
    if not data.get("label") or not data.get("line1") or not data.get("city"):
        return jsonify({"error": MSG.AUTH_ADDRESS_FIELDS_REQUIRED}), 400
    fields, err = _validate_address_fields(data)
    if err:
        return jsonify({"error": err}), 400
    if not fields.get("label") or not fields.get("line1") or not fields.get("city"):
        return jsonify({"error": MSG.AUTH_ADDRESS_FIELDS_REQUIRED}), 400

    # DB trigger hg_enforce_single_default_address un-defaults the others atomically
    row = db.table("user_addresses").insert({
        "user_id": g.user_id,
        "label": fields["label"], "line1": fields["line1"], "line2": fields.get("line2"),
        "hostel": fields.get("hostel"), "city": fields["city"], "state": fields.get("state") or "",
        "landmark": fields.get("landmark"),
        "latitude": fields.get("latitude"), "longitude": fields.get("longitude"),
        "is_default": bool(data.get("is_default", False)),
        "campus_id": getattr(g, "campus_id", None),
        # Replayable delivery selection — see _validate_address_fields.
        "delivery_type": fields.get("delivery_type"),
        "gate_id": fields.get("gate_id"),
        "location_id": fields.get("location_id"),
    })
    res = row[0] if isinstance(row, list) and row else row
    if not res:
        return jsonify({"error": MSG.ADDRESS_SAVE_FAILED}), 500
    res["message"] = MSG.ADDRESS_ADDED
    return jsonify(res), 201


@auth_bp.route("/addresses/<address_id>", methods=["PATCH"])
@require_auth
def update_address(address_id):
    """
    Update a saved delivery address.
    ---
    tags: [Auth]
    parameters:
      - in: path
        name: address_id
        type: string
        required: true
      - in: body
        name: body
        schema:
          properties:
            label: {type: string}
            address_line: {type: string}
            city: {type: string}
            state: {type: string}
            landmark: {type: string}
            latitude: {type: number}
            longitude: {type: number}
            is_default: {type: boolean}
    responses:
      200:
        description: Address updated
      404:
        description: Address not found
    """
    db = get_user_client()
    existing = db.table("user_addresses").select("id").eq("id", address_id).eq("user_id", g.user_id).single().execute()
    if not existing:
        return jsonify({"error": MSG.AUTH_ADDRESS_NOT_FOUND}), 404

    data = _json_body()
    if data is None:
        return _bad_body()
    if "address_line" in data and "line1" not in data:
        data["line1"] = data["address_line"]
    fields, err = _validate_address_fields(data)
    if err:
        return jsonify({"error": err}), 400
    for required in ("label", "line1", "city"):
        if required in fields and not fields[required]:
            return jsonify({"error": MSG.AUTH_ADDRESS_FIELDS_REQUIRED}), 400
    payload = dict(fields)
    if "is_default" in data:
        payload["is_default"] = bool(data["is_default"])
    if not payload:
        return jsonify({"error": MSG.NO_VALID_FIELDS_TO_UPDATE}), 400

    result = db.table("user_addresses").eq("id", address_id).eq("user_id", g.user_id).update(payload)
    res = result[0] if isinstance(result, list) and result else result
    if not res:
        return jsonify({"error": MSG.AUTH_ADDRESS_NOT_FOUND}), 404
    res["message"] = MSG.ADDRESS_UPDATED
    return jsonify(res), 200


@auth_bp.route("/addresses/<address_id>", methods=["DELETE"])
@require_auth
def delete_address(address_id):
    """
    Delete a saved delivery address.
    ---
    tags: [Auth]
    parameters:
      - in: path
        name: address_id
        type: string
        required: true
    responses:
      200:
        description: Address deleted
      404:
        description: Address not found
    """
    db = get_user_client()
    existing = db.table("user_addresses").select("id").eq("id", address_id).eq("user_id", g.user_id).single().execute()
    if not existing:
        return jsonify({"error": MSG.AUTH_ADDRESS_NOT_FOUND}), 404
    db.table("user_addresses").eq("id", address_id).delete()
    return jsonify({"message": MSG.ADDRESS_DELETED}), 200


@auth_bp.route("/change-password", methods=["POST"])
@require_auth
@rate_limit(5, 900)
def change_password():
    """
    Change password for the authenticated user.
    ---
    tags: [Auth]
    parameters:
      - in: body
        name: body
        required: true
        schema:
          required: [current_password, new_password]
          properties:
            current_password: {type: string}
            new_password: {type: string, minLength: 8}
    responses:
      200:
        description: Password changed successfully
      400:
        description: Validation error or wrong current password
    """
    data = _json_body()
    if data is None:
        return _bad_body()
    current_password = data.get("current_password")
    new_password = data.get("new_password")
    if (not isinstance(current_password, str) or not isinstance(new_password, str)
            or not current_password or not new_password):
        return jsonify({"error": MSG.AUTH_CHANGE_PW_REQUIRED}), 400
    if len(new_password) < 8:
        return jsonify({"error": MSG.AUTH_PASSWORD_TOO_SHORT}), 400
    if new_password == current_password:
        return jsonify({"error": MSG.AUTH_NEW_PASSWORD_SAME}), 400

    db = get_user_client()
    profile = db.table("profiles").select("email").eq("id", g.user_id).single().execute()
    if not profile:
        return jsonify({"error": MSG.AUTH_USER_NOT_FOUND}), 404
    try:
        db.auth_sign_in(profile["email"], current_password)
    except Exception:
        return jsonify({"error": MSG.AUTH_CURRENT_PASSWORD_WRONG}), 400
    try:
        db.auth_update_user(g.jwt_token, {"password": new_password})
    except Exception as e:
        # Never log `e` here: this call carries the new password, and a provider
        # exception can echo the request body back into the log file.
        logger.error("change_password: update failed for %s (%s, status %s)",
                     g.user_id, type(e).__name__, getattr(e, "status_code", None))
        return jsonify({"error": MSG.AUTH_PASSWORD_UPDATE_FAILED}), 500

    devices_revoked, sessions_revoked = _revoke_all_sessions(g.user_id, g.jwt_token)
    _notify_security(g.user_id, "password_changed")
    return jsonify({
        "message": MSG.PASSWORD_CHANGED_LOGGED_OUT,
        "devices_revoked": devices_revoked,
        "sessions_revoked": sessions_revoked,
    }), 200


_CLOSED_ORDER_STATUSES = ["delivered", "cancelled", "refunded"]   # mirrors hg_anonymize_user's open-order rule


@auth_bp.route("/account", methods=["DELETE"])
@require_auth
@rate_limit(5, 900)
def delete_account():
    """
    Delete the authenticated user's account (NDPR/GDPR self-deletion).
    Deactivates the account and anonymises PII. Cannot be undone.
    ---
    tags: [Auth]
    parameters:
      - in: body
        name: body
        required: true
        schema:
          required: [password]
          properties:
            password: {type: string, description: "Confirm identity before deletion"}
            reason: {type: string, description: "Optional deletion reason"}
    responses:
      200:
        description: Account deletion initiated
      400:
        description: Wrong password
    """
    data = _json_body()
    if data is None:
        return _bad_body()
    password = data.get("password")
    if not isinstance(password, str) or not password:
        return jsonify({"error": MSG.AUTH_CONFIRM_DELETE_REQUIRED}), 400

    db = get_db()
    profile = db.table("profiles").select("email,full_name").eq("id", g.user_id).single().execute()
    if not profile:
        return jsonify({"error": MSG.AUTH_USER_NOT_FOUND}), 404
    try:
        db.auth_sign_in(profile["email"], password)
    except Exception:
        return jsonify({"error": MSG.AUTH_PASSWORD_INCORRECT}), 400

    # Irreversible: never destroy money or in-flight orders
    wallet = db.table("wallets").select("balance").eq("user_id", g.user_id).single().execute()
    if wallet and float(wallet.get("balance") or 0) > 0:
        return jsonify({"error": MSG.ACCOUNT_DELETE_WALLET_BALANCE}), 400
    active = (db.table("orders").select("id").eq("user_id", g.user_id)
              .not_.in_("status", _CLOSED_ORDER_STATUSES).limit(1).execute())
    if active:
        return jsonify({"error": MSG.ACCOUNT_DELETE_OPEN_ORDERS}), 409

    result = db.rpc("hg_anonymize_user", {"p_user_id": g.user_id})
    if not result or not isinstance(result, dict) or not result.get("success"):
        err_msg = result.get("error", MSG.ACCOUNT_DELETE_FAILED) if isinstance(result, dict) else MSG.ACCOUNT_DELETE_FAILED
        if err_msg == "open_orders":   # the database function refused: an order was placed in the meantime
            return jsonify({"error": MSG.ACCOUNT_DELETE_OPEN_ORDERS}), 409
        return jsonify({"error": err_msg}), 400

    _lock_auth_account(g.user_id)                          # frees the email + blocks login (logged on failure)
    _revoke_all_sessions(g.user_id, g.jwt_token)           # logged on failure

    try:   # email captured BEFORE anonymisation (profile email is scrubbed now)
        from app.services.notification_templates import render_notification_template
        from app.services.notification_service import _dispatch_email_via_onesignal
        from app.services.squad_service import resolve_display_name
        rendered = render_notification_template(
            "account_deleted",
            {"name": resolve_display_name(profile=profile) or "there"},
        )
        if rendered:
            title, body, _inc, _ch = rendered
            _dispatch_email_via_onesignal(profile["email"], profile.get("full_name") or "", title, f"<p>{body}</p>")
    except Exception as e:
        logger.warning("delete_account: confirmation email failed for %s: %s", g.user_id, e)

    resp = {"message": MSG.ACCOUNT_DELETED}
    if result.get("anonymized_at"):
        resp["anonymized_at"] = result["anonymized_at"]
    return jsonify(resp), 200


@auth_bp.route("/verify-email", methods=["POST"])
@rate_limit("RATE_LIMIT_VERIFY_EMAIL_REQUESTS", "RATE_LIMIT_VERIFY_EMAIL_WINDOW")
def verify_email():
    """
    Resend the email verification link to an unconfirmed address.

    Safe to call even if the email is already confirmed — always returns the
    same vague success message to prevent email-enumeration. Rate-limited to
    3 requests per hour per IP to prevent abuse.
    ---
    tags: [Auth]
    security: []
    parameters:
      - in: body
        name: body
        required: true
        schema:
          required: [email]
          properties:
            email:
              type: string
              format: email
              example: student@futa.edu.ng
    responses:
      200:
        description: >
          Verification link sent (or silently skipped if already confirmed).
          Always returns the same message regardless of account status.
        schema:
          properties:
            message: {type: string}
      400:
        description: email field missing
      429:
        description: Rate limit exceeded — max 3 requests per hour
    """
    data = _json_body() or {}
    if not isinstance(data.get("email"), str) or not data["email"].strip():
        return jsonify({"error": MSG.AUTH_VERIFY_EMAIL_MISSING}), 400
    result = auth_service.resend_verification_email(data["email"].strip().lower())
    result["message"] = MSG.VERIFICATION_EMAIL_SENT
    return jsonify(result), 200


@auth_bp.route("/reset-password", methods=["POST"])
@rate_limit("RATE_LIMIT_RESET_PW_REQUESTS", "RATE_LIMIT_RESET_PW_WINDOW")
def reset_password():
    """
    Request password reset email.
    ---
    tags: [Auth]
    security: []
    parameters:
      - in: body
        name: body
        required: true
        schema:
          required: [email]
          properties:
            email: {type: string}
    responses:
      200:
        description: Reset email sent if account exists
    """
    data = _json_body()
    if data is None or not isinstance(data.get("email"), str) or not data["email"].strip():
        return jsonify({"error": MSG.AUTH_EMAIL_REQUIRED}), 400
    result = auth_service.reset_password_request(data["email"].strip().lower())
    result["message"] = MSG.PASSWORD_RESET_SENT
    return jsonify(result), 200


@auth_bp.route("/reset-password/confirm", methods=["POST"])
@rate_limit("RATE_LIMIT_RESET_PW_REQUESTS", "RATE_LIMIT_RESET_PW_WINDOW")
def reset_password_confirm():
    """
    Confirm password reset with access_token and new_password.
    ---
    tags: [Auth]
    security: []
    parameters:
      - in: body
        name: body
        required: true
        schema:
          required: [access_token, new_password]
          properties:
            access_token: {type: string}
            new_password: {type: string, minLength: 8}
    responses:
      200:
        description: Password reset successfully
      400:
        description: Validation error or invalid/expired token
    """
    data = _json_body()
    if data is None:
        return _bad_body()
    access_token = data.get("access_token")
    new_password = data.get("new_password")
    if (not isinstance(access_token, str) or not isinstance(new_password, str)
            or not access_token or not new_password):
        return jsonify({"error": MSG.AUTH_RESET_CONFIRM_REQUIRED}), 400
    if len(new_password) < 8:
        return jsonify({"error": MSG.AUTH_PASSWORD_TOO_SHORT}), 400

    db = get_db()
    try:
        res = db.auth_update_user(access_token, {"password": new_password})
    except SupabaseError as e:
        logger.info("reset_password_confirm rejected: %s", e)
        return jsonify({"error": MSG.AUTH_RESET_FAILED}), 400
    except Exception as e:
        logger.error("reset_password_confirm failed: %s", e)
        return jsonify({"error": MSG.AUTH_RESET_FAILED}), 400

    user = res.get("user") or res
    _revoke_supabase_sessions(access_token)      # a reset must end every other (possibly hostile) session
    if user.get("id"):
        _notify_security(user["id"], "password_changed")
    return jsonify({"message": MSG.PASSWORD_CHANGED, "user": user}), 200


@auth_bp.route("/device-token", methods=["POST"])
@require_auth
@rate_limit("RATE_LIMIT_DEVICE_TOKEN_REQUESTS", "RATE_LIMIT_DEVICE_TOKEN_WINDOW")
def register_device_token():
    """
    Register or update a push-notification device token for the authenticated user.

    Call this immediately after the user grants push-notification permission in
    the app. The token (OneSignal subscription ID or player ID) is stored in the
    device_tokens table so the server can target this device with push alerts.

    The mobile SDK must also call ``OneSignal.login(userId)`` so the subscription
    is linked by external_id — that is what ``send_notification`` uses to fan out
    push messages server-side.
    ---
    tags: [Auth]
    parameters:
      - in: body
        name: body
        required: true
        schema:
          required: [token]
          properties:
            token:
              type: string
              description: OneSignal subscription_id or player_id returned by the SDK
              example: "a1b2c3d4-e5f6-7890-abcd-ef1234567890"
            platform:
              type: string
              enum: [ios, android, web]
              description: Device platform (defaults to "unknown" if omitted)
            device_model:
              type: string
              description: Human-readable device model, e.g. "iPhone 15 Pro"
    responses:
      200:
        description: Token already registered — updated last-seen timestamp
      201:
        description: Token registered for the first time
      400:
        description: token field missing or empty
    """
    db = get_user_client()
    data = _json_body() or {}
    token = data.get("token")
    if not isinstance(token, str) or not token.strip():
        return jsonify({"error": MSG.DEVICE_TOKEN_REQUIRED}), 400
    token = token.strip()
    if len(token) > 512:
        return jsonify({"error": MSG.DEVICE_TOKEN_INVALID}), 400
    platform = data.get("platform") or "unknown"
    if platform not in ("ios", "android", "web", "unknown"):
        return jsonify({"error": MSG.DEVICE_PLATFORM_INVALID}), 400
    device_model = data.get("device_model")
    if device_model is not None and not (isinstance(device_model, str) and len(device_model) <= 100):
        return jsonify({"error": MSG.AUTH_FIELD_INVALID.format(field="device_model")}), 400

    now = datetime.now(timezone.utc).isoformat()
    record = {
        "user_id": g.user_id,
        "token": token,
        "platform": platform,
        "device_model": device_model,
        "updated_at": now,
    }

    # a phone that switches account must stop being linked to the previous account
    try:
        get_db().table("device_tokens").neq("user_id", g.user_id).eq("token", token).delete()
    except SupabaseError as e:
        logger.warning("device-token reassign cleanup failed: %s", e)

    existing = (
        db.table("device_tokens")
        .select("id")
        .eq("user_id", g.user_id)
        .eq("token", token)
        .single()
        .execute()
    )
    if existing:
        db.table("device_tokens").eq("id", existing["id"]).update(record)
        return jsonify({"message": MSG.DEVICE_TOKEN_UPDATED, "token": token}), 200
    record["created_at"] = now
    try:
        db.table("device_tokens").insert(record)
    except SupabaseError as e:
        if e.status_code == 409:   # concurrent first registration: the other request won the UNIQUE(user_id, token) race
            return jsonify({"message": MSG.DEVICE_TOKEN_UPDATED, "token": token}), 200
        raise
    return jsonify({"message": MSG.DEVICE_TOKEN_REGISTERED, "token": token}), 201


@auth_bp.route("/streak", methods=["GET"])
@require_auth
def get_login_streak():
    """
    Get the authenticated user's current login streak.
    ---
    tags: [Auth]
    security:
      - Bearer: []
    responses:
      200:
        description: Current streak info
        schema:
          properties:
            streak_count: {type: integer}
            last_login_date: {type: string, format: date}
            last_updated: {type: string, format: date-time}
    """
    from app.services.streak_service import get_streak
    return jsonify(get_streak(g.user_id)), 200


@auth_bp.route("/logout-all-devices", methods=["POST"])
@require_auth
def logout_all_devices():
    """
    Revoke all sessions and device tokens for the authenticated user.
    ---
    tags: [Auth]
    security:
      - Bearer: []
    responses:
      200:
        description: Signed out from all devices
        schema:
          properties:
            message: {type: string}
            devices_revoked: {type: integer}
      401:
        description: Missing or invalid token
    """
    devices_revoked, sessions_revoked = _revoke_all_sessions(g.user_id, g.jwt_token)
    if not sessions_revoked:
        return jsonify({"error": MSG.LOGOUT_ALL_FAILED, "devices_revoked": devices_revoked}), 502
    return jsonify({"message": MSG.LOGOUT_ALL_DEVICES_OK, "devices_revoked": devices_revoked}), 200


@users_bp.route("/search", methods=["GET"])
@auth_bp.route("/users/search", methods=["GET"])
@require_auth
@rate_limit(30, 60)
def search_users():
    """
    Search users on the requesting user's campus by name, nickname, or email.
    ---
    tags: [Auth]
    parameters:
      - in: query
        name: q
        type: string
        required: true
        description: Search term (e.g. "chidi" or "chidi@futa.edu.ng")
    responses:
      200:
        description: Search results
      400:
        description: Search term missing
    """
    q_raw = (request.args.get("q") or "").strip()
    if not q_raw:
        return jsonify({"results": []}), 200

    # profiles RLS lets a student read ONLY their own row, so the user-scoped client always returned [].
    # Service client + explicit campus / role / is_active filters below ARE the security boundary.
    db = get_db()
    campus_id = getattr(g, "campus_id", None)
    my_user_id = g.user_id
    if not campus_id and getattr(g, "user_role", None) != "super_admin":
        return jsonify({"results": []}), 200      # fail closed: never search without a campus boundary

    # strip every character that is special inside a PostgREST or=() filter (incl. , . : ) and cap length
    q_clean = re.sub(r"[%*(),.:\\\"']", "", q_raw).strip()[:50]
    if not q_clean:
        return jsonify({"results": []}), 200

    q_pattern = f"*{q_clean}*"
    or_conds = [f"full_name.ilike.{q_pattern}", f"nickname.ilike.{q_pattern}"]
    if "@" in q_raw:
        or_conds.append(f"email.ilike.{q_pattern}")
    or_filter = ",".join(or_conds)

    def _shape(r):
        return {"id": r.get("id"), "full_name": r.get("full_name") or r.get("nickname") or "Student",
                "nickname": r.get("nickname"), "email": r.get("email")}

    results = []
    try:
        query = (db.table("profiles").select("id,full_name,nickname,email,campus_id")
                 .neq("id", my_user_id).eq("role", "student").eq("is_active", True))
        if campus_id:
            query = query.eq("campus_id", campus_id)
        rows = query.or_(or_filter).limit(20).execute() or []
        results = [_shape(r) for r in rows]
    except Exception as e:
        logger.warning("search_users: filtered query failed, using fallback: %s", e)
        try:
            base_q = (db.table("profiles").select("id,full_name,nickname,email,campus_id")
                      .neq("id", my_user_id).eq("role", "student").eq("is_active", True))
            if campus_id:
                base_q = base_q.eq("campus_id", campus_id)
            q_lower = q_clean.lower()
            for r in (base_q.limit(100).execute() or []):
                hay = ((r.get("full_name") or "") + " " + (r.get("nickname") or "")).lower()
                if q_lower in hay or ("@" in q_raw and q_lower in (r.get("email") or "").lower()):
                    results.append(_shape(r))
                    if len(results) >= 20:
                        break
        except Exception as e2:
            logger.error("search_users: fallback failed: %s", e2)
            return jsonify({"error": MSG.SEARCH_FAILED}), 500
    return jsonify({"results": results}), 200
