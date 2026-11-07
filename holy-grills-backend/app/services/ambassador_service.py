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
import re
from copy import deepcopy
from datetime import datetime, timezone, timedelta
from decimal import Decimal, ROUND_HALF_UP

from flask import current_app, g, has_request_context, request

from app.constants import ADMIN_ROLES
from app.db import get_db, SupabaseError
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
    if month is not None and not isinstance(month, str):
        raise AmbassadorError(MSG.AMBASSADOR_INVALID_MONTH)
    month = (month or "").strip() or current_month()
    if not re.fullmatch(r"[0-9]{4}-(0[1-9]|1[0-2])", month):
        raise AmbassadorError(MSG.AMBASSADOR_INVALID_MONTH)
    try:
        datetime.strptime(month, "%Y-%m")
    except ValueError:
        raise AmbassadorError(MSG.AMBASSADOR_INVALID_MONTH)
    return month


def _request_read(db, key, read):
    """Reuse metric reads only within this request and authorization scope."""
    if not has_request_context():
        return read()
    current_request = request._get_current_object()
    cache = getattr(g, '_ambassador_metric_reads', None)
    if cache is None or getattr(g, '_ambassador_metric_request', None) is not current_request:
        cache = g._ambassador_metric_reads = {}
        g._ambassador_metric_request = current_request
    scoped = (id(db), getattr(g, 'user_id', None), getattr(g, 'user_role', None),
              getattr(g, 'campus_id', None), key)
    if scoped not in cache:
        cache[scoped] = read()
    return deepcopy(cache[scoped])


def _invalidate_metric_reads():
    if has_request_context():
        g.pop('_ambassador_metric_reads', None)


def month_bounds(month: str) -> tuple[datetime, datetime]:
    year, mon = map(int, month.split("-"))
    start = datetime(year, mon, 1, tzinfo=timezone.utc)
    last_day = calendar.monthrange(year, mon)[1]
    end = datetime(year, mon, last_day, 23, 59, 59, 999999, tzinfo=timezone.utc)
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
    _invalidate_metric_reads()
    result = get_db().rpc("hg_ambassador_record_click", {
        "p_ref_code": str(ref_code).strip(),
        "p_visitor_user_id": visitor_user_id,
        "p_anonymous_id": anonymous_id,
        "p_campus_id": campus_id,
    })
    return result if isinstance(result, dict) else {"attributed": False}


def merge_visitor(anonymous_id: str, user_id: str) -> dict:
    _invalidate_metric_reads()
    result = get_db().rpc("hg_ambassador_merge_visitor", {
        "p_anonymous_id": anonymous_id,
        "p_user_id": user_id,
    })
    return result if isinstance(result, dict) else {"adopted_clicks": 0, "attributed": False}


def attribute_delivered_order(order_id: str) -> dict:
    """Called from the order lifecycle when an order reaches 'delivered'."""
    try:
        _invalidate_metric_reads()
        result = get_db().rpc("hg_ambassador_attribute_order", {"p_order_id": order_id})
        return result if isinstance(result, dict) else {"attributed": False}
    except Exception:
        logger.exception("ambassador attribution failed for order %s", order_id)
        return {"attributed": False, "error": "attribution_failed"}


def reverse_attributed_order(order_id: str, reason: str = "order_refunded") -> dict:
    try:
        _invalidate_metric_reads()
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
        row = db.table(AMBASSADOR_TABLE).eq(
            "profile_id", target_profile["id"]).update(payload).execute()
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
    updated = db.table(AMBASSADOR_TABLE).eq("profile_id", ambassador_id).update({
        "status": "inactive", "untagged_at": datetime.now(timezone.utc).isoformat(),
    }).execute()
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


def _instant(value):
    try:
        parsed = datetime.fromisoformat(str(value).replace('Z', '+00:00'))
        return (parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)).astimezone(timezone.utc)
    except (TypeError, ValueError):
        return None


def _attributed_signups(db, ambassador_id: str) -> list[dict]:
    """New accounts whose first qualifying pre-signup click belongs here.

    Existing users clicking an ambassador link are attributed customers/orders,
    never new signups. Count once across ambassadors, within the click window.
    """
    clicks = db.table("ambassador_link_clicks").select(
        "visitor_user_id,created_at").eq("ambassador_id", ambassador_id).execute() or []
    visitor_ids = {row['visitor_user_id'] for row in clicks if row.get('visitor_user_id')}
    if not visitor_ids: return []
    profiles = db.table("profiles").select("id,created_at").in_("id",list(visitor_ids)).execute() or []
    trail = db.table("ambassador_link_clicks").select(
        "id,ambassador_id,visitor_user_id,created_at").in_("visitor_user_id",list(visitor_ids)).execute() or []
    days = int(setting_or_config(db,'ambassador_attribution_window_days',7,minimum=1,maximum=365))
    result=[]
    for profile in profiles:
        created=_instant(profile.get('created_at'))
        if created is None: continue
        qualifying=[]
        for click in trail:
            clicked=_instant(click.get('created_at'))
            if click.get('visitor_user_id')==profile['id'] and click.get('ambassador_id') != profile['id'] and clicked and created-timedelta(days=days) <= clicked <= created:
                qualifying.append((clicked,str(click.get('id') or ''),click))
        first=min(qualifying,key=lambda entry:(entry[0],entry[1]))[2] if qualifying else None
        if first and first.get('ambassador_id')==ambassador_id: result.append(profile)
    return result


