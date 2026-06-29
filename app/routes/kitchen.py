"""Kitchen dashboard routes — role: kitchen only."""

from flask import Blueprint, request, jsonify, g
from app.middleware.auth import require_role
from app.db import get_db
from datetime import datetime, timezone

kitchen_bp = Blueprint("kitchen", __name__)


@kitchen_bp.route("/queue", methods=["GET"])
@require_role("kitchen", "admin")
def live_queue():
    """
    Get live order queue for kitchen. Shows received and preparing orders.
    No financial data exposed to kitchen role.
    ---
    tags: [Kitchen]
    parameters:
      - in: query
        name: window_id
        type: string
    responses:
      200:
        description: Kitchen order queue
    """
    db = get_db()
    q = (
        db.table("orders")
        .select("id,status,notes,received_at,preparing_at,delivery_windows(label,ends_at),order_items(name_snapshot,quantity)")
        .in_("status", ["received", "preparing"])
        .order("received_at")
    )
    window_id = request.args.get("window_id")
    if window_id:
        q = q.eq("delivery_window_id", window_id)

    orders = q.execute()
    return jsonify(orders), 200


@kitchen_bp.route("/windows", methods=["GET"])
@require_role("kitchen", "admin")
def delivery_windows():
    """
    Get current and upcoming delivery windows for kitchen view.
    ---
    tags: [Kitchen]
    responses:
      200:
        description: Delivery windows
    """
    db = get_db()
    now = datetime.now(timezone.utc).isoformat()
    windows = (
        db.table("delivery_windows")
        .select("id,label,starts_at,ends_at,status")
        .gte("ends_at", now)
        .order("starts_at")
        .execute()
    )
    window_ids = [w["id"] for w in windows]
    counts = {}
    for wid in window_ids:
        rows = db.table("orders").select("id").eq("delivery_window_id", wid).execute()
        counts[wid] = len(rows)

    for w in windows:
        w["order_count"] = counts.get(w["id"], 0)

    return jsonify(windows), 200


@kitchen_bp.route("/metrics", methods=["GET"])
@require_role("kitchen", "admin")
def kitchen_metrics():
    """
    Kitchen performance metrics — average prep time, throughput per window, completion rate.
    ---
    tags: [Kitchen]
    parameters:
      - in: query
        name: window_id
        type: string
        description: Filter to a specific delivery window
    responses:
      200:
        description: Kitchen metrics summary
    """
    db = get_db()
    q = db.table("orders").select("id,status,received_at,preparing_at,ready_at,delivery_window_id")

    window_id = request.args.get("window_id")
    if window_id:
        q = q.eq("delivery_window_id", window_id)

    orders = q.execute() or []

    prep_times = []
    for o in orders:
        received = o.get("received_at") or o.get("preparing_at")
        ready = o.get("ready_at")
        if received and ready:
            try:
                from datetime import datetime as _dt
                r = _dt.fromisoformat(received.replace("Z", "+00:00"))
                rd = _dt.fromisoformat(ready.replace("Z", "+00:00"))
                diff_minutes = (rd - r).total_seconds() / 60
                if 0 < diff_minutes < 300:
                    prep_times.append(round(diff_minutes, 1))
            except Exception:
                pass

    avg_prep_time = round(sum(prep_times) / len(prep_times), 1) if prep_times else None

    total = len(orders)
    by_status = {}
    for o in orders:
        s = o.get("status", "unknown")
        by_status[s] = by_status.get(s, 0) + 1

    throughput_by_window = {}
    for o in orders:
        wid = o.get("delivery_window_id")
        if wid:
            throughput_by_window[wid] = throughput_by_window.get(wid, 0) + 1

    ready_or_delivered = by_status.get("ready", 0) + by_status.get("assigned", 0) + by_status.get("out_for_delivery", 0) + by_status.get("delivered", 0)
    throughput_rate = round(ready_or_delivered / total * 100, 1) if total > 0 else 0

    return jsonify({
        "window_id": window_id,
        "total_orders": total,
        "orders_by_status": by_status,
        "avg_prep_time_minutes": avg_prep_time,
        "throughput_rate_pct": throughput_rate,
        "throughput_by_window": throughput_by_window,
        "prep_time_samples": len(prep_times),
    }), 200


@kitchen_bp.route("/batch-summary/<window_id>", methods=["GET"])
@require_role("kitchen", "admin")
def batch_summary(window_id):
    """
    Get consolidated prep list for a delivery window batch.
    ---
    tags: [Kitchen]
    parameters:
      - in: path
        name: window_id
        type: string
        required: true
    responses:
      200:
        description: Aggregated item quantities for the window
    """
    db = get_db()
    orders = (
        db.table("orders")
        .select("id,order_items(name_snapshot,quantity)")
        .eq("delivery_window_id", window_id)
        .in_("status", ["received", "preparing", "ready"])
        .execute()
    )

    aggregated: dict[str, int] = {}
    for order in orders:
        for item in order.get("order_items", []):
            name = item.get("name_snapshot", "Unknown")
            qty = item.get("quantity", 1)
            aggregated[name] = aggregated.get(name, 0) + qty

    summary = [{"item_name": k, "total_quantity": v} for k, v in sorted(aggregated.items())]
    return jsonify({"window_id": window_id, "summary": summary, "total_orders": len(orders)}), 200
