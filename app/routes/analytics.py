"""Analytics routes — admin-only reporting and insights."""

from flask import Blueprint, request, jsonify, g, current_app, Response
from app.middleware.auth import require_role
from app.db import get_db
from app.messages import MSG
from datetime import datetime, timezone, timedelta
import csv
import io

analytics_bp = Blueprint("analytics", __name__)


@analytics_bp.route("/sales", methods=["GET"])
@require_role("admin")
def sales_analytics():
    """
    Sales analytics — revenue, order volume, AOV by date range.
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
    db = get_db()
    from_date = request.args.get("from_date", (datetime.now(timezone.utc) - timedelta(days=30)).date().isoformat())
    to_date = request.args.get("to_date", datetime.now(timezone.utc).date().isoformat())

    orders = (
        db.table("orders")
        .select("id,total_amount,subtotal,status,payment_status,created_at,wallet_amount_used")
        .gte("created_at", from_date)
        .lte("created_at", to_date + "T23:59:59Z")
        .neq("status", "cancelled")
        .execute()
    )

    delivered = [o for o in orders if o.get("status") == "delivered"]
    total_revenue = sum(float(o.get("total_amount", 0)) for o in delivered)
    order_count = len(delivered)
    aov = total_revenue / order_count if order_count > 0 else 0

    wallet_revenue = sum(float(o.get("wallet_amount_used", 0)) for o in delivered if "wallet_amount_used" in o)
    card_revenue = total_revenue - wallet_revenue

    return jsonify({
        "from_date": from_date,
        "to_date": to_date,
        "total_revenue": round(total_revenue, 2),
        "order_count": order_count,
        "average_order_value": round(aov, 2),
        "wallet_revenue": round(wallet_revenue, 2),
        "card_revenue": round(card_revenue, 2),
    }), 200


@analytics_bp.route("/hp", methods=["GET"])
@require_role("admin")
def hp_analytics():
    """
    HP ecosystem analytics — issued vs redeemed, tier distribution.
    ---
    tags: [Analytics]
    responses:
      200:
        description: HP analytics
    """
    db = get_db()
    EARN_TYPES = {"earn_order", "earn_first_order", "earn_referral", "earn_event_checkin",
                  "earn_review", "earn_birthday", "earn_challenge", "earn_admin_grant",
                  "earn_squad_bonus", "earn_streak"}
    SPEND_TYPES = {"spend_reward", "spend_marketplace", "spend_order_discount"}
    hp_txns = db.table("hp_transactions").select("amount,type,status").execute()
    earned = sum(t["amount"] for t in hp_txns if t.get("type") in EARN_TYPES and t["amount"] > 0)
    spent = abs(sum(t["amount"] for t in hp_txns if t.get("type") in SPEND_TYPES and t["amount"] < 0))
    expired = abs(sum(t["amount"] for t in hp_txns if t.get("type") == "expire" and t["amount"] < 0))
    pending = sum(t["amount"] for t in hp_txns if t.get("status") == "pending" and t["amount"] > 0)

    tiers = db.table("hp_tiers").select("id,name").order("sort_order").execute()
    tier_distribution = []
    for tier in tiers:
        count = db.table("profiles").select("id").eq("current_tier_id", tier["id"]).eq("is_active", "true").execute()
        tier_distribution.append({"tier": tier["name"], "count": len(count)})

    return jsonify({
        "hp_earned_active": earned,
        "hp_spent": spent,
        "hp_expired": expired,
        "hp_pending": pending,
        "hp_in_circulation": earned - spent - expired,
        "redemption_rate": round(spent / earned * 100, 1) if earned > 0 else 0,
        "tier_distribution": tier_distribution,
    }), 200


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
    db = get_db()
    all_referrals = db.table("referrals").select("id,hp_awarded").execute()
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
    Single call for the admin home screen. Does NOT duplicate /sales, /delivery-windows, or /batch-summary.
    ---
    tags: [Analytics]
    responses:
      200:
        description: Live dashboard snapshot
    """
    db = get_db()
    today = datetime.now(timezone.utc).date().isoformat()
    today_start = f"{today}T00:00:00Z"
    today_end   = f"{today}T23:59:59Z"

    orders_today = (
        db.table("orders")
        .select("id,status,total_amount,payment_status,delivery_window_id,batch_id,created_at")
        .gte("created_at", today_start)
        .lte("created_at", today_end)
        .execute()
    )
    orders_today = orders_today if isinstance(orders_today, list) else []

    status_counts = {}
    for o in orders_today:
        s = o.get("status", "unknown")
        status_counts[s] = status_counts.get(s, 0) + 1

    delivered_today = [o for o in orders_today if o.get("status") == "delivered"]
    revenue_today   = sum(float(o.get("total_amount", 0)) for o in delivered_today)
    active_orders   = [o for o in orders_today if o.get("status") not in ("cancelled", "refunded", "delivered")]

    open_windows = (
        db.table("delivery_windows")
        .select("id,label,starts_at,ends_at,status")
        .eq("status", "open")
        .execute()
    )
    open_windows = open_windows if isinstance(open_windows, list) else []
    windows_with_counts = []
    for w in open_windows:
        wid = w["id"]
        cnt = len([o for o in orders_today if o.get("delivery_window_id") == wid])
        windows_with_counts.append({**w, "order_count": cnt})

    active_batches = (
        db.table("delivery_batches")
        .select("id,window_id,zone,status,rider_id")
        .in_("status", ["assigned", "in_transit", "out_for_delivery"])
        .execute()
    )
    active_batches = active_batches if isinstance(active_batches, list) else []
    batches_with_counts = []
    for b in active_batches:
        bid = b["id"]
        cnt = len([o for o in orders_today if o.get("batch_id") == bid])
        batches_with_counts.append({**b, "order_count": cnt})

    payment_split = {}
    for o in orders_today:
        pm = o.get("payment_method", "unknown")
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
    Filterable by date range. Complements /sales (which covers revenue); this covers flow.
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
    db = get_db()
    from_date = request.args.get("from_date", (datetime.now(timezone.utc) - timedelta(days=7)).date().isoformat())
    to_date   = request.args.get("to_date", datetime.now(timezone.utc).date().isoformat())

    orders = (
        db.table("orders")
        .select("id,status,delivery_window_id,batch_id,created_at,total_amount")
        .gte("created_at", from_date)
        .lte("created_at", to_date + "T23:59:59Z")
        .execute()
    )
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
        batch_zone = {b["id"]: b.get("zone", "unzoned") for b in (batch_rows if isinstance(batch_rows, list) else [])}
        for o in orders:
            bid = o.get("batch_id")
            if bid:
                zone = batch_zone.get(bid, "unzoned")
                zone_counts[zone] = zone_counts.get(zone, 0) + 1

    unassigned = len([o for o in orders if not o.get("batch_id") and o.get("status") not in ("cancelled", "refunded")])

    hour_counts = {}
    for o in orders:
        try:
            hr = int(o["created_at"][11:13])
            hour_counts[hr] = hour_counts.get(hr, 0) + 1
        except Exception:
            pass
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
        "peak_hour_utc": peak_hour,
        "hourly_distribution": hour_counts,
    }), 200


