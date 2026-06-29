"""Admin panel routes — users, orders, delivery windows, promo codes, audit log."""

from flask import Blueprint, request, jsonify, g
from app.middleware.auth import require_role
from app.services.notification_service import send_notification
from app.db import get_db
from datetime import datetime, timezone

admin_bp = Blueprint("admin", __name__)


@admin_bp.route("/users", methods=["GET"])
@require_role("admin")
def list_users():
    """
    List all users with HP balance and tier info.
    ---
    tags: [Admin]
    parameters:
      - in: query
        name: q
        type: string
      - in: query
        name: role
        type: string
      - in: query
        name: limit
        type: integer
        default: 50
    responses:
      200:
        description: User list
    """
    db = get_db()
    limit = min(int(request.args.get("limit", 50)), 200)
    offset = int(request.args.get("offset", 0))

    q = db.table("profiles").select("id,full_name,phone,role,is_active,created_at,referral_code,hp_balance,wallet_balance,current_tier_id")
    role_filter = request.args.get("role")
    if role_filter:
        q = q.eq("role", role_filter)
    search = request.args.get("q")
    if search:
        q = q.ilike("full_name", f"%{search}%")

    users = q.order("created_at", ascending=False).limit(limit).offset(offset).execute()
    return jsonify(users), 200


@admin_bp.route("/users/<user_id>", methods=["GET"])
@require_role("admin")
def get_user(user_id):
    """
    Get full user profile with order history and HP ledger.
    ---
    tags: [Admin]
    parameters:
      - in: path
        name: user_id
        type: string
        required: true
    responses:
      200:
        description: User detail
    """
    db = get_db()
    profile = db.table("profiles").select("*").eq("id", user_id).single().execute()
    if not profile:
        return jsonify({"error": "User not found"}), 404

    from app.services.hp_service import get_hp_balance, get_user_tier
    balance = get_hp_balance(user_id)
    tier = get_user_tier(user_id)
    wallet = db.table("wallets").select("balance").eq("user_id", user_id).single().execute()
    recent_orders = (
        db.table("orders")
        .select("id,status,total_amount,created_at")
        .eq("user_id", user_id)
        .order("created_at", ascending=False)
        .limit(10)
        .execute()
    )

    return jsonify({
        "profile": profile,
        "hp_balance": balance,
        "tier": tier,
        "wallet_balance": float(wallet.get("balance", 0)) if wallet else 0,
        "recent_orders": recent_orders,
    }), 200


@admin_bp.route("/orders", methods=["GET"])
@require_role("admin")
def list_all_orders():
    """
    List all orders across all users (admin only).
    Supports filtering by status, user, date range, and payment method.
    ---
    tags: [Admin]
    parameters:
      - in: query
        name: status
        type: string
        description: Filter by order status
      - in: query
        name: user_id
        type: string
        description: Filter by user UUID
      - in: query
        name: from_date
        type: string
        format: date
      - in: query
        name: to_date
        type: string
        format: date
      - in: query
        name: payment_method
        type: string
      - in: query
        name: limit
        type: integer
        default: 50
      - in: query
        name: offset
        type: integer
        default: 0
    responses:
      200:
        description: List of all orders with user and item details
    """
    db = get_db()
    limit = min(int(request.args.get("limit", 50)), 200)
    offset = int(request.args.get("offset", 0))

    q = db.table("orders").select("*,order_items(name_snapshot,quantity,price_snapshot,line_total)")

    status = request.args.get("status")
    if status:
        q = q.eq("status", status)

    user_id = request.args.get("user_id")
    if user_id:
        q = q.eq("user_id", user_id)

    payment_method = request.args.get("payment_method")
    if payment_method:
        if payment_method == "wallet":
            q = q.gt("wallet_amount_used", 0)
        elif payment_method == "card":
            q = q.gt("card_amount_used", 0)

    from_date = request.args.get("from_date")
    if from_date:
        q = q.gte("created_at", from_date)

    to_date = request.args.get("to_date")
    if to_date:
        q = q.lte("created_at", to_date + "T23:59:59Z")

    orders = q.order("created_at", ascending=False).limit(limit).offset(offset).execute() or []
    return jsonify({"orders": orders, "count": len(orders), "limit": limit, "offset": offset}), 200


