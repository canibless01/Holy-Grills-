"""
HP Service — central authority for all Holy Points operations. See module docstring in the reading guide for the full earning-rule reference.
"""

import json
import math
import uuid
from datetime import datetime, timezone
from app.db import get_db, get_user_client, SupabaseError
from flask import current_app
from app.utils.logger import get_logger

logger = get_logger(__name__)   # [D19 B-19] module had none -- _update_earned_counters already called
                                 # logger.warning() below with nothing defined, a latent NameError on any RPC failure


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
    "degraded" is True when any lookup failed, so callers can show "unavailable" instead of a false zero.
    """
    db = get_user_client()
    degraded = False
    try:
        profile = (
            db.table("profiles")
            .select("hp_balance,hp_earned_120day,tier_grace_ends_at,tier_grace_started_at")
            .eq("id", user_id)
            .single()
            .execute()
        )
    except SupabaseError as e:
        logger.error("get_hp_balance: profile read failed for %s: %s", user_id, e)
        profile = {}
        degraded = True
    profile = profile or {}

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
    except Exception as e:
        logger.error("get_hp_balance: pending read failed for %s: %s", user_id, e)
        pending = 0
        degraded = True

    tier_info = None
    try:
        tier_info = get_user_tier(user_id)
    except Exception as e:
        logger.error("get_hp_balance: tier read failed for %s: %s", user_id, e)
        degraded = True
    if (tier_info or {}).get("degraded"):
        degraded = True

    multiplier = 1.0
    try:
        # [cross-file finding] reads hp_tiers.earn_multiplier directly, while the actual HP calculation
        # (calculate_delivery_hp, above) goes through resolve_perk(), which checks a system_settings
        # per-tier override first. No override rows exist live today (confirmed against test 2), so this
        # was not yet visibly wrong -- but would silently show the wrong multiplier the moment one is
        # added. Matching resolve_perk's own source here so the two can't disagree.
        from app.services.tier_service import resolve_perk
        multiplier = float(resolve_perk(user_id, "earn_multiplier") or 1.0)
    except Exception as e:
        logger.error("get_hp_balance: multiplier lookup failed for %s: %s", user_id, e)
        t = (tier_info or {}).get("tier") or {}
        try:
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
        "tier_grace_ends_at": profile.get("tier_grace_ends_at"),
        "tier_grace_started_at": profile.get("tier_grace_started_at"),
        "degraded": degraded,
    }


def _ambient_campus_id(campus_id: str = None):
    """An explicit campus wins; otherwise the current request's campus (if any). Cron/worker contexts have none."""
    if campus_id:
        return campus_id
    try:
        from flask import has_app_context, g
        if has_app_context():
            return getattr(g, "campus_id", None)
    except Exception:
        pass
    return None


def _setting_raw(db, key: str, campus_id: str = None):
    """
    system_settings.value for `key` at exactly this scope (campus_id=None -> the global row).
    Returns None when the row is absent or unreadable. Unwraps a JSON-quoted string value, which the
    settings writer can produce -- the event multiplier already handled that, the menu multiplier didn't.
    """
    try:
        q = db.table("system_settings").select("value").eq("key", key)
        q = q.eq("campus_id", campus_id) if campus_id else q.is_("campus_id", "null")
        row = q.single().execute()
    except Exception:
        return None
    if not row:
        return None
    val = row.get("value")
    if isinstance(val, str) and len(val) >= 2 and val.startswith('"') and val.endswith('"'):
        try:
            val = json.loads(val)
        except Exception:
            pass
    return val


def _get_hp_multiplier(campus_id: str = None) -> float:
    """
    Read the active HP earn multiplier (global event multiplier) from system_settings.
    Supported multiplier event values are 0.5, 1.0, and 2.0.
    Campus-scoped row first, then the global row -- the admin settings route lets an admin save a
    campus-specific hp_multiplier, but this used to read only the global row, so a campus event was
    silently ignored while the broadcast told users it was live. The expiry is read at the same scope
    as the multiplier row that won. Returns 1.0 if disabled, expired, or invalid.
    """
    try:
        db = get_db()
        scope, raw = None, None
        if campus_id:
            raw = _setting_raw(db, "hp_multiplier", campus_id)
            if raw is not None:
                scope = campus_id
        if raw is None:
            raw = _setting_raw(db, "hp_multiplier", None)
        if raw is None:
            return 1.0
        multiplier = float(raw)
        if multiplier not in (0.5, 1.0, 2.0):
            return 1.0
        expires_at = str(_setting_raw(db, "multiplier_expires_at", scope) or "").strip()
        if expires_at:
            exp_dt = datetime.fromisoformat(expires_at.replace("Z", "+00:00"))
            if datetime.now(timezone.utc) > exp_dt:
                return 1.0
        return multiplier
    except Exception:
        return 1.0