@analytics_bp.route("/export", methods=["GET"])
@require_role("admin")
def export_csv():
    """
    Export analytics data as CSV (admin only).
    Exports orders, HP transactions, or wallet transactions depending on the 'type' param.
    ---
    tags: [Analytics]
    parameters:
      - in: query
        name: type
        type: string
        required: true
        enum: [orders, hp_transactions, wallet_transactions, users]
        description: Dataset to export
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
      400:
        description: Unknown export type
    """
    db = get_db()
    export_type = request.args.get("type", "").lower()
    from_date = request.args.get("from_date", (datetime.now(timezone.utc) - timedelta(days=30)).date().isoformat())
    to_date = request.args.get("to_date", datetime.now(timezone.utc).date().isoformat())

    if export_type == "orders":
        rows = (
            db.table("orders")
            .select("id,status,payment_status,total_amount,subtotal,delivery_fee,discount_amount,wallet_amount_used,card_amount_used,created_at,user_id,guest_phone")
            .gte("created_at", from_date)
            .lte("created_at", to_date + "T23:59:59Z")
            .order("created_at", ascending=False)
            .execute()
        ) or []
        fieldnames = ["id", "status", "payment_status", "total_amount", "subtotal", "delivery_fee", "discount_amount", "wallet_amount_used", "card_amount_used", "user_id", "guest_phone", "created_at"]
        filename = f"orders_{from_date}_{to_date}.csv"

    elif export_type == "hp_transactions":
        rows = (
            db.table("hp_transactions")
            .select("id,user_id,amount,type,status,source,reference_type,reference_id,created_at")
            .gte("created_at", from_date)
            .lte("created_at", to_date + "T23:59:59Z")
            .order("created_at", ascending=False)
            .execute()
        ) or []
        fieldnames = ["id", "user_id", "amount", "type", "status", "source", "reference_type", "reference_id", "created_at"]
        filename = f"hp_transactions_{from_date}_{to_date}.csv"

    elif export_type == "wallet_transactions":
        rows = (
            db.table("wallet_transactions")
            .select("id,user_id,type,amount,balance_after,reason,reference_type,provider_reference,created_at")
            .gte("created_at", from_date)
            .lte("created_at", to_date + "T23:59:59Z")
            .order("created_at", ascending=False)
            .execute()
        ) or []
        fieldnames = ["id", "user_id", "type", "amount", "balance_after", "reason", "reference_type", "provider_reference", "created_at"]
        filename = f"wallet_transactions_{from_date}_{to_date}.csv"

    elif export_type == "users":
        rows = (
            db.table("profiles")
            .select("id,full_name,phone,role,is_active,hp_balance,wallet_balance,current_tier_id,created_at")
            .order("created_at", ascending=False)
            .execute()
        ) or []
        fieldnames = ["id", "full_name", "phone", "role", "is_active", "hp_balance", "wallet_balance", "current_tier_id", "created_at"]
        filename = f"users_{datetime.now(timezone.utc).date().isoformat()}.csv"

    else:
        return jsonify({"error": MSG.ANALYTICS_UNKNOWN_EXPORT.format(export_type=export_type)}), 400

    output = io.StringIO()
    writer = csv.DictWriter(output, fieldnames=fieldnames, extrasaction="ignore", lineterminator="\n")
    writer.writeheader()
    for row in rows:
        writer.writerow(row)

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
    db = get_db()
    gifts = db.table("first_order_gifts").select("id,status,created_at").execute() or []
    status_counts = {}
    for g in gifts:
        s = g.get("status", "unknown")
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
    db = get_db()
    carts = db.table("abandoned_carts").select("id,is_recovered,created_at").execute() or []
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
    db = get_db()
    purchases = db.table("marketplace_purchases").select("id,wallet_amount,card_amount").execute()
    total_revenue = sum(float(p.get("wallet_amount", 0)) + float(p.get("card_amount", 0)) for p in purchases)
    hp_discount_count = 0

    listings = db.table("marketplace_listings").select("id,title,is_out_of_stock,listing_type").execute()
    low_stock = []
    low_stock_threshold = current_app.config.get("LOW_CODE_INVENTORY_THRESHOLD", 5)
    for l in listings:
        if l.get("listing_type") == "code":
            codes = db.table("marketplace_access_codes").select("id").eq("listing_id", l["id"]).eq("status", "available").execute()
            if len(codes) <= low_stock_threshold:
                low_stock.append({"listing_id": l["id"], "title": l["title"], "codes_remaining": len(codes)})

    return jsonify({
        "total_purchases": len(purchases),
        "total_revenue": round(total_revenue, 2),
        "hp_priced_purchases": hp_discount_count,
        "low_stock_listings": low_stock,
    }), 200


