"""
HP Service — central authority for all Holy Points operations.

EARNING RULES (Master Brand Document — final):
  Food order:     1 HP per ₦10 → ACTIVE + tier multiplier bonus → ACTIVE
  Welcome bonus:  50 HP → ACTIVE (first order only)
  Referral:       75 HP → ACTIVE (no per-month cap), milestones 5×→+150, 10×→+400
  Event check-in: 40 HP → PENDING (no per-month cap)
  Review:         20 HP → PENDING (no per-month cap)
  Birthday:       150 HP → ACTIVE (30-day window)
  Wallet top-up:  50 HP → ACTIVE (≥ ₦3,000 only)
  Social share:   25 HP → PENDING (per valid share)
  Pending ceiling: 800 HP maximum in pending pool at any time

UNLOCK MECHANIC:
  Unlock = food_spend × HP_PER_NAIRA_FOOD × HP_UNLOCK_RATE_PCT
  (e.g. ₦1,000 × 0.1 × 0.30 = 30 HP unlocked per ₦1,000 food spend)

TIER SYSTEM (rolling 120-day hp_earned):
  Ember/Starter: 0 HP        multiplier 1.00
  Flame:         2,500 HP    multiplier 1.08
  Blaze/Inferno: 7,500 HP    multiplier 1.15
  Holy:          20,000 HP   multiplier 1.25
  Grace period: 7 days before downgrade

HP TRANSACTION TYPE ENUM VALUES (from live DB — confirmed):
  ONLY 3 valid values: earn | spend | expire
  Direction is set by `type`; what it was for is captured in `source` column.
  Common source values: food_order, welcome, referral, review, spin_wheel,
    unlock, admin_grant, event_checkin, birthday, challenge, expiry
"""

import math
from datetime import datetime, timezone, timedelta
from app.db import get_db, get_user_client, SupabaseError
from flask import current_app


def _resolve_txn_type(source_type: str, is_spend: bool = False, is_unlock: bool = False) -> str:
    """Map any transaction type or source_type to a DB-valid type: 'earn' | 'spend' | 'expire'.
    'unlock' is not a valid DB enum value — treated as 'earn'.
    """
    if not source_type:
        return "spend" if is_spend else "earn"
    s_lower = str(source_type).lower()
    if s_lower in {"expiry", "expire", "decay"}:
        return "expire"
    if is_spend or s_lower.startswith("spend") or s_lower in {
        "reward_redemption", "flash_reward_redemption",
        "marketplace_purchase", "order_hp_redemption", "spin_cost",
    }:
        return "spend"
    return "earn"


def get_hp_balance(user_id: str) -> dict:
    """
    Fetch HP balance from profiles.hp_balance (authoritative active balance).
    Pending HP is tracked via hp_transactions rows where status='pending'.
    hp_earned_120day is read from profiles.hp_earned_120day (updated by daily task).
    """
    db = get_user_client()
    try:
        profile = (
            db.table("profiles")
            .select("hp_balance,hp_earned_120day")
            .eq("id", user_id)
            .single()
            .execute()
        )
    except SupabaseError:
        profile = {}

    active = int(profile.get("hp_balance") or 0)
    hp_earned_120day = int(profile.get("hp_earned_120day") or 0)

    try:
        pending_rows = (
            db.table("hp_transactions")
            .select("amount")
            .eq("user_id", user_id)
            .eq("status", "pending")
            .execute()
        )
        pending = sum(int(r.get("amount", 0)) for r in (pending_rows or []))
    except Exception:
        pending = 0

    tier_info = None
    try:
        tier_info = get_user_tier(user_id)
    except Exception:
        pass

    multiplier = 1.0
    try:
        t = (tier_info or {}).get("tier") or {}
        multiplier = float(t.get("earn_multiplier") or 1.0)
    except Exception:
        pass

    return {
        "active": max(0, active),
        "pending": max(0, pending),
        "total_visible": max(0, active + pending),
        "monthly_hp_earned": 0,
        "hp_earned_120day": max(0, hp_earned_120day),
        "tier_bonus_multiplier": multiplier,
        "tier": tier_info,
    }


