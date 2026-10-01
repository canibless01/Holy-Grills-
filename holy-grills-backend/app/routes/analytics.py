"""
Analytics routes — admin-only reporting and insights.
"""
from flask import Blueprint, request, jsonify, current_app, Response
from app.middleware.auth import require_role, resolve_scoped_campus_id
from app.db import get_user_client
from app.messages import MSG
from datetime import date, datetime, timezone, timedelta
from dateutil.parser import isoparse
from app.utils.tz import today_wat, WAT_OFFSET
from app.utils.validators import validate_date, validate_uuid, validate_choice, validate_email, sanitize_string
from app.utils.logger import get_logger
import csv
import io

analytics_bp = Blueprint("analytics", __name__)

logger = get_logger(__name__)

_WAT = timezone(WAT_OFFSET)   # Africa/Lagos, fixed UTC+1 (no DST) - the same offset today_wat() uses
_BRAND_STATUSES = ("pending", "approved", "rejected")   # brand_partnership_requests.status CHECK
_CODE_LISTING_TYPES = ("code", "digital_code", "voucher", "subscription")   # same set the purchase flow uses


def _wat_window(from_date: str, to_date: str):
    """WAT calendar days from_date..to_date (YYYY-MM-DD) -> (start_utc_iso, end_utc_iso_EXCLUSIVE).
    Raises ValueError on malformed input."""
    if not (validate_date(from_date) and validate_date(to_date)):
        raise ValueError("date")
    start = datetime.strptime(from_date, "%Y-%m-%d").replace(tzinfo=_WAT)
    end = datetime.strptime(to_date, "%Y-%m-%d").replace(tzinfo=_WAT) + timedelta(days=1)
    return start.astimezone(timezone.utc).isoformat(), end.astimezone(timezone.utc).isoformat()


def _date_range(default_days: int = 30):
    """Read from_date / to_date (YYYY-MM-DD, WAT days). Returns (from_date, to_date, start_utc, end_utc_exclusive)."""
    from_date = request.args.get("from_date", (today_wat() - timedelta(days=default_days)).isoformat())
    to_date = request.args.get("to_date", today_wat().isoformat())
    start_utc, end_utc = _wat_window(from_date, to_date)
    return from_date, to_date, start_utc, end_utc


def _parse_ts(value) -> datetime:
    """ISO-8601 -> timezone-aware datetime. isoparse accepts any fractional-second length on every Python version
    (datetime.fromisoformat before 3.11 rejects Postgres timestamps such as '...39.50624+00:00')."""
    dt = isoparse(str(value))
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def _net_total(o: dict) -> float:
    """Order total minus what was refunded (card + wallet), never below 0."""
    refunded = float(o.get("card_refund_total") or 0) + float(o.get("wallet_refund_total") or 0)
    return max(float(o.get("total_amount") or 0) - refunded, 0.0)


def _int_arg(name: str, default: int, lo: int, hi: int) -> int:
    """Whole-number query arg clamped to [lo, hi]. Raises ValueError on non-numeric input."""
    raw = request.args.get(name)
    if raw is None or raw == "":
        return default
    return max(lo, min(int(raw), hi))


def _scoped_campus():
    """resolve_scoped_campus_id(...) plus a UUID check, so junk never reaches PostgREST. Raises ValueError."""
    campus_id = resolve_scoped_campus_id(request.args.get("campus_id") or None)
    if campus_id and not validate_uuid(campus_id):
        raise ValueError("campus")
    return campus_id


def _derive_payment_method(order: dict) -> str:
    """
    Derive payment method for an order using exact 4-branch precedence rule:
    1. wallet_amount_used > 0 AND card_amount_used > 0  → "split"
    2. wallet_amount_used > 0                           → "wallet"
    3. card_amount_used > 0                             → "card"
    4. both are zero                                    → "hp_or_free"
    """
    w_amt = float(order.get("wallet_amount_used") or 0)
    c_amt = float(order.get("card_amount_used") or 0)
    if w_amt > 0 and c_amt > 0:
        return "split"
    elif w_amt > 0:
        return "wallet"
    elif c_amt > 0:
        return "card"
    else:
        return "hp_or_free"


@analytics_bp.route("/sales", methods=["GET"])
@analytics_bp.route("/revenue", methods=["GET"])
@require_role("admin")
def sales_analytics():
    """
    Sales & Revenue analytics — revenue, order volume, AOV, and 4-branch payment mix.
    ---
    tags: [Analytics]
    parameters:
      - in: query
        name: from_date
        type: string
        format: date
      - in: query
        name: to_date
        type: string
        format: date
    responses:
      200:
        description: Sales analytics summary
    """
    db = get_user_client(paginate=True)
    try:
        from_date, to_date, start_utc, end_utc = _date_range(30)
    except ValueError:
        return jsonify({"error": MSG.ANALYTICS_INVALID_DATE}), 400

    q = (
        db.table("orders")
        .select("id,total_amount,subtotal,status,payment_status,created_at,wallet_amount_used,card_amount_used,hp_redeemed,discount_amount,card_refund_total,wallet_refund_total")
        .gte("created_at", start_utc)
        .lt("created_at", end_utc)
        .neq("status", "cancelled")
    )
    try:
        campus_id = _scoped_campus()
    except ValueError:
        return jsonify({"error": MSG.ANALYTICS_INVALID_CAMPUS}), 400
    if campus_id:
        q = q.eq("campus_id", campus_id)
    orders = q.execute() or []

    delivered = [o for o in orders if o.get("status") == "delivered"]
    total_revenue = sum(_net_total(o) for o in delivered)
    order_count = len(delivered)
    aov = total_revenue / order_count if order_count > 0 else 0

    wallet_revenue = sum(max(float(o.get("wallet_amount_used") or 0) - float(o.get("wallet_refund_total") or 0), 0.0) for o in delivered)
    card_revenue = sum(max(float(o.get("card_amount_used") or 0) - float(o.get("card_refund_total") or 0), 0.0) for o in delivered)

    payment_method_breakdown = {"split": 0, "wallet": 0, "card": 0, "hp_or_free": 0}
    payment_method_revenue = {"split": 0.0, "wallet": 0.0, "card": 0.0, "hp_or_free": 0.0}

    for o in delivered:
        pm = _derive_payment_method(o)
        payment_method_breakdown[pm] = payment_method_breakdown.get(pm, 0) + 1
        payment_method_revenue[pm] = payment_method_revenue.get(pm, 0.0) + _net_total(o)

    return jsonify({
        "from_date": from_date,
        "to_date": to_date,
        "total_revenue": round(total_revenue, 2),
        "order_count": order_count,
        "average_order_value": round(aov, 2),
        "wallet_revenue": round(wallet_revenue, 2),
        "card_revenue": round(card_revenue, 2),
        "payment_method_breakdown": payment_method_breakdown,
        "payment_method_revenue": {k: round(v, 2) for k, v in payment_method_revenue.items()},
    }), 200


@analytics_bp.route("/payment-methods", methods=["GET"])
@require_role("admin")
def payment_method_analytics():
    """
    A7 — Payment Method Analytics: Split by wallet, card, split, or hp_or_free.
    Uses exact 4-branch precedence rules.
    ---
    tags: [Analytics]
    responses:
      200:
        description: Breakdown of order payment methods
    """
    db = get_user_client(paginate=True)
    try:
        from_date, to_date, start_utc, end_utc = _date_range(30)
    except ValueError:
        return jsonify({"error": MSG.ANALYTICS_INVALID_DATE}), 400

    q = (
        db.table("orders")
        .select("id,total_amount,wallet_amount_used,card_amount_used,hp_redeemed,discount_amount,status,payment_status,card_refund_total,wallet_refund_total,created_at")
        .in_("payment_status", ["paid", "partially_refunded"])
        .gte("created_at", start_utc)
        .lt("created_at", end_utc)
        .neq("status", "cancelled")
    )
    try:
        campus_id = _scoped_campus()
    except ValueError:
        return jsonify({"error": MSG.ANALYTICS_INVALID_CAMPUS}), 400
    if campus_id:
        q = q.eq("campus_id", campus_id)
    orders = q.execute() or []

    counts = {"split": 0, "wallet": 0, "card": 0, "hp_or_free": 0}
    revenue = {"split": 0.0, "wallet": 0.0, "card": 0.0, "hp_or_free": 0.0}

    for o in orders:
        pm = _derive_payment_method(o)
        counts[pm] += 1
        revenue[pm] += _net_total(o)

    total_orders = len(orders)
    percentages = {
        k: round(v / total_orders * 100, 1) if total_orders > 0 else 0
        for k, v in counts.items()
    }

    return jsonify({
        "from_date": from_date,
        "to_date": to_date,
        "total_orders": total_orders,
        "counts": counts,
        "percentages": percentages,
        "revenue_by_method": {k: round(v, 2) for k, v in revenue.items()},
    }), 200


