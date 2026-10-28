"""
Campus Ambassador Programme — domain service.

Design principles (see docs/AMBASSADOR_PROGRAMME.md):
  * Reuses the existing referral_code/link, HP, free-side, wallet and order
    services. Nothing here rewrites profiles.referred_by or public.referrals.
  * All attribution state lives in the ambassador_* tables created by the
    2026102712* migrations; order eligibility is "delivered and not fully
    refunded", counted once via the primary key on order_id.
  * Financial grants go through the existing atomic services/RPCs. This module
    never edits balances directly.
"""
import calendar
import uuid
from datetime import datetime, timezone
from decimal import Decimal, ROUND_HALF_UP

from flask import current_app, g

from app.constants import ADMIN_ROLES
from app.db import get_db
from app.messages import MSG
from app.utils.logger import get_logger
from app.utils.settings import setting_or_config
from app.utils.validators import validate_uuid

logger = get_logger(__name__)

AMBASSADOR_TABLE = "ambassadors"
LINK_PLACEHOLDERS = ("{{link}}", "{link}", "{{LINK}}")
ASSIGNMENT_STATUSES = ("pending", "seen", "shared")
GRANT_CATEGORIES = ("hp", "free_side", "meal_discount")
MILESTONE_METRICS = ("orders", "signups", "shares")


class AmbassadorError(ValueError):
    """A programme rule violation carrying an HTTP status for the route layer."""

    def __init__(self, message, status=400):
        super().__init__(message)
        self.status = status


class DuplicateGrant(AmbassadorError):
    def __init__(self, message):
        super().__init__(message, status=409)


# ---------------------------------------------------------------------------
# Month helpers (UTC programme months, YYYY-MM)
# ---------------------------------------------------------------------------
def current_month() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m")


def parse_month(month: str | None) -> str:
    month = (month or "").strip() or current_month()
    try:
        datetime.strptime(month, "%Y-%m")
    except (TypeError, ValueError):
        raise AmbassadorError(MSG.AMBASSADOR_INVALID_MONTH)
    return month


def month_bounds(month: str) -> tuple[datetime, datetime]:
    year, mon = map(int, month.split("-"))
    start = datetime(year, mon, 1, tzinfo=timezone.utc)
    last_day = calendar.monthrange(year, mon)[1]
    end = datetime(year, mon, last_day, 23, 59, 59, tzinfo=timezone.utc)
    return start, end


def _iso(dt: datetime) -> str:
    return dt.isoformat()


# ---------------------------------------------------------------------------
# Campus permission helper
# ---------------------------------------------------------------------------
def assert_campus_access(ambassador_row: dict | None):
    """403 when a campus-scoped staff member touches another campus's ambassador."""
    actor_role = getattr(g, "user_role", None)
    if actor_role == "super_admin" or not ambassador_row:
        return
    if ambassador_row.get("campus_id") != getattr(g, "campus_id", None):
        raise AmbassadorError(MSG.AMBASSADOR_CAMPUS_FORBIDDEN, status=403)


def _active_ambassador(db, ambassador_id: str) -> dict:
    row = (
        db.table(AMBASSADOR_TABLE)
        .select("*")
        .eq("profile_id", ambassador_id)
        .eq("status", "active")
        .single()
        .execute()
    )
    if not row:
        raise AmbassadorError(MSG.AMBASSADOR_NOT_FOUND, status=404)
    assert_campus_access(row)
    return row


# ---------------------------------------------------------------------------
# Audit (same table/shape as admin._audit; never breaks the main action)
# ---------------------------------------------------------------------------
def audit(actor_id: str, action: str, target_id: str, after: dict = None,
          before: dict = None, campus_id: str = None):
    try:
        get_db().table("admin_audit_logs").insert({
            "actor_id": actor_id,
            "actor_role": getattr(g, "user_role", None) or "community_manager",
            "entity_type": "ambassador_programme",
            "entity_id": target_id,
            "action": action,
            "before_value": before,
            "after_value": after,
            "campus_id": campus_id or getattr(g, "campus_id", None),
        }).execute()
    except Exception:
        logger.warning("ambassador audit failed: %s/%s", action, target_id, exc_info=True)


# ---------------------------------------------------------------------------
# Click tracking / attribution (thin wrappers over the SECURITY DEFINER RPCs)
# ---------------------------------------------------------------------------
def record_click(ref_code: str, anonymous_id: str = None,
                 visitor_user_id: str = None, campus_id: str = None) -> dict:
    if not ref_code or not str(ref_code).strip():
        return {"attributed": False, "reason": "missing_code"}
    result = get_db().rpc("hg_ambassador_record_click", {
        "p_ref_code": str(ref_code).strip(),
        "p_visitor_user_id": visitor_user_id,
        "p_anonymous_id": anonymous_id,
        "p_campus_id": campus_id,
    })
    return result if isinstance(result, dict) else {"attributed": False}