def _get_hp_multiplier() -> float:
    """
    Read the active HP earn multiplier from system_settings.
    Supported multiplier event values are 0.5, 1.0, and 2.0.
    Returns 1.0 if disabled, expired, or invalid.
    """
    try:
        db = get_user_client()
        m_row = db.table("system_settings").select("value").eq("key", "hp_multiplier").is_("campus_id", "null").single().execute()
        m_val = (m_row or {}).get("value", "1") or "1"
        if isinstance(m_val, str) and m_val.startswith('"') and m_val.endswith('"'):
            import json
            try:
                m_val = json.loads(m_val)
            except Exception:
                pass
        multiplier = float(m_val)
        if multiplier not in (0.5, 1.0, 2.0):
            return 1.0
        # Check expiry
        exp_row = db.table("system_settings").select("value").eq("key", "multiplier_expires_at").is_("campus_id", "null").single().execute()
        exp_val = (exp_row or {}).get("value") or ""
        if isinstance(exp_val, str) and exp_val.startswith('"') and exp_val.endswith('"'):
            import json
            try:
                exp_val = json.loads(exp_val)
            except Exception:
                pass
        expires_at = str(exp_val).strip()
        if expires_at:
            exp_dt = datetime.fromisoformat(expires_at.replace("Z", "+00:00"))
            if datetime.now(timezone.utc) > exp_dt:
                return 1.0
        return multiplier
    except Exception:
        return 1.0


def calculate_delivery_hp(order_total, tier_slug, order_items) -> int:
    """Pure calculation — no DB writes. Extracted from award_food_order_hp."""
    config = current_app.config
    tier_multiplier = config.get("TIER_MULTIPLIERS", {}).get(str(tier_slug).lower() if tier_slug else "ember", 1.0)
    if order_items:
        base_hp = 0
        multiplied_base_hp = 0
        total_hp = 0
        for item in order_items:
            if item.get("is_addon") or not item.get("price_snapshot"):
                continue
            line_base_hp = int(
                float(item.get("price_snapshot") or 0)
                * int(item.get("quantity") or 1)
                * config["HP_PER_NAIRA_FOOD"]
            )
            base_hp += line_base_hp
            try:
                item_multiplier = float(item.get("hp_multiplier_snapshot") or 1.0)
            except (TypeError, ValueError):
                item_multiplier = 1.0
            if item_multiplier not in (0.5, 1.0, 2.0):
                item_multiplier = 1.0
            multiplied_line_hp = round(line_base_hp * item_multiplier)
            multiplied_base_hp += multiplied_line_hp
            total_hp += round(multiplied_line_hp * tier_multiplier)
    else:
        base_hp = int(order_total * config["HP_PER_NAIRA_FOOD"])
        tier_bonus_hp = round(base_hp * (tier_multiplier - 1.0))
        event_multiplier = _get_hp_multiplier()
        total_hp = round(base_hp * event_multiplier) + tier_bonus_hp

    return total_hp


def unlock_pending_hp(user_id: str, order_id: str, food_spend: float) -> dict:
    """
    Unlock pending HP proportional to food spend — FIFO.
    Formula: floor(food_spend × HP_PER_NAIRA_FOOD × HP_UNLOCK_RATE_PCT)
    = 30% of the order's BASE food HP. Uses atomic database-level RPC.
    """
    config = current_app.config
    amount_to_unlock = math.floor(
        food_spend * config["HP_PER_NAIRA_FOOD"] * config.get("HP_UNLOCK_RATE_PCT", 0.30)
    )
    if amount_to_unlock <= 0:
        return {"unlocked": 0}

    db = get_db()
    res = db.rpc("unlock_pending_hp_fifo_atomic", {
        "p_user_id": user_id,
        "p_order_id": order_id,
        "p_amount_to_unlock": amount_to_unlock,
    })

    if isinstance(res, dict) and res.get("error"):
        logger.warning("unlock_pending_hp failed: %s", res["error"])
        return {"unlocked": 0}

    unlocked_amount = res.get("unlocked_amount", 0) if isinstance(res, dict) else 0

    if unlocked_amount > 0:
        try:
            recalculate_tier(user_id)
        except Exception:
            pass

    return {"unlocked": unlocked_amount}