@analytics_bp.route("/order-timing", methods=["GET"])
@require_role("admin")
def order_timing_analytics():
    """
    A1 — Order Timing: Hourly and day-of-week distributions.
    ---
    tags: [Analytics]
    responses:
      200:
        description: Hourly and weekday distributions
    """
    db = get_user_client(paginate=True)
    try:
        from_date, to_date, start_utc, end_utc = _date_range(30)
    except ValueError:
        return jsonify({"error": MSG.ANALYTICS_INVALID_DATE}), 400

    q = (
        db.table("orders")
        .select("id,created_at,received_at,delivered_at,status")
        .gte("created_at", start_utc)
        .lt("created_at", end_utc)
        .neq("status", "cancelled")
    )
    try:
        campus_id = _scoped_campus()
    except ValueError:
        return jsonify({"error": MSG.ANALYTICS_INVALID_CAMPUS}), 400
    if campus_id:
        q = q.eq("campus_id", campus_id)
    orders = q.execute() or []

    hours = {h: 0 for h in range(24)}
    days = {"Monday": 0, "Tuesday": 0, "Wednesday": 0, "Thursday": 0, "Friday": 0, "Saturday": 0, "Sunday": 0}
    day_names = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]

    for o in orders:
        created_str = o.get("created_at")
        if not created_str:
            continue
        try:
            dt = _parse_ts(created_str).astimezone(_WAT)
            hours[dt.hour] += 1
            days[day_names[dt.weekday()]] += 1
        except Exception:
            logger.warning("order-timing: unparseable created_at %r skipped", created_str)

    return jsonify({
        "from_date": from_date,
        "to_date": to_date,
        "total_orders": len(orders),
        "hourly_distribution": hours,
        "day_of_week_distribution": days,
    }), 200


@analytics_bp.route("/addon-acceptance", methods=["GET"])
@require_role("admin")
def addon_acceptance_analytics():
    """
    A2 — Add-On Acceptance: How often students add extras, and which ones.
    Reads add-on picks from order_addon_selections (embedded under order_items).
    ---
    tags: [Analytics]
    responses:
      200:
        description: Add-on attachment rate and top add-ons
    """
    db = get_user_client(paginate=True)
    try:
        from_date, to_date, start_utc, end_utc = _date_range(30)
    except ValueError:
        return jsonify({"error": MSG.ANALYTICS_INVALID_DATE}), 400

    q = (
        db.table("orders")
        .select("id,status,order_items(id,is_addon,quantity,price_snapshot,name_snapshot,order_addon_selections(name_snapshot,price_delta_snapshot,quantity))")
        .gte("created_at", start_utc)
        .lt("created_at", end_utc)
        .neq("status", "cancelled")
    )
    try:
        campus_id = _scoped_campus()
    except ValueError:
        return jsonify({"error": MSG.ANALYTICS_INVALID_CAMPUS}), 400
    if campus_id:
        q = q.eq("campus_id", campus_id)
    orders = q.execute() or []

    total_orders = len(orders)
    orders_with_addons = 0
    from collections import defaultdict
    addon_counts = defaultdict(int)
    addon_revenue = defaultdict(float)

    for o in orders:
        has_addon = False
        for item in o.get("order_items", []):
            selections = item.get("order_addon_selections") or []
            if isinstance(selections, list) and len(selections) > 0:
                has_addon = True
                for sel in selections:
                    if isinstance(sel, dict):
                        name = sel.get("name_snapshot") or "Add-on"
                        qty = int(sel.get("quantity") or 1)
                        price = float(sel.get("price_delta_snapshot") or 0.0)
                        addon_counts[name] += qty
                        addon_revenue[name] += price * qty
            elif item.get("is_addon"):
                has_addon = True
                name = item.get("name_snapshot") or "Add-on"
                qty = int(item.get("quantity") or 1)
                price = float(item.get("price_snapshot") or 0.0)
                addon_counts[name] += qty
                addon_revenue[name] += price * qty

        if has_addon:
            orders_with_addons += 1

    top_addons = [
        {"name": name, "quantity": addon_counts[name], "revenue": round(addon_revenue[name], 2)}
        for name in sorted(addon_counts.keys(), key=lambda k: addon_counts[k], reverse=True)[:20]
    ]

    return jsonify({
        "from_date": from_date,
        "to_date": to_date,
        "total_orders": total_orders,
        "orders_with_addons": orders_with_addons,
        "attachment_rate": round(orders_with_addons / total_orders * 100, 1) if total_orders > 0 else 0,
        "top_addons": top_addons,
    }), 200


@analytics_bp.route("/delivery-locations", methods=["GET"])
@require_role("admin")
def delivery_location_analytics():
    """
    A3 — Delivery Location: Volume and revenue grouped by hostel/gate.
    ---
    tags: [Analytics]
    responses:
      200:
        description: Breakdown by delivery location
    """
    db = get_user_client(paginate=True)
    try:
        from_date, to_date, start_utc, end_utc = _date_range(30)
    except ValueError:
        return jsonify({"error": MSG.ANALYTICS_INVALID_DATE}), 400

    q = (
        db.table("orders")
        .select("id,delivery_type,delivery_location_id,total_amount,status")
        .gte("created_at", start_utc)
        .lt("created_at", end_utc)
        .neq("status", "cancelled")
    )
    try:
        campus_id = _scoped_campus()
    except ValueError:
        return jsonify({"error": MSG.ANALYTICS_INVALID_CAMPUS}), 400
    if campus_id:
        q = q.eq("campus_id", campus_id)
    orders = q.execute() or []

    hostel_ids = {o["delivery_location_id"] for o in orders if o.get("delivery_type") == "on_campus" and o.get("delivery_location_id")}
    gate_ids = {o["delivery_location_id"] for o in orders if o.get("delivery_type") == "off_campus" and o.get("delivery_location_id")}

    hostels_map = {}
    if hostel_ids:
        rows = db.table("hostels").select("id,name").in_("id", list(hostel_ids)).execute() or []
        hostels_map = {h["id"]: h["name"] for h in rows}

    gates_map = {}
    if gate_ids:
        rows = db.table("gates").select("id,name").in_("id", list(gate_ids)).execute() or []
        gates_map = {g_row["id"]: g_row["name"] for g_row in rows}

    from collections import defaultdict
    locations = defaultdict(lambda: {"order_count": 0, "revenue": 0.0, "delivery_type": "unknown"})

    for o in orders:
        dtype = o.get("delivery_type") or "unknown"
        loc_id = o.get("delivery_location_id")
        if dtype == "on_campus" and loc_id in hostels_map:
            loc_name = hostels_map[loc_id]
        elif dtype == "off_campus" and loc_id in gates_map:
            loc_name = gates_map[loc_id]
        else:
            loc_name = f"Unspecified ({dtype})"

        locations[loc_name]["order_count"] += 1
        locations[loc_name]["revenue"] += float(o.get("total_amount") or 0)
        locations[loc_name]["delivery_type"] = dtype

    breakdown = [
        {"location": loc, "delivery_type": data["delivery_type"], "order_count": data["order_count"], "revenue": round(data["revenue"], 2)}
        for loc, data in sorted(locations.items(), key=lambda x: x[1]["order_count"], reverse=True)
    ]

    return jsonify({
        "from_date": from_date,
        "to_date": to_date,
        "total_orders": len(orders),
        "locations": breakdown,
    }), 200