def merge_visitor(anonymous_id: str, user_id: str) -> dict:
    result = get_db().rpc("hg_ambassador_merge_visitor", {
        "p_anonymous_id": anonymous_id,
        "p_user_id": user_id,
    })
    return result if isinstance(result, dict) else {"adopted_clicks": 0, "attributed": False}


def attribute_delivered_order(order_id: str) -> dict:
    """Called from the order lifecycle when an order reaches 'delivered'."""
    try:
        result = get_db().rpc("hg_ambassador_attribute_order", {"p_order_id": order_id})
        return result if isinstance(result, dict) else {"attributed": False}
    except Exception:
        logger.exception("ambassador attribution failed for order %s", order_id)
        return {"attributed": False, "error": "attribution_failed"}


def reverse_attributed_order(order_id: str, reason: str = "order_refunded") -> dict:
    try:
        result = get_db().rpc("hg_ambassador_reverse_order", {
            "p_order_id": order_id, "p_reason": reason,
        })
        return result if isinstance(result, dict) else {"reversed": False}
    except Exception:
        logger.exception("ambassador reversal failed for order %s", order_id)
        return {"reversed": False}


# ---------------------------------------------------------------------------
# Ambassador tag
# ---------------------------------------------------------------------------
def tag_ambassador(actor_id: str, target_profile: dict) -> dict:
    db = get_db()
    existing = (
        db.table(AMBASSADOR_TABLE)
        .select("*").eq("profile_id", target_profile["id"]).single().execute()
    )
    if existing and existing.get("status") == "active":
        return {**existing, "unchanged": True}
    payload = {
        "profile_id": target_profile["id"],
        "campus_id": target_profile.get("campus_id"),
        "status": "active",
        "tagged_by": actor_id,
        "untagged_at": None,
    }
    if existing:
        row = db.table(AMBASSADOR_TABLE).update(payload).eq(
            "profile_id", target_profile["id"]).execute()
        row = row[0] if isinstance(row, list) else row
    else:
        row = db.table(AMBASSADOR_TABLE).insert(payload).execute()
        row = row[0] if isinstance(row, list) else row
    audit(actor_id, "ambassador_tagged", target_profile["id"],
          after={"profile_id": target_profile["id"]},
          campus_id=target_profile.get("campus_id"))
    return row


def untag_ambassador(actor_id: str, ambassador_id: str) -> dict:
    db = get_db()
    row = _active_ambassador(db, ambassador_id)
    updated = db.table(AMBASSADOR_TABLE).update({
        "status": "inactive", "untagged_at": datetime.now(timezone.utc).isoformat(),
    }).eq("profile_id", ambassador_id).execute()
    audit(actor_id, "ambassador_untagged", ambassador_id,
          before={"status": "active"}, campus_id=row.get("campus_id"))
    return (updated[0] if isinstance(updated, list) and updated else updated) or row


# ---------------------------------------------------------------------------
# Metrics
# ---------------------------------------------------------------------------
def _profile_basics(db, user_ids: list[str]) -> dict[str, dict]:
    if not user_ids:
        return {}
    rows = db.table("profiles").select(
        "id,full_name,nickname,phone,referral_code,campus_id,created_at"
    ).in_("id", user_ids).execute() or []
    return {r["id"]: r for r in rows}


def attributed_signups(db, ambassador_id: str, month: str | None = None) -> list[dict]:
    """Distinct customers whose FIRST recorded ambassador click is this ambassador's
    and whose account was created in the period (new-customer signups)."""
    q = db.table("ambassador_link_clicks").select(
        "visitor_user_id,created_at"
    ).eq("ambassador_id", ambassador_id)
    clicks = q.execute() or []
    visitor_ids = {c["visitor_user_id"] for c in clicks if c.get("visitor_user_id")}
    if not visitor_ids:
        return []
    profiles = db.table("profiles").select("id,created_at").in_(
        "id", list(visitor_ids)).execute() or []
    if month:
        start, end = month_bounds(month)
        profiles = [
            p for p in profiles
            if p.get("created_at") and start.isoformat() <= p["created_at"] <= end.isoformat()
        ]
    return profiles


def attributed_orders(db, ambassador_id: str, month: str | None = None,
                      eligible_only: bool = True) -> list[dict]:
    q = db.table("ambassador_order_attributions").select("*").eq(
        "ambassador_id", ambassador_id)
    if eligible_only:
        q = q.eq("eligibility", "eligible")
    rows = q.order("attributed_at", ascending=False).execute() or []
    if month:
        start, end = month_bounds(month)
        rows = [r for r in rows
                if r.get("attributed_at") and start.isoformat() <= r["attributed_at"] <= end.isoformat()]
    return rows


