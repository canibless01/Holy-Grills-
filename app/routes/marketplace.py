"""Marketplace routes — listings, purchases, code redemption."""

from flask import Blueprint, request, jsonify, g
from app.middleware.auth import require_auth, require_role
from app.services.hp_service import spend_hp, get_hp_balance, award_active_hp
from app.services.wallet_service import debit_wallet
from app.db import get_db
from app.messages import MSG
from app.utils.validators import validate_choice, validate_non_negative_number
from datetime import datetime, timezone
import uuid

LISTING_STATUSES = ("active", "rejected", "archived")

marketplace_bp = Blueprint("marketplace", __name__)


@marketplace_bp.route("", methods=["GET"])
def list_listings():
    """
    List active marketplace listings.
    ---
    tags: [Marketplace]
    security: []
    parameters:
      - in: query
        name: category
        type: string
      - in: query
        name: q
        type: string
    responses:
      200:
        description: Marketplace listings
    """
    db = get_db()
    q = db.table("marketplace_listings").select("*,hp_tiers(name,slug)").eq("status", "active").eq("is_out_of_stock", False)
    category = request.args.get("category") or request.args.get("listing_type")
    if category:
        q = q.eq("listing_type", category)
    search = request.args.get("q")
    if search:
        q = q.ilike("title", f"%{search}%")
    listings = q.order("is_featured", ascending=False).order("sort_order").execute()
    return jsonify(listings), 200


@marketplace_bp.route("/<listing_id>", methods=["GET"])
def get_listing(listing_id):
    """
    Get marketplace listing detail.
    ---
    tags: [Marketplace]
    security: []
    parameters:
      - in: path
        name: listing_id
        type: string
        required: true
    responses:
      200:
        description: Listing detail
      404:
        description: Not found
    """
    db = get_db()
    listing = db.table("marketplace_listings").select("*,hp_tiers(name,slug)").eq("id", listing_id).single().execute()
    if not listing:
        return jsonify({"error": MSG.LISTING_NOT_FOUND}), 404
    codes_available = db.table("marketplace_access_codes").select("id").eq("listing_id", listing_id).eq("status", "available").execute()
    listing["codes_remaining"] = len(codes_available) if isinstance(codes_available, list) else 0
    return jsonify(listing), 200