@analytics_bp.route("/squad-orders", methods=["GET"])
@require_role("admin")
def squad_order_analytics():
    """
    A4 — Squad/Group Orders: Squad order metrics, group sizes, and volume.
    ---
    tags: [Analytics]
    responses:
      200:
        description: Group order stats
    """
    db = get_user_client(paginate=True)
    try:
        from_date, to_date, start_utc, end_utc = _date_range(30)
    except ValueError:
        return jsonify({"error": MSG.ANALYTICS_INVALID_DATE}), 400

    q = (
        db.table("orders")
        .select("id,is_squad_order,squad_item_count,squad_name,squad_id,squad_member_snapshot,total_amount,status")
        .gte("created_at", start_utc)
        .lt("created_at", end_utc)
        .neq("status", "cancelled")
    )
    try:
        campus_id = _scoped_campus()
    except ValueError:
        return jsonify({"error": MSG.ANALYTICS_INVALID_CAMPUS}), 400
    if campus_id:
        q = q.eq("campus_id", campus_id)
    orders = q.execute() or []

    squad_orders = [o for o in orders if o.get("is_squad_order")]
    total_orders = len(orders)
    squad_count = len(squad_orders)

    item_counts = [int(o.get("squad_item_count") or 1) for o in squad_orders]
    avg_item_count = round(sum(item_counts) / len(item_counts), 1) if item_counts else 0

    member_counts = []
    for o in squad_orders:
        snap = o.get("squad_member_snapshot")
        if isinstance(snap, list):
            member_counts.append(len(snap))
        else:
            member_counts.append(1)
    avg_group_size = round(sum(member_counts) / len(member_counts), 1) if member_counts else 0

    return jsonify({
        "from_date": from_date,
        "to_date": to_date,
        "total_orders": total_orders,
        "squad_orders_count": squad_count,
        "squad_order_pct": round(squad_count / total_orders * 100, 1) if total_orders > 0 else 0,
        "avg_items_per_squad_order": avg_item_count,
        "avg_squad_group_size": avg_group_size,
    }), 200


@analytics_bp.route("/demographics", methods=["GET"])
@require_role("admin")
def demographics_analytics():
    """
    A5 — Demographics: Spending and order volume by department, faculty, and level.
    Fallback logic: Uses profiles.faculty when present, otherwise joins departments table via department_id.
    ---
    tags: [Analytics]
    responses:
      200:
        description: Spending by department, faculty, and academic level
    """
    db = get_user_client(paginate=True)
    try:
        from_date, to_date, start_utc, end_utc = _date_range(30)
    except ValueError:
        return jsonify({"error": MSG.ANALYTICS_INVALID_DATE}), 400

    q = (
        db.table("orders")
        .select("id,user_id,total_amount,status")
        .gte("created_at", start_utc)
        .lt("created_at", end_utc)
        .neq("status", "cancelled")
        .not_.is_("user_id", "null")
    )
    try:
        campus_id = _scoped_campus()
    except ValueError:
        return jsonify({"error": MSG.ANALYTICS_INVALID_CAMPUS}), 400
    if campus_id:
        q = q.eq("campus_id", campus_id)
    orders = q.execute() or []

    user_ids = list({o["user_id"] for o in orders if o.get("user_id")})
    profiles_map = {}
    if user_ids:
        # Pre-fetch departments table for fallback
        depts_rows = db.table("departments").select("id,name,faculty").execute() or []
        dept_faculty_map = {d["id"]: d.get("faculty") for d in depts_rows if d.get("id")}

        # Fetch profiles for users
        chunk_size = 200
        for i in range(0, len(user_ids), chunk_size):
            chunk = user_ids[i:i + chunk_size]
            prof_rows = (
                db.table("profiles")
                .select("id,department,faculty,department_id,academic_level")
                .in_("id", chunk)
                .execute()
            ) or []
            for p in prof_rows:
                fac = p.get("faculty")
                if not fac and p.get("department_id"):
                    fac = dept_faculty_map.get(p["department_id"])
                p["resolved_faculty"] = fac or "Unspecified"
                profiles_map[p["id"]] = p

    from collections import defaultdict
    by_dept = defaultdict(lambda: {"order_count": 0, "revenue": 0.0})
    by_fac = defaultdict(lambda: {"order_count": 0, "revenue": 0.0})
    by_level = defaultdict(lambda: {"order_count": 0, "revenue": 0.0})

    for o in orders:
        uid = o.get("user_id")
        prof = profiles_map.get(uid, {})
        dept = prof.get("department") or "Unspecified"
        fac = prof.get("resolved_faculty") or "Unspecified"
        level = prof.get("academic_level") or "Unspecified"
        amt = float(o.get("total_amount") or 0)

        by_dept[dept]["order_count"] += 1
        by_dept[dept]["revenue"] += amt

        by_fac[fac]["order_count"] += 1
        by_fac[fac]["revenue"] += amt

        by_level[level]["order_count"] += 1
        by_level[level]["revenue"] += amt

    return jsonify({
        "from_date": from_date,
        "to_date": to_date,
        "by_department": [
            {"department": k, "order_count": v["order_count"], "revenue": round(v["revenue"], 2)}
            for k, v in sorted(by_dept.items(), key=lambda x: x[1]["revenue"], reverse=True)
        ],
        "by_faculty": [
            {"faculty": k, "order_count": v["order_count"], "revenue": round(v["revenue"], 2)}
            for k, v in sorted(by_fac.items(), key=lambda x: x[1]["revenue"], reverse=True)
        ],
        "by_academic_level": [
            {"academic_level": k, "order_count": v["order_count"], "revenue": round(v["revenue"], 2)}
            for k, v in sorted(by_level.items(), key=lambda x: x[1]["revenue"], reverse=True)
        ],
    }), 200


@analytics_bp.route("/engagement", methods=["GET"])
@require_role("admin")
def engagement_analytics():
    """
    A6 — Student Engagement: Review, check-in, referral, and event engagement.
    ---
    tags: [Analytics]
    responses:
      200:
        description: Engagement metrics
    """
    db = get_user_client(paginate=True)
    try:
        campus_id = _scoped_campus()
    except ValueError:
        return jsonify({"error": MSG.ANALYTICS_INVALID_CAMPUS}), 400

    def _count(table: str) -> int:
        q = db.table(table).select("id", count="exact").limit(1)
        if campus_id:
            q = q.eq("campus_id", campus_id)
        res = q.execute()
        return (res.get("count") or 0) if isinstance(res, dict) else len(res or [])

    reviews = _count("order_reviews")
    referrals = _count("referrals")
    event_checkins = _count("event_checkins")

    return jsonify({
        "total_reviews_left": reviews,
        "total_referrals_made": referrals,
        "total_event_checkins": event_checkins,
    }), 200