def attributed_signups(db, ambassador_id: str, month: str | None = None) -> list[dict]:
    rows = _request_read(db, ('signups', ambassador_id), lambda: _attributed_signups(db, ambassador_id))
    return [row for row in rows if _instant(row.get('created_at')).strftime('%Y-%m') == month] if month else rows


def attributed_orders(db, ambassador_id: str, month: str | None = None,
                      eligible_only: bool = True) -> list[dict]:
    q = db.table("ambassador_order_attributions").select("*").eq(
        "ambassador_id", ambassador_id)
    if eligible_only:
        q = q.eq("eligibility", "eligible")
    rows = _request_read(db, ('orders', ambassador_id, eligible_only),
                         lambda: q.order('attributed_at', ascending=False).execute() or [])
    if month:
        start, end = month_bounds(month)
        rows = [r for r in rows
                if _instant(r.get("attributed_at")) is not None and start <= _instant(r["attributed_at"]) <= end]
    return rows


def _assignment_metrics(db, ambassador_id: str, month: str) -> dict:
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


def assignment_metrics(db, ambassador_id: str, month: str) -> dict:
    return _request_read(db, ('activity', ambassador_id, month), lambda: _assignment_metrics(db, ambassador_id, month))


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


def _system_actor(db, creator_id=None) -> dict | None:
    """The admin profile that authorizes milestone AUTO-issue grants.

    Returns None when the setting is missing/invalid rather than inventing an
    issuer: ambassador_grants.issued_by is a NOT NULL foreign key to profiles,
    and a reward must never appear without a real authorizing admin. Callers
    then fall back to the normal pending-approval/manual-grant flow.
    """
    actor_id = str(current_app.config.get("AMBASSADOR_SYSTEM_ACTOR_ID") or creator_id or "").strip()
    if not actor_id or not validate_uuid(actor_id):
        return None
    profile = (
        db.table("profiles")
        .select("id,role,campus_id,is_active")
        .eq("id", actor_id)
        .single()
        .execute()
    )
    if not profile or profile.get("is_active") is False or profile.get("role") not in ADMIN_ROLES:
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
    actor = _system_actor(db, milestone.get("created_by"))
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
    return {**claim, "status": "issued", "grant_id": grant["id"],
            "decided_by": actor["id"], "decided_at": _iso(datetime.now(timezone.utc))}


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
            try:
                claim = db.table("ambassador_milestone_claims").insert({
                    "milestone_id": ms["id"],
                    "ambassador_id": ambassador_id,
                    "period_month": month,
                    "metric_value_at_claim": value,
                    "status": "pending_approval",
                }).execute()
                claim = claim[0] if isinstance(claim, list) else claim
            except SupabaseError as error:
                if str((error.details or {}).get('code')) != '23505': raise
                claim = db.table('ambassador_milestone_claims').select('*').eq(
                    'ambassador_id',ambassador_id).eq('milestone_id',ms['id']).eq('period_month',month).single().execute()
        if reached and claim and claim.get("status") == "pending_approval" and ms.get("auto_issue"):
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
    review = {"recommendation": "none", "decision": "pending", **(existing or {})}
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
    existing = db.table("ambassador_monthly_reviews").select("id,assigned_count,seen_count,shared_count,completion_rate,signups_count,orders_count").eq(
        "ambassador_id", ambassador_id).eq("month", month).single().execute()
    if existing:
        if any(existing.get(key) != value for key, value in payload.items()):
            db.table("ambassador_monthly_reviews").eq("id", existing["id"]).update(payload).execute()
    else:
        db.table("ambassador_monthly_reviews").insert({
            "ambassador_id": ambassador_id, "month": month, **payload,
        }).execute()
    return data