@marketplace_bp.route("/<listing_id>/purchase", methods=["POST"])
@require_auth
def purchase(listing_id):
    """
    Purchase a marketplace listing. Supports HP pricing, wallet, card, or split.
    ---
    tags: [Marketplace]
    parameters:
      - in: path
        name: listing_id
        type: string
        required: true
      - in: body
        name: body
        required: true
        schema:
          required: [use_hp_pricing, payment_method]
          properties:
            use_hp_pricing: {type: boolean}
            payment_method: {type: string, enum: [wallet, card, split]}
            wallet_amount: {type: number}
            payment_reference: {type: string, description: "Required for card payment confirmation"}
    responses:
      201:
        description: Purchase successful, code returned if applicable
      400:
        description: Validation error
    """
    db = get_db()
    data = request.get_json(force=True)
    listing = db.table("marketplace_listings").select("*").eq("id", listing_id).eq("status", "active").single().execute()
    if not listing:
        return jsonify({"error": MSG.LISTING_NOT_AVAILABLE}), 404
    if listing.get("is_out_of_stock"):
        return jsonify({"error": MSG.LISTING_OUT_OF_STOCK}), 400

    payment_method = data.get("payment_method", "wallet")
    hp_price = int(listing.get("hp_price") or 0)
    cash_price = float(listing.get("cash_price") or 0)
    total_value = float(listing.get("total_value") or listing.get("price") or 0)

    # §Pricing model:
    # If user active HP ≥ hp_price → deduct hp_price HP + charge cash_price ₦
    # Else                           → charge total_value ₦ only (no HP deducted)
    balance = get_hp_balance(g.user_id)
    user_hp = balance.get("active", 0)

    if hp_price > 0 and user_hp >= hp_price:
        hp_to_spend = hp_price
        naira_to_pay = cash_price
        use_hp = True
    else:
        hp_to_spend = 0
        naira_to_pay = total_value
        use_hp = False

    wallet_amount = 0.0
    card_amount = 0.0
    if payment_method == "wallet":
        wallet_amount = naira_to_pay
        if wallet_amount > 0:
            debit_wallet(g.user_id, wallet_amount, listing_id, "marketplace", f"Purchase: {listing['title']}")
    elif payment_method == "card":
        card_amount = naira_to_pay
    elif payment_method == "split":
        wallet_amount = float(data.get("wallet_amount", 0))
        if wallet_amount > naira_to_pay:
            wallet_amount = naira_to_pay
        card_amount = naira_to_pay - wallet_amount
        if wallet_amount > 0:
            debit_wallet(g.user_id, wallet_amount, listing_id, "marketplace", f"Wallet portion: {listing['title']}")

    purchase_record = {
        "user_id": g.user_id,
        "listing_id": listing_id,
        "pay_with_hp": use_hp,
        "payment_method": payment_method,
        "wallet_amount": wallet_amount,
        "card_amount": card_amount,
        "payment_reference": data.get("payment_reference", ""),
        "quantity": 1,
        "status": "pending",
    }

    if listing.get("listing_type") == "code":
        available_codes = (
            db.table("marketplace_access_codes")
            .select("id")
            .eq("listing_id", listing_id)
            .eq("status", "available")
            .limit(1)
            .execute()
        )
        if not available_codes or len(available_codes) == 0:
            db.table("marketplace_listings").eq("id", listing_id).update({"is_out_of_stock": True})
            return jsonify({"error": MSG.LISTING_NO_CODES}), 400
        purchase_record["metadata"] = {"code_id": available_codes[0]["id"]}

    if hp_to_spend > 0:
        spend_hp(g.user_id, hp_to_spend, listing_id, "marketplace_purchase", f"HP discount on: {listing['title']}")

    saved = db.table("marketplace_purchases").insert(purchase_record)
    purchase_row = saved[0] if isinstance(saved, list) else saved

    from flask import current_app
    marketplace_hp = int(current_app.config.get("MARKETPLACE_PURCHASE_HP", 50))
    if marketplace_hp > 0:
        # NOTE: source_type must NOT be "marketplace_purchase" — that string is
        # reserved for the HP *spend* leg above (_resolve_txn_type maps it to
        # "spend"), which would silently deduct this reward instead of adding it.
        award_active_hp(
            user_id=g.user_id,
            amount=marketplace_hp,
            reference_id=purchase_row.get("id") if isinstance(purchase_row, dict) else None,
            reference_type="marketplace_purchase",
            source_type="marketplace_purchase_reward",
            notes="HP earned on marketplace purchase",
        )

    code_value = None
    code_id = (purchase_record.get("metadata") or {}).get("code_id")
    if code_id:
        code_row = db.table("marketplace_access_codes").select("code").eq("id", code_id).single().execute()
        code_value = code_row.get("code") if code_row else None
        if code_value:
            db.table("marketplace_access_codes").eq("id", code_id).update({
                "status": "assigned",
                "assigned_purchase_id": purchase_row.get("id") if isinstance(purchase_row, dict) else None,
                "assigned_at": datetime.now(timezone.utc).isoformat(),
            })

    from app.services.notification_service import send_notification
    _purchase_body = MSG.MARKETPLACE_PURCHASE_BODY.format(title=listing["title"])
    if code_value:
        _purchase_body += MSG.MARKETPLACE_PURCHASE_CODE_SUFFIX.format(code=code_value)
    send_notification(
        user_id=g.user_id,
        notif_type="marketplace_purchase",
        title=MSG.MARKETPLACE_PURCHASE_TITLE,
        body=_purchase_body,
        reference_id=purchase_row["id"],
        reference_type="marketplace_purchase",
        channels=["push", "in_app", "email"],
    )

    codes_left = db.table("marketplace_access_codes").select("id").eq("listing_id", listing_id).eq("status", "available").execute()
    from flask import current_app
    if len(codes_left) <= current_app.config.get("LOW_CODE_INVENTORY_THRESHOLD", 5):
        _alert_admin_low_inventory(listing_id, listing["title"], len(codes_left))

    return jsonify({
        "purchase": purchase_row,
        "code": code_value,
        "hp_earned": marketplace_hp,
    }), 201