@admin_bp.route("/users/<user_id>/orders", methods=["GET"])
@require_role("admin")
def user_order_history(user_id):
    """
    Get complete order history for a specific user (admin only).
    ---
    tags: [Admin]
    parameters:
      - in: path
        name: user_id
        type: string
        required: true
      - in: query
        name: status
        type: string
      - in: query
        name: limit
        type: integer
        default: 50
      - in: query
        name: offset
        type: integer
        default: 0
    responses:
      200:
        description: User's full order history
      404:
        description: User not found
    """
    db = get_db()
    profile = db.table("profiles").select("id,full_name").eq("id", user_id).single().execute()
    if not profile:
        return jsonify({"error": "User not found"}), 404

    limit = min(int(request.args.get("limit", 50)), 200)
    offset = int(request.args.get("offset", 0))

    q = db.table("orders").select("*,order_items(name_snapshot,quantity,price_snapshot,line_total)").eq("user_id", user_id)
    status = request.args.get("status")
    if status:
        q = q.eq("status", status)

    orders = q.order("created_at", ascending=False).limit(limit).offset(offset).execute() or []

    total_spent = sum(float(o.get("total_amount", 0)) for o in orders if o.get("status") == "delivered")

    return jsonify({
        "user": {"id": profile["id"], "full_name": profile["full_name"]},
        "orders": orders,
        "count": len(orders),
        "total_spent": round(total_spent, 2),
        "limit": limit,
        "offset": offset,
    }), 200


@admin_bp.route("/users/<user_id>/deactivate", methods=["POST"])
@require_role("admin")
def deactivate_user(user_id):
    """
    Deactivate a user account (admin only).
    ---
    tags: [Admin]
    parameters:
      - in: path
        name: user_id
        type: string
        required: true
    responses:
      200:
        description: User deactivated
    """
    db = get_db()
    db.table("profiles").eq("id", user_id).update({
        "is_active": False,
        "deactivated_at": datetime.now(timezone.utc).isoformat(),
        "deactivated_by": g.user_id,
    })
    _audit(g.user_id, "profiles", user_id, "deactivate_account")
    return jsonify({"message": "User deactivated"}), 200


@admin_bp.route("/users/<user_id>/activate", methods=["POST"])
@require_role("admin")
def activate_user(user_id):
    """
    Reactivate a previously deactivated user account (admin only).
    ---
    tags: [Admin]
    parameters:
      - in: path
        name: user_id
        type: string
        required: true
    responses:
      200:
        description: User reactivated
      404:
        description: User not found
    """
    db = get_db()
    profile = db.table("profiles").select("id,is_active,full_name").eq("id", user_id).single().execute()
    if not profile:
        return jsonify({"error": "User not found"}), 404
    if profile.get("is_active"):
        return jsonify({"message": "User is already active", "user_id": user_id}), 200

    db.table("profiles").eq("id", user_id).update({
        "is_active": True,
        "deactivated_at": None,
        "deactivated_by": None,
    })
    _audit(g.user_id, "profiles", user_id, "activate_account")
    return jsonify({"message": "User reactivated", "user_id": user_id}), 200


@admin_bp.route("/delivery-windows", methods=["GET"])
@require_role("admin", "kitchen")
def list_windows():
    """
    List delivery windows (admin/kitchen).
    ---
    tags: [Admin]
    responses:
      200:
        description: Delivery windows
    """
    db = get_db()
    windows = db.table("delivery_windows").select("*").order("starts_at", ascending=False).limit(50).execute()
    for w in (windows or []):
        orders = db.table("orders").select("id").eq("delivery_window_id", w["id"]).execute()
        w["order_count"] = len(orders or [])
    return jsonify(windows), 200


@admin_bp.route("/delivery-windows", methods=["POST"])
@require_role("admin")
def create_window():
    """
    Create a delivery window (admin only).
    ---
    tags: [Admin]
    parameters:
      - in: body
        name: body
        required: true
        schema:
          required: [label, starts_at, ends_at]
          properties:
            label: {type: string}
            starts_at: {type: string, format: date-time}
            ends_at: {type: string, format: date-time}
    responses:
      201:
        description: Window created
    """
    db = get_db()
    data = request.get_json(force=True)
    if "opens_at" in data:
        data["starts_at"] = data.pop("opens_at")
    if "closes_at" in data:
        data["ends_at"] = data.pop("closes_at")
    data["status"] = "open"
    data["created_by"] = g.user_id
    result = db.table("delivery_windows").insert(data)
    return jsonify(result[0] if isinstance(result, list) else result), 201


