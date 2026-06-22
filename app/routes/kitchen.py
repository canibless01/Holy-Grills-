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
        .select("id,status,order_notes,received_at,preparing_at,delivery_windows(label,closes_at),order_items(item_name,quantity)")
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
        .select("id,label,opens_at,closes_at,status")
        .gte("closes_at", now)
        .order("opens_at")
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
        .select("id,order_items(item_name,quantity)")
        .eq("delivery_window_id", window_id)
        .in_("status", ["received", "preparing", "ready"])
        .execute()
    )

    aggregated: dict[str, int] = {}
    for order in orders:
        for item in order.get("order_items", []):
            name = item.get("item_name", "Unknown")
            qty = item.get("quantity", 1)
            aggregated[name] = aggregated.get(name, 0) + qty

    summary = [{"item_name": k, "total_quantity": v} for k, v in sorted(aggregated.items())]
    return jsonify({"window_id": window_id, "summary": summary, "total_orders": len(orders)}), 200
