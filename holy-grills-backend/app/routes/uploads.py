"""
app/routes/uploads.py

Admin-only direct-upload helpers.
"""

import hashlib
import time

from flask import Blueprint, current_app, jsonify, request, g

from app.middleware.auth import require_auth
from app.constants import ADMIN_ROLES
from app.messages import MSG
from app.utils.logger import get_logger

logger = get_logger(__name__)

uploads_bp = Blueprint("uploads", __name__)


@uploads_bp.route("/status", methods=["GET"])
@require_auth
def upload_status():
    """Whether direct uploads are available, and exactly what is missing when
    they are not. Lets the admin UI explain a disabled uploader (and offer the
    paste-a-URL fallback) instead of failing on every attempt."""
    configured = {
        "CLOUDINARY_CLOUD_NAME": bool(current_app.config.get("CLOUDINARY_CLOUD_NAME")),
        "CLOUDINARY_API_KEY": bool(current_app.config.get("CLOUDINARY_API_KEY")),
        "CLOUDINARY_API_SECRET": bool(current_app.config.get("CLOUDINARY_API_SECRET")),
    }
    missing = [name for name, ok in configured.items() if not ok]
    return jsonify({
        "configured": not missing,
        "missing": missing,
        "cloud_name": current_app.config.get("CLOUDINARY_CLOUD_NAME") or None,
    }), 200


@uploads_bp.route("/signature", methods=["POST"])
@require_auth
def upload_signature():
    """Generate a short-lived Cloudinary signature for a direct client upload.
    Admins may target any folder; everyone else is restricted to their own
    profile-photo folder."""
    cloud_name = current_app.config.get("CLOUDINARY_CLOUD_NAME")
    api_key = current_app.config.get("CLOUDINARY_API_KEY")
    api_secret = current_app.config.get("CLOUDINARY_API_SECRET")

    # Every image upload in the admin panel failed with one generic toast, which
    # read like a broken button rather than a missing setting. Name the exact
    # environment variables that are unset so the failure is fixable without
    # reading server logs — and tell the caller the service is misconfigured,
    # not merely busy.
    missing = [
        name
        for name, value in (
            ("CLOUDINARY_CLOUD_NAME", cloud_name),
            ("CLOUDINARY_API_KEY", api_key),
            ("CLOUDINARY_API_SECRET", api_secret),
        )
        if not value
    ]
    if missing:
        logger.error("upload/signature: Cloudinary is not configured — missing %s", ", ".join(missing))
        return jsonify({
            "error": MSG.UPLOAD_NOT_CONFIGURED,
            "missing": missing,
            "hint": (
                "Image upload needs Cloudinary credentials on the server. Set "
                + ", ".join(missing)
                + " in the backend environment (see .env.example → "
                  "\"Cloudinary direct uploads\") and restart the service. "
                  "Until then, paste an image URL instead of uploading a file."
            ),
        }), 503

    data = request.get_json(silent=True) or {}
    caller_role = getattr(g, "user_role", None)

    if caller_role in ADMIN_ROLES:
        folder = str(data.get("folder") or "general").strip()
        if not folder or len(folder) > 255 or folder.startswith("/") or ".." in folder:
            return jsonify({"error": MSG.UPLOAD_FOLDER_INVALID}), 400
    else:
        folder = f"profile_photos/{g.user_id}"

    timestamp = int(time.time())
    params_to_sign = {"folder": folder, "timestamp": timestamp}
    to_sign = "&".join(f"{k}={params_to_sign[k]}" for k in sorted(params_to_sign)) + api_secret
    signature = hashlib.sha1(to_sign.encode("utf-8")).hexdigest()

    return jsonify({
        "signature": signature,
        "timestamp": timestamp,
        "api_key": api_key,
        "cloud_name": cloud_name,
        "folder": folder,
        "message": MSG.UPLOAD_SIGNATURE_ISSUED,
    }), 200