@admin_bp.route("/delivery-windows/<window_id>/close", methods=["POST"])
@require_role("admin")
def close_window(window_id):
    """
    Close a delivery window (admin only).
    ---
    tags: [Admin]
    parameters:
      - in: path
        name: window_id
        type: string
        required: true
    responses:
      200:
        description: Window closed
    """
    db = get_db()
    db.table("delivery_windows").eq("id", window_id).update({"status": "closed"})
    _audit(g.user_id, "delivery_windows", window_id, "close_window")
    return jsonify({"message": "Window closed"}), 200


@admin_bp.route("/delivery-windows/<window_id>/reopen", methods=["POST"])
@require_role("admin")
def reopen_window(window_id):
    """
    Reopen a previously closed delivery window (admin only).
    ---
    tags: [Admin]
    parameters:
      - in: path
        name: window_id
        type: string
        required: true
    responses:
      200:
        description: Window reopened
      404:
        description: Window not found
    """
    db = get_db()
    window = db.table("delivery_windows").select("id,status").eq("id", window_id).single().execute()
    if not window:
        return jsonify({"error": "Delivery window not found"}), 404
    if window.get("status") == "open":
        return jsonify({"message": "Window is already open", "status": "open"}), 200
    db.table("delivery_windows").eq("id", window_id).update({"status": "open"})
    _audit(g.user_id, "delivery_windows", window_id, "reopen_window")
    return jsonify({"message": "Window reopened", "window_id": window_id, "status": "open"}), 200


@admin_bp.route("/delivery-batches", methods=["POST"])
@require_role("admin")
def create_batch():
    """
    Create a delivery batch and assign a rider (admin only).
    ---
    tags: [Admin]
    parameters:
      - in: body
        name: body
        required: true
        schema:
          required: [window_id, rider_id, zone]
          properties:
            window_id: {type: string}
            rider_id: {type: string}
            zone: {type: string}
            order_ids: {type: array, items: {type: string}}
    responses:
      201:
        description: Batch created and orders assigned
    """
    db = get_db()
    data = request.get_json(force=True)
    batch = db.table("delivery_batches").insert({
        "window_id": data["window_id"],
        "rider_id": data["rider_id"],
        "zone": data.get("zone", ""),
        "status": "assigned",
    })
    batch_row = batch[0] if isinstance(batch, list) else batch
    batch_id = batch_row["id"]

    for order_id in data.get("order_ids", []):
        db.table("orders").eq("id", order_id).update({"batch_id": batch_id})

    return jsonify(batch_row), 201


@admin_bp.route("/promo-codes", methods=["GET"])
@require_role("admin")
def list_promos():
    """
    List all promo codes (admin only).
    ---
    tags: [Admin]
    responses:
      200:
        description: Promo code list
    """
    db = get_db()
    codes = db.table("promo_codes").select("*").order("created_at", ascending=False).execute()
    return jsonify(codes), 200


@admin_bp.route("/promo-codes", methods=["POST"])
@require_role("admin")
def create_promo():
    """
    Create a promo code (admin only).
    ---
    tags: [Admin]
    parameters:
      - in: body
        name: body
        required: true
        schema:
          required: [code, discount_type, discount_value]
          properties:
            code: {type: string}
            discount_type: {type: string, enum: [percentage, flat]}
            discount_value: {type: number}
            min_order_value: {type: number}
            max_discount_cap: {type: number}
            max_uses: {type: integer}
            max_uses_per_user: {type: integer}
            valid_from: {type: string, format: date-time}
            valid_until: {type: string, format: date-time}
            scope: {type: string, enum: [cart, item]}
    responses:
      201:
        description: Promo code created
    """
    db = get_db()
    data = request.get_json(force=True)
    required = ["code", "discount_type", "discount_value"]
    for f in required:
        if data.get(f) is None:
            return jsonify({"error": f"'{f}' is required"}), 400
    data["code"] = data["code"].upper()
    data["used_count"] = 0
    data["is_active"] = True
    data["created_by"] = g.user_id
    KNOWN_COLUMNS = {
        "code", "discount_type", "discount_value", "min_order_value",
        "max_discount_cap", "max_uses", "max_uses_per_user",
        "scope", "used_count", "is_active", "created_by",
        "starts_at", "ends_at", "expires_at",
        "description", "is_one_time", "applicable_item_ids",
    }
    safe = {k: v for k, v in data.items() if k in KNOWN_COLUMNS}
    result = db.table("promo_codes").insert(safe)
    return jsonify(result[0] if isinstance(result, list) else result), 201