def _get_food_earn_rate() -> float:
    try:
        row = get_db().table("system_settings").select("value").eq(
            "key", "hp_per_naira_food").is_("campus_id", "null").single().execute()
        if row and row.get("value") is not None:
            return float(row["value"])
    except Exception as exc:
        logger.warning("hp: hp_per_naira_food unreadable — using the built-in earn rate: %s", exc)
    return current_app.config["HP_PER_NAIRA_FOOD"]


def get_food_earn_rate() -> float:
    """
    HP earned per naira of food (system_settings first, Config as fallback) -- the same number calculate_delivery_hp
    pays out with. Public so callers that need to PREVIEW earnings (order_service's per-item preview) use it instead of
    reading Config["HP_PER_NAIRA_FOOD"] directly, which stops matching the payout the moment an admin edits the setting.
    """
    return _get_food_earn_rate()


def _get_unlock_rate() -> float:
    try:
        row = get_db().table("system_settings").select("value").eq(
            "key", "hp_unlock_rate_pct").is_("campus_id", "null").single().execute()
        if row and row.get("value") is not None:
            return float(row["value"])
    except Exception as exc:
        logger.warning("hp: hp_unlock_rate_pct unreadable — using the built-in unlock rate: %s",
                        exc)
    return current_app.config.get("HP_UNLOCK_RATE_PCT", 0.30)


def _get_menu_multiplier(campus_id: str = None) -> float:
    db = get_db()
    raw = _setting_raw(db, "menu_hp_multiplier", campus_id) if campus_id else None
    if raw is None:
        raw = _setting_raw(db, "menu_hp_multiplier", None)
    if raw is None:
        return 1.0
    try:
        multiplier = float(raw)
        return multiplier if multiplier in (0.5, 1.0, 2.0) else 1.0
    except Exception:
        return 1.0


def _tier_multiplier_for_slug(tier_slug) -> float:
    """
    Tier earn multiplier when only the tier SLUG is known (no user_id) -- calls straight into
    tier_service.get_tier_perks(), the same function resolve_perk() itself falls back to. Does not
    duplicate tier_service's own logic; if that function's perk schema changes, this changes with it.
    """
    try:
        from app.services.tier_service import get_tier_perks
        val = (get_tier_perks(tier_slug) or {}).get("earn_multiplier")
        return float(val) if val is not None else 1.0
    except Exception:
        return 1.0


def calculate_delivery_hp(order_total, tier_slug, order_items, user_id: str = None, campus_id: str = None) -> int:
    """Pure calculation — no DB writes. Extracted from award_food_order_hp."""
    tier_multiplier = 1.0
    if user_id:
        try:
            from app.services.tier_service import resolve_perk
            tier_multiplier = float(resolve_perk(user_id, "earn_multiplier") or 1.0)
        except Exception:
            tier_multiplier = _tier_multiplier_for_slug(tier_slug)
    else:
        tier_multiplier = _tier_multiplier_for_slug(tier_slug)

    food_earn_rate = _get_food_earn_rate()
    event_multiplier = _get_hp_multiplier(campus_id)
    menu_multiplier = _get_menu_multiplier(campus_id)

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
                * food_earn_rate
            )
            base_hp += line_base_hp
            try:
                item_multiplier = float(item.get("hp_multiplier_snapshot") or 1.0)
            except (TypeError, ValueError):
                item_multiplier = 1.0
            if item_multiplier not in (0.5, 1.0, 2.0):
                item_multiplier = 1.0
            multiplied_line_hp = round(line_base_hp * item_multiplier * event_multiplier * menu_multiplier)
            multiplied_base_hp += multiplied_line_hp
            total_hp += round(multiplied_line_hp * tier_multiplier)
    else:
        # Same order of operations as the per-item branch (event x menu first, tier on top). This branch used to
        # skip the menu multiplier and add the tier bonus to the unmultiplied base, so the two paths disagreed
        # whenever an event or menu multiplier was active.
        base_hp = int(order_total * food_earn_rate)
        total_hp = round(round(base_hp * event_multiplier * menu_multiplier) * tier_multiplier)

    return total_hp