@marketplace_bp.route("/purchases", methods=["GET"])
@require_auth
def my_purchases():
    """
    Get the authenticated user's marketplace purchase history.
    ---
    tags: [Marketplace]
    parameters:
      - in: query
        name: limit
        type: integer
        default: 20
      - in: query
        name: offset
        type: integer
        default: 0
    responses:
      200:
        description: User's purchase history
    """
    db = get_db()
    limit = min(int(request.args.get("limit", 20)), 100)
    offset = int(request.args.get("offset", 0))
    rows = (
        db.table("marketplace_purchases")
        .select("*,marketplace_listings(title,listing_type,image_url)")
        .eq("user_id", g.user_id)
        .order("created_at", ascending=False)
        .limit(limit)
        .offset(offset)
        .execute()
    ) or []
    return jsonify({"purchases": rows, "count": len(rows)}), 200


@marketplace_bp.route("/admin/purchases", methods=["GET"])
@require_role("admin")
def admin_all_purchases():
    """
    List all marketplace purchases across all users (admin only).
    ---
    tags: [Marketplace]
    parameters:
      - in: query
        name: status
        type: string
      - in: query
        name: listing_id
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
        description: All marketplace purchases
    """
    db = get_db()
    limit = min(int(request.args.get("limit", 50)), 200)
    offset = int(request.args.get("offset", 0))
    q = db.table("marketplace_purchases").select(
        "*,marketplace_listings(title,listing_type,image_url),profiles!user_id(full_name,email)"
    )
    status = request.args.get("status")
    if status:
        q = q.eq("status", status)
    listing_id = request.args.get("listing_id")
    if listing_id:
        q = q.eq("listing_id", listing_id)
    rows = q.order("created_at", ascending=False).limit(limit).offset(offset).execute() or []
    return jsonify({"purchases": rows, "count": len(rows)}), 200


@marketplace_bp.route("/admin/purchases/<purchase_id>", methods=["PATCH"])
@require_auth
@require_role("admin")
def admin_update_purchase(purchase_id):
    """
    Admin: update marketplace purchase status with buyer notification.
    Escrow state transitions: pending → completed | refunded | cancelled
    A notification is sent to the buyer on every status change.
    ---
    tags: [Marketplace]
    parameters:
      - in: path
        name: purchase_id
        type: string
        required: true
      - in: body
        name: body
        required: true
        schema:
          required: [status]
          properties:
            status: {type: string, enum: [pending, completed, refunded, cancelled]}
            admin_note: {type: string}
    responses:
      200:
        description: Purchase updated and buyer notified
      400:
        description: Invalid status
      404:
        description: Purchase not found
    """
    db = get_db()
    data = request.get_json(force=True) or {}
    new_status = (data.get("status") or "").strip()
    VALID_STATUSES = {"pending", "completed", "refunded", "cancelled"}
    if new_status not in VALID_STATUSES:
        return jsonify({"error": f"status must be one of: {', '.join(sorted(VALID_STATUSES))}"}), 400

    purchase = (
        db.table("marketplace_purchases")
        .select("id,user_id,status,marketplace_listings(title)")
        .eq("id", purchase_id)
        .single()
        .execute()
    )
    if not purchase:
        return jsonify({"error": MSG.LISTING_NOT_FOUND}), 404

    old_status = purchase.get("status")
    if old_status == new_status:
        return jsonify({"message": "No change", "status": new_status}), 200

    update_payload = {
        "status": new_status,
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }
    if data.get("admin_note"):
        update_payload["admin_note"] = data["admin_note"]

    db.table("marketplace_purchases").eq("id", purchase_id).update(update_payload)

    # Notify buyer on every escrow state transition
    listing_info = purchase.get("marketplace_listings") or {}
    listing_title = listing_info.get("title") or "your purchase"
    try:
        from app.services.notification_service import send_notification
        send_notification(
            user_id=purchase["user_id"],
            notif_type="marketplace_purchase_status",
            template_data={"title": listing_title, "status": new_status},
            reference_id=purchase_id,
            reference_type="marketplace_purchase",
        )
    except Exception:
        pass

    return jsonify({
        "message": "Purchase updated",
        "purchase_id": purchase_id,
        "old_status": old_status,
        "status": new_status,
    }), 200


