"""Auth routes — register, login, refresh, profile, logout, addresses."""

import os
import requests as _req
from flask import Blueprint, request, jsonify, g
from app.middleware.auth import require_auth, optional_auth
from app.middleware.rate_limit import rate_limit
from app.services import auth_service
from app.utils.retry import with_retry
from app.db import get_db, SupabaseError
from app.messages import MSG

auth_bp = Blueprint("auth", __name__)


@with_retry()
def _revoke_supabase_sessions(user_id: str) -> None:
    """Revoke all Supabase Auth sessions for a user (global scope)."""
    supabase_url = os.environ.get("SUPABASE_URL", "").rstrip("/")
    srk = os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "")
    if not supabase_url or not srk:
        return
    _req.post(
        f"{supabase_url}/auth/v1/admin/users/{user_id}/logout",
        headers={
            "apikey": srk,
            "Authorization": f"Bearer {srk}",
            "Content-Type": "application/json",
        },
        json={"scope": "global"},
        timeout=10,
    )


def _revoke_all_sessions(user_id: str) -> int:
    """Delete all device tokens and revoke Supabase sessions for a user. Returns devices_revoked count."""
    db = get_db()
    revoked = (
        db.table("device_tokens")
        .eq("user_id", user_id)
        .delete()
    )
    devices_revoked = len(revoked) if isinstance(revoked, list) else 0
    _revoke_supabase_sessions(user_id)
    return devices_revoked


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
    responses:
      201:
        description: Registration successful, returns session tokens
      400:
        description: Validation error
    """
    data = request.get_json(force=True)
    required = ["email", "password", "full_name"]
    for field in required:
        if not data.get(field):
            return jsonify({"error": MSG.AUTH_FIELD_REQUIRED.format(field=field)}), 400

    if len(data["password"]) < 8:
        return jsonify({"error": MSG.AUTH_PASSWORD_TOO_SHORT}), 400

    try:
        result = auth_service.register(
            email=data["email"],
            password=data["password"],
            full_name=data["full_name"],
            phone=data.get("phone"),
            date_of_birth=data.get("date_of_birth"),
            referred_by_code=data.get("referred_by_code"),
            department=data.get("department"),
            academic_level=data.get("academic_level"),
        )
    except ValueError as e:
        return jsonify({"error": str(e)}), 400
    except Exception as e:
        return jsonify({"error": MSG.AUTH_REGISTRATION_FAILED, "detail": str(e)}), 500

    return jsonify(result), 201


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
    data = request.get_json(force=True)
    if not data.get("email") or not data.get("password"):
        return jsonify({"error": MSG.AUTH_EMAIL_PASSWORD_REQUIRED}), 400

    try:
        result = auth_service.login(data["email"], data["password"])
    except ValueError:
        return jsonify({"error": MSG.AUTH_LOGIN_FAILED}), 401
    except SupabaseError as e:
        if e.status_code in (400, 401):
            return jsonify({"error": MSG.AUTH_LOGIN_FAILED}), 401
        return jsonify({"error": MSG.AUTH_LOGIN_FAILED, "detail": str(e)}), 500
    except Exception as e:
        return jsonify({"error": MSG.AUTH_LOGIN_FAILED, "detail": str(e)}), 500

    # Process login streak asynchronously so it doesn't slow login response
    user_id = (result.get("user") or {}).get("id")
    if user_id:
        import threading as _t
        from app.services.streak_service import process_login_streak as _pls
        _t.Thread(target=lambda: _pls(user_id), daemon=True).start()

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
    from flask import current_app
    import jwt as _jwt
    from datetime import datetime, timezone

    data = request.get_json(force=True)
    if not data.get("refresh_token"):
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
        return jsonify({"error": str(e)}), 500


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
    data = request.get_json(force=True)
    try:
        result = auth_service.update_profile(g.user_id, data)
        return jsonify(result), 200
    except ValueError as e:
        return jsonify({"error": str(e)}), 400


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
    auth_service.logout(g.jwt_token)
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
    db = get_db()
    rows = db.table("user_addresses").select("*").eq("user_id", g.user_id).order("is_default", ascending=False).execute()
    return jsonify(rows), 200


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
    responses:
      201:
        description: Address saved
    """
    db = get_db()
    data = request.get_json(force=True)
    if not data.get("label") or not (data.get("line1") or data.get("address_line")) or not data.get("city"):
        return jsonify({"error": MSG.AUTH_ADDRESS_FIELDS_REQUIRED}), 400

    if data.get("is_default"):
        db.table("user_addresses").eq("user_id", g.user_id).update({"is_default": False})

    row = db.table("user_addresses").insert({
        "user_id": g.user_id,
        "label": data["label"],
        "line1": data.get("line1") or data.get("address_line"),
        "line2": data.get("line2"),
        "hostel": data.get("hostel"),
        "city": data["city"],
        "state": data.get("state") or "",
        "landmark": data.get("landmark"),
        "latitude": data.get("latitude"),
        "longitude": data.get("longitude"),
        "is_default": bool(data.get("is_default", False)),
    })
    return jsonify(row[0] if isinstance(row, list) else row), 201


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
    db = get_db()
    existing = db.table("user_addresses").select("id").eq("id", address_id).eq("user_id", g.user_id).single().execute()
    if not existing:
        return jsonify({"error": MSG.AUTH_ADDRESS_NOT_FOUND}), 404

    data = request.get_json(force=True)
    if data.get("is_default"):
        db.table("user_addresses").eq("user_id", g.user_id).update({"is_default": False})

    allowed = ["label", "line1", "line2", "hostel", "city", "state", "landmark", "latitude", "longitude", "is_default"]
    payload = {k: v for k, v in data.items() if k in allowed}
    if "address_line" in data and "line1" not in payload:
        payload["line1"] = data["address_line"]
    result = db.table("user_addresses").eq("id", address_id).update(payload)
    return jsonify(result[0] if isinstance(result, list) else result), 200


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
    db = get_db()
    existing = db.table("user_addresses").select("id").eq("id", address_id).eq("user_id", g.user_id).single().execute()
    if not existing:
        return jsonify({"error": MSG.AUTH_ADDRESS_NOT_FOUND}), 404
    db.table("user_addresses").eq("id", address_id).delete()
    return jsonify({"message": MSG.ADDRESS_DELETED}), 200