@admin_bp.route("/abandoned-carts", methods=["GET"])
@require_role("admin")
def abandoned_carts():
    """
    List abandoned carts for recovery (admin only).
    ---
    tags: [Admin]
    responses:
      200:
        description: Abandoned cart list
    """
    db = get_db()
    carts = (
        db.table("abandoned_carts")
        .select("*,profiles(full_name)")
        .eq("is_recovered", "false")
        .order("last_active_at", ascending=False)
        .execute()
    )
    return jsonify(carts), 200


@admin_bp.route("/abandoned-carts/<cart_id>/nudge", methods=["POST"])
@require_role("admin")
def nudge_cart(cart_id):
    """
    Manually trigger recovery nudge for an abandoned cart (admin only).
    ---
    tags: [Admin]
    parameters:
      - in: path
        name: cart_id
        type: string
        required: true
    responses:
      200:
        description: Recovery nudge sent
    """
    db = get_db()
    cart = db.table("abandoned_carts").select("*").eq("id", cart_id).single().execute()
    if not cart or not cart.get("user_id"):
        return jsonify({"error": "Cart not found or guest cart"}), 404

    send_notification(
        user_id=cart["user_id"],
        notif_type="abandoned_cart",
        title="You left something behind!",
        body="Your cart is still waiting — and so is your HP. Complete your order today.",
        action_url="/cart",
        channels=["in_app", "email"],
    )
    db.table("abandoned_carts").eq("id", cart_id).update({
        "recovery_attempts": (cart.get("recovery_attempts") or 0) + 1,
        "last_recovery_sent_at": datetime.now(timezone.utc).isoformat(),
    })
    return jsonify({"message": "Recovery nudge sent"}), 200


@admin_bp.route("/audit-log", methods=["GET"])
@require_role("admin")
def audit_log():
    """
    View admin audit log (admin only).
    ---
    tags: [Admin]
    parameters:
      - in: query
        name: limit
        type: integer
        default: 50
    responses:
      200:
        description: Audit log entries
    """
    db = get_db()
    limit = min(int(request.args.get("limit", 50)), 200)
    logs = db.table("admin_audit_logs").select("*").order("created_at", ascending=False).limit(limit).execute()
    return jsonify(logs), 200


@admin_bp.route("/cron/<job_name>", methods=["POST"])
@require_role("admin")
def run_cron_job(job_name):
    """
    Manually trigger a scheduled cron job (admin only).
    Useful for testing or forcing an immediate run without waiting for Celery beat.
    ---
    tags: [Admin]
    parameters:
      - in: path
        name: job_name
        type: string
        required: true
        enum:
          - birthday-hp
          - reset-monthly-leaderboard
          - recalculate-120day-hp
          - tier-grace-period-check
          - hp-expiry-check
          - scan-abandoned-carts
          - monthly-birthday-report
    responses:
      200:
        description: Cron job result
      404:
        description: Unknown job name
      500:
        description: Job execution failed
    """
    from app.tasks.scheduled import (
        birthday_hp_awards,
        reset_monthly_leaderboard,
        recalculate_120day_hp,
        tier_grace_period_check,
        hp_expiry_check,
        scan_abandoned_carts,
        monthly_birthday_report,
    )

    task_map = {
        "birthday-hp": birthday_hp_awards,
        "reset-monthly-leaderboard": reset_monthly_leaderboard,
        "recalculate-120day-hp": recalculate_120day_hp,
        "tier-grace-period-check": tier_grace_period_check,
        "hp-expiry-check": hp_expiry_check,
        "scan-abandoned-carts": scan_abandoned_carts,
        "monthly-birthday-report": monthly_birthday_report,
    }

    task_fn = task_map.get(job_name)
    if not task_fn:
        return jsonify({
            "error": f"Unknown cron job: '{job_name}'",
            "available_jobs": sorted(task_map.keys()),
        }), 404

    import threading
    triggered_by = g.user_id

    def _run():
        try:
            task_fn.apply().get(timeout=300)
            _audit(triggered_by, "cron_jobs", job_name, "manual_trigger", {})
        except Exception as exc:
            print(f"[cron/{job_name}] background run failed: {exc}")

    t = threading.Thread(target=_run, daemon=True)
    t.start()
    return jsonify({
        "job": job_name,
        "status": "started",
        "triggered_by": triggered_by,
        "note": "Running in background — check server logs for result",
    }), 202