@marketplace_bp.route("/admin/listings/<listing_id>", methods=["GET"])
@require_role("admin")
def admin_get_listing(listing_id):
    """
    Get full marketplace listing detail, including archived/rejected listings (admin only).
    ---
    tags: [Marketplace]
    parameters:
      - in: path
        name: listing_id
        type: string
        required: true
    responses:
      200:
        description: Listing detail
      404:
        description: Not found
    """
    db = get_db()
    listing = db.table("marketplace_listings").select("*,hp_tiers(name,slug)").eq("id", listing_id).limit(1).execute()
    listing = listing[0] if listing else None
    if not listing:
        return jsonify({"error": MSG.LISTING_NOT_FOUND}), 404
    codes = db.table("marketplace_access_codes").select("id,status").eq("listing_id", listing_id).execute() or []
    listing["codes_total"] = len(codes)
    listing["codes_remaining"] = len([c for c in codes if c.get("status") == "available"])
    purchases = db.table("marketplace_purchases").select("id").eq("listing_id", listing_id).execute() or []
    listing["purchase_count"] = len(purchases)
    return jsonify(listing), 200


@marketplace_bp.route("/admin/listings", methods=["GET"])
@require_role("admin")
def admin_list_listings():
    """
    List all marketplace listings regardless of status (admin only).
    ---
    tags: [Marketplace]
    parameters:
      - in: query
        name: status
        type: string
        enum: [active, rejected, archived]
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
        description: All listings for admin review
    """
    db = get_db()
    limit = min(int(request.args.get("limit", 50)), 200)
    offset = int(request.args.get("offset", 0))
    q = db.table("marketplace_listings").select("*,hp_tiers(name,slug)")
    status = request.args.get("status")
    if status:
        q = q.eq("status", status)
    rows = q.order("created_at", ascending=False).limit(limit).offset(offset).execute() or []
    return jsonify({"listings": rows, "count": len(rows)}), 200