def assignment_metrics(db, ambassador_id: str, month: str) -> dict:
    rows = db.table("ambassador_promo_assignments").select(
        "id,status"
    ).eq("ambassador_id", ambassador_id).eq("month", month).execute() or []
    assigned = len(rows)
    shared = sum(1 for r in rows if r.get("status") == "shared")
    seen = sum(1 for r in rows if r.get("status") in ("seen", "shared"))
    rate = round((shared / assigned) * 100, 2) if assigned else 0.0
    # 4 shares/week expectation → target for the month's number of weeks.
    year, mon = map(int, month.split("-"))
    weeks = max(1, round(calendar.monthrange(year, mon)[1] / 7))
    target = weeks * 4
    return {
        "assigned_count": assigned,
        "seen_count": seen,
        "shared_count": shared,
        "completion_rate": rate,
        "weekly_share_target": 4,
        "monthly_share_target": target,
        "share_target_progress": round(min(100.0, (shared / target) * 100), 2) if target else 0.0,
    }


def milestone_metrics(db, ambassador_id: str, month: str) -> dict:
    return {
        "orders": len(attributed_orders(db, ambassador_id, month)),
        "signups": len(attributed_signups(db, ambassador_id, month)),
        "shares": assignment_metrics(db, ambassador_id, month)["shared_count"],
    }


def lifetime_metrics(db, ambassador_id: str) -> dict:
    orders = attributed_orders(db, ambassador_id)
    signups = attributed_signups(db, ambassador_id)
    return {
        "total_orders": len(orders),
        "total_signups": len(signups),
        "total_order_value": round(sum(float(o.get("order_total") or 0) for o in orders), 2),
    }


# ---------------------------------------------------------------------------
# Milestones
# ---------------------------------------------------------------------------
def list_milestones(db, campus_id: str | None, include_inactive: bool = False) -> list[dict]:
    rows = db.table("ambassador_milestones").select("*").order(
        "metric", ascending=True).order("threshold", ascending=True).execute() or []
    # Global (campus_id IS NULL) plus this campus's own.
    rows = [r for r in rows if r.get("campus_id") is None or r.get("campus_id") == campus_id]
    if not include_inactive:
        rows = [r for r in rows if r.get("is_active", True)]
    return rows


def _system_actor(db) -> dict | None:
    """The admin profile that authorizes milestone AUTO-issue grants.

    Returns None when the setting is missing/invalid rather than inventing an
    issuer: ambassador_grants.issued_by is a NOT NULL foreign key to profiles,
    and a reward must never appear without a real authorizing admin. Callers
    then fall back to the normal pending-approval/manual-grant flow.
    """
    actor_id = str(current_app.config.get("AMBASSADOR_SYSTEM_ACTOR_ID") or "").strip()
    if not actor_id or not validate_uuid(actor_id):
        return None
    profile = (
        db.table("profiles")
        .select("id,role,campus_id")
        .eq("id", actor_id)
        .single()
        .execute()
    )
    if not profile or profile.get("role") not in ADMIN_ROLES:
        logger.warning(
            "AMBASSADOR_SYSTEM_ACTOR_ID %s is not an admin profile; "
            "milestone auto-issue stays in manual approval", actor_id)
        return None
    return {"id": profile["id"], "role": profile["role"],
            "campus_id": profile.get("campus_id")}


def _auto_issue_milestone_grant(ambassador: dict, milestone: dict,
                                claim: dict, month: str) -> dict:
    """Issue the configured reward for an ``auto_issue`` milestone as soon as
    its claim is created, and mark the claim ``issued`` with the grant linked.

    This is a system action and deliberately runs on the service-role client
    (``get_db``), not the caller's user-scoped client: the ambassador tables
    are SELECT-only for authenticated users, and this path can be reached from
    a student's own dashboard read. The configured system actor profile is the
    authorization. Best effort: every failure leaves the claim in
    ``pending_approval`` for a manual decision instead of breaking the page. A
    same-month/category grant already existing (the duplicate guard) is the
    common case — an admin can still grant with the explicit override.
    """
    db = get_db()
    actor = _system_actor(db)
    if not actor:
        logger.info(
            "auto-issue milestone %s reached but no system actor is configured; "
            "claim %s stays pending_approval", milestone.get("id"), claim.get("id"))
        return claim
    try:
        grant = issue_grant(
            db, actor,
            ambassador_id=ambassador["profile_id"],
            category=milestone["reward_type"],
            amount=float(milestone["reward_amount"]),
            reason=f"Auto milestone {milestone['metric']} >= "
                   f"{milestone['threshold']} ({month})",
            month=month,
            validity_days=milestone.get("validity_days"),
            uses_count=milestone.get("reward_uses") or 1,
            source="milestone",
            milestone_claim_id=claim["id"],
        )
    except DuplicateGrant:
        logger.info(
            "auto-issue skipped for claim %s: a %s grant for %s already exists "
            "this month; manual override remains available",
            claim.get("id"), milestone.get("reward_type"), month)
        return claim
    except AmbassadorError:
        logger.exception("auto-issue failed for claim %s", claim.get("id"))
        return claim
    updated = db.table("ambassador_milestone_claims").update({
        "status": "issued",
        "grant_id": grant["id"],
        "decided_by": actor["id"],
        "decided_at": _iso(datetime.now(timezone.utc)),
        "decision_note": "Auto-issued by configured milestone rule",
    }).eq("id", claim["id"]).execute()
    rows = updated if isinstance(updated, list) else [updated]
    return rows[0] if rows else claim