@analytics_bp.route("/retention-ltv", methods=["GET"])
@require_role("admin")
def retention_ltv_analytics():
    """
    A8 — Retention & LTV: Repeat order rate and customer LTV.
    ---
    tags: [Analytics]
    responses:
      200:
        description: Retention and LTV metrics
    """
    db = get_user_client(paginate=True)
    try:
        campus_id = _scoped_campus()
    except ValueError:
        return jsonify({"error": MSG.ANALYTICS_INVALID_CAMPUS}), 400

    q_prof = db.table("profiles").select("id").eq("role", "student")
    if campus_id:
        q_prof = q_prof.eq("campus_id", campus_id)
    students = q_prof.execute() or []
    total_students = len(students)

    q_orders = db.table("orders").select("user_id,total_amount,card_refund_total,wallet_refund_total").eq("status", "delivered")
    if campus_id:
        q_orders = q_orders.eq("campus_id", campus_id)
    orders = q_orders.execute() or []

    from collections import defaultdict
    user_spend = defaultdict(float)
    user_orders = defaultdict(int)

    for o in orders:
        uid = o.get("user_id")
        if uid:
            user_spend[uid] += _net_total(o)
            user_orders[uid] += 1

    repeat_customers = len([uid for uid, cnt in user_orders.items() if cnt >= 2])
    total_revenue = sum(user_spend.values())
    ordering_customers = len(user_spend)

    arpu = total_revenue / total_students if total_students > 0 else 0
    ltv = total_revenue / ordering_customers if ordering_customers > 0 else 0

    return jsonify({
        "total_students": total_students,
        "ordering_customers": ordering_customers,
        "repeat_customers": repeat_customers,
        "repeat_customer_rate": round(repeat_customers / ordering_customers * 100, 1) if ordering_customers > 0 else 0,
        "total_revenue": round(total_revenue, 2),
        "arpu": round(arpu, 2),
        "customer_ltv": round(ltv, 2),
    }), 200


@analytics_bp.route("/referral-network", methods=["GET"])
@require_role("admin")
def referral_network_analytics():
    """
    A9 — Referral Network: Top referrers driving new signups.
    ---
    tags: [Analytics]
    responses:
      200:
        description: Referral network and top referrers
    """
    db = get_user_client(paginate=True)
    try:
        campus_id = _scoped_campus()
    except ValueError:
        return jsonify({"error": MSG.ANALYTICS_INVALID_CAMPUS}), 400

    q = db.table("referrals").select("id,referrer_id,hp_awarded")
    if campus_id:
        q = q.eq("campus_id", campus_id)
    all_refs = q.execute() or []

    from collections import defaultdict
    ref_counts = defaultdict(int)
    hp_awarded = defaultdict(int)

    for r in all_refs:
        rid = r.get("referrer_id")
        if rid:
            ref_counts[rid] += 1
            hp_awarded[rid] += int(r.get("hp_awarded") or 0)

    top_referrer_ids = sorted(ref_counts.keys(), key=lambda k: ref_counts[k], reverse=True)[:10]
    top_referrers = []
    if top_referrer_ids:
        profs = db.table("profiles").select("id,full_name,email").in_("id", top_referrer_ids).execute() or []
        prof_map = {p["id"]: p.get("full_name") or p.get("email") for p in profs}
        for rid in top_referrer_ids:
            top_referrers.append({
                "referrer_id": rid,
                "name": prof_map.get(rid, rid),
                "referral_count": ref_counts[rid],
                "hp_earned": hp_awarded[rid],
            })

    return jsonify({
        "total_referrals": len(all_refs),
        "completed_referrals": len([r for r in all_refs if r.get("hp_awarded", 0) > 0]),
        "top_referrers": top_referrers,
    }), 200


@analytics_bp.route("/hp-ecosystem", methods=["GET"])
@analytics_bp.route("/hp", methods=["GET"])
@require_role("admin")
def hp_analytics():
    """
    A10 — HP Ecosystem analytics: issued, spent, expired, and 4-tier distribution.
    Tiers: Ember/Starter (0 HP), Flame (2,500 HP), Blaze/Inferno (7,500 HP), Holy (20,000 HP).
    Blaze/Inferno is strictly preserved as its own segment.
    ---
    tags: [Analytics]
    responses:
      200:
        description: HP analytics across all 4 tiers
    """
    db = get_user_client(paginate=True)
    try:
        from_date, to_date, start_utc, end_utc = _date_range(30)
    except ValueError:
        return jsonify({"error": MSG.ANALYTICS_INVALID_DATE}), 400


    q = (
        db.table("hp_transactions")
        .select("amount,type,status,source")
        .gte("created_at", start_utc)
        .lt("created_at", end_utc)
    )
    try:
        campus_id = _scoped_campus()
    except ValueError:
        return jsonify({"error": MSG.ANALYTICS_INVALID_CAMPUS}), 400
    if campus_id:
        q = q.eq("campus_id", campus_id)
    hp_txns = q.execute() or []

    # hp_transactions.amount is always positive (CHECK amount > 0); the direction lives in `type`.
    earned = sum(t["amount"] for t in hp_txns if t.get("type") == "earn")
    spent = sum(t["amount"] for t in hp_txns if t.get("type") == "spend")
    expired = sum(t["amount"] for t in hp_txns if t.get("type") == "expire")
    pending = sum(t["amount"] for t in hp_txns if t.get("status") == "pending" and t["amount"] > 0)

    # All 4 Tiers check
    tiers = db.table("hp_tiers").select("id,name,slug,min_points").order("sort_order").execute() or []

    tier_distribution = []
    if tiers:
        for tier in tiers:
            tq = db.table("profiles").select("id", count="exact").eq("current_tier_id", tier["id"]).eq("is_active", "true")
            if campus_id:
                tq = tq.eq("campus_id", campus_id)
            res = tq.execute()
            cnt = res.get("count", 0) if isinstance(res, dict) else len(res or [])
            tier_distribution.append({"tier": tier["name"], "slug": tier.get("slug"), "count": cnt})
    else:
        # Fallback to standard 4 tiers if hp_tiers table is not populated yet
        tier_names = [
            ("Ember / Starter", 0),
            ("Flame", 2500),
            ("Blaze / Inferno", 7500),
            ("Holy", 20000),
        ]
        for name, _ in tier_names:
            tier_distribution.append({"tier": name, "count": 0})

    return jsonify({
        "from_date": from_date,
        "to_date": to_date,
        "hp_earned_active": earned,
        "hp_spent": spent,
        "hp_expired": expired,
        "hp_pending": pending,
        "hp_in_circulation": earned - spent - expired,
        "redemption_rate": round(spent / earned * 100, 1) if earned > 0 else 0,
        "tier_distribution": tier_distribution,
    }), 200


@analytics_bp.route("/items-menu", methods=["GET"])
@analytics_bp.route("/items", methods=["GET"])
@require_role("admin")
def items_analytics():
    """
    A11 — Items & Menu analytics: Quantity sold and revenue per menu item.
    ---
    tags: [Analytics]
    responses:
      200:
        description: Per-item sales breakdown sorted by qty desc
    """
    db = get_user_client(paginate=True)
    try:
        from_date, to_date, start_utc, end_utc = _date_range(30)
    except ValueError:
        return jsonify({"error": MSG.ANALYTICS_INVALID_DATE}), 400
    try:
        limit = _int_arg("limit", 50, 1, 200)
    except ValueError:
        return jsonify({"error": MSG.ANALYTICS_INVALID_NUMBER.format(param="limit")}), 400

    q = (
        db.table("orders")
        .select("id,subtotal")
        .eq("status", "delivered")
        .gte("delivered_at", start_utc)
        .lt("delivered_at", end_utc)
    )
    try:
        campus_id = _scoped_campus()
    except ValueError:
        return jsonify({"error": MSG.ANALYTICS_INVALID_CAMPUS}), 400
    if campus_id:
        q = q.eq("campus_id", campus_id)
    orders = q.execute() or []

    if not orders:
        return jsonify({"from_date": from_date, "to_date": to_date, "items": [], "total_items_found": 0}), 200

    order_ids = [o["id"] for o in orders]
    all_items = []
    chunk_size = 200
    for i in range(0, len(order_ids), chunk_size):
        chunk = order_ids[i:i + chunk_size]
        rows = (
            db.table("order_items")
            .select("name_snapshot,quantity,price_snapshot")
            .in_("order_id", chunk)
            .execute()
        ) or []
        all_items.extend(rows)

    from collections import defaultdict
    agg = defaultdict(lambda: {"qty": 0, "revenue": 0.0})
    for item in all_items:
        name = item.get("name_snapshot") or "Unknown"
        qty = int(item.get("quantity") or 1)
        price = float(item.get("price_snapshot") or 0)
        agg[name]["qty"] += qty
        agg[name]["revenue"] += price * qty

    sorted_items = sorted(agg.items(), key=lambda x: x[1]["qty"], reverse=True)[:limit]
    result = [
        {"item_name": name, "qty_sold": v["qty"], "revenue": round(v["revenue"], 2)}
        for name, v in sorted_items
    ]
    return jsonify({"from_date": from_date, "to_date": to_date, "items": result, "total_items_found": len(agg)}), 200


