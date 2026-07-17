"""Kitchen dashboard routes — role: kitchen only."""

from flask import Blueprint, request, jsonify, g
from app.middleware.auth import require_role
from app.db import get_db
from app.messages import MSG
from datetime import datetime, timezone

kitchen_bp = Blueprint("kitchen", __name__)


@kitchen_bp.route("/settings", methods=["GET"])
@require_role("kitchen", "admin")
def get_kitchen_settings():
    """
    Get all kitchen settings as a key/value map.
    ---
    tags: [Kitchen]
    responses:
      200:
        description: Kitchen settings key/value map
    """
    db = get_db()
    rows = db.table("kitchen_settings").select("*").execute() or []
    settings = {r["key"]: r["value"] for r in rows}
    return jsonify({
        "settings": settings,
        "updated_at": {r["key"]: r.get("updated_at") for r in rows},
    }), 200


@kitchen_bp.route("/settings/<key>", methods=["GET"])
@require_role("kitchen", "admin")
def get_kitchen_setting(key):
    """
    Get a single kitchen setting by key.
    ---
    tags: [Kitchen]
    parameters:
      - in: path
        name: key
        type: string
        required: true
    responses:
      200:
        description: Kitchen setting
      404:
        description: Setting not found
    """
    db = get_db()
    row = db.table("kitchen_settings").select("*").eq("key", key).limit(1).execute()
    row = row[0] if row else None
    if not row:
        return jsonify({"error": MSG.KITCHEN_SETTING_NOT_FOUND}), 404
    return jsonify(row), 200


@kitchen_bp.route("/settings", methods=["PATCH"])
@require_role("admin")
def update_kitchen_settings():
    """
    Update one or more kitchen settings (key/value upsert). Admin only.
    ---
    tags: [Kitchen]
    parameters:
      - in: body
        name: body
        required: true
        schema:
          required: [settings]
          properties:
            settings:
              type: object
              description: Map of setting key -> new value
              example: {"max_active_orders": "40", "auto_accept_orders": "true"}
    responses:
      200:
        description: Kitchen settings updated
      400:
        description: "settings object missing or empty"
    """
    data = request.get_json(force=True) or {}
    settings = data.get("settings")
    if not settings or not isinstance(settings, dict):
        return jsonify({"error": MSG.KITCHEN_SETTINGS_REQUIRED}), 400

    db = get_db()
    now = datetime.now(timezone.utc).isoformat()
    updated = {}
    for key, value in settings.items():
        payload = {
            "key": key,
            "value": str(value),
            "updated_by": g.user_id,
            "updated_at": now,
        }
        result = db.table("kitchen_settings").upsert(payload, on_conflict="key")
        updated[key] = (result[0] if isinstance(result, list) else result) or payload

    return jsonify({"message": MSG.KITCHEN_SETTINGS_UPDATED, "settings": updated}), 200


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


@kitchen_bp.route("/scheduled", methods=["GET"])
@require_role("kitchen", "admin")
def scheduled_orders():
    """
    Get all scheduled orders awaiting promotion to the live queue.

    Returns orders with status='scheduled', sorted by scheduled_for ascending
    so the soonest orders appear first. Optionally filtered by delivery window.

    Kitchen staff use this view to see upcoming scheduled work before it
    auto-promotes to 'received'. Transition: PATCH /orders/<id>/status with
    {"status": "received"} to pull an order into the live queue early.
    ---
    tags: [Kitchen]
    parameters:
      - in: query
        name: window_id
        type: string
        description: Filter to a specific delivery window
    responses:
      200:
        description: List of scheduled orders with items and window info
    """
    db = get_db()
    # Scheduled orders: is_scheduled=True AND status='received' (not yet activated).
    # The DB enum does not include a 'scheduled' status value; the is_scheduled
    # boolean column is the authoritative discriminator. Once kitchen promotes an
    # order to 'preparing' it leaves this view automatically.
    q = (
        db.table("orders")
        .select(
            "id,status,notes,scheduled_for,is_scheduled,received_at,created_at,"
            "delivery_windows(id,label,starts_at,ends_at),"
            "order_items(name_snapshot,quantity,price_snapshot)"
        )
        .eq("is_scheduled", "true")
        .eq("status", "received")
        .order("scheduled_for", ascending=True)
    )
    window_id = request.args.get("window_id")
    if window_id:
        q = q.eq("delivery_window_id", window_id)

    orders = q.execute() or []
    return jsonify({"scheduled_orders": orders, "count": len(orders)}), 200


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


@kitchen_bp.route("/batch/<batch_id>/advance", methods=["POST"])
@require_role("kitchen", "admin")
def batch_advance(batch_id):
    """
    Advance every order in a delivery-window batch to its next status.
    Batch ID is a delivery_window_id. Each order is advanced one step
    using the standard state machine (received → preparing → ready, etc.).

    Orders that cannot be advanced (e.g. already delivered, cancelled)
    are skipped — their IDs are returned in `skipped`.
    ---
    tags: [Kitchen]
    parameters:
      - in: path
        name: batch_id
        description: Delivery window ID whose active orders should be advanced
        type: string
        required: true
      - in: body
        name: body
        schema:
          properties:
            from_status:
              type: string
              description: Only advance orders currently in this status (optional filter)
            notes:
              type: string
    responses:
      200:
        description: Orders advanced. Returns count of advanced + skipped orders.
      404:
        description: No orders found in this batch
    """
    from app.services.order_service import update_order_status, VALID_TRANSITIONS
    db = get_db()
    data = request.get_json(force=True) or {}
    from_status_filter = data.get("from_status")
    notes = data.get("notes", f"Batch advance by kitchen ({batch_id[:8]})")

    q = (
        db.table("orders")
        .select("id,status")
        .eq("delivery_window_id", batch_id)
        .not_.in_("status", ["delivered", "cancelled", "delivery_attempted", "unclaimed"])
    )
    if from_status_filter:
        q = q.eq("status", from_status_filter)

    orders = q.execute() or []
    if not orders:
        return jsonify({"error": "No advanceable orders found in this batch", "batch_id": batch_id}), 404

    advanced = []
    skipped = []
    for order in orders:
        oid = order["id"]
        current = order.get("status")
        next_statuses = VALID_TRANSITIONS.get(current, [])
        if not next_statuses:
            skipped.append({"order_id": oid, "reason": f"No valid transitions from '{current}'"})
            continue
        next_status = next_statuses[0]
        try:
            update_order_status(oid, next_status, changed_by=g.user_id, notes=notes)
            advanced.append({"order_id": oid, "from": current, "to": next_status})
        except Exception as e:
            skipped.append({"order_id": oid, "reason": str(e)})

    return jsonify({
        "batch_id": batch_id,
        "advanced_count": len(advanced),
        "skipped_count": len(skipped),
        "advanced": advanced,
        "skipped": skipped,
    }), 200