def evaluate_milestones(db, ambassador_id: str, month: str | None = None) -> list[dict]:
    """Return each applicable milestone with live progress; create pending
    claims when a threshold is first reached in the programme month. A claim
    for an ``auto_issue`` milestone is immediately granted via the configured
    system actor; everything else waits for an admin decision."""
    month = parse_month(month)
    ambassador = _active_ambassador(db, ambassador_id)
    metrics = milestone_metrics(db, ambassador_id, month)
    milestones = list_milestones(db, ambassador.get("campus_id"))
    claims = db.table("ambassador_milestone_claims").select(
        "*"
    ).eq("ambassador_id", ambassador_id).eq("period_month", month).execute() or []
    claim_by_milestone = {c["milestone_id"]: c for c in claims}
    out = []
    for ms in milestones:
        value = metrics.get(ms["metric"], 0)
        reached = value >= int(ms["threshold"])
        claim = claim_by_milestone.get(ms["id"])
        if reached and not claim:
            claim = db.table("ambassador_milestone_claims").insert({
                "milestone_id": ms["id"],
                "ambassador_id": ambassador_id,
                "period_month": month,
                "metric_value_at_claim": value,
                "status": "pending_approval",
            }).execute()
            claim = claim[0] if isinstance(claim, list) else claim
            if ms.get("auto_issue"):
                # Best effort; any failure leaves the pending claim untouched.
                # The helper elevates to the service-role client itself.
                try:
                    claim = _auto_issue_milestone_grant(
                        ambassador, ms, claim, month)
                except Exception:
                    logger.exception(
                        "milestone auto-issue evaluation failed for claim %s",
                        claim.get("id"))
        out.append({
            "milestone": ms,
            "metric_value": value,
            "reached": reached,
            "claim": claim,
        })
    return out


# ---------------------------------------------------------------------------
# Monthly reviews
# ---------------------------------------------------------------------------
def build_review(db, ambassador_id: str, month: str) -> dict:
    month = parse_month(month)
    _active_ambassador(db, ambassador_id)  # validates the tag + campus access
    activity = assignment_metrics(db, ambassador_id, month)
    orders = attributed_orders(db, ambassador_id, month)
    signups = attributed_signups(db, ambassador_id, month)
    existing = db.table("ambassador_monthly_reviews").select("*").eq(
        "ambassador_id", ambassador_id).eq("month", month).single().execute()
    review = existing or {}
    review.update({
        "ambassador_id": ambassador_id,
        "month": month,
        **activity,
        "signups_count": len(signups),
        "orders_count": len(orders),
        "milestones": evaluate_milestones(db, ambassador_id, month),
    })
    return review


def persist_review_metrics(db, ambassador_id: str, month: str) -> dict:
    """Upsert the computed counters so the review row always reflects the records."""
    data = build_review(db, ambassador_id, month)
    payload = {k: data[k] for k in (
        "assigned_count", "seen_count", "shared_count", "completion_rate",
        "signups_count", "orders_count")}
    existing = db.table("ambassador_monthly_reviews").select("id").eq(
        "ambassador_id", ambassador_id).eq("month", month).single().execute()
    if existing:
        db.table("ambassador_monthly_reviews").update(payload).eq("id", existing["id"]).execute()
    else:
        db.table("ambassador_monthly_reviews").insert({
            "ambassador_id": ambassador_id, "month": month, **payload,
        }).execute()
    return data


def list_monthly_reviews(db, month: str, campus_id: str | None,
                         is_super: bool) -> list[dict]:
    month = parse_month(month)
    q = db.table(AMBASSADOR_TABLE).select("*").eq("status", "active")
    ambassadors = q.execute() or []
    if not is_super:
        ambassadors = [a for a in ambassadors if a.get("campus_id") == campus_id]
    reviews = []
    for amb in ambassadors:
        reviews.append(persist_review_metrics(db, amb["profile_id"], month))
    return reviews