import logging as _logging
logger = _logging.getLogger(__name__)


def earn_pending_hp(user_id: str, amount: int, source_type: str, reference_id: str = None, notes: str = "", campus_id: str = None) -> dict:
    """
    Add HP to pending pool.
    Referral HP goes to ACTIVE (referral → active per brand spec).
    All other source types (event, review, challenge, social, bundle_purchase) → pending.
    HP multiplier is applied to all HP earning.
    """
    if amount <= 0:
        return {"added_to_pending": 0, "added_to_overflow": 0, "source_type": source_type}

    # Apply multiplier
    multiplier = _get_hp_multiplier()
    if multiplier > 1.0:
        amount = round(amount * multiplier)

    is_referral = source_type in ("referral", "earn_referral")
    status = "active" if is_referral else "pending"

    txn_type = _resolve_txn_type(source_type)
    _record_hp_transaction(
        user_id=user_id,
        amount=amount,
        txn_type=txn_type,
        reference_id=reference_id,
        reference_type=source_type,
        source_type=source_type,
        notes=notes or f"{source_type} HP → {status}" + (f" (×{multiplier} multiplier)" if multiplier > 1.0 else ""),
        status=status,
        campus_id=campus_id,
    )
    if is_referral:
        _update_earned_counters(user_id, amount)
    return {
        "added_to_pending": 0 if is_referral else amount,
        "added_to_overflow": 0,
        "source_type": source_type,
    }


def award_active_hp(
    user_id: str,
    amount: int,
    txn_type: str = None,
    reference_id: str = None,
    reference_type: str = None,
    source_type: str = None,
    notes: str = "",
    issued_by_admin_id: str = None,
    apply_multiplier: bool = True,
    campus_id: str = None,
) -> dict:
    """
    Directly award HP to ACTIVE balance.
    Used for: welcome_bonus, birthday, wallet_topup, newsletter, admin_grant, milestone bonuses.
    Admin reversals (negative amount) are allowed when issued_by_admin_id is provided.
    apply_multiplier=False for admin grants and system corrections.
    """
    if amount == 0:
        return {"awarded": 0}
    if amount < 0 and not issued_by_admin_id:
        return {"awarded": 0}

    # Apply multiplier for positive earnings (not admin grants or reversals)
    original_amount = amount
    if amount > 0 and apply_multiplier and not issued_by_admin_id:
        multiplier = _get_hp_multiplier()
        if multiplier > 1.0:
            amount = round(amount * multiplier)

    resolved_type = txn_type or _resolve_txn_type(source_type or reference_type or "admin_grant")
    _record_hp_transaction(
        user_id=user_id,
        amount=amount,
        txn_type=resolved_type,
        reference_id=reference_id,
        reference_type=reference_type,
        source_type=source_type or reference_type,
        notes=notes + (f" (×{round(amount / original_amount, 2)} multiplier)" if amount != original_amount and notes else ""),
        status="active",
        issued_by_admin_id=issued_by_admin_id,
        campus_id=campus_id,
    )
    _update_earned_counters(user_id, amount)
    return {"awarded": amount}