def list_monthly_reviews(db, month: str, campus_id: str | None,
                         is_super: bool) -> list[dict]:
    month = parse_month(month)
    q = db.table(AMBASSADOR_TABLE).select("*").eq("status", "active")
    if campus_id or not is_super:
        q = q.eq("campus_id", campus_id)
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
        db.table("ambassador_monthly_reviews").eq("id", existing["id"]).update(patch).execute()
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
        db.table("ambassador_monthly_reviews").eq("id", existing["id"]).update(patch).execute()
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
                         month: str, request_id: str | None = None) -> dict:
    caption = (caption or "").strip()
    if not caption:
        raise AmbassadorError(MSG.AMBASSADOR_PROMO_CAPTION_REQUIRED)
    if not any(token in caption for token in LINK_PLACEHOLDERS):
        raise AmbassadorError(MSG.AMBASSADOR_PROMO_LINK_PLACEHOLDER_REQUIRED)
    if not isinstance(target_all, bool) or not isinstance(ambassador_ids, list) or any(not validate_uuid(value) for value in ambassador_ids):
        raise AmbassadorError(MSG.AUTH_FIELD_INVALID.format(field='target_all / ambassador_ids'))
    if request_id is not None and not validate_uuid(request_id):
        raise AmbassadorError(MSG.AUTH_FIELD_INVALID.format(field='request_id'))
    month = parse_month(month)
    result = db.rpc('hg_create_ambassador_promo_atomic', {
        'p_actor_id': actor['id'], 'p_message_id': request_id or str(uuid.uuid4()),
        'p_campus_id': actor.get('campus_id'), 'p_caption': caption,
        'p_image_url': image_url or None, 'p_month': month,
        'p_target_all': target_all, 'p_ambassador_ids': sorted(set(ambassador_ids)),
    })
    error = result.get('error') if isinstance(result, dict) else None
    if error == 'promo_no_targets':
        raise AmbassadorError(MSG.AMBASSADOR_PROMO_NO_TARGETS)
    if error == 'promo_forbidden':
        raise AmbassadorError(MSG.RESOURCE_ACCESS_DENIED, status=403)
    if error == 'promo_intent_conflict':
        raise AmbassadorError(MSG.AMBASSADOR_PROMO_CONFLICT, status=409)
    if error:
        raise AmbassadorError(MSG.AUTH_FIELD_INVALID.format(field='promotional message'))
    if not isinstance(result, dict) or not (result.get('message') or {}).get('id'):
        raise AmbassadorError(MSG.SERVICE_UNAVAILABLE, status=503)
    _invalidate_metric_reads()
    if not result.get('idempotent'):
        audit(actor['id'], 'ambassador_promo_created', result['message']['id'],
              after={'recipients': result['recipient_count'], 'month': month},
              campus_id=result['message'].get('campus_id'))
    return result


def list_promo_messages(db, month: str, campus_id: str | None, is_super: bool) -> list[dict]:
    month = parse_month(month)
    rows = db.table("ambassador_promo_messages").select("*").eq(
        "month", month).order("created_at", ascending=False).execute() or []
    if campus_id or not is_super:
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
    if not ambassador:
        raise AmbassadorError(MSG.AMBASSADOR_NOT_FOUND, status=404)
    assert_campus_access(ambassador)
    patch = {"status": status, "updated_by": actor_id}
    if evidence_note is not None:
        patch["evidence_note"] = evidence_note[:500]
    updated = db.table("ambassador_promo_assignments").eq(
        "id", assignment_id).update(patch).execute()
    if not updated:
        raise AmbassadorError(MSG.AMBASSADOR_ASSIGNMENT_NOT_FOUND, status=404)
    _invalidate_metric_reads()
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


def _effective_discount(row):
    value = dict(row)
    if value.get('status') == 'active':
        try:
            expiry = datetime.fromisoformat(str(value.get('expires_at')).replace('Z', '+00:00'))
            if expiry.tzinfo is None:
                expiry = expiry.replace(tzinfo=timezone.utc)
            expired = expiry <= datetime.now(timezone.utc)
        except (TypeError, ValueError):
            expired = True
        if expired:
            value['status'] = 'expired'
        elif int(value.get('uses_remaining') or 0) <= 0:
            value['status'] = 'redeemed'
    return value


def list_my_discounts(db, user_id: str) -> list[dict]:
    rows = db.table("ambassador_meal_discounts").select("*").eq(
        "ambassador_id", user_id).order("expires_at", ascending=True).execute() or []
    return [_effective_discount(row) for row in rows]


def resolve_discount_for_checkout(db, user_id: str, discount_id: str) -> dict:
    discount = db.table("ambassador_meal_discounts").select("*").eq(
        "id", discount_id).single().execute()
    if not discount or discount.get("ambassador_id") != user_id:
        raise AmbassadorError(MSG.MEAL_DISCOUNT_NOT_FOUND, status=404)
    discount = _effective_discount(discount)
    if discount.get("status") == "voided":
        raise AmbassadorError(MSG.MEAL_DISCOUNT_VOIDED)
    if discount.get("status") == "expired":
        raise AmbassadorError(MSG.MEAL_DISCOUNT_EXPIRED)
    if discount.get("status") != "active" or int(discount.get("uses_remaining") or 0) <= 0:
        raise AmbassadorError(MSG.MEAL_DISCOUNT_NO_USES)
    return discount


