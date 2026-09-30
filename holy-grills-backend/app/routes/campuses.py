"""Public campus list, used by sign-up so the user picks a campus before department and level."""
import requests
from flask import Blueprint, jsonify

from app.db import get_user_client, SupabaseError
from app.messages import MSG
from app.utils.logger import get_logger

logger = get_logger(__name__)

campuses_bp = Blueprint("campuses", __name__)


@campuses_bp.route("", methods=["GET"])
def list_public_campuses():
    """
    List active campuses (public). Sign-up uses this so the user picks a campus first.
    ---
    tags: [Campuses]
    responses:
      200:
        description: Active campuses
    """
    db = get_user_client()
    try:
        rows = (
            db.table("campuses").select("id,name,slug,lat,lon,is_default")
            .eq("is_active", True).order("name").execute()
        ) or []
    except (SupabaseError, requests.RequestException) as e:
        logger.error("list_public_campuses failed: %s", e)
        return jsonify({"error": MSG.REFERENCE_DATA_UNAVAILABLE}), 503
    return jsonify({"campuses": rows, "count": len(rows)}), 200