def spend_hp(user_id: str, amount: int, reference_id: str, reference_type: str, notes: str = "", campus_id: str = None) -> dict:
    """Deduct HP from active balance atomically via RPC. Raises ValueError if insufficient."""
    if amount <= 0:
        return {"spent": 0, "balance_after": get_hp_balance(user_id)["active"]}

    current_active = get_hp_balance(user_id)["active"]
    if current_active < amount:
        from app.messages import MSG, resolve_msg
        raise ValueError(resolve_msg(MSG.HP_INSUFFICIENT, have=current_active, need=amount))

    txn_type = _resolve_txn_type(reference_type, is_spend=True)
    _record_hp_transaction(
        user_id=user_id,
        amount=-amount,
        txn_type=txn_type,
        reference_id=reference_id,
        reference_type=reference_type,
        source_type=reference_type,
        notes=notes or f"HP spent on {reference_type}",
        status="active",
        campus_id=campus_id,
    )
    new_bal = get_hp_balance(user_id)["active"]
    return {"spent": amount, "balance_after": new_bal}


def expire_hp(user_id: str, amount: int, notes: str = "HP decayed due to inactivity", campus_id: str = None) -> dict:
    """Apply HP decay. Deducts from active balance."""
    balance = get_hp_balance(user_id)
    expire_amount = min(amount, max(0, balance["active"]))
    if expire_amount <= 0:
        return {"expired": 0}
    _record_hp_transaction(
        user_id=user_id,
        amount=-expire_amount,
        txn_type="expire",
        reference_id=None,
        reference_type="expiry",
        source_type="expiry",
        notes=notes,
        status="active",
        campus_id=campus_id,
    )
    return {"expired": expire_amount}


def award_signup_bonus(user_id: str) -> dict:
    """Grant SIGNUP_BONUS_HP active HP on account creation. No-op when amount is 0."""
    amount = current_app.config.get("SIGNUP_BONUS_HP", 0)
    if not amount:
        return {"awarded": 0, "reason": "Signup bonus disabled"}
    db = get_user_client()
    already = (
        db.table("hp_transactions")
        .select("id")
        .eq("user_id", user_id)
        .eq("source", "signup")
        .execute()
    )
    if already:
        return {"awarded": 0, "reason": "Already received"}
    return award_active_hp(
        user_id=user_id,
        amount=amount,
        txn_type="earn",
        reference_id=user_id,
        reference_type="signup_bonus",
        source_type="signup",
        notes=f"Welcome to {current_app.config.get('APP_NAME', 'Holy Grills')} — {amount} HP signup gift",
    )


def award_welcome_bonus(user_id: str, order_id: str) -> dict:
    """Award WELCOME_BONUS_HP active HP on the user's first delivered order. Checks if already awarded."""
    db = get_user_client()
    already = (
        db.table("hp_transactions")
        .select("id")
        .eq("user_id", user_id)
        .eq("source", "welcome")
        .execute()
    )
    if already:
        return {"awarded": 0, "reason": "Already received"}
    amount = current_app.config["WELCOME_BONUS_HP"]
    return award_active_hp(
        user_id=user_id,
        amount=amount,
        txn_type="earn",
        reference_id=order_id,
        reference_type="welcome_bonus",
        source_type="welcome",
        notes=f"Welcome bonus — {amount} HP on first order",
    )


def get_user_tier(user_id: str, campus_id: str = None) -> dict:
    """Get user's current tier from profiles.current_tier_id → hp_tiers."""
    db = get_db()
    try:
        profile = (
            db.table("profiles")
            .select("current_tier_id,tier_grace_ends_at,tier_grace_started_at")
            .eq("id", user_id)
            .single()
            .execute()
        )
        tier_id = profile.get("current_tier_id") if profile else None
        if not tier_id:
            base_tiers = (
                db.table("hp_tiers")
                .select("*")
                .eq("is_active", "true")
                .order("sort_order")
                .limit(1)
                .execute()
            )
            return {"tier": base_tiers[0] if base_tiers else None, "is_in_grace_period": False}

        tier = db.table("hp_tiers").select("*").eq("id", tier_id).single().execute()
        grace_ends = profile.get("tier_grace_ends_at")
        now_iso = datetime.now(timezone.utc).isoformat()
        is_in_grace = bool(grace_ends and grace_ends > now_iso)
        return {
            "tier": tier,
            "is_in_grace_period": is_in_grace,
            "grace_period_ends_at": grace_ends,
        }
    except Exception:
        return {"tier": None, "is_in_grace_period": False}