def submit_recommendation(db, actor_id: str, ambassador_id: str, month: str,
                          recommendation: str, note: str) -> dict:
    if recommendation not in ("recommend", "do_not_recommend"):
        raise AmbassadorError(MSG.AMBASSADOR_INVALID_RECOMMENDATION)
    month = parse_month(month)
    _active_ambassador(db, ambassador_id)
    persist_review_metrics(db, ambassador_id, month)
    existing = db.table("ambassador_monthly_reviews").select("id").eq(
        "ambassador_id", ambassador_id).eq("month", month).single().execute()
    patch = {
        "recommendation": recommendation,
        "recommendation_note": (note or "")[:1000],
        "recommended_by": actor_id,
        "recommended_at": datetime.now(timezone.utc).isoformat(),
    }
    if existing:
        db.table("ambassador_monthly_reviews").update(patch).eq("id", existing["id"]).execute()
    else:
        db.table("ambassador_monthly_reviews").insert({
            "ambassador_id": ambassador_id, "month": month, **patch,
        }).execute()
    audit(actor_id, "ambassador_recommendation", ambassador_id,
          after={"month": month, "recommendation": recommendation})
    return build_review(db, ambassador_id, month)


def record_decision(db, actor_id: str, ambassador_id: str, month: str,
                    decision: str, note: str) -> dict:
    if decision not in ("approved", "rejected"):
        raise AmbassadorError(MSG.AMBASSADOR_INVALID_DECISION)
    month = parse_month(month)
    _active_ambassador(db, ambassador_id)
    existing = db.table("ambassador_monthly_reviews").select("id").eq(
        "ambassador_id", ambassador_id).eq("month", month).single().execute()
    patch = {
        "decision": decision,
        "decision_note": (note or "")[:1000],
        "decided_by": actor_id,
        "decided_at": datetime.now(timezone.utc).isoformat(),
    }
    if existing:
        db.table("ambassador_monthly_reviews").update(patch).eq("id", existing["id"]).execute()
    else:
        db.table("ambassador_monthly_reviews").insert({
            "ambassador_id": ambassador_id, "month": month, **patch,
        }).execute()
    audit(actor_id, "ambassador_decision", ambassador_id,
          after={"month": month, "decision": decision})
    return build_review(db, ambassador_id, month)


# ---------------------------------------------------------------------------
# Promotional distribution + manual activity tracking
# ---------------------------------------------------------------------------
def personalize_caption(caption: str, link: str) -> str:
    out = caption or ""
    for token in LINK_PLACEHOLDERS:
        out = out.replace(token, link)
    return out


def create_promo_message(db, actor: dict, *, image_url: str, caption: str,
                         target_all: bool, ambassador_ids: list[str],
                         month: str) -> dict:
    caption = (caption or "").strip()
    if not caption:
        raise AmbassadorError(MSG.AMBASSADOR_PROMO_CAPTION_REQUIRED)
    if not any(token in caption for token in LINK_PLACEHOLDERS):
        raise AmbassadorError(MSG.AMBASSADOR_PROMO_LINK_PLACEHOLDER_REQUIRED)
    month = parse_month(month)
    is_super = actor.get("role") == "super_admin"
    q = db.table(AMBASSADOR_TABLE).select("*").eq("status", "active")
    ambassadors = q.execute() or []
    if not is_super:
        ambassadors = [a for a in ambassadors
                       if a.get("campus_id") == actor.get("campus_id")]
    if target_all:
        targets = ambassadors
    else:
        wanted = set(ambassador_ids or [])
        targets = [a for a in ambassadors if a["profile_id"] in wanted]
        if not targets:
            raise AmbassadorError(MSG.AMBASSADOR_PROMO_NO_TARGETS)
    message = db.table("ambassador_promo_messages").insert({
        "created_by": actor["id"],
        "campus_id": None if is_super else actor.get("campus_id"),
        "image_url": image_url or None,
        "caption": caption,
        "target_all": bool(target_all),
        "month": month,
    }).execute()
    message = message[0] if isinstance(message, list) else message
    assignment_rows = [{
        "message_id": message["id"],
        "ambassador_id": a["profile_id"],
        "month": month,
        "status": "pending",
    } for a in targets]
    # Insert in batches to stay within PostgREST payload limits.
    for i in range(0, len(assignment_rows), 500):
        db.table("ambassador_promo_assignments").insert(assignment_rows[i:i + 500]).execute()
    audit(actor["id"], "ambassador_promo_created", message["id"],
          after={"recipients": len(targets), "month": month},
          campus_id=message.get("campus_id"))
    return {"message": message, "recipient_count": len(targets),
            "ambassador_ids": [a["profile_id"] for a in targets]}


