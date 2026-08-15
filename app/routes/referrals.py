"""Referral routes — tracking and HP awards."""

from flask import Blueprint, request, jsonify, g, current_app
from app.middleware.auth import require_auth, require_role
from app.services.hp_service import award_active_hp
from app.db import get_db
from app.services.notification_service import send_notification
from app.messages import MSG
from datetime import datetime, timezone

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
        from app.utils.logger import get_logger
        get_logger(__name__).error("hg_complete_referral_atomic failed for referred_user %s: %s",
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
        from app.utils.logger import get_logger
        get_logger(__name__).warning("Referral milestone trigger failed for user %s: %s", referrer_id, e)

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
        db = get_db()

        profile = (
            db.table("profiles")
            .select("referral_code")
            .eq("id", g.user_id)
            .single()
            .execute()
        )

        referral_code = profile.get("referral_code") if profile else None

        referrals = (
            db.table("referrals")
            .select("*")
            .eq("referrer_id", g.user_id)
            .order("created_at", ascending=False)
            .execute()
        )

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
        db = get_db()

        profile = (
            db.table("profiles")
            .select("referral_code")
            .eq("id", g.user_id)
            .single()
            .execute()
        )
        referral_code = profile.get("referral_code") if profile else None

        referrals = (
            db.table("referrals")
            .select("hp_awarded,status")
            .eq("referrer_id", g.user_id)
            .execute()
        ) or []

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
    Awards HP directly to ACTIVE balance — no pending, no unlock required.
    No monthly cap — refer as many as you like.
    ---
    tags: [Referrals]
    security: [{"Bearer": []}]
    parameters:
      - in: body
        name: body
        required: true
        schema:
          required: [referred_user_id, order_id]
          properties:
            referred_user_id: {type: string}
            order_id: {type: string}
    responses:
      200:
        description: Referral HP awarded
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

    referrer_id = referral["referrer_id"]
    now = datetime.now(timezone.utc)
    hp_amount = int(current_app.config.get("REFERRAL_HP", 75))

    hp_result = award_active_hp(
        user_id=referrer_id,
        amount=hp_amount,
        txn_type="earn_referral",
        reference_id=referral["id"],
        reference_type="referral",
        source_type="referral",
        notes="Referral HP — friend placed first order",
    )

    db.table("referrals").eq("id", referral["id"]).update({
        "hp_awarded": hp_amount,
        "status": "completed",
        "trigger_order_id": order_id,
    })

    send_notification(
        user_id=referrer_id,
        notif_type="referral_completed",
        template_data={"hp": hp_amount},
        reference_id=referral["id"],
        reference_type="referral",
    )

    completed_count = (
        db.table("referrals")
        .select("id")
        .eq("referrer_id", referrer_id)
        .gt("hp_awarded", 0)
        .execute()
    )
    completed_count = len(completed_count or [])

    return jsonify({
        "hp_awarded": hp_amount,
        "hp_destination": "active",
        "completed_referral_count": completed_count,
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


class SimpleMilestone:
    def __init__(self, threshold, hp_amount):
        self.threshold = threshold
        self.hp_amount = hp_amount


def get_next_uncredited_milestone(user_id: str):
    db = get_db()
    try:
        referrer_id = get_referrer_id(user_id)
        if not referrer_id:
            return None
        completed = (
            db.table("referrals")
            .select("id")
            .eq("referrer_id", referrer_id)
            .eq("status", "completed")
            .execute()
        ) or []
        completed_count = len(completed)
        milestones = (
            db.table("milestones")
            .select("id,trigger_value,hp_awarded")
            .eq("trigger_type", "referral_count")
            .eq("is_active", True)
            .order("trigger_value", ascending=True)
            .execute()
        ) or []
        credited = (
            db.table("user_milestones")
            .select("milestone_id")
            .eq("user_id", referrer_id)
            .execute()
        ) or []
        credited_ids = {c["milestone_id"] for c in credited if "milestone_id" in c}
        for m in milestones:
            val = int(m.get("trigger_value") or 0)
            if completed_count >= val and m.get("id") not in credited_ids:
                return SimpleMilestone(val, int(m.get("hp_awarded") or 0))
    except Exception:
        pass
    return None