@auth_bp.route("/change-password", methods=["POST"])
@require_auth
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
    data = request.get_json(force=True)
    current_password = data.get("current_password")
    new_password = data.get("new_password")

    if not current_password or not new_password:
        return jsonify({"error": MSG.AUTH_CHANGE_PW_REQUIRED}), 400
    if len(new_password) < 8:
        return jsonify({"error": MSG.AUTH_PASSWORD_TOO_SHORT}), 400

    db = get_db()
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
        return jsonify({"error": MSG.AUTH_PASSWORD_UPDATE_FAILED, "detail": str(e)}), 500

    devices_revoked = _revoke_all_sessions(g.user_id)

    return jsonify({
        "message": MSG.PASSWORD_CHANGED_LOGGED_OUT,
        "devices_revoked": devices_revoked,
    }), 200


@auth_bp.route("/account", methods=["DELETE"])
@require_auth
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
    data = request.get_json(force=True) or {}
    password = data.get("password")
    if not password:
        return jsonify({"error": MSG.AUTH_CONFIRM_DELETE_REQUIRED}), 400

    db = get_db()
    profile = db.table("profiles").select("email,full_name").eq("id", g.user_id).single().execute()
    if not profile:
        return jsonify({"error": MSG.AUTH_USER_NOT_FOUND}), 404

    try:
        db.auth_sign_in(profile["email"], password)
    except Exception:
        return jsonify({"error": MSG.AUTH_PASSWORD_INCORRECT}), 400

    from datetime import datetime, timezone
    now = datetime.now(timezone.utc).isoformat()
    db.table("profiles").eq("id", g.user_id).update({
        "is_active": False,
        "deactivated_at": now,
        "deactivation_reason": data.get("reason", "user_requested"),
        "full_name": "[Deleted User]",
        "phone": None,
        "date_of_birth": None,
    })

    try:
        db.auth_sign_out(g.jwt_token)
    except Exception:
        pass

    return jsonify({"message": MSG.ACCOUNT_DELETED}), 200


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
    data = request.get_json(force=True) or {}
    if not data.get("email"):
        return jsonify({"error": MSG.AUTH_VERIFY_EMAIL_MISSING}), 400
    result = auth_service.resend_verification_email(data["email"])
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
    data = request.get_json(force=True)
    if not data.get("email"):
        return jsonify({"error": MSG.AUTH_EMAIL_REQUIRED}), 400
    result = auth_service.reset_password_request(data["email"])
    return jsonify(result), 200


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
    from datetime import datetime, timezone
    db = get_db()
    data = request.get_json(force=True) or {}
    token = (data.get("token") or "").strip()
    if not token:
        return jsonify({"error": MSG.DEVICE_TOKEN_REQUIRED}), 400

    now = datetime.now(timezone.utc).isoformat()
    record = {
        "user_id": g.user_id,
        "token": token,
        "platform": data.get("platform", "unknown"),
        "device_model": data.get("device_model"),
        "updated_at": now,
    }

    try:
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
        else:
            record["created_at"] = now
            db.table("device_tokens").insert(record)
            return jsonify({"message": MSG.DEVICE_TOKEN_REGISTERED, "token": token}), 201
    except Exception as exc:
        err = str(exc)
        if "does not exist" in err or "schema cache" in err or "relation" in err:
            return jsonify({
                "message": MSG.DEVICE_TOKEN_REGISTERED,
                "token": token,
                "note": "push notifications not yet provisioned",
            }), 201
        raise


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
    devices_revoked = _revoke_all_sessions(g.user_id)

    return jsonify({
        "message": MSG.LOGOUT_ALL_DEVICES_OK,
        "devices_revoked": devices_revoked,
    }), 200
