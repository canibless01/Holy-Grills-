"""Admin economics reporting routes."""
from flask import Blueprint, request, jsonify, g
from app.db import get_user_client
from app.middleware.auth import require_role
from app.services import economics_dashboard_service

admin_economics_bp = Blueprint("admin_economics", __name__)


@admin_economics_bp.route("/overview", methods=["GET"])
@require_role("admin")
def economics_overview():
    db = get_user_client()
    campus_id = getattr(g, "campus_id", None) or request.args.get("campus_id")
    start_date = request.args.get("start_date")
    end_date = request.args.get("end_date")
    return jsonify(economics_dashboard_service.get_economics_overview(db, start_date, end_date, campus_id)), 200


@admin_economics_bp.route("/tier-breakdown", methods=["GET"])
@require_role("admin")
def economics_tier_breakdown():
    db = get_user_client()
    campus_id = getattr(g, "campus_id", None) or request.args.get("campus_id")
    start_date = request.args.get("start_date")
    end_date = request.args.get("end_date")
    return jsonify(economics_dashboard_service.get_tier_breakdown(db, start_date, end_date, campus_id)), 200


@admin_economics_bp.route("/redemption-analytics", methods=["GET"])
@require_role("admin")
def economics_redemption_analytics():
    db = get_user_client()
    campus_id = getattr(g, "campus_id", None) or request.args.get("campus_id")
    start_date = request.args.get("start_date")
    end_date = request.args.get("end_date")
    return jsonify(economics_dashboard_service.get_redemption_analytics(db, start_date, end_date, campus_id)), 200