@analytics_bp.route("/academic-calendar", methods=["GET"])
@require_role("admin")
def academic_calendar_analytics():
    """
    B1 — Academic Calendar analytics: Order volume during exam/semester periods vs normal days.
    ---
    tags: [Analytics]
    responses:
      200:
        description: Order trends across academic calendar periods
    """
    db = get_user_client(paginate=True)
    try:
        campus_id = _scoped_campus()
    except ValueError:
        return jsonify({"error": MSG.ANALYTICS_INVALID_CAMPUS}), 400

    q = db.table("academic_calendar").select("*").eq("is_active", True)
    if campus_id:
        q = q.or_(f"campus_id.eq.{campus_id},campus_id.is.null")
    periods = q.order("start_date").execute() or []

    period_stats = []
    for p in periods:
        s_date = p.get("start_date")
        e_date = p.get("end_date")
        if not s_date or not e_date:
            continue

        p_start, p_end = _wat_window(str(s_date)[:10], str(e_date)[:10])
        oq = (
            db.table("orders")
            .select("id,total_amount")
            .gte("created_at", p_start)
            .lt("created_at", p_end)
            .neq("status", "cancelled")
        )
        if campus_id:
            oq = oq.eq("campus_id", campus_id)
        p_orders = oq.execute() or []
        tot_rev = sum(float(o.get("total_amount") or 0) for o in p_orders)

        period_stats.append({
            "id": p["id"],
            "name": p.get("name"),
            "period_type": p.get("period_type"),
            "start_date": s_date,
            "end_date": e_date,
            "total_orders": len(p_orders),
            "total_revenue": round(tot_rev, 2),
            "avg_orders_per_day": round(len(p_orders) / max((date.fromisoformat(str(e_date)[:10]) - date.fromisoformat(str(s_date)[:10])).days + 1, 1), 2),
        })

    # Normal-day baseline: average per day over the last 90 WAT days that fall outside every active period.
    from collections import defaultdict
    base_to = today_wat()
    base_from = base_to - timedelta(days=89)
    period_days = set()
    for p in periods:
        try:
            d = date.fromisoformat(str(p["start_date"])[:10])
            last = date.fromisoformat(str(p["end_date"])[:10])
        except (KeyError, TypeError, ValueError):
            continue
        while d <= last:
            period_days.add(d)
            d += timedelta(days=1)
    normal_days = [base_from + timedelta(days=i) for i in range(90) if (base_from + timedelta(days=i)) not in period_days]
    b_start, b_end = _wat_window(base_from.isoformat(), base_to.isoformat())
    bq = (
        db.table("orders")
        .select("id,total_amount,created_at")
        .gte("created_at", b_start)
        .lt("created_at", b_end)
        .neq("status", "cancelled")
    )
    if campus_id:
        bq = bq.eq("campus_id", campus_id)
    orders_by_day = defaultdict(int)
    revenue_by_day = defaultdict(float)
    for o in (bq.execute() or []):
        try:
            day = _parse_ts(o["created_at"]).astimezone(_WAT).date()
        except Exception:
            logger.warning("academic-calendar: unparseable created_at %r skipped", o.get("created_at"))
            continue
        orders_by_day[day] += 1
        revenue_by_day[day] += float(o.get("total_amount") or 0)
    n_normal = len(normal_days)
    baseline = {
        "window_days": 90,
        "normal_days": n_normal,
        "avg_orders_per_day": round(sum(orders_by_day[d] for d in normal_days) / n_normal, 2) if n_normal else None,
        "avg_revenue_per_day": round(sum(revenue_by_day[d] for d in normal_days) / n_normal, 2) if n_normal else None,
    }

    return jsonify({"academic_periods": period_stats, "normal_day_baseline": baseline}), 200


@analytics_bp.route("/order-sources", methods=["GET"])
@require_role("admin")
def order_sources_analytics():
    """
    B2 — Order Sources: Breakdown of orders by channel (website, whatsapp, instagram, referral, sms, other).
    ---
    tags: [Analytics]
    responses:
      200:
        description: Order volume by channel
    """
    db = get_user_client(paginate=True)
    try:
        from_date, to_date, start_utc, end_utc = _date_range(30)
    except ValueError:
        return jsonify({"error": MSG.ANALYTICS_INVALID_DATE}), 400

    q = (
        db.table("orders")
        .select("id,order_source,total_amount,status")
        .gte("created_at", start_utc)
        .lt("created_at", end_utc)
        .neq("status", "cancelled")
    )
    try:
        campus_id = _scoped_campus()
    except ValueError:
        return jsonify({"error": MSG.ANALYTICS_INVALID_CAMPUS}), 400
    if campus_id:
        q = q.eq("campus_id", campus_id)
    orders = q.execute() or []

    from collections import defaultdict
    sources = defaultdict(int)
    revenue = defaultdict(float)

    for o in orders:
        src = o.get("order_source") or "unspecified"
        sources[src] += 1
        revenue[src] += float(o.get("total_amount") or 0)

    total_orders = len(orders)
    breakdown = [
        {
            "order_source": src,
            "count": cnt,
            "pct": round(cnt / total_orders * 100, 1) if total_orders > 0 else 0,
            "revenue": round(revenue[src], 2),
        }
        for src, cnt in sorted(sources.items(), key=lambda x: x[1], reverse=True)
    ]

    return jsonify({
        "from_date": from_date,
        "to_date": to_date,
        "total_orders": total_orders,
        "order_sources": breakdown,
    }), 200


@analytics_bp.route("/brand-partnerships", methods=["GET"])
@require_role("admin")
def list_brand_partnerships():
    """
    B4 — Brand Partnerships: List brand partnership data requests (admin and super_admin).
    ---
    tags: [Analytics]
    responses:
      200:
        description: Brand partnership requests
    """
    db = get_user_client(paginate=True)
    # TableQuery.order() builds "{column}.{direction}" as ONE string (a second .order() call would
    # overwrite this one, not add to it), so a compound sort has to be built as a single call: passing
    # "created_at.desc,id" with ascending=False yields "created_at.desc,id.desc" -- exactly the PostgREST
    # syntax for "newest first, id descending as tiebreaker" -- so every row is returned exactly once
    # even if two rows share the same created_at timestamp at a pagination page boundary.
    rows = db.table("brand_partnership_requests").select("*").order("created_at.desc,id", ascending=False).execute() or []
    return jsonify({"brand_partnerships": rows, "count": len(rows)}), 200


@analytics_bp.route("/brand-partnerships/<request_id>", methods=["PATCH"])
@require_role("admin")
def update_brand_partnership(request_id):
    """
    B4 — Brand Partnerships: Update status or shared_at timestamp (admin and super_admin).
    ---
    tags: [Analytics]
    responses:
      200:
        description: Updated brand partnership request
    """
    db = get_user_client(paginate=True)
    if not validate_uuid(request_id):
        return jsonify({"error": MSG.ANALYTICS_BRAND_NOT_FOUND}), 404
    data = request.get_json(force=True) or {}
    if not isinstance(data, dict):
        return jsonify({"error": MSG.NO_VALID_FIELDS}), 400
    update_data = {}
    if data.get("status"):
        ok, msg = validate_choice(data["status"], _BRAND_STATUSES, "status")
        if not ok:
            return jsonify({"error": msg}), 400
        update_data["status"] = data["status"]
    if data.get("shared_at"):
        try:
            datetime.fromisoformat(str(data["shared_at"]).replace("Z", "+00:00"))
        except ValueError:
            return jsonify({"error": MSG.ANALYTICS_INVALID_DATETIME}), 400
        update_data["shared_at"] = data["shared_at"]
    if not update_data:
        return jsonify({"error": MSG.NO_VALID_FIELDS}), 400
    result = db.table("brand_partnership_requests").eq("id", request_id).update(update_data).execute()
    if not result:
        return jsonify({"error": MSG.ANALYTICS_BRAND_NOT_FOUND}), 404
    return jsonify(result[0] if isinstance(result, list) else result), 200


