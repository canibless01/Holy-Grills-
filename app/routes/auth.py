"""Auth routes — register, login, refresh, profile, logout, addresses."""

from flask import Blueprint, request, jsonify, g
from app.middleware.auth import require_auth, optional_auth
from app.middleware.rate_limit import rate_limit
from app.services import auth_service
from app.db import get_db

auth_bp = Blueprint("auth", __name__)


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
            return jsonify({"error": f"'{field}' is required"}), 400

    if len(data["password"]) < 8:
        return jsonify({"error": "Password must be at least 8 characters"}), 400

    try:
        result = auth_service.register(
            email=data["email"],
            password=data["password"],
            full_name=data["full_name"],
            phone=data.get("phone"),
            date_of_birth=data.get("date_of_birth"),
            referred_by_code=data.get("referred_by_code"),
        )
        return jsonify(result), 201
    except ValueError as e:
        return jsonify({"error": str(e)}), 400
    except Exception as e:
        return jsonify({"error": "Registration failed", "detail": str(e)}), 500


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
        return jsonify({"error": "Email and password are required"}), 400

    try:
        result = auth_service.login(data["email"], data["password"])
        return jsonify(result), 200
    except ValueError as e:
        return jsonify({"error": str(e)}), 401
    except Exception as e:
        return jsonify({"error": "Login failed", "detail": str(e)}), 500


@auth_bp.route("/refresh", methods=["POST"])
def refresh():
    """
    Refresh access token using refresh token.
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
            refresh_token: {type: string}
    responses:
      200:
        description: New access_token returned
    """
    data = request.get_json(force=True)
    if not data.get("refresh_token"):
        return jsonify({"error": "refresh_token is required"}), 400
    try:
        result = auth_service.refresh_token(data["refresh_token"])
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
    return jsonify({"message": "Logged out successfully"}), 200


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
        return jsonify({"error": "label, line1 (or address_line), and city are required"}), 400

    if data.get("is_default"):
        db.table("user_addresses").eq("user_id", g.user_id).update({"is_default": False})

    row = db.table("user_addresses").insert({
        "user_id": g.user_id,
        "label": data["label"],
        "line1": data.get("line1") or data.get("address_line"),
        "line2": data.get("line2"),
        "hostel": data.get("hostel"),
        "city": data["city"],
        "state": data.get("state"),
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
        return jsonify({"error": "Address not found"}), 404

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
        return jsonify({"error": "Address not found"}), 404
    db.table("user_addresses").eq("id", address_id).delete()
    return jsonify({"message": "Address deleted"}), 200


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
        return jsonify({"error": "current_password and new_password are required"}), 400
    if len(new_password) < 8:
        return jsonify({"error": "New password must be at least 8 characters"}), 400

    db = get_db()
    profile = db.table("profiles").select("email").eq("id", g.user_id).single().execute()
    if not profile:
        return jsonify({"error": "User not found"}), 404

    try:
        db.auth_sign_in(profile["email"], current_password)
    except Exception:
        return jsonify({"error": "Current password is incorrect"}), 400

    try:
        db.auth_update_user(g.jwt_token, {"password": new_password})
        return jsonify({"message": "Password changed successfully"}), 200
    except Exception as e:
        return jsonify({"error": "Failed to update password", "detail": str(e)}), 500


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
        return jsonify({"error": "password is required to confirm account deletion"}), 400

    db = get_db()
    profile = db.table("profiles").select("email,full_name").eq("id", g.user_id).single().execute()
    if not profile:
        return jsonify({"error": "User not found"}), 404

    try:
        db.auth_sign_in(profile["email"], password)
    except Exception:
        return jsonify({"error": "Password is incorrect"}), 400

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

    return jsonify({"message": "Account has been deleted. Your data will be purged within 30 days."}), 200


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
        return jsonify({"error": "Email is required"}), 400
    result = auth_service.reset_password_request(data["email"])
    return jsonify(result), 200
