"""Referral routes — tracking, milestones, HP awards."""

from flask import Blueprint, request, jsonify, g
from app.middleware.auth import require_auth
from app.services.hp_service import earn_pending_hp, award_active_hp
from app.services.notification_service import send_notification
from app.db import get_db
from datetime import datetime, timezone

referrals_bp = Blueprint("referrals", __name__)

MILESTONE_BONUSES = {
    5: {"hp": 150, "badge": None},
    10: {"hp": 400, "badge": "super_referrer"},
}


def _complete_referral_award(referral: dict, order_id: str):
    """
    Internal helper: award pending HP to referrer for a completed referral.
    Called by order_service when a referred user's first order is delivered.
    """
    from app.db import get_db
    db = get_db()
    referrer_id = referral["referrer_id"]
    now = datetime.now(timezone.utc)
    hp_amount = 75
    hp_result = earn_pending_hp(
        user_id=referrer_id,
        amount=hp_amount,
        source_type="referral",
        reference_id=referral.get("id"),
        notes="Referral HP — friend placed first order",
    )
    db.table("referrals").eq("id", referral["id"]).update({
        "hp_awarded": hp_amount,
        "hp_awarded_at": now.isoformat(),
        "triggering_order_id": order_id,
    })
    all_referrals = db.table("referrals").select("id").eq("referrer_id", referrer_id).execute()
    completed_count = len(all_referrals)
    if completed_count in MILESTONE_BONUSES:
        milestone = MILESTONE_BONUSES[completed_count]
        award_active_hp(
            user_id=referrer_id,
            amount=milestone["hp"],
            txn_type="earn",
            reference_id=referrer_id,
            reference_type="referral_milestone",
            notes=f"Referral milestone bonus — {completed_count} referrals completed",
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
    db = get_db()
    profile = db.table("profiles").select("referral_code").eq("id", g.user_id).single().execute()
    referral_code = profile.get("referral_code") if profile else None

    referrals = (
        db.table("referrals")
        .select("*,profiles!referred_user_id(full_name,created_at)")
        .eq("referrer_id", g.user_id)
        .order("created_at", ascending=False)
        .execute()
    )

    total_hp = sum(r.get("hp_awarded", 0) or 0 for r in referrals)
    completed = [r for r in referrals if r.get("hp_awarded", 0) > 0]

    return jsonify({
        "referral_code": referral_code,
        "referral_link": f"https://holygrill.app?ref={referral_code}",
        "total_referrals": len(referrals),
        "completed_referrals": len(completed),
        "total_hp_earned": total_hp,
        "referrals": referrals,
    }), 200


@referrals_bp.route("/complete", methods=["POST"])
def complete_referral():
    """
    Internal endpoint called when a referred user completes their first order.
    Awards 75 HP (pending) to the referrer. No monthly cap — refer as many as you like.
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

    hp_amount = 75
    hp_result = earn_pending_hp(
        user_id=referrer_id,
        amount=hp_amount,
        source_type="referral",
        reference_id=referral["id"],
        notes="Referral HP — friend placed first order",
    )

    db.table("referrals").eq("id", referral["id"]).update({
        "hp_awarded": hp_amount,
        "hp_awarded_at": now.isoformat(),
        "triggering_order_id": order_id,
    })

    send_notification(
        user_id=referrer_id,
        notif_type="referral_completed",
        title="+75 HP Pending — Referral Bonus!",
        body="A friend you referred just placed their first order. Order food to unlock your HP!",
        reference_id=referral["id"],
        reference_type="referral",
        channels=["in_app"],
    )

    all_referrals = db.table("referrals").select("id").eq("referrer_id", referrer_id).execute()
    completed_count = len(all_referrals)
    if completed_count in MILESTONE_BONUSES:
        milestone = MILESTONE_BONUSES[completed_count]
        award_active_hp(
            user_id=referrer_id,
            amount=milestone["hp"],
            txn_type="earn",
            reference_id=referrer_id,
            reference_type="referral_milestone",
            notes=f"Referral milestone bonus — {completed_count} referrals completed",
        )
        send_notification(
            user_id=referrer_id,
            notif_type="referral_milestone",
            title=f"Milestone! {completed_count} Referrals Completed",
            body=f"You earned {milestone['hp']} bonus HP for referring {completed_count} friends!",
            channels=["in_app", "email"],
        )

    return jsonify({"hp_added_to_pending": hp_result["added_to_pending"]}), 200
