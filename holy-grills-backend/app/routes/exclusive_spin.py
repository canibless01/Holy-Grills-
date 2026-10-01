import random
from flask import Blueprint, request, jsonify, g, current_app
from app.middleware.auth import require_auth
from app.db import get_db, get_user_client
from app.messages import MSG, resolve_msg
from app.services.feature_flags import is_feature_enabled
from app.utils.logger import get_logger
from datetime import datetime, timezone, timedelta

logger = get_logger(__name__)

exclusive_spin_bp = Blueprint("exclusive_spin", __name__)

# Every source a spin credit may come from. A credit with any other source is ignored
# on read, so a new way of granting spins must be added here or it is silently unusable.
#   leaderboard_prize — top-N monthly finish (scheduled.py)
#   tier_grant        — a tier's monthly exclusive_spins_monthly perk (grant_monthly_tier_perks)
#   admin_grant       — POST /admin/exclusive-spin-grant (compensation, support, promos)
SPIN_GRANT_SOURCES = ["leaderboard_prize", "tier_grant", "admin_grant"]


def _available_spins(db, user_id: str) -> list:
    """Return only non-expired spin credits from a recognized grant source.

    Exclusive spins are intentionally not purchasable — legacy/admin-created credits outside
    these two sources are deliberately excluded so there's no back door around that rule.
    Two legitimate sources exist: leaderboard_prize (top-N monthly finish) and tier_grant
    (a tier's monthly exclusive_spins_monthly perk, granted by scheduled.py's
    grant_monthly_tier_perks). Both must be honored here or the tier perk is silently unusable.
    """
    now = datetime.now(timezone.utc).isoformat()
    q = (
        db.table("exclusive_spins")
        .select("id,spin_count,source,month,expires_at")
        .eq("user_id", user_id)
        .in_("source", SPIN_GRANT_SOURCES)
        .gt("spin_count", 0)
        .gte("expires_at", now)
    )
    campus_id = getattr(g, 'campus_id', None)
    if campus_id:
        q = q.eq("campus_id", campus_id)
    return q.order("expires_at").execute() or []


def _spin_prizes() -> list:
    """Load prize table from the database, falling back to the full config/env default if empty or unreachable."""
    prizes = []
    try:
        db = get_db()
        campus_id = getattr(g, "campus_id", None)

        q = db.table("exclusive_spin_prizes").select("name,weight").eq("is_active", True)
        if campus_id:
            q = q.eq("campus_id", campus_id)
        prizes = q.execute() or []

        if not prizes and campus_id:
            # no campus-specific rows — fall back to global (campus_id IS NULL) rows before giving up
            prizes = (
                db.table("exclusive_spin_prizes")
                .select("name,weight")
                .eq("is_active", True)
                .is_("campus_id", "null")
                .execute()
            ) or []
    except Exception as e:
        logger.warning("_spin_prizes: prize lookup failed, using default list: %s", e)
        prizes = []

    if not prizes or not isinstance(prizes, list):
        # table genuinely empty (e.g. pre-seed) or DB error — use the same full default the app shipped with
        prizes = current_app.config.get("EXCLUSIVE_SPIN_TEMPLATE_ITEMS", [
            {"name": "Free Sausage ×2", "weight": 15},
            {"name": "Free Gizzard ×3", "weight": 15},
            {"name": "Free Side",       "weight": 10},
            {"name": "Free Coleslaw",   "weight": 10},
            {"name": "HP Jackpot +750", "weight": 5},
            {"name": "HP Bolt +300",    "weight": 20},
            {"name": "HP Boost +150",   "weight": 15},
            {"name": "Double HP next order", "weight": 10},
        ])

    return prizes


def _draw_prize(prizes: list) -> str:
    """Weighted random draw. Returns prize name."""
    if not prizes:
        return "HP Boost +50"
    names   = [p["name"]   for p in prizes]
    weights = [p.get("weight", 1) for p in prizes]
    return random.choices(names, weights=weights, k=1)[0]