def recalculate_tier(user_id: str, campus_id: str = None) -> dict:
    """
    Compare hp_earned_120day against tier thresholds (min_points column in hp_tiers).
    Uses the rolling 120-day earned HP — not the current balance — to determine tier.
    Updates profiles.current_tier_id and logs to user_tiers (event log).
    """
    db = get_db()
    try:
        profile = (
            db.table("profiles")
            .select("hp_earned_120day,current_tier_id")
            .eq("id", user_id)
            .single()
            .execute()
        )
        hp_earned_120day = int(profile.get("hp_earned_120day") or 0)
        current_tier_id = profile.get("current_tier_id")
    except Exception:
        hp_earned_120day = 0
        current_tier_id = None

    tiers_raw = (
        db.table("hp_tiers")
        .select("*")
        .eq("is_active", "true")
        .order("sort_order", ascending=False)
        .execute()
    )
    tiers = sorted(tiers_raw or [], key=lambda t: int(t.get("min_points") or 0), reverse=True)
    new_tier = None
    for tier in tiers:
        if hp_earned_120day >= int(tier.get("min_points") or 0):
            new_tier = tier
            break
    if not new_tier and tiers:
        new_tier = tiers[-1]

    if not new_tier:
        return {"tier": None, "changed": False}

    if current_tier_id == new_tier["id"]:
        return {"tier": new_tier, "changed": False}

    event = "upgraded" if (not current_tier_id or _tier_sort_order(new_tier) > _tier_sort_order_by_id(current_tier_id, tiers_raw)) else "downgraded"

    if event == "downgraded":
        # Downgrades are handled exclusively by the tier_grace_period_check
        # scheduled task, which respects the maintenance_points threshold and
        # the 7-day grace window. Applying a downgrade here would skip both.
        return {"tier": new_tier, "changed": False, "event": "downgrade_deferred_to_grace_job"}

    try:
        db.table("user_tiers").insert({
            "user_id": user_id,
            "tier_id": new_tier["id"],
            "previous_tier_id": current_tier_id,
            "event": event,
            "hp_at_event": hp_earned_120day,
        }).execute()
    except Exception:
        pass

    try:
        db.table("profiles").eq("id", user_id).update({"current_tier_id": new_tier["id"]}).execute()
    except Exception:
        pass

    return {"tier": new_tier, "changed": True, "previous_tier_id": current_tier_id, "event": event}


def _tier_sort_order(tier: dict) -> int:
    return int(tier.get("sort_order") or 0)


def _tier_sort_order_by_id(tier_id: str, tiers: list) -> int:
    t = next((t for t in (tiers or []) if t.get("id") == tier_id), None)
    return int(t.get("sort_order") or 0) if t else 0


def process_flash_redeem(reward_id: str, user_id: str) -> dict:
    """Flash redemption: per-sale % discount, first N users only, time-windowed.
    Delegates the whole check+redeem to an atomic Supabase RPC so concurrent
    requests can't oversell the slot limit or bypass the discount config."""
    db = get_user_client()
    from app.messages import MSG, resolve_msg

    res = db.rpc("hg_redeem_flash_reward_atomic", {
        "p_user_id": user_id,
        "p_reward_id": reward_id,
    })

    if not res or not res.get("success"):
        error = (res or {}).get("error", "unknown_error")
        if error == "no_active_sale":
            raise ValueError(MSG.HP_FLASH_NO_ACTIVE_SALE)
        if error == "window_closed" or error == "window_not_started":
            raise ValueError(MSG.HP_FLASH_WINDOW_CLOSED)
        if error == "limit_reached":
            raise ValueError(MSG.HP_FLASH_LIMIT_REACHED.format(qty=res.get("qty")))
        if error == "Insufficient active HP balance":
            raise ValueError(resolve_msg(MSG.HP_FLASH_INSUFFICIENT, need=res.get("hp_cost", 0), have=0))
        raise ValueError(f"Flash redemption failed: {error}")

    return {
        "redemption_id": res["redemption_id"],
        "hp_cost": res["hp_cost"],
        "discount_pct": res["discount_pct"],
        "reward_name": res["reward_name"],
    }