@analytics_bp.route("/brand-partnerships", methods=["POST"])
@require_role("admin")
def create_brand_partnership():
    """
    B4 — Brand Partnerships: Log a brand's data request for record keeping (admin and super_admin).
    ---
    tags: [Analytics]
    responses:
      201:
        description: Logged brand partnership request (status starts as pending)
    """
    db = get_user_client()
    data = request.get_json(force=True) or {}
    if not isinstance(data, dict):
        return jsonify({"error": MSG.NO_VALID_FIELDS}), 400
    brand_name = sanitize_string(data.get("brand_name"), 200)
    if not brand_name:
        return jsonify({"error": MSG.BRAND_NAME_INVALID}), 400
    contact_email = sanitize_string(data.get("contact_email"), 254).lower()
    if not validate_email(contact_email):
        return jsonify({"error": MSG.BRAND_EMAIL_INVALID}), 400
    requested_data = data.get("requested_data", {})
    if not isinstance(requested_data, dict) or len(str(requested_data)) > 10000:
        return jsonify({"error": MSG.BRAND_REQUESTED_DATA_INVALID}), 400
    result = db.table("brand_partnership_requests").insert({
        "brand_name": brand_name,
        "contact_email": contact_email,
        "requested_data": requested_data,
        "status": "pending",
    })
    return jsonify(result[0] if isinstance(result, list) and len(result) > 0 else result), 201


@analytics_bp.route("/referrals", methods=["GET"])
@require_role("admin")
def referral_analytics():
    """
    Referral funnel analytics.
    ---
    tags: [Analytics]
    responses:
      200:
        description: Referral stats
    """
    db = get_user_client(paginate=True)
    q = db.table("referrals").select("id,hp_awarded")
    try:
        campus_id = _scoped_campus()
    except ValueError:
        return jsonify({"error": MSG.ANALYTICS_INVALID_CAMPUS}), 400
    if campus_id:
        q = q.eq("campus_id", campus_id)
    all_referrals = q.execute() or []
    completed = [r for r in all_referrals if r.get("hp_awarded", 0) > 0]
    total_hp = sum(r.get("hp_awarded", 0) for r in completed)

    return jsonify({
        "total_referral_links_used": len(all_referrals),
        "completed_referrals": len(completed),
        "conversion_rate": round(len(completed) / len(all_referrals) * 100, 1) if all_referrals else 0,
        "total_hp_distributed": total_hp,
    }), 200


@analytics_bp.route("/dashboard", methods=["GET"])
@require_role("admin")
def dashboard_summary():
    """
    Live admin dashboard — today's order pipeline, delivery batch status, revenue snapshot.
    Single call for the admin home screen.
    ---
    tags: [Analytics]
    responses:
      200:
        description: Live dashboard snapshot
    """
    db = get_user_client(paginate=True)
    today = today_wat().isoformat()
    today_start, today_end = _wat_window(today, today)

    q = (
        db.table("orders")
        .select("id,status,total_amount,payment_status,delivery_window_id,batch_id,created_at,wallet_amount_used,card_amount_used,card_refund_total,wallet_refund_total")
        .gte("created_at", today_start)
        .lt("created_at", today_end)
    )
    try:
        campus_id = _scoped_campus()
    except ValueError:
        return jsonify({"error": MSG.ANALYTICS_INVALID_CAMPUS}), 400
    if campus_id:
        q = q.eq("campus_id", campus_id)
    orders_today = q.execute()
    orders_today = orders_today if isinstance(orders_today, list) else []

    status_counts = {}
    for o in orders_today:
        s = o.get("status", "unknown")
        status_counts[s] = status_counts.get(s, 0) + 1

    delivered_today = [o for o in orders_today if o.get("status") == "delivered"]
    revenue_today   = sum(_net_total(o) for o in delivered_today)
    active_orders   = [o for o in orders_today if o.get("status") not in ("cancelled", "refunded", "delivered")]

    wq = (
        db.table("delivery_windows")
        .select("id,label,starts_at,ends_at,status")
        .eq("status", "open")
    )
    if campus_id:
        wq = wq.eq("campus_id", campus_id)
    open_windows = wq.execute()
    open_windows = open_windows if isinstance(open_windows, list) else []
    windows_with_counts = []
    for w in open_windows:
        wid = w["id"]
        cnt = len([o for o in orders_today if o.get("delivery_window_id") == wid])
        windows_with_counts.append({**w, "order_count": cnt})

    bq = (
        db.table("delivery_batches")
        .select("id,window_id,zone,status,rider_id")
        .in_("status", ["assigned", "in_progress"])
    )
    if campus_id:
        bq = bq.eq("campus_id", campus_id)
    active_batches = bq.execute()
    active_batches = active_batches if isinstance(active_batches, list) else []
    batches_with_counts = []
    for b in active_batches:
        bid = b["id"]
        cnt = len([o for o in orders_today if o.get("batch_id") == bid])
        batches_with_counts.append({**b, "order_count": cnt})

    payment_split = {}
    for o in orders_today:
        pm = _derive_payment_method(o)
        payment_split[pm] = payment_split.get(pm, 0) + 1

    return jsonify({
        "as_of": datetime.now(timezone.utc).isoformat(),
        "today": {
            "total_orders": len(orders_today),
            "active_orders": len(active_orders),
            "delivered_orders": len(delivered_today),
            "revenue_delivered": round(revenue_today, 2),
            "orders_by_status": status_counts,
            "orders_by_payment_method": payment_split,
        },
        "delivery_pipeline": {
            "open_windows": windows_with_counts,
            "active_batches": batches_with_counts,
            "unassigned_orders": len([o for o in active_orders if not o.get("batch_id")]),
        },
    }), 200


@analytics_bp.route("/orders", methods=["GET"])
@require_role("admin")
def orders_analytics():
    """
    Order flow analytics — volume by window, zone coverage, status funnel, peak hours.
    Filterable by date range.
    ---
    tags: [Analytics]
    parameters:
      - in: query
        name: from_date
        type: string
        format: date
      - in: query
        name: to_date
        type: string
        format: date
    responses:
      200:
        description: Order flow analytics
    """
    db = get_user_client(paginate=True)
    try:
        from_date, to_date, start_utc, end_utc = _date_range(7)
    except ValueError:
        return jsonify({"error": MSG.ANALYTICS_INVALID_DATE}), 400

    q = (
        db.table("orders")
        .select("id,status,delivery_window_id,batch_id,created_at,total_amount")
        .gte("created_at", start_utc)
        .lt("created_at", end_utc)
    )
    try:
        campus_id = _scoped_campus()
    except ValueError:
        return jsonify({"error": MSG.ANALYTICS_INVALID_CAMPUS}), 400
    if campus_id:
        q = q.eq("campus_id", campus_id)
    orders = q.execute()
    orders = orders if isinstance(orders, list) else []

    status_funnel = {}
    for o in orders:
        s = o.get("status", "unknown")
        status_funnel[s] = status_funnel.get(s, 0) + 1

    window_ids = list({o["delivery_window_id"] for o in orders if o.get("delivery_window_id")})
    windows_map = {}
    if window_ids:
        win_rows = db.table("delivery_windows").select("id,label").in_("id", window_ids).execute()
        windows_map = {w["id"]: w["label"] for w in (win_rows if isinstance(win_rows, list) else [])}

    orders_per_window = {}
    for o in orders:
        wid = o.get("delivery_window_id")
        if wid:
            label = windows_map.get(wid, wid)
            orders_per_window[label] = orders_per_window.get(label, 0) + 1

    batch_ids = list({o["batch_id"] for o in orders if o.get("batch_id")})
    zone_counts = {}
    if batch_ids:
        batch_rows = db.table("delivery_batches").select("id,zone").in_("id", batch_ids).execute()
        batch_zone = {b["id"]: b.get("zone") or "unzoned" for b in (batch_rows if isinstance(batch_rows, list) else [])}
        for o in orders:
            bid = o.get("batch_id")
            if bid:
                zone = batch_zone.get(bid, "unzoned")
                zone_counts[zone] = zone_counts.get(zone, 0) + 1

    unassigned = len([o for o in orders if not o.get("batch_id") and o.get("status") not in ("cancelled", "refunded")])

    hour_counts = {}
    for o in orders:
        try:
            hr = _parse_ts(o["created_at"]).astimezone(_WAT).hour
            hour_counts[hr] = hour_counts.get(hr, 0) + 1
        except Exception:
            logger.warning("orders analytics: unparseable created_at %r skipped", o.get("created_at"))
    peak_hour = max(hour_counts, key=hour_counts.get) if hour_counts else None

    total = len(orders)
    delivered = status_funnel.get("delivered", 0)

    return jsonify({
        "from_date": from_date,
        "to_date": to_date,
        "total_orders": total,
        "completion_rate": round(delivered / total * 100, 1) if total > 0 else 0,
        "status_funnel": status_funnel,
        "orders_per_delivery_window": orders_per_window,
        "orders_by_zone": zone_counts,
        "unassigned_to_batch": unassigned,
        "peak_hour_wat": peak_hour,
        "hourly_distribution": hour_counts,
    }), 200