@marketplace_bp.route("/admin/listings", methods=["POST"])
@require_role("admin")
def admin_create_listing():
    """
    Create a marketplace listing directly (admin only).
    ---
    tags: [Marketplace]
    parameters:
      - in: body
        name: body
        required: true
        schema:
          required: [title, listing_type, price]
          properties:
            title: {type: string}
            description: {type: string}
            listing_type: {type: string, enum: [code, service, product, experience]}
            price: {type: number}
            hp_price: {type: integer}
            image_url: {type: string}
            vendor_name: {type: string}
            hp_tier_id: {type: string}
            is_featured: {type: boolean}
            sort_order: {type: integer}
            status: {type: string, enum: [active, rejected, archived]}
    responses:
      201:
        description: Listing created
      400:
        description: Validation error
    """
    db = get_db()
    data = request.get_json(force=True) or {}
    for f in ["title", "listing_type", "price"]:
        if not data.get(f) and data.get(f) != 0:
            return jsonify({"error": MSG.AUTH_FIELD_REQUIRED.format(field=f)}), 400
    VALID_LISTING_TYPES = ("code", "service", "product", "experience")
    ok_lt, err_lt = validate_choice(data["listing_type"], VALID_LISTING_TYPES, "listing_type")
    if not ok_lt:
        return jsonify({"error": err_lt, "allowed_values": list(VALID_LISTING_TYPES)}), 400
    if data.get("status") and data["status"] not in ("active", "rejected", "archived"):
        return jsonify({"error": MSG.MARKETPLACE_STATUS_INVALID}), 400
    LISTING_COLS = {
        "title", "description", "listing_type", "price", "hp_price",
        "cash_price", "total_value",
        "image_url", "vendor_name", "hp_tier_id", "is_featured",
        "sort_order", "status", "is_out_of_stock",
    }
    safe = {k: v for k, v in data.items() if k in LISTING_COLS}
    from flask import current_app
    # Admin-created listings go live immediately — "active" matches the
    # marketplace_listings.status check constraint (active|rejected|archived).
    safe.setdefault("status", "active")
    safe.setdefault("is_out_of_stock", False)
    safe.setdefault("vendor_name", current_app.config.get("MARKETPLACE_DEFAULT_VENDOR_NAME", "Holy Grills"))

    import re, uuid as _uuid
    base_slug = re.sub(r"[^a-z0-9]+", "-", safe["title"].lower()).strip("-")[:54]
    safe["slug"] = f"{base_slug}-{_uuid.uuid4().hex[:5]}"

    try:
        result = db.table("marketplace_listings").insert(safe)
    except Exception as exc:
        from app.db import SupabaseError
        # Only intercept DB check-constraint violations that mention the listing_type column.
        # All other DB errors are re-raised so they surface as 500 with a request ID.
        if isinstance(exc, SupabaseError):
            detail_str = (str(exc) + str(exc.details)).lower()
            if "listing_type" in detail_str and (
                "check" in detail_str or "constraint" in detail_str or "violates" in detail_str
            ):
                return jsonify({
                    "error": f"listing_type '{safe.get('listing_type')}' is not yet enabled in the database schema.",
                    "allowed_values": ["code"],
                }), 400
        raise
    return jsonify(result[0] if isinstance(result, list) else result), 201


@marketplace_bp.route("/admin/listings/<listing_id>", methods=["PATCH"])
@require_role("admin")
def admin_update_listing(listing_id):
    """
    Approve, reject, or update a marketplace listing (admin only).
    ---
    tags: [Marketplace]
    parameters:
      - in: path
        name: listing_id
        type: string
        required: true
      - in: body
        name: body
        schema:
          properties:
            status: {type: string, enum: [active, rejected, archived]}
            title: {type: string}
            description: {type: string}
            price: {type: number}
            hp_price: {type: integer}
            image_url: {type: string}
            is_featured: {type: boolean}
            sort_order: {type: integer}
            is_out_of_stock: {type: boolean}
            rejection_reason: {type: string}
    responses:
      200:
        description: Listing updated
      404:
        description: Not found
    """
    db = get_db()
    listing = db.table("marketplace_listings").select("id,title,status").eq("id", listing_id).single().execute()
    if not listing:
        return jsonify({"error": MSG.MARKETPLACE_LISTING_NOT_FOUND}), 404
    data = request.get_json(force=True) or {}
    ALLOWED = {
        "status", "title", "description", "price", "hp_price",
        "cash_price", "total_value",
        "image_url", "is_featured", "sort_order", "is_out_of_stock", "rejection_reason",
    }
    safe = {k: v for k, v in data.items() if k in ALLOWED}
    if not safe:
        return jsonify({"error": MSG.NO_VALID_FIELDS}), 400

    if "status" in safe:
        ok, err = validate_choice(safe["status"], LISTING_STATUSES, "status")
        if not ok:
            return jsonify({"error": err}), 400
        if safe["status"] == "rejected" and not (safe.get("rejection_reason") or "").strip():
            return jsonify({"error": MSG.MARKETPLACE_REJECTION_REASON_REQUIRED}), 400

    for numeric_field in ("price", "hp_price"):
        if numeric_field in safe and safe[numeric_field] is not None:
            ok, err = validate_non_negative_number(safe[numeric_field], numeric_field)
            if not ok:
                return jsonify({"error": err}), 400

    for bool_field in ("is_featured", "is_out_of_stock"):
        if bool_field in safe and not isinstance(safe[bool_field], bool):
            return jsonify({"error": f"{bool_field} must be a boolean"}), 400

    if "sort_order" in safe and safe["sort_order"] is not None:
        try:
            safe["sort_order"] = int(safe["sort_order"])
        except (TypeError, ValueError):
            return jsonify({"error": MSG.FIELD_MUST_BE_INTEGER.format(field="sort_order")}), 400

    if "title" in safe and (not isinstance(safe["title"], str) or not safe["title"].strip()):
        return jsonify({"error": MSG.FIELD_MUST_BE_NONEMPTY_STR.format(field="title")}), 400

    safe["updated_at"] = datetime.now(timezone.utc).isoformat()
    result = db.table("marketplace_listings").eq("id", listing_id).update(safe)
    return jsonify(result[0] if isinstance(result, list) else result), 200