def list_promo_messages(db, month: str, campus_id: str | None, is_super: bool) -> list[dict]:
    month = parse_month(month)
    rows = db.table("ambassador_promo_messages").select("*").eq(
        "month", month).order("created_at", ascending=False).execute() or []
    if not is_super:
        rows = [r for r in rows if r.get("campus_id") is None or r.get("campus_id") == campus_id]
    return rows


def promo_assignments(db, message_id: str) -> list[dict]:
    rows = db.table("ambassador_promo_assignments").select("*").eq(
        "message_id", message_id).execute() or []
    ids = [r["ambassador_id"] for r in rows]
    profiles = _profile_basics(db, ids)
    for r in rows:
        r["profile"] = profiles.get(r["ambassador_id"], {})
    return rows


def set_assignment_status(db, actor_id: str, assignment_id: str,
                          status: str, evidence_note: str | None) -> dict:
    if status not in ASSIGNMENT_STATUSES:
        raise AmbassadorError(MSG.AMBASSADOR_INVALID_STATUS)
    row = db.table("ambassador_promo_assignments").select("*").eq(
        "id", assignment_id).single().execute()
    if not row:
        raise AmbassadorError(MSG.AMBASSADOR_ASSIGNMENT_NOT_FOUND, status=404)
    ambassador = db.table(AMBASSADOR_TABLE).select("*").eq(
        "profile_id", row["ambassador_id"]).single().execute()
    assert_campus_access(ambassador)
    patch = {"status": status, "updated_by": actor_id}
    if evidence_note is not None:
        patch["evidence_note"] = evidence_note[:500]
    updated = db.table("ambassador_promo_assignments").update(patch).eq(
        "id", assignment_id).execute()
    audit(actor_id, "ambassador_promo_status", assignment_id,
          after={"status": status}, campus_id=ambassador.get("campus_id"))
    return (updated[0] if isinstance(updated, list) and updated else updated) or row


# ---------------------------------------------------------------------------
# Meal discounts — checkout validation/redemption
# ---------------------------------------------------------------------------
def sweep_expired_discounts(db) -> int:
    try:
        return int(db.rpc("hg_expire_ambassador_discounts") or 0)
    except Exception:
        logger.warning("ambassador discount expiry sweep failed", exc_info=True)
        return 0


def list_my_discounts(db, user_id: str) -> list[dict]:
    sweep_expired_discounts(db)
    return db.table("ambassador_meal_discounts").select("*").eq(
        "ambassador_id", user_id).order("expires_at", ascending=True).execute() or []


def resolve_discount_for_checkout(db, user_id: str, discount_id: str) -> dict:
    """Validate ownership, status, expiry and remaining uses. Raises ValueError
    with a user-facing message on any failure so checkout can reject cleanly."""
    sweep_expired_discounts(db)
    discount = db.table("ambassador_meal_discounts").select("*").eq(
        "id", discount_id).single().execute()
    if not discount or discount.get("ambassador_id") != user_id:
        raise AmbassadorError(MSG.MEAL_DISCOUNT_NOT_FOUND, status=404)
    if discount.get("status") == "voided":
        raise AmbassadorError(MSG.MEAL_DISCOUNT_VOIDED)
    if discount.get("status") == "expired":
        raise AmbassadorError(MSG.MEAL_DISCOUNT_EXPIRED)
    if int(discount.get("uses_remaining") or 0) <= 0:
        raise AmbassadorError(MSG.MEAL_DISCOUNT_NO_USES)
    return discount


def compute_discount_amount(discount: dict, order_items: list[dict],
                            subtotal_dec: Decimal,
                            existing_food_discount_dec: Decimal) -> Decimal:
    """The discount covers ONE meal up to max_meal_value, never touches delivery,
    and can never push the food total below zero."""
    unit_prices = [Decimal(str(i.get("price_snapshot") or 0)) for i in order_items]
    priciest = max(unit_prices, default=Decimal("0"))
    cap = Decimal(str(discount["max_meal_value"]))
    headroom = max(Decimal("0"), subtotal_dec - existing_food_discount_dec)
    amount = min(cap, priciest, headroom)
    return amount.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def redeem_discount(db, discount_id: str, order_id: str, user_id: str,
                    amount: Decimal, meal_item_id: str | None) -> dict:
    result = db.rpc("hg_redeem_ambassador_meal_discount", {
        "p_discount_id": discount_id,
        "p_order_id": order_id,
        "p_ambassador_id": user_id,
        "p_amount": float(amount),
        "p_meal_item_id": meal_item_id,
    })
    if isinstance(result, dict) and result.get("error"):
        raise AmbassadorError(result["error"])
    return result if isinstance(result, dict) else {"redeemed": True}


def restore_discount_for_order(db, order_id: str) -> dict:
    try:
        return db.rpc("hg_restore_ambassador_meal_discount", {"p_order_id": order_id})
    except Exception:
        logger.warning("meal discount restore failed for order %s", order_id, exc_info=True)
        return {"restored": False}