@analytics_bp.route("/export", methods=["GET"])
@require_role("admin")
def export_csv():
    """
    Export analytics data as CSV (admin only).
    ---
    tags: [Analytics]
    parameters:
      - in: query
        name: type
        type: string
        required: true
        enum: [orders, hp_transactions, wallet_transactions, users]
      - in: query
        name: from_date
        type: string
        format: date
      - in: query
        name: to_date
        type: string
        format: date
    responses:
      200:
        description: CSV file download
    """
    db = get_user_client(paginate=True)
    export_type = request.args.get("type", "").lower()
    try:
        from_date, to_date, start_utc, end_utc = _date_range(30)
    except ValueError:
        return jsonify({"error": MSG.ANALYTICS_INVALID_DATE}), 400

    try:
        campus_id = _scoped_campus()
    except ValueError:
        return jsonify({"error": MSG.ANALYTICS_INVALID_CAMPUS}), 400

    if export_type == "orders":
        q = (
            db.table("orders")
            .select("id,status,payment_status,total_amount,subtotal,delivery_fee,discount_amount,wallet_amount_used,card_amount_used,created_at,user_id,guest_phone")
            .gte("created_at", start_utc)
            .lt("created_at", end_utc)
        )
        if campus_id:
            q = q.eq("campus_id", campus_id)
        rows = q.order("created_at.desc,id", ascending=False).execute() or []  # id: tiebreaker for a deterministic page sweep
        fieldnames = ["id", "status", "payment_status", "total_amount", "subtotal", "delivery_fee", "discount_amount", "wallet_amount_used", "card_amount_used", "user_id", "guest_phone", "created_at"]
        filename = f"orders_{from_date}_{to_date}.csv"

    elif export_type == "hp_transactions":
        q = (
            db.table("hp_transactions")
            .select("id,user_id,amount,type,status,source,reference_type,reference_id,created_at")
            .gte("created_at", start_utc)
            .lt("created_at", end_utc)
        )
        if campus_id:
            q = q.eq("campus_id", campus_id)
        rows = q.order("created_at.desc,id", ascending=False).execute() or []  # id: tiebreaker for a deterministic page sweep
        fieldnames = ["id", "user_id", "amount", "type", "status", "source", "reference_type", "reference_id", "created_at"]
        filename = f"hp_transactions_{from_date}_{to_date}.csv"

    elif export_type == "wallet_transactions":
        q = (
            db.table("wallet_transactions")
            .select("id,user_id,type,amount,balance_after,reason,reference_type,provider_reference,created_at")
            .gte("created_at", start_utc)
            .lt("created_at", end_utc)
        )
        if campus_id:
            q = q.eq("campus_id", campus_id)
        rows = q.order("created_at.desc,id", ascending=False).execute() or []  # id: tiebreaker for a deterministic page sweep
        fieldnames = ["id", "user_id", "type", "amount", "balance_after", "reason", "reference_type", "provider_reference", "created_at"]
        filename = f"wallet_transactions_{from_date}_{to_date}.csv"

    elif export_type == "users":
        q = db.table("profiles").select("id,full_name,phone,role,is_active,hp_balance,wallet_balance,current_tier_id,created_at")
        if campus_id:
            q = q.eq("campus_id", campus_id)
        rows = q.order("created_at.desc,id", ascending=False).execute() or []  # id: tiebreaker for a deterministic page sweep
        fieldnames = ["id", "full_name", "phone", "role", "is_active", "hp_balance", "wallet_balance", "current_tier_id", "created_at"]
        filename = f"users_{today_wat().isoformat()}.csv"

    else:
        return jsonify({"error": MSG.ANALYTICS_UNKNOWN_EXPORT.format(export_type=export_type)}), 400

    try:
        row_limit = _int_arg("limit", 5000, 1, 10000)
    except ValueError:
        return jsonify({"error": MSG.ANALYTICS_INVALID_NUMBER.format(param="limit")}), 400
    capped_rows = rows[:row_limit] if isinstance(rows, list) else rows

    def _csv_safe(value):
        if isinstance(value, str) and value[:1] in ("=", "+", "-", "@", "\t", "\r"):
            return "'" + value
        return value

    output = io.StringIO()
    writer = csv.DictWriter(output, fieldnames=fieldnames, extrasaction="ignore", lineterminator="\n")
    writer.writeheader()
    for row in capped_rows:
        writer.writerow({k: _csv_safe(v) for k, v in row.items()})

    return Response(
        output.getvalue(),
        mimetype="text/csv",
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )


@analytics_bp.route("/gifts", methods=["GET"])
@require_role("admin")
def gifts_analytics():
    """
    Gift analytics — first-order gift status breakdown.
    ---
    tags: [Analytics]
    responses:
      200:
        description: Gift stats by status
    """
    db = get_user_client(paginate=True)
    q = db.table("first_order_gifts").select("id,status,created_at")
    try:
        campus_id = _scoped_campus()
    except ValueError:
        return jsonify({"error": MSG.ANALYTICS_INVALID_CAMPUS}), 400
    if campus_id:
        q = q.eq("campus_id", campus_id)
    gifts = q.execute() or []
    status_counts = {}
    for gift in gifts:
        s = gift.get("status", "unknown")
        status_counts[s] = status_counts.get(s, 0) + 1

    return jsonify({
        "total_gifts": len(gifts),
        "by_status": status_counts,
    }), 200


@analytics_bp.route("/abandoned-carts", methods=["GET"])
@require_role("admin")
def abandoned_carts_analytics():
    """
    Abandoned cart analytics — total, recovered, and unrecovered counts.
    ---
    tags: [Analytics]
    responses:
      200:
        description: Abandoned cart stats
    """
    db = get_user_client(paginate=True)
    q = db.table("abandoned_carts").select("id,is_recovered,created_at")
    try:
        campus_id = _scoped_campus()
    except ValueError:
        return jsonify({"error": MSG.ANALYTICS_INVALID_CAMPUS}), 400
    if campus_id:
        q = q.eq("campus_id", campus_id)
    carts = q.execute() or []
    recovered = [c for c in carts if c.get("is_recovered")]
    unrecovered = [c for c in carts if not c.get("is_recovered")]

    return jsonify({
        "total_abandoned": len(carts),
        "recovered": len(recovered),
        "unrecovered": len(unrecovered),
        "recovery_rate": round(len(recovered) / len(carts) * 100, 1) if carts else 0,
    }), 200


