"""Referral routes — tracking, milestones, HP awards."""

from flask import Blueprint, request, jsonify, g, current_app
from app.middleware.auth import require_auth
from app.services.hp_service import award_active_hp
from app.db import get_db
from app.services.notification_service import send_notification
from datetime import datetime, timezone

referrals_bp = Blueprint("referrals", __name__)


def _get_milestone_bonuses() -> dict:
    """Return milestone bonus map keyed by referral count. Reads from config."""
    cfg = current_app.config
    return {
        int(cfg.get("REFERRAL_MILESTONE_1_COUNT", 5)): {
            "hp": int(cfg.get("REFERRAL_MILESTONE_5_HP", 150)),
            "badge": None,
        },
        int(cfg.get("REFERRAL_MILESTONE_2_COUNT", 10)): {
            "hp": int(cfg.get("REFERRAL_MILESTONE_10_HP", 400)),
            "badge": "super_referrer",
        },
    }


def _complete_referral_award(referral: dict, order_id: str):
    """
    Internal helper: award ACTIVE HP to referrer for a completed referral.
    Called by order_service when a referred user's first order is delivered.
    HP goes directly to active — no pending, no unlock required.
    """
    db = get_db()
    referrer_id = referral["referrer_id"]
    now = datetime.now(timezone.utc)
    hp_amount = int(current_app.config.get("REFERRAL_HP", 75))

    hp_result = award_active_hp(
        user_id=referrer_id,
        amount=hp_amount,
        txn_type="earn_referral",
        reference_id=referral.get("id"),
        reference_type="referral",
        source_type="referral",
        notes="Referral HP — friend placed first order",
    )

    db.table("referrals").eq("id", referral["id"]).update({
        "hp_awarded": hp_amount,
        "status": "completed",
        "trigger_order_id": order_id,
    })

    completed_referrals = (
        db.table("referrals")
        .select("id")
        .eq("referrer_id", referrer_id)
        .gt("hp_awarded", 0)
        .execute()
    )
    completed_count = len(completed_referrals)
    milestone_bonuses = _get_milestone_bonuses()

    if completed_count in milestone_bonuses:
        milestone = milestone_bonuses[completed_count]
        award_active_hp(
            user_id=referrer_id,
            amount=milestone["hp"],
            txn_type="earn_referral",
            reference_id=referrer_id,
            reference_type="referral_milestone",
            source_type="referral",
            notes=f"Referral milestone bonus — {completed_count} referrals completed",
        )
        send_notification(
            user_id=referrer_id,
            notif_type="referral_milestone",
            title=f"Milestone! {completed_count} Referrals Completed",
            body=f"You earned {milestone['hp']} bonus HP for referring {completed_count} friends!",
            channels=["in_app", "email"],
        )

    return hp_result


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


@referrals_bp.route("/complete", methods=["POST"])
def complete_referral():
    """
    Internal endpoint called when a referred user completes their first order.
    Awards HP directly to ACTIVE balance — no pending, no unlock required.
    No monthly cap — refer as many as you like.
    ---
    tags: [Referrals]
    security: []
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
        return jsonify({"error": "referred_user_id and order_id are required"}), 400

    referral = (
        db.table("referrals")
        .select("*")
        .eq("referred_user_id", referred_user_id)
        .single()
        .execute()
    )
    if not referral:
        return jsonify({"message": "No referral found"}), 200

    if referral.get("hp_awarded", 0) > 0:
        return jsonify({"message": "Referral already completed"}), 200

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
        title=f"+{hp_amount} HP — Referral Bonus!",
        body=f"A friend you referred just placed their first order. You earned {hp_amount} HP!",
        reference_id=referral["id"],
        reference_type="referral",
        channels=["in_app"],
    )

    completed_referrals = (
        db.table("referrals")
        .select("id")
        .eq("referrer_id", referrer_id)
        .gt("hp_awarded", 0)
        .execute()
    )
    completed_count = len(completed_referrals)
    milestone_bonuses = _get_milestone_bonuses()

    if completed_count in milestone_bonuses:
        milestone = milestone_bonuses[completed_count]
        award_active_hp(
            user_id=referrer_id,
            amount=milestone["hp"],
            txn_type="earn_referral",
            reference_id=referrer_id,
            reference_type="referral_milestone",
            source_type="referral",
            notes=f"Referral milestone bonus — {completed_count} referrals completed",
        )
        send_notification(
            user_id=referrer_id,
            notif_type="referral_milestone",
            title=f"Milestone! {completed_count} Referrals Completed",
            body=f"You earned {milestone['hp']} bonus HP for referring {completed_count} friends!",
            channels=["in_app", "email"],
        )

    return jsonify({
        "hp_awarded": hp_amount,
        "hp_destination": "active",
        "completed_referral_count": completed_count,
    }), 200