@marketplace_bp.route("/admin/listings/<listing_id>", methods=["DELETE"])
@require_role("admin")
def admin_delete_listing(listing_id):
    """
    Delete a marketplace listing (admin only). Also removes associated access codes.
    ---
    tags: [Marketplace]
    parameters:
      - in: path
        name: listing_id
        type: string
        required: true
    responses:
      200:
        description: Listing deleted
      404:
        description: Not found
    """
    db = get_db()
    listing = db.table("marketplace_listings").select("id,title").eq("id", listing_id).single().execute()
    if not listing:
        return jsonify({"error": MSG.LISTING_NOT_FOUND}), 404
    try:
        db.table("marketplace_access_codes").eq("listing_id", listing_id).delete()
    except Exception:
        pass
    db.table("marketplace_listings").eq("id", listing_id).delete()
    return jsonify({"message": f"Listing '{listing.get('title', listing_id)}' deleted"}), 200


@marketplace_bp.route("/requests", methods=["POST"])
def submit_listing_request():
    """
    Submit a vendor listing request for admin review.
    ---
    tags: [Marketplace]
    security: []
    parameters:
      - in: body
        name: body
        required: true
        schema:
          required: [vendor_name, vendor_email, service_title, category, description, proposed_price]
          properties:
            vendor_name: {type: string}
            vendor_email: {type: string}
            vendor_phone: {type: string}
            service_title: {type: string}
            category: {type: string}
            description: {type: string}
            proposed_price: {type: number}
    responses:
      201:
        description: Request submitted
      400:
        description: Validation error
      503:
        description: Vendor request intake temporarily unavailable
    """
    db = get_db()
    data = request.get_json(force=True) or {}
    required = ["vendor_name", "vendor_email", "service_title", "category", "description", "proposed_price"]
    for f in required:
        if data.get(f) is None or data.get(f) == "":
            return jsonify({"error": MSG.AUTH_FIELD_REQUIRED.format(field=f)}), 400

    record = {
        "vendor_name": data["vendor_name"],
        "vendor_email": data["vendor_email"],
        "vendor_phone": data.get("vendor_phone"),
        "service_title": data["service_title"],
        "category": data["category"],
        "description": data["description"],
        "proposed_price": data["proposed_price"],
        "status": "pending",
    }
    try:
        result = db.table("marketplace_requests").insert(record)
    except Exception:
        # Table not provisioned yet on this environment — degrade gracefully
        # instead of a raw 500. See migrations/new_features.sql.
        return jsonify({"error": MSG.LISTING_VENDOR_UNAVAILABLE}), 503
    saved = result[0] if isinstance(result, list) else result

    admins = db.table("profiles").select("id").eq("role", "admin").execute() or []
    from app.services.notification_service import send_notification
    for admin in admins:
        send_notification(
            user_id=admin["id"],
            notif_type="marketplace_request",
            template_data={
                "vendor_name": data["vendor_name"],
                "service_title": data["service_title"],
            },
            reference_id=saved.get("id") if isinstance(saved, dict) else None,
            reference_type="marketplace_request",
        )

    return jsonify({"message": MSG.MARKETPLACE_REQUEST_SUBMITTED, "request": saved}), 201