@admin_bp.route("/cron/status", methods=["GET"])
@require_role("admin")
def cron_status():
    """
    Show last run time, result, and status of every cron job (admin only).
    Reads from admin_audit_logs — any job that has never been manually triggered
    will show as 'never_run'. Silent failures in background threads are surfaced
    by cross-referencing the last trigger time against expected schedule cadence.
    ---
    tags: [Admin]
    responses:
      200:
        description: Cron job status map
    """
    db = get_db()

    KNOWN_JOBS = [
        "birthday-hp",
        "monthly-birthday-report",
        "hp-expiry-check",
        "tier-grace-period-check",
        "recalculate-120day-hp",
        "reset-monthly-leaderboard",
        "scan-abandoned-carts",
    ]

    EXPECTED_CADENCE = {
        "birthday-hp":               "daily @ 08:00 WAT",
        "monthly-birthday-report":   "1st of month @ 07:00 WAT",
        "hp-expiry-check":           "weekly (Sunday) @ 04:00 WAT",
        "tier-grace-period-check":   "daily @ 03:00 WAT",
        "recalculate-120day-hp":     "daily @ 02:00 WAT",
        "reset-monthly-leaderboard": "1st of month @ 00:01 WAT",
        "scan-abandoned-carts":      "every 30 minutes",
    }

    try:
        logs = (
            db.table("admin_audit_logs")
            .select("entity_id,action,created_at,after_value,actor_id")
            .eq("entity_type", "cron_jobs")
            .order("created_at", ascending=False)
            .limit(200)
            .execute()
        ) or []
    except Exception as exc:
        return jsonify({"error": f"Could not read audit logs: {exc}"}), 500

    last_by_job = {}
    for row in logs:
        job = row.get("entity_id")
        if job and job not in last_by_job:
            last_by_job[job] = row

    now_iso = datetime.now(timezone.utc).isoformat()
    status_map = {}
    for job in KNOWN_JOBS:
        entry = last_by_job.get(job)
        if entry:
            status_map[job] = {
                "status":        "ok",
                "last_triggered": entry["created_at"],
                "triggered_by":  entry.get("actor_id"),
                "last_result":   entry.get("after_value"),
                "cadence":       EXPECTED_CADENCE.get(job),
            }
        else:
            status_map[job] = {
                "status":        "never_run",
                "last_triggered": None,
                "triggered_by":  None,
                "last_result":   None,
                "cadence":       EXPECTED_CADENCE.get(job),
            }

    return jsonify({
        "checked_at": now_iso,
        "jobs":       status_map,
        "summary": {
            "total":      len(KNOWN_JOBS),
            "ok":         sum(1 for v in status_map.values() if v["status"] == "ok"),
            "never_run":  sum(1 for v in status_map.values() if v["status"] == "never_run"),
        },
    }), 200