# ---------------------------------------------------------------------------
# Reward granting (financial admins only; enforced at the route layer too)
# ---------------------------------------------------------------------------
_GRANT_NS = uuid.UUID("7c2e4f51-9b13-4d6f-8a25-0f6d9b3c7e11")


def _grant_idempotency_key(actor_id, ambassador_id, month, category, amount, override):
    raw = "|".join(map(str, (actor_id, ambassador_id, month, category, amount, override)))
    return str(uuid.uuid5(_GRANT_NS, raw))


def issue_grant(db, actor: dict, *, ambassador_id: str, category: str, amount: float,
                reason: str, month: str, validity_days: int = None,
                uses_count: int = 1, source: str = "manual",
                milestone_claim_id: str = None, override: bool = False) -> dict:
    if category not in GRANT_CATEGORIES:
        raise AmbassadorError(MSG.AMBASSADOR_INVALID_GRANT_CATEGORY)
    month = parse_month(month)
    reason = (reason or "").strip()
    if not reason:
        raise AmbassadorError(MSG.AMBASSADOR_GRANT_REASON_REQUIRED)
    amount = float(amount)
    if amount <= 0:
        raise AmbassadorError(MSG.AMBASSADOR_GRANT_AMOUNT_INVALID)
    ambassador = _active_ambassador(db, ambassador_id)
    uses_count = max(1, int(uses_count or 1))

    # Accidental-duplicate guard. The partial unique index
    # uq_amb_grant_month_category is the hard backstop; this pre-check gives a
    # clean 409. An intentional extra grant sets override=true.
    existing = db.table("ambassador_grants").select("id").eq(
        "ambassador_id", ambassador_id).eq("month", month).eq(
        "reward_category", category).eq("duplicate_override", False).execute() or []
    if existing and not override:
        raise DuplicateGrant(MSG.AMBASSADOR_GRANT_DUPLICATE)

    idem = _grant_idempotency_key(
        actor["id"], ambassador_id, month, category, amount, override)
    grant_row = {
        "ambassador_id": ambassador_id,
        "month": month,
        "reward_category": category,
        "amount": amount,
        "uses_count": uses_count,
        "reason": reason[:500],
        "source": source if source in ("manual", "monthly_review", "milestone") else "manual",
        "milestone_claim_id": milestone_claim_id,
        "duplicate_override": bool(override),
        "idempotency_key": idem,
        "issued_by": actor["id"],
    }

    if category == "hp":
        grant = db.table("ambassador_grants").insert(grant_row).execute()
        grant = grant[0] if isinstance(grant, list) else grant
        from app.services.hp_service import award_active_hp
        award_active_hp(
            user_id=ambassador_id, amount=int(amount),
            txn_type="earn", reference_id=grant["id"],
            reference_type="ambassador_grant",
            notes=f"Ambassador programme grant ({month}): {reason}",
            issued_by_admin_id=actor["id"], apply_multiplier=False,
            campus_id=ambassador.get("campus_id"),
        )
        txn = db.table("hp_transactions").select("id").eq(
            "user_id", ambassador_id).eq("reference_id", grant["id"]).single().execute()
        if txn:
            db.table("ambassador_grants").update(
                {"hp_transaction_id": txn["id"]}).eq("id", grant["id"]).execute()
            grant["hp_transaction_id"] = txn["id"]

    elif category == "free_side":
        validity_days = int(validity_days or setting_or_config(
            db, "free_side_credits_validity_days", 60, minimum=1, maximum=365))
        grant_row["validity_days"] = validity_days
        grant = db.table("ambassador_grants").insert(grant_row).execute()
        grant = grant[0] if isinstance(grant, list) else grant
        intent = str(uuid.uuid4())
        result = db.rpc("hg_grant_free_sides_atomic", {
            "p_actor_id": actor["id"], "p_user_id": ambassador_id,
            "p_intent_key": intent, "p_credits": int(amount),
            "p_days": validity_days,
            "p_reason": f"Ambassador programme ({month}): {reason}"[:200],
        })
        if isinstance(result, dict) and result.get("error"):
            db.table("ambassador_grants").update(
                {"status": "voided"}).eq("id", grant["id"]).execute()
            raise AmbassadorError(str(result["error"]))
        if isinstance(result, dict) and result.get("credit_id"):
            db.table("ambassador_grants").update(
                {"free_side_grant_id": result["credit_id"]}).eq("id", grant["id"]).execute()
            grant["free_side_grant_id"] = result["credit_id"]

    else:  # meal_discount
        validity_days = int(validity_days or setting_or_config(
            db, "ambassador_meal_discount_default_validity", 14, minimum=1, maximum=365))
        grant_row["validity_days"] = validity_days
        grant = db.table("ambassador_grants").insert(grant_row).execute()
        grant = grant[0] if isinstance(grant, list) else grant
        discount = db.rpc("hg_grant_ambassador_meal_discount", {
            "p_actor_id": actor["id"],
            "p_ambassador_id": ambassador_id,
            "p_max_meal_value": amount,
            "p_uses": uses_count,
            "p_validity_days": validity_days,
            "p_grant_id": grant["id"],
            "p_source_note": f"{source} ({month}): {reason}"[:500],
        })
        if isinstance(discount, dict) and discount.get("error"):
            db.table("ambassador_grants").update(
                {"status": "voided"}).eq("id", grant["id"]).execute()
            raise AmbassadorError(str(discount["error"]))
        if isinstance(discount, dict) and discount.get("id"):
            grant["meal_discount_id"] = discount["id"]

    audit(actor["id"], f"ambassador_grant_{category}", ambassador_id,
          after={"grant_id": grant["id"], "amount": amount, "month": month},
          campus_id=ambassador.get("campus_id"))
    try:
        from app.services.notification_service import send_notification
        send_notification(
            ambassador_id, "ambassador_grant_issued",
            title="Ambassador reward approved",
            body=f"Your {category.replace('_', ' ')} reward for {month} has been issued.",
            reference_id=grant["id"], reference_type="ambassador_grant",
            campus_id=ambassador.get("campus_id"))
    except Exception:
        logger.warning("ambassador grant notification failed", exc_info=True)
    return grant