def _apply_prize(user_id: str, prize_name: str, db):
    """Award HP prizes automatically; physical prizes are logged for admin fulfilment.

    Returns the prize name to show the user (adjusted to the real credited HP amount if a
    sitewide multiplier applied) on success, or None if the prize could not be applied —
    callers must check for None rather than assume a spin credit always pays out.
    """
    hp_map = {
        "+750 HP": 750,
        "+300 HP": 300,
    }
    for key, amount in hp_map.items():
        if prize_name == key:
            try:
                from app.services.hp_service import award_active_hp
                hp_result = award_active_hp(
                    user_id=user_id,
                    amount=amount,
                    source_type="exclusive_spin",
                    reference_type="exclusive_spin",
                    notes=f"Exclusive Spin prize: {prize_name}",
                )
                # A sitewide HP multiplier can scale the amount actually credited above `amount` —
                # keep the displayed name in sync with what was really awarded. Format is "+N HP"
                # (the "+" is a prefix here, not a separator before a trailing number like the old
                # "HP Jackpot +750" naming — rpartition("+") would silently do the wrong thing).
                credited_amount = hp_result.get("awarded", amount)
                if credited_amount != amount:
                    prize_name = f"+{credited_amount} HP"
                return prize_name
            except Exception as e:
                logger.warning("_apply_prize: HP award failed for %s: %s", user_id, e)
                return None

    if prize_name == "Free Delivery":
        try:
            from app.utils.settings import get_validated_setting
            cap = get_validated_setting(db, "exclusive_spin_free_delivery_cap", default=1500, minimum=0)
            db.table("profiles").eq("id", user_id).update({"next_order_free_delivery_cap": cap})
            return prize_name
        except Exception as e:
            logger.warning("_apply_prize: free delivery grant failed for %s: %s", user_id, e)
            return None
    else:
        # Physical prize (Free Sausage, Free Gizzard ×2, Free Side of Choice, Free Chicken
        # Kebab, etc.) — nothing to credit automatically, but staff need a record to fulfil it.
        try:
            db.table("exclusive_spin_fulfillments").insert({
                "user_id": user_id,
                "prize_name": prize_name,
                "status": "pending",
            })
            return prize_name
        except Exception as e:
            logger.warning("Failed to log physical prize fulfilment for %s: %s", user_id, e)
            return None


@exclusive_spin_bp.route("", methods=["GET"])
@require_auth
def my_spins():
    """
    Return the authenticated user's available exclusive spin credits.
    ---
    tags: [ExclusiveSpin]
    responses:
      200:
        description: Spin summary
    """
    user_id = g.user_id
    if not is_feature_enabled("exclusive_spin"):
        return jsonify({"error": resolve_msg(MSG.FEATURE_NOT_AVAILABLE, feature="Exclusive spin")}), 403
    db = get_user_client()
    spins = _available_spins(db, user_id)
    total = sum(s.get("spin_count", 0) for s in spins)

    return jsonify({
        "total_spins": total,
        "spins": spins,
        "prizes": _spin_prizes(),
    }), 200
@exclusive_spin_bp.route("/spin", methods=["POST"])
@require_auth
def do_spin():
    """
    Consume one exclusive spin credit and return the prize.
    ---
    tags: [ExclusiveSpin]
    responses:
      200:
        description: Spin result with prize name
      400:
        description: No spin credits available
    """
    user_id = g.user_id
    if not is_feature_enabled("exclusive_spin"):
        return jsonify({"error": resolve_msg(MSG.FEATURE_NOT_AVAILABLE, feature="Exclusive spin")}), 403
    db = get_user_client()
    spins = _available_spins(db, user_id)

    if not spins:
        return jsonify({"error": MSG.SPIN_NO_CREDITS}), 400

    # Use oldest-expiring spin first, try to update atomically using Optimistic Concurrency Control (OCC)
    write_db = get_db()
    success = False
    new_count = 0
    for spin_row in spins:
        try:
            res = (
                write_db.table("exclusive_spins")
                .eq("id", spin_row["id"])
                .eq("user_id", user_id)
                .eq("spin_count", spin_row["spin_count"])
                .update({"spin_count": spin_row["spin_count"] - 1})
                .execute()
            )
            if res:
                success = True
                new_count = spin_row["spin_count"] - 1
                break
        except Exception as e:
            logger.error("do_spin OCC update failed for spin row %s: %s", spin_row["id"], e)

    if not success:
        return jsonify({"error": MSG.SPIN_NO_CREDITS_RETRY}), 409

    prizes = _spin_prizes()
    prize  = _draw_prize(prizes)

    # Apply HP prizes instantly; log physical prizes for admin fulfilment.
    # write_db (service role) is required here — "Double HP next order" and the physical-prize
    # fulfilment insert are refused (42501) under the user's own token once A-01 is in place.
    applied_name = _apply_prize(user_id, prize, write_db)
    if applied_name is None:
        logger.error("do_spin: prize application failed for user %s, prize %s — spin credit already consumed", user_id, prize)
    else:
        prize = applied_name  # reflects the real HP amount if a sitewide multiplier scaled it

    # Send notification
    try:
        from app.services.notification_service import send_notification
        send_notification(
            user_id=user_id,
            notif_type="exclusive_spin_won",
            template_data={"prize": prize},
        )
    except Exception:
        pass

    return jsonify({
        "message": resolve_msg(MSG.SPIN_SUCCESS, prize=prize),
        "prize": prize,
        "spins_remaining": new_count,
    }), 200