@admin_bp.route("/hp/bulk-grant", methods=["POST"])
@require_role("admin")
def bulk_grant_hp():
    """
    Bulk-grant HP to a segment of users (by tier, last-order date, etc.) — for promotions.
    ---
    tags: [Admin]
    parameters:
      - in: body
        name: body
        required: true
        schema:
          required: [amount, reason]
          properties:
            amount:
              type: integer
              description: HP amount to award each matched user
            reason:
              type: string
              description: Human-readable reason (saved as notes on every transaction)
            tier_slug:
              type: string
              description: "Filter: only award users currently on this tier (e.g. flame, blaze, holy)"
            last_order_before:
              type: string
              format: date-time
              description: "Filter: only users whose last order was BEFORE this ISO datetime (win-back)"
            last_order_after:
              type: string
              format: date-time
              description: "Filter: only users whose last order was AFTER this ISO datetime (reward active)"
            user_ids:
              type: array
              items:
                type: string
              description: "Explicit list of user IDs — overrides all other filters"
            dry_run:
              type: boolean
              description: "If true, return matched user count/IDs without actually awarding HP"
    responses:
      200:
        description: Bulk grant result
      400:
        description: Validation error
    """
    from app.services.hp_service import award_active_hp

    db = get_db()
    data = request.get_json(force=True) or {}

    amount = data.get("amount")
    reason = data.get("reason", "").strip()
    dry_run = bool(data.get("dry_run", False))

    if not amount or int(amount) <= 0:
        return jsonify({"error": "'amount' must be a positive integer"}), 400
    if not reason:
        return jsonify({"error": "'reason' is required"}), 400

    amount = int(amount)

    # ── Build the user list ──────────────────────────────────────────────────
    explicit_ids = data.get("user_ids")
    if explicit_ids:
        # Explicit list — validate they're real users
        profiles = (
            db.table("profiles")
            .select("id,full_name,current_tier_id")
            .in_("id", explicit_ids)
            .eq("is_active", True)
            .execute()
        ) or []
    else:
        # Start from all active users
        query = db.table("profiles").select("id,full_name,current_tier_id").eq("is_active", True)

        tier_slug = data.get("tier_slug")
        if tier_slug:
            tier_row = (
                db.table("hp_tiers")
                .select("id")
                .eq("slug", tier_slug.lower())
                .single()
                .execute()
            )
            if not tier_row:
                return jsonify({"error": f"Tier slug '{tier_slug}' not found"}), 400
            query = query.eq("current_tier_id", tier_row["id"])

        profiles = query.execute() or []

        # Last-order date filters: applied in Python against orders table
        last_order_before = data.get("last_order_before")
        last_order_after = data.get("last_order_after")

        if last_order_before or last_order_after:
            user_ids_after_filter = []
            for p in profiles:
                uid = p["id"]
                q2 = (
                    db.table("orders")
                    .select("created_at")
                    .eq("user_id", uid)
                    .order("created_at", ascending=False)
                    .limit(1)
                    .execute()
                )
                last_order_date = q2[0]["created_at"] if q2 else None

                if last_order_before:
                    if not last_order_date or last_order_date >= last_order_before:
                        continue
                if last_order_after:
                    if not last_order_date or last_order_date <= last_order_after:
                        continue
                user_ids_after_filter.append(p)
            profiles = user_ids_after_filter

    if dry_run:
        return jsonify({
            "dry_run": True,
            "matched_count": len(profiles),
            "matched_user_ids": [p["id"] for p in profiles],
            "amount_per_user": amount,
            "total_hp_to_award": amount * len(profiles),
            "reason": reason,
        }), 200

    # ── Award HP to each matched user ────────────────────────────────────────
    awarded_ids = []
    failed_ids = []
    for p in profiles:
        uid = p["id"]
        try:
            award_active_hp(
                user_id=uid,
                amount=amount,
                txn_type="earn",
                reference_id=g.user_id,
                reference_type="admin_grant",
                source_type="admin_grant",
                notes=f"Bulk grant: {reason}",
                issued_by_admin_id=g.user_id,
            )
            awarded_ids.append(uid)
        except Exception as exc:
            failed_ids.append({"user_id": uid, "error": str(exc)})

    _audit(g.user_id, "profiles", "bulk", "bulk_hp_grant", {
        "amount": amount,
        "reason": reason,
        "awarded_count": len(awarded_ids),
        "failed_count": len(failed_ids),
    })

    return jsonify({
        "awarded_count": len(awarded_ids),
        "failed_count": len(failed_ids),
        "amount_per_user": amount,
        "total_hp_awarded": amount * len(awarded_ids),
        "reason": reason,
        "failed": failed_ids,
    }), 200


def _audit(actor_id, table, target_id, action, after_data=None):
    db = get_db()
    try:
        db.table("admin_audit_logs").insert({
            "actor_id": actor_id,
            "actor_role": "admin",
            "entity_type": table,
            "entity_id": target_id,
            "action": action,
            "after_value": after_data,
        })
    except Exception:
        pass