@marketplace_bp.route("/admin/requests", methods=["GET"])
@require_role("admin")
def admin_list_requests():
    """
    List vendor listing requests for admin review.
    ---
    tags: [Marketplace]
    parameters:
      - in: query
        name: status
        type: string
        enum: [pending, approved, rejected]
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
        description: Vendor listing requests
    """
    db = get_db()
    limit = min(int(request.args.get("limit", 50)), 200)
    offset = int(request.args.get("offset", 0))
    q = db.table("marketplace_requests").select("*")
    status = request.args.get("status")
    if status:
        q = q.eq("status", status)
    rows = q.order("created_at", ascending=False).limit(limit).offset(offset).execute() or []
    return jsonify({"requests": rows, "count": len(rows)}), 200


@marketplace_bp.route("/admin/requests/<request_id>", methods=["PATCH"])
@require_role("admin")
def admin_respond_to_request(request_id):
    """
    Approve or reject a vendor listing request (admin only).
    ---
    tags: [Marketplace]
    parameters:
      - in: path
        name: request_id
        type: string
        required: true
      - in: body
        name: body
        required: true
        schema:
          required: [status]
          properties:
            status: {type: string, enum: [approved, rejected]}
            admin_notes: {type: string}
    responses:
      200:
        description: Request updated
      400:
        description: Validation error
      404:
        description: Not found
    """
    db = get_db()
    row = db.table("marketplace_requests").select("id,status").eq("id", request_id).single().execute()
    if not row:
        return jsonify({"error": MSG.MARKETPLACE_REQUEST_NOT_FOUND}), 404
    if row.get("status") != "pending":
        return jsonify({"error": MSG.MARKETPLACE_REQUEST_ALREADY_REVIEWED}), 400

    data = request.get_json(force=True) or {}
    status = data.get("status")
    if status not in ("approved", "rejected"):
        return jsonify({"error": MSG.MARKETPLACE_APPROVE_REJECT}), 400

    update = {
        "status": status,
        "admin_notes": data.get("admin_notes"),
        "reviewed_by": g.user_id,
        "reviewed_at": datetime.now(timezone.utc).isoformat(),
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }
    result = db.table("marketplace_requests").eq("id", request_id).update(update)
    return jsonify(result[0] if isinstance(result, list) else result), 200


@marketplace_bp.route("/admin/codes/<listing_id>", methods=["POST"])
@require_role("admin")
def upload_codes(listing_id):
    """
    Upload access codes for a listing (admin only). Accepts list of code strings.
    ---
    tags: [Marketplace]
    parameters:
      - in: path
        name: listing_id
        type: string
        required: true
      - in: body
        name: body
        required: true
        schema:
          required: [codes]
          properties:
            codes:
              type: array
              items: {type: string}
    responses:
      201:
        description: Codes uploaded
    """
    db = get_db()
    data = request.get_json(force=True)
    codes = data.get("codes", [])
    if not codes:
        return jsonify({"error": MSG.MARKETPLACE_CODES_REQUIRED}), 400

    records = [{"listing_id": listing_id, "code": c, "status": "available"} for c in codes]
    db.table("marketplace_access_codes").insert(records)

    db.table("marketplace_listings").eq("id", listing_id).update({
        "is_out_of_stock": False,
        "updated_at": datetime.now(timezone.utc).isoformat(),
    })
    return jsonify({"uploaded": len(records)}), 201


def _alert_admin_low_inventory(listing_id: str, title: str, remaining: int):
    from app.db import get_db
    db = get_db()
    admins = db.table("profiles").select("id").eq("role", "admin").execute()
    from app.services.notification_service import send_notification
    for admin in admins:
        send_notification(
            user_id=admin["id"],
            notif_type="low_inventory",
            template_data={"title": title, "remaining": remaining},
            reference_id=listing_id,
            reference_type="marketplace_listing",
        )