@analytics_bp.route("/marketplace", methods=["GET"])
@require_role("admin")
def marketplace_analytics():
    """
    Marketplace analytics — purchases, code inventory status.
    ---
    tags: [Analytics]
    responses:
      200:
        description: Marketplace stats
    """
    db = get_user_client(paginate=True)
    try:
        campus_id = _scoped_campus()
    except ValueError:
        return jsonify({"error": MSG.ANALYTICS_INVALID_CAMPUS}), 400
    q_p = db.table("marketplace_purchases").select("id,wallet_amount,card_amount,pay_with_hp").eq("status", "completed")
    if campus_id:
        q_p = q_p.eq("campus_id", campus_id)
    purchases = q_p.execute() or []
    total_revenue = sum(float(p.get("wallet_amount", 0)) + float(p.get("card_amount", 0)) for p in purchases)
    hp_discount_count = len([p for p in purchases if p.get("pay_with_hp")])

    q_l = db.table("marketplace_listings").select("id,title,is_out_of_stock,listing_type")
    if campus_id:
        q_l = q_l.eq("campus_id", campus_id)
    listings = q_l.execute() or []
    low_stock = []
    low_stock_threshold = current_app.config.get("LOW_CODE_INVENTORY_THRESHOLD", 5)
    for l in listings:
        if l.get("listing_type") in _CODE_LISTING_TYPES:
            codes = db.table("marketplace_access_codes").select("id").eq("listing_id", l["id"]).eq("status", "available").execute() or []
            if len(codes) <= low_stock_threshold:
                low_stock.append({"listing_id": l["id"], "title": l["title"], "codes_remaining": len(codes)})

    return jsonify({
        "total_purchases": len(purchases),
        "total_revenue": round(total_revenue, 2),
        "hp_priced_purchases": hp_discount_count,
        "low_stock_listings": low_stock,
    }), 200


@analytics_bp.route("/users", methods=["GET"])
@require_role("admin")
def users_analytics():
    """
    User analytics — DAU, MAU, and breakdown by tier.
    ---
    tags: [Analytics]
    parameters:
      - in: query
        name: from_date
        type: string
        format: date
      - in: query
        name: to_date
        type: string
        format: date
    responses:
      200:
        description: User activity metrics with tier segmentation
    """
    db = get_user_client(paginate=True)
    now = datetime.now(timezone.utc)
    try:
        from_date, to_date, start_utc, end_utc = _date_range(30)
    except ValueError:
        return jsonify({"error": MSG.ANALYTICS_INVALID_DATE}), 400

    today_str = today_wat().isoformat()
    day_start, day_end = _wat_window(today_str, today_str)
    try:
        campus_id = _scoped_campus()
    except ValueError:
        return jsonify({"error": MSG.ANALYTICS_INVALID_CAMPUS}), 400

    q_daily = (
        db.table("orders")
        .select("user_id")
        .gte("created_at", day_start)
        .lt("created_at", day_end)
        .not_.is_("user_id", "null")
    )
    if campus_id:
        q_daily = q_daily.eq("campus_id", campus_id)
    daily_orders = q_daily.execute() or []
    dau = len({o["user_id"] for o in daily_orders})

    mau_cutoff = (now - timedelta(days=30)).isoformat()
    q_monthly = (
        db.table("orders")
        .select("user_id")
        .gte("created_at", mau_cutoff)
        .not_.is_("user_id", "null")
    )
    if campus_id:
        q_monthly = q_monthly.eq("campus_id", campus_id)
    monthly_orders = q_monthly.execute() or []
    mau = len({o["user_id"] for o in monthly_orders})

    q_users = (
        db.table("profiles")
        .select("id")
        .gte("created_at", start_utc)
        .lt("created_at", end_utc)
        .eq("role", "student")
    )
    if campus_id:
        q_users = q_users.eq("campus_id", campus_id)
    new_users = q_users.execute() or []

    tiers = db.table("hp_tiers").select("id,name,slug").execute() or []
    tier_map = {t["id"]: t.get("name", t.get("slug", "unknown")) for t in tiers}

    q_prof = (
        db.table("profiles")
        .select("current_tier_id")
        .eq("is_active", "true")
        .eq("role", "student")
    )
    if campus_id:
        q_prof = q_prof.eq("campus_id", campus_id)
    all_profiles = q_prof.execute() or []

    from collections import defaultdict
    tier_counts = defaultdict(int)
    for p in all_profiles:
        tid = p.get("current_tier_id")
        tier_name = tier_map.get(tid, "untiered") if tid else "untiered"
        tier_counts[tier_name] += 1

    return jsonify({
        "from_date": from_date,
        "to_date": to_date,
        "daily_ordering_users": dau,
        "monthly_ordering_users": mau,
        "new_signups": len(new_users),
        "total_active_users": len(all_profiles),
        "tier_breakdown": dict(tier_counts),
    }), 200


@analytics_bp.route("/retention", methods=["GET"])
@require_role("admin")
def retention_analytics():
    """
    Cohort retention — percentage of users who placed a second order,
    grouped by signup week (ISO week). Returns the last N cohort weeks.
    ---
    tags: [Analytics]
    parameters:
      - in: query
        name: weeks
        type: integer
        default: 12
    responses:
      200:
        description: Cohort retention by signup week
    """
    db = get_user_client(paginate=True)
    try:
        weeks = _int_arg("weeks", 12, 1, 52)
    except ValueError:
        return jsonify({"error": MSG.ANALYTICS_INVALID_NUMBER.format(param="weeks")}), 400
    now = datetime.now(timezone.utc)
    cutoff = (now - timedelta(weeks=weeks)).isoformat()

    try:
        campus_id = _scoped_campus()
    except ValueError:
        return jsonify({"error": MSG.ANALYTICS_INVALID_CAMPUS}), 400
    q_prof = (
        db.table("profiles")
        .select("id,created_at")
        .eq("role", "student")
        .gte("created_at", cutoff)
    )
    if campus_id:
        q_prof = q_prof.eq("campus_id", campus_id)
    profiles = q_prof.execute() or []

    if not profiles:
        return jsonify({"cohorts": [], "weeks": weeks}), 200

    user_ids = [p["id"] for p in profiles]

    from collections import defaultdict
    all_orders = []
    chunk_size = 200
    for i in range(0, len(user_ids), chunk_size):
        chunk = user_ids[i:i + chunk_size]
        q_orders = (
            db.table("orders")
            .select("user_id,created_at")
            .in_("user_id", chunk)
            .eq("status", "delivered")
        )
        if campus_id:
            q_orders = q_orders.eq("campus_id", campus_id)
        rows = q_orders.execute() or []
        all_orders.extend(rows)

    orders_per_user = defaultdict(int)
    for o in all_orders:
        if o.get("user_id"):
            orders_per_user[o["user_id"]] += 1

    cohort_data = defaultdict(lambda: {"total": 0, "retained": 0})
    for p in profiles:
        created_str = str(p.get("created_at") or "")
        try:
            dt = _parse_ts(created_str).astimezone(_WAT)
            iso = dt.isocalendar()
            cohort_key = f"{iso[0]:04d}-W{iso[1]:02d}"
        except Exception:
            logger.warning("retention: unparseable created_at %r - counted as cohort 'unknown'", created_str)
            cohort_key = "unknown"

        uid = p["id"]
        cohort_data[cohort_key]["total"] += 1
        if orders_per_user.get(uid, 0) >= 2:
            cohort_data[cohort_key]["retained"] += 1

    cohorts = []
    for week_key, data in sorted(cohort_data.items()):
        total = data["total"]
        retained = data["retained"]
        cohorts.append({
            "cohort_week": week_key,
            "total_users": total,
            "retained_users": retained,
            "retention_pct": round(100 * retained / total, 1) if total > 0 else 0,
        })

    return jsonify({"cohorts": cohorts, "weeks": weeks}), 200