def list_grants(db, ambassador_id: str | None = None) -> list[dict]:
    q = db.table("ambassador_grants").select("*").order("issued_at", ascending=False)
    if ambassador_id:
        q = q.eq("ambassador_id", ambassador_id)
    return q.execute() or []


# ---------------------------------------------------------------------------
# Ambassador self-service dashboard payload
# ---------------------------------------------------------------------------
def ambassador_dashboard(db, user_id: str, frontend_url: str) -> dict | None:
    tag = db.table(AMBASSADOR_TABLE).select("*").eq(
        "profile_id", user_id).eq("status", "active").single().execute()
    if not tag:
        return None
    month = current_month()
    profile = db.table("profiles").select(
        "id,full_name,nickname,referral_code,campus_id"
    ).eq("id", user_id).single().execute() or {}
    code = profile.get("referral_code")
    lifetime = lifetime_metrics(db, user_id)
    month_metrics = milestone_metrics(db, user_id, month)
    activity = assignment_metrics(db, user_id, month)
    milestones = evaluate_milestones(db, user_id, month)
    discounts = list_my_discounts(db, user_id)
    redemptions = db.table("ambassador_meal_discount_redemptions").select(
        "*"
    ).eq("ambassador_id", user_id).order("created_at", ascending=False).execute() or []
    # Existing referral HP stays in the normal referrals system — read-only here.
    referral_rows = db.table("referrals").select(
        "hp_awarded,status"
    ).eq("referrer_id", user_id).execute() or []
    referral_hp = sum(int(r.get("hp_awarded") or 0) for r in referral_rows)
    attribution = db.table("ambassador_attributions").select("*").eq(
        "customer_user_id", user_id).single().execute()
    return {
        "is_ambassador": True,
        "month": month,
        "referral_code": code,
        "tracking_link": f"{frontend_url}?ref={code}" if code else None,
        "lifetime": lifetime,
        "month_activity": {**activity, **month_metrics},
        "milestones": milestones,
        "meal_discounts": discounts,
        "meal_discount_redemptions": redemptions,
        "referral_hp_earned": referral_hp,
        "attribution_window": attribution,
    }


def staff_ambassador_list(db, campus_id: str | None, is_super: bool) -> list[dict]:
    """Ambassador roster with the totals the promo/distribution page shows."""
    rows = db.table(AMBASSADOR_TABLE).select("*").eq("status", "active").execute() or []
    if not is_super:
        rows = [r for r in rows if r.get("campus_id") == campus_id]
    ids = [r["profile_id"] for r in rows]
    profiles = _profile_basics(db, ids)
    month = current_month()
    out = []
    for r in rows:
        p = profiles.get(r["profile_id"], {})
        lifetime = lifetime_metrics(db, r["profile_id"])
        monthly = milestone_metrics(db, r["profile_id"], month)
        activity = assignment_metrics(db, r["profile_id"], month)
        code = p.get("referral_code")
        out.append({
            "ambassador": r,
            "profile": p,
            "tracking_link": f"{_frontend_base()}?ref={code}" if code else None,
            "lifetime": lifetime,
            "month": {**activity, **monthly},
        })
    return out


def _frontend_base() -> str:
    try:
        from flask import current_app
        return current_app.config.get("FRONTEND_URL", "")
    except Exception:
        return ""