def unlock_pending_hp(user_id: str, order_id: str, food_spend: float) -> dict:
    """
    Unlock pending HP proportional to food spend — FIFO.
    Formula: floor(food_spend × HP_PER_NAIRA_FOOD × HP_UNLOCK_RATE_PCT)
    = 30% of the order's BASE food HP. Uses atomic database-level RPC.
    """
    # Earning reads hp_per_naira_food from system_settings (Config as fallback); unlocking read Config directly, so an
    # admin changing the rate moved one side and not the other. _get_unlock_rate() already existed but was never used.
    amount_to_unlock = math.floor(food_spend * _get_food_earn_rate() * _get_unlock_rate())
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
        except Exception as e:                     # [B-20] was a bare `pass` -- a tier recalc failure was invisible
            logger.warning("recalculate_tier failed for %s: %s", user_id, e)

    return {"unlocked": unlocked_amount}


import logging as _logging
logger = _logging.getLogger(__name__)


def earn_pending_hp(user_id: str, amount: int, source_type: str, reference_id: str = None, notes: str = "",
                    campus_id: str = None, apply_multiplier: bool = True) -> dict:
    """
    Add HP to pending pool or active pool.
    source_type == 'event' -> ACTIVE HP.
    All other source types -> pending HP subject to monthly pending cap.
    apply_multiplier=False for a paid grant (e.g. a bundle purchase) -- the event multiplier is a
    bonus on HP a user EARNED, not a discount on HP they paid cash for.
    """
    if amount <= 0:
        return {"added_to_pending": 0, "added_to_overflow": 0, "source_type": source_type}

    if apply_multiplier:
        campus_id = _ambient_campus_id(campus_id)
        multiplier = _get_hp_multiplier(campus_id)
        if multiplier > 1.0:
            amount = round(amount * multiplier)

    is_instant_active = source_type == "event"
    status = "active" if is_instant_active else "pending"

    if status == "pending":
        from app.services.streak_service import check_monthly_cap
        cap_check = check_monthly_cap(user_id, amount)
        if not cap_check["allowed"] or cap_check.get("capped_amount", amount) <= 0:
            # [gift/hp cross-file finding] every OTHER return path here includes added_to_pending
            # and added_to_overflow -- process_hp_bundle_purchase (and any other caller) reads
            # result["added_to_pending"] unconditionally, so a shape missing that key raised a
            # bare KeyError instead of a clean "you've hit your monthly HP cap" outcome. Confirmed
            # live: a capped bundle purchase crashed after the customer had already paid.
            return {"success": False, "hp_awarded": 0, "capped": True, "reason": "monthly_pending_cap_reached",
                    "added_to_pending": 0, "added_to_overflow": 0, "source_type": source_type}
        amount = cap_check["capped_amount"]

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

    if status == "pending" and amount > 0:
        from app.services.streak_service import update_monthly_tracker
        update_monthly_tracker(user_id, amount)
    if is_instant_active:
        _update_earned_counters(user_id, amount)

    return {
        "added_to_pending": 0 if is_instant_active else amount,
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
        campus_id = _ambient_campus_id(campus_id)
        multiplier = _get_hp_multiplier(campus_id)
        if multiplier > 1.0:
            amount = round(amount * multiplier)

    resolved_type = txn_type or _resolve_txn_type(source_type or reference_type or "admin_grant")
    res = _record_hp_transaction(
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
    replayed = bool(isinstance(res, dict) and res.get("replayed"))
    if not replayed:
        _update_earned_counters(user_id, amount)  # [Appendix H] a replay must not count twice in the monthly tracker
    return {"awarded": 0 if replayed else amount, "replayed": replayed}


# Fixed namespace so the same (user, month) always maps to the same reference UUID, on every worker, forever.
_TIER_MONTHLY_HP_NS = uuid.UUID("6f0c1b64-2f0e-4d0a-9d55-7b3d5a1c9e21")


def award_tier_monthly_hp(user_id: str, amount: int, month: str = None, campus_id: str = None) -> dict:
    """
    Grant a tier's flat monthly HP perk (e.g. Flame's +50 HP) to the ACTIVE balance, at most once per user per month.

    Safe to call again for the same (user, month) -- a scheduled job retry, a second worker, a manual re-run: the
    reference is derived deterministically, so record_hp_transaction_atomic reports a replay and hp_transactions'
    unique (user_id, reference_type, reference_id) index backs it up. Returns {"awarded": N, "replayed": bool}.
    Flat perk, not an earning: the event multiplier is not applied (same as the birthday grant).

    The caller (the scheduled job) decides WHO gets it and HOW MUCH -- read the amount from the tier perk
    (resolve_perk(user_id, "<perk key>")) and pass month as "YYYY-MM" (defaults to the current UTC month).
    """
    try:
        amount = int(amount or 0)
    except (TypeError, ValueError):
        amount = 0
    if amount <= 0:
        return {"awarded": 0, "replayed": False, "reason": "no_perk"}

    month = month or datetime.now(timezone.utc).strftime("%Y-%m")
    try:
        datetime.strptime(month, "%Y-%m")
    except (TypeError, ValueError):
        raise ValueError("month must be formatted YYYY-MM")

    reference_id = str(uuid.uuid5(_TIER_MONTHLY_HP_NS, f"tier_monthly_hp:{user_id}:{month}"))
    return award_active_hp(
        user_id=user_id,
        amount=amount,
        txn_type="earn",
        reference_id=reference_id,
        reference_type="tier_monthly_hp",
        source_type="tier_monthly_hp",
        notes=f"Monthly tier perk \u2014 {amount} HP ({month})",
        apply_multiplier=False,
        campus_id=campus_id,
    )


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
    """Grant signup_bonus_hp (system_settings, falls back to SIGNUP_BONUS_HP) active HP on account creation. No-op when amount is 0."""
    try:
        row = get_db().table("system_settings").select("value").eq("key", "signup_bonus_hp").is_("campus_id", "null").single().execute()
        amount = int(row["value"]) if row and row.get("value") is not None else current_app.config.get("SIGNUP_BONUS_HP", 0)
    except Exception:
        amount = current_app.config.get("SIGNUP_BONUS_HP", 0)
    if not amount:
        return {"awarded": 0, "reason": "Signup bonus disabled"}
    db = get_db()
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
    """Award welcome_bonus_hp (system_settings, falls back to WELCOME_BONUS_HP) active HP on the user's first delivered order. Checks if already awarded."""
    db = get_db()
    already = (
        db.table("hp_transactions")
        .select("id")
        .eq("user_id", user_id)
        .eq("source", "welcome")
        .execute()
    )
    if already:
        return {"awarded": 0, "reason": "Already received"}
    try:
        row = db.table("system_settings").select("value").eq("key", "welcome_bonus_hp").is_("campus_id", "null").single().execute()
        amount = int(row["value"]) if row and row.get("value") is not None else current_app.config["WELCOME_BONUS_HP"]
    except Exception:
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
    except Exception as e:
        logger.error("get_user_tier: failed for %s: %s", user_id, e)
        return {"tier": None, "is_in_grace_period": False, "degraded": True}


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
    except Exception as exc:
        logger.warning("recalculate_tier: could not record the tier history row for %s: %s",
                        user_id, exc)

    try:
        db.table("profiles").eq("id", user_id).update({"current_tier_id": new_tier["id"]}).execute()
    except Exception as exc:
        logger.error("recalculate_tier: could not persist the new tier on the profile for %s — the user keeps the old tier: %s",
                      user_id, exc)

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
            raise ValueError(resolve_msg(MSG.HP_FLASH_INSUFFICIENT, need=res.get("hp_cost", 0), have=res.get("have", 0)))
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

    db = get_db()
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
        apply_multiplier=False,   # paid for in naira -- a live event multiplier must not double it
    )
    # A capped purchase still already took the customer's money (the insert above already succeeded) --
    # surface that clearly rather than silently returning less HP than they paid for. Whether a PAID
    # bundle should be exempt from the monthly pending cap in the first place is a product decision,
    # not something to decide here; flagging it rather than picking a side.
    response = {"hp_credited_to_pending": result["added_to_pending"], "hp_to_overflow": result["added_to_overflow"]}
    if result.get("capped"):
        response["capped"] = True
        response["reason"] = result.get("reason")
    return response



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
        except Exception as e:                     # [B-20] was a bare `pass` -- a tier recalc failure was invisible
            logger.warning("recalculate_tier failed for %s: %s", user_id, e)

    return res


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