@analytics_bp.route("/items", methods=["GET"])
@require_role("admin")
def items_analytics():
    """
    Item-level analytics — quantity sold and revenue per menu item over a date range.
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
      - in: query
        name: limit
        type: integer
        default: 50
    responses:
      200:
        description: Per-item sales breakdown sorted by qty desc
    """
    db = get_db()
    from_date = request.args.get("from_date", (datetime.now(timezone.utc) - timedelta(days=30)).date().isoformat())
    to_date = request.args.get("to_date", datetime.now(timezone.utc).date().isoformat())
    limit = min(int(request.args.get("limit", 50)), 200)

    # Fetch delivered orders in range
    orders = (
        db.table("orders")
        .select("id,subtotal")
        .eq("status", "delivered")
        .gte("delivered_at", from_date)
        .lte("delivered_at", to_date + "T23:59:59Z")
        .execute()
    ) or []

    if not orders:
        return jsonify({"from_date": from_date, "to_date": to_date, "items": [], "total_items_found": 0}), 200

    order_ids = [o["id"] for o in orders]

    # Chunk order_ids if large (avoid URL length limits in .in_() calls)
    all_items = []
    chunk_size = 200
    for i in range(0, len(order_ids), chunk_size):
        chunk = order_ids[i:i + chunk_size]
        rows = (
            db.table("order_items")
            .select("name_snapshot,quantity,unit_price")
            .in_("order_id", chunk)
            .execute()
        ) or []
        all_items.extend(rows)

    # Aggregate
    from collections import defaultdict
    agg: dict = defaultdict(lambda: {"qty": 0, "revenue": 0.0})
    for item in all_items:
        name = item.get("name_snapshot") or "Unknown"
        qty = int(item.get("quantity") or 1)
        price = float(item.get("unit_price") or 0)
        agg[name]["qty"] += qty
        agg[name]["revenue"] += price * qty

    sorted_items = sorted(agg.items(), key=lambda x: x[1]["qty"], reverse=True)[:limit]
    result = [
        {"item_name": name, "qty_sold": v["qty"], "revenue": round(v["revenue"], 2)}
        for name, v in sorted_items
    ]
    return jsonify({"from_date": from_date, "to_date": to_date, "items": result, "total_items_found": len(agg)}), 200


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
    db = get_db()
    now = datetime.now(timezone.utc)
    to_date = request.args.get("to_date", now.date().isoformat())
    from_date = request.args.get("from_date", (now - timedelta(days=30)).date().isoformat())

    # DAU: unique users who placed or received an order today
    today_str = now.date().isoformat()
    daily_orders = (
        db.table("orders")
        .select("user_id")
        .gte("created_at", today_str)
        .lte("created_at", today_str + "T23:59:59Z")
        .not_.is_("user_id", "null")
        .execute()
    ) or []
    dau = len({o["user_id"] for o in daily_orders})

    # MAU: unique users active in the last 30 days
    mau_cutoff = (now - timedelta(days=30)).isoformat()
    monthly_orders = (
        db.table("orders")
        .select("user_id")
        .gte("created_at", mau_cutoff)
        .not_.is_("user_id", "null")
        .execute()
    ) or []
    mau = len({o["user_id"] for o in monthly_orders})

    # New signups in the range
    new_users = (
        db.table("profiles")
        .select("id")
        .gte("created_at", from_date)
        .lte("created_at", to_date + "T23:59:59Z")
        .eq("role", "student")
        .execute()
    ) or []

    # Tier distribution
    tiers = db.table("hp_tiers").select("id,name,slug").execute() or []
    tier_map = {t["id"]: t.get("name", t.get("slug", "unknown")) for t in tiers}

    all_profiles = (
        db.table("profiles")
        .select("current_tier_id")
        .eq("is_active", "true")
        .eq("role", "student")
        .execute()
    ) or []

    from collections import defaultdict
    tier_counts: dict = defaultdict(int)
    for p in all_profiles:
        tid = p.get("current_tier_id")
        tier_name = tier_map.get(tid, "untiered") if tid else "untiered"
        tier_counts[tier_name] += 1

    return jsonify({
        "from_date": from_date,
        "to_date": to_date,
        "dau": dau,
        "mau": mau,
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
        description: Number of signup cohort weeks to look back
    responses:
      200:
        description: Cohort retention by signup week
    """
    db = get_db()
    weeks = min(int(request.args.get("weeks", 12)), 52)
    now = datetime.now(timezone.utc)
    cutoff = (now - timedelta(weeks=weeks)).isoformat()

    # Get all student profiles signed up in the window
    profiles = (
        db.table("profiles")
        .select("id,created_at")
        .eq("role", "student")
        .gte("created_at", cutoff)
        .execute()
    ) or []

    if not profiles:
        return jsonify({"cohorts": [], "weeks": weeks}), 200

    user_ids = [p["id"] for p in profiles]

    # Fetch all orders for these users (delivered only — true engagement)
    from collections import defaultdict
    all_orders = []
    chunk_size = 200
    for i in range(0, len(user_ids), chunk_size):
        chunk = user_ids[i:i + chunk_size]
        rows = (
            db.table("orders")
            .select("user_id,created_at")
            .in_("user_id", chunk)
            .eq("status", "delivered")
            .execute()
        ) or []
        all_orders.extend(rows)

    # Count orders per user
    orders_per_user: dict = defaultdict(int)
    for o in all_orders:
        if o.get("user_id"):
            orders_per_user[o["user_id"]] += 1

    # Group profiles by signup ISO week
    cohort_data: dict = defaultdict(lambda: {"total": 0, "retained": 0})
    for p in profiles:
        created_str = str(p.get("created_at") or "")
        try:
            dt = datetime.fromisoformat(created_str.replace("Z", "+00:00"))
            iso = dt.isocalendar()
            cohort_key = f"{iso[0]:04d}-W{iso[1]:02d}"
        except Exception:
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
