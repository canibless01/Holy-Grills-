"""Referral routes — tracking and HP awards."""

from flask import Blueprint, request, jsonify, g, current_app
from app.middleware.auth import require_auth, require_role
from app.services.hp_service import award_active_hp
from app.db import get_db, get_user_client
from app.services.notification_service import send_notification
from app.messages import MSG
from app.utils.logger import get_logger
from datetime import datetime, timezone

logger = get_logger(__name__)

referrals_bp = Blueprint("referrals", __name__)


def _complete_referral_award(referral: dict, order_id: str):
    """
    Complete referral via atomic database function, then handle Python milestones.
    Supabase owns atomic completion (75 HP to referrer), Python owns milestone logic.
    """
    db = get_db()
    referrer_id = referral["referrer_id"]

    # 1. Call atomic DB function for base referral award (75 HP to referrer only)
    try:
        result = db.rpc("hg_complete_referral_atomic", {
            "p_referred_user_id": referral["referred_user_id"],
            "p_trigger_order_id": order_id
        })
    except Exception as e:
        logger.error("hg_complete_referral_atomic failed for referred_user %s: %s",
                     referral["referred_user_id"], e)
        return {"hp_awarded": 0, "error": str(e)}

    # 2. Handle idempotent case
    if result.get("already_completed"):
        return {
            "hp_awarded": result.get("hp_awarded", 0),
            "already_completed": True,
            "referral_id": result.get("referral_id")
        }

    # 3. Python-owned milestone logic (5, 10, 20 referrals → bonus HP)
    try:
        completed_rows = (
            db.table("referrals")
            .select("id")
            .eq("referrer_id", referrer_id)
            .eq("status", "completed")
            .execute()
        ) or []
        completed_count = len(completed_rows)

        from app.services.milestone_service import check_milestone_trigger
        check_milestone_trigger(referrer_id, "referral_count", completed_count)
        check_milestone_trigger(referrer_id, "first_referral", completed_count)
    except Exception as e:
        logger.warning("Referral milestone trigger failed for user %s: %s", referrer_id, e)

    return {
        "hp_awarded": result.get("hp_awarded", 0),
        "referral_id": result.get("referral_id"),
        "transaction_id": result.get("transaction_id"),
    }


@referrals_bp.route("", methods=["GET"])
@require_auth
def my_referrals():
    """
    Get authenticated user's referral stats and list.
    ---
    tags: [Referrals]
    responses:
      200:
        description: Referral stats and history
    """
    try:
        db = get_user_client()

        profile = (
            db.table("profiles")
            .select("referral_code")
            .eq("id", g.user_id)
            .single()
            .execute()
        )

        referral_code = profile.get("referral_code") if profile else None

        q = db.table("referrals").select("*").eq("referrer_id", g.user_id)
        campus_id = getattr(g, 'campus_id', None)
        if campus_id:
            q = q.eq("campus_id", campus_id)
        referrals = q.order("created_at", ascending=False).execute()

        enriched_referrals = []
        for referral in referrals:
            referred_user = None
            referred_user_id = referral.get("referred_user_id")
            if referred_user_id:
                try:
                    referred_user = (
                        db.table("profiles")
                        .select("full_name,created_at")
                        .eq("id", referred_user_id)
                        .single()
                        .execute()
                    )
                except Exception:
                    referred_user = None
            referral["referred_user"] = referred_user
            enriched_referrals.append(referral)

        total_hp = sum(r.get("hp_awarded", 0) or 0 for r in enriched_referrals)
        completed = [r for r in enriched_referrals if (r.get("hp_awarded") or 0) > 0]

        frontend_url = current_app.config.get("FRONTEND_URL", "")
        return jsonify({
            "referral_code": referral_code,
            "referral_link": f"{frontend_url}?ref={referral_code}" if referral_code else None,
            "total_referrals": len(enriched_referrals),
            "completed_referrals": len(completed),
            "total_hp_earned": total_hp,
            "referrals": enriched_referrals,
        }), 200

    except Exception as e:
        return jsonify({"error": str(e), "type": type(e).__name__}), 500


@referrals_bp.route("/stats", methods=["GET"])
@require_auth
def referral_stats():
    """
    Get a lightweight summary of the authenticated user's referral performance
    (counts + HP earned only, no per-referral list). Useful for dashboard
    widgets that don't need the full referral history from GET /referrals.
    ---
    tags: [Referrals]
    responses:
      200:
        description: Referral summary stats
    """
    try:
        db = get_user_client()

        profile = (
            db.table("profiles")
            .select("referral_code")
            .eq("id", g.user_id)
            .single()
            .execute()
        )
        referral_code = profile.get("referral_code") if profile else None

        q = db.table("referrals").select("hp_awarded,status").eq("referrer_id", g.user_id)
        campus_id = getattr(g, 'campus_id', None)
        if campus_id:
            q = q.eq("campus_id", campus_id)
        referrals = q.execute() or []

        total_hp = sum(r.get("hp_awarded", 0) or 0 for r in referrals)
        completed = [r for r in referrals if (r.get("hp_awarded") or 0) > 0]
        frontend_url = current_app.config.get("FRONTEND_URL", "")
        return jsonify({
            "referral_code": referral_code,
            "referral_link": f"{frontend_url}?ref={referral_code}" if referral_code else None,
            "total_referrals": len(referrals),
            "completed_referrals": len(completed),
            "pending_referrals": len(referrals) - len(completed),
            "total_hp_earned": total_hp,
        }), 200

    except Exception as e:
        return jsonify({"error": str(e), "type": type(e).__name__}), 500


@referrals_bp.route("/complete", methods=["POST"])
@require_auth
@require_role("admin")
def complete_referral():
    """
    Internal endpoint called when a referred user completes their first order.
    Uses the same atomic RPC as the automatic flow.
    """
    db = get_db()
    data = request.get_json(force=True)
    referred_user_id = data.get("referred_user_id")
    order_id = data.get("order_id")

    if not referred_user_id or not order_id:
        return jsonify({"error": MSG.REFERRAL_FIELDS_REQUIRED}), 400

    referral = (
        db.table("referrals")
        .select("*")
        .eq("referred_user_id", referred_user_id)
        .single()
        .execute()
    )
    if not referral:
        return jsonify({"message": MSG.REFERRAL_NOT_FOUND}), 200

    if referral.get("hp_awarded", 0) > 0:
        return jsonify({"message": MSG.REFERRAL_ALREADY_DONE}), 200

    result = _complete_referral_award(referral, order_id)

    if result.get("error"):
        return jsonify({"error": result["error"]}), 400

    try:
        send_notification(
            user_id=referral["referrer_id"],
            notif_type="referral_completed",
            template_data={"hp": result.get("hp_awarded", 0)},
            reference_id=referral["id"],
            reference_type="referral",
        )
    except Exception:
        pass

    return jsonify({
        "hp_awarded": result.get("hp_awarded", 0),
        "hp_destination": "active",
    }), 200


def get_referrer_id(user_id: str) -> str | None:
    db = get_db()
    try:
        referral = (
            db.table("referrals")
            .select("referrer_id")
            .eq("referred_user_id", user_id)
            .single()
            .execute()
        )
        return referral.get("referrer_id") if referral else None
    except Exception:
        return None