def process_hp_bundle_purchase(event_host_id: str, hp_amount: int, naira_paid: float, provider: str = "paystack", provider_reference: str = None) -> dict:
    """Event hosts purchase HP bundles at ₦5/HP. HP credited to pending pool."""
    config = current_app.config
    price_per_hp = config.get("HP_BUNDLE_PRICE_PER_HP", 5.0)
    expected_naira = hp_amount * price_per_hp
    if abs(naira_paid - expected_naira) > 1:
        raise ValueError(f"Payment mismatch: ₦{naira_paid} received, ₦{expected_naira} expected")

    db = get_user_client()
    try:
        db.table("hp_bundle_purchases").insert({
            "event_host_id": event_host_id,
            "hp_amount": hp_amount,
            "naira_paid": naira_paid,
            "price_per_hp": price_per_hp,
            "provider": provider,
            "provider_reference": provider_reference,
        }).execute()
    except SupabaseError as exc:
        if exc.details and exc.details.get("code") == "23505":
            raise ValueError("Payment reference already processed") from exc
        raise

    result = earn_pending_hp(
        user_id=event_host_id,
        amount=hp_amount,
        source_type="bundle_purchase",
        notes=f"HP bundle: {hp_amount} HP at ₦{price_per_hp}/HP (₦{naira_paid:.0f} total)",
    )
    return {"hp_credited_to_pending": result["added_to_pending"], "hp_to_overflow": result["added_to_overflow"]}



# ── Internal helpers ──────────────────────────────────────────────────────────

def _record_hp_transaction(
    user_id: str,
    amount: int,
    txn_type: str,
    reference_id: str = None,
    reference_type: str = None,
    source_type: str = None,
    notes: str = "",
    status: str = "active",
    issued_by_admin_id: str = None,
    campus_id: str = None,
):
    if campus_id is None:
        from flask import has_app_context, g
        if has_app_context():
            campus_id = getattr(g, 'campus_id', None)
    db = get_db()
    # Preserves the specific business context concept (e.g. earn_order, earn_referral) in the source/context field
    resolved_source = source_type or reference_type or txn_type or "system"
    # Enforce that p_type passed to the DB atomic RPC is strictly a valid enum value ('earn' | 'spend' | 'expire')
    db_type = _resolve_txn_type(txn_type or resolved_source)

    # Call atomic RPC function to mutate profiles.hp_balance and insert hp_transactions in one transaction
    res = db.rpc("record_hp_transaction_atomic", {
        "p_user_id": user_id,
        "p_amount": int(amount),
        "p_type": db_type,
        "p_status": status,
        "p_source": resolved_source,
        "p_reference_type": reference_type,
        "p_reference_id": reference_id,
        "p_issued_by_admin_id": issued_by_admin_id,
        "p_notes": notes,
        "p_campus_id": campus_id,
    })

    if isinstance(res, dict) and res.get("error"):
        raise ValueError(res["error"])

    # Recalculate tier whenever active HP changes
    if status != "pending":
        try:
            recalculate_tier(user_id)
        except Exception:
            pass


def _update_earned_counters(user_id: str, amount: int):
    if amount <= 0:
        return
    db = get_db()
    month = datetime.now(timezone.utc).strftime("%Y-%m")
    try:
        db.rpc("increment_monthly_hp_tracker", {
            "p_user_id": user_id,
            "p_month": month,
            "p_amount": amount
        })
    except Exception as e:
        logger.warning("_update_earned_counters: failed for %s: %s", user_id, e)