def compute_discount_amount(discount: dict, order_items: list[dict],
                            subtotal_dec: Decimal,
                            existing_food_discount_dec: Decimal) -> Decimal:
    """The discount covers ONE meal up to max_meal_value, never touches delivery,
    and can never push the food total below zero."""
    unit_prices = [Decimal(str(i.get("price_snapshot") or 0)) for i in order_items if not i.get("is_addon") and i.get("menu_item_id")]
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


def _grant_integer(value, default, maximum):
    value = default if value is None else value
    try:
        number = Decimal(str(value))
        if isinstance(value, bool) or not number.is_finite() or number != number.to_integral_value() or not 1 <= number <= maximum:
            raise ValueError()
        return int(number)
    except Exception:
        raise AmbassadorError(MSG.AMBASSADOR_GRANT_TERMS_INVALID)


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
    if isinstance(amount, bool):
        raise AmbassadorError(MSG.AMBASSADOR_GRANT_AMOUNT_INVALID)
    amount = float(amount)
    if not Decimal(str(amount)).is_finite() or amount <= 0:
        raise AmbassadorError(MSG.AMBASSADOR_GRANT_AMOUNT_INVALID)
    ambassador = _active_ambassador(db, ambassador_id)
    uses_count = _grant_integer(uses_count, 1, 100)
    if not isinstance(override, bool):
        raise AmbassadorError(MSG.AMBASSADOR_GRANT_TERMS_INVALID)
    if milestone_claim_id is not None and not validate_uuid(milestone_claim_id):
        raise AmbassadorError(MSG.AMBASSADOR_GRANT_TERMS_INVALID)

    # Accidental-duplicate guard. The partial unique index
    # uq_amb_grant_month_category is the hard backstop; this pre-check gives a
    # clean 409. An intentional extra grant sets override=true.

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

    if not Decimal(str(amount)).is_finite() or amount > 1000000 or (category == 'meal_discount' and Decimal(str(amount)).quantize(Decimal('0.01')) != Decimal(str(amount))) or (category in ('hp','free_side') and amount != int(amount)) or (category == 'free_side' and amount > 20):
        raise AmbassadorError(MSG.AMBASSADOR_GRANT_AMOUNT_INVALID)
    default_days = setting_or_config(
        db, 'free_side_credits_validity_days' if category == 'free_side' else 'ambassador_meal_discount_default_validity',
        60 if category == 'free_side' else 14, minimum=1, maximum=365) if validity_days is None else None
    validity_days = _grant_integer(validity_days, default_days, 365)
    # Include all terms, so an intentional later override is distinct while a
    # retry of the same operation resolves the committed receipt.
    idem = str(uuid.uuid5(_GRANT_NS, '|'.join(map(str, (idem, reason, validity_days, uses_count, source, milestone_claim_id)))))
    grant = db.rpc('hg_issue_ambassador_grant_atomic', {
        'p_actor_id': actor['id'], 'p_ambassador_id': ambassador_id,
        'p_category': category, 'p_amount': amount, 'p_month': month,
        'p_reason': reason[:500], 'p_validity_days': validity_days, 'p_uses': uses_count,
        'p_source': grant_row['source'], 'p_claim_id': milestone_claim_id,
        'p_override': bool(override), 'p_intent': idem,
    })
    if isinstance(grant, dict) and grant.get('error') == 'duplicate_monthly_grant':
        raise DuplicateGrant(MSG.AMBASSADOR_GRANT_DUPLICATE)
    if not isinstance(grant, dict) or not grant.get('id'):
        raise AmbassadorError(MSG.SERVICE_UNAVAILABLE, status=503)
    if grant.get('status') == 'voided':
        raise AmbassadorError(MSG.AMBASSADOR_GRANT_VOIDED, status=409)
    if not grant.get("idempotent"):
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


def list_grants(db, ambassador_id: str | None = None, ambassador_ids: list[str] | None = None) -> list[dict]:
    q = db.table("ambassador_grants").select("*").order("issued_at", ascending=False)
    if ambassador_id:
        q = q.eq("ambassador_id", ambassador_id)
    elif ambassador_ids is not None:
        if not ambassador_ids:
            return []
        q = q.in_("ambassador_id", ambassador_ids)
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
    query = db.table(AMBASSADOR_TABLE).select("*").eq("status", "active")
    if campus_id or not is_super:
        query = query.eq("campus_id", campus_id)
    rows = query.execute() or []
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
