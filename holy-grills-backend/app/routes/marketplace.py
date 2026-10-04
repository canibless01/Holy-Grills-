from flask import Blueprint, request, jsonify, g, current_app
from app.middleware.auth import require_auth, require_role, resolve_scoped_campus_id
from app.services.hp_service import get_hp_balance, award_active_hp
from app.services.wallet_service import debit_wallet
from app.constants import ADMIN_ROLES
from app.db import get_db, get_user_client
from app.messages import MSG
from app.utils.settings import setting_or_config
from app.services.feature_flags import is_feature_enabled
from app.utils.upload_urls import is_trusted_upload_url
from app.utils.validators import validate_choice
from datetime import datetime, timezone
import uuid

LISTING_STATUSES = ("pending", "active", "paused", "rejected", "archived", "draft")
PURCHASE_STATUSES = ("pending", "completed", "refunded", "cancelled")
CODE_LISTING_TYPES = ("code", "digital_code", "voucher", "subscription")
PURCHASE_ADMIN_SELECT = (
    "id,user_id,status,is_fulfilled,pay_with_hp,payment_method,wallet_amount,card_amount,"
    "payment_reference,hp_tx_id,listing_id,quantity,campus_id,metadata,marketplace_listings(title,hp_price)"
)


def _non_negative_number(value):
    """True for a real number that is 0 or more (rejects bool, NaN, infinity and text)."""
    if isinstance(value, bool) or value is None:
        return False
    try:
        number = float(value)
    except (TypeError, ValueError):
        return False
    return number == number and number != float("inf") and number >= 0


def _page_args(default_limit, max_limit):
    """Read ?limit and ?offset. Returns (limit, offset), or None when they are not whole numbers."""
    try:
        limit = int(request.args.get("limit", default_limit))
        offset = int(request.args.get("offset", 0))
    except (TypeError, ValueError):
        return None
    return max(1, min(limit, max_limit)), max(0, offset)


def _log_marketplace_admin_action(entity_type, entity_id, action, before=None, after=None):
    """Write an admin_audit_logs row for a marketplace admin action. Failures are logged, never raised."""
    try:
        get_user_client().table("admin_audit_logs").insert({
            "actor_id": g.user_id,
            "actor_role": getattr(g, "user_role", "admin"),
            "entity_type": entity_type,
            "entity_id": str(entity_id),
            "action": action,
            "before_value": before,
            "after_value": after,
            "campus_id": getattr(g, "campus_id", None),
        }).execute()
    except Exception:
        current_app.logger.exception("marketplace audit log write failed (%s %s)", action, entity_id)


def _notify_campus_admins(campus_id, notif_type, template_data, reference_id=None, reference_type=None):
    """Send a notification to every admin of a campus. Super admins and campus-less admins get all of them."""
    from app.services.notification_service import send_notification
    admins = get_db().table("profiles").select("id,campus_id").in_("role", list(ADMIN_ROLES)).execute() or []
    for admin in admins:
        if campus_id and admin.get("campus_id") and admin["campus_id"] != campus_id:
            continue
        send_notification(
            user_id=admin["id"],
            notif_type=notif_type,
            template_data=template_data,
            reference_id=reference_id,
            reference_type=reference_type,
        )


def _effective_price(listing, avail):
    """The cash price a buyer pays without HP: campus override, else total_value, else price."""
    override = avail.get("price_override") if avail else None
    if override is not None:
        return float(override)
    base = listing.get("total_value")
    if base is None:
        base = listing.get("price")
    return float(base or 0)


def _is_sold_out_for_campus(listing, avail):
    if listing.get("is_out_of_stock"):
        return True
    if avail:
        if avail.get("is_out_of_stock"):
            return True
        stock = avail.get("inventory_count")
        if stock is not None and stock <= 0:
            return True
    return False


def _apply_campus_availability(db, listings, campus_id, hide_sold_out=True):
    """
    Apply the buyer campus's availability rows to listings: set the price the buyer will
    actually be charged (price, total_value, charge_price), set is_out_of_stock, and
    optionally drop sold-out listings. Used by the list, the detail page and the purchase.
    """
    availability_by_listing = {}
    if campus_id and listings:
        rows = (
            db.table("marketplace_listing_availability")
            .select("listing_id,is_out_of_stock,inventory_count,price_override")
            .in_("listing_id", [l["id"] for l in listings])
            .eq("campus_id", campus_id)
            .execute()
        ) or []
        availability_by_listing = {a["listing_id"]: a for a in rows}
    result = []
    for listing in listings:
        avail = availability_by_listing.get(listing["id"])
        sold_out = _is_sold_out_for_campus(listing, avail)
        if sold_out and hide_sold_out:
            continue
        override = avail.get("price_override") if avail else None
        base = listing.get("total_value") if listing.get("total_value") is not None else listing.get("price")
        listing["hp_only"] = (
            override is None and float(base or 0) <= 0 and int(listing.get("hp_price") or 0) > 0
        )
        price = _effective_price(listing, avail)
        listing["price"] = price
        if listing.get("total_value") is not None:
            listing["total_value"] = price
        listing["charge_price"] = price
        listing["is_out_of_stock"] = sold_out
        result.append(listing)
    return result


marketplace_bp = Blueprint("marketplace", __name__)


@marketplace_bp.route("", methods=["GET"])
@require_auth
def list_listings():
    """
    List active marketplace listings with availability filters.
    ---
    tags: [Marketplace]
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
    from app.routes.events import _get_campus_id
    db = get_user_client()
    q = db.table("marketplace_listings").select("*,hp_tiers(name,slug)").eq("status", "active").eq("is_out_of_stock", False)
    campus_id = resolve_scoped_campus_id(_get_campus_id())
    if not is_feature_enabled("marketplace_general", campus_id):
        return jsonify({"error": MSG.MARKETPLACE_NOT_OPEN}), 403
    if campus_id:
        q = q.or_(f"campus_id.eq.{campus_id},campus_id.is.null")
    now_iso = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    q = q.or_(f"available_from.is.null,available_from.lte.{now_iso}")
    q = q.or_(f"available_until.is.null,available_until.gte.{now_iso}")
    category = request.args.get("category") or request.args.get("listing_type")
    if category:
        q = q.eq("listing_type", category)
    search = request.args.get("q")
    if search:
        q = q.ilike("title", f"%{search}%")
    listings = q.order("is_featured", ascending=False).order("sort_order").execute() or []

    listings = _apply_campus_availability(db, listings, campus_id)

    return jsonify(listings), 200


@marketplace_bp.route("/<listing_id>", methods=["GET"])
@require_auth
def get_listing(listing_id):
    """
    Get marketplace listing detail.
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
    from app.routes.events import _get_campus_id
    db = get_user_client()
    listing = db.table("marketplace_listings").select("*,hp_tiers(name,slug)").eq("id", listing_id).single().execute()
    if not listing:
        return jsonify({"error": MSG.LISTING_NOT_FOUND}), 404
    campus_id = resolve_scoped_campus_id(_get_campus_id())
    if not is_feature_enabled("marketplace_general", campus_id):
        return jsonify({"error": MSG.MARKETPLACE_NOT_OPEN}), 403
    if campus_id and listing.get("campus_id") and listing.get("campus_id") != campus_id:
        return jsonify({"error": MSG.LISTING_NOT_FOUND}), 404
    listing = _apply_campus_availability(db, [listing], campus_id, hide_sold_out=False)[0]
    counted = (
        get_db().table("marketplace_access_codes")
        .select("id", count="exact")
        .eq("listing_id", listing_id)
        .eq("status", "available")
        .limit(1)
        .execute()
    )
    listing["codes_remaining"] = (counted.get("count") or 0) if isinstance(counted, dict) else 0
    return jsonify(listing), 200


@marketplace_bp.route("/<listing_id>/purchase", methods=["POST"])
@require_auth
def purchase(listing_id):
    """
    Purchase a marketplace listing. Uses atomic hg_purchase_marketplace_item RPC.
    """
    db = get_user_client()
    data = request.get_json(force=True) or {}
    buyer_campus_id = getattr(g, "campus_id", None)
    if not is_feature_enabled("marketplace_general", buyer_campus_id):
        return jsonify({"error": MSG.MARKETPLACE_NOT_OPEN}), 403
    listing = db.table("marketplace_listings").select("*").eq("id", listing_id).eq("status", "active").single().execute()
    if not listing:
        hidden = (
            get_db().table("marketplace_listings")
            .select("id,campus_id,is_out_of_stock")
            .eq("id", listing_id).eq("status", "active")
            .single().execute()
        )
        if (
            hidden
            and hidden.get("is_out_of_stock")
            and (not hidden.get("campus_id") or hidden.get("campus_id") == buyer_campus_id)
        ):
            return jsonify({"error": MSG.LISTING_OUT_OF_STOCK}), 400
        return jsonify({"error": MSG.LISTING_NOT_AVAILABLE}), 404
    if listing.get("listing_type") == "subscription" and not is_feature_enabled("subscription_codes", buyer_campus_id):
        return jsonify({"error": MSG.SUBSCRIPTION_CODES_NOT_AVAILABLE}), 403
    listing = _apply_campus_availability(db, [listing], buyer_campus_id, hide_sold_out=False)[0]
    if listing.get("is_out_of_stock"):
        return jsonify({"error": MSG.LISTING_OUT_OF_STOCK}), 400
    min_tier_id = listing.get("min_tier_id")
    if min_tier_id:
        from app.services.tier_service import can_access_tier_resource
        if not can_access_tier_resource(g.user_id, min_tier_id):
            return jsonify({"error": MSG.LISTING_TIER_TOO_LOW}), 400
    requested_use_hp = bool(data.get("use_hp", False))
    payment_method = data.get("payment_method", "wallet")
    hp_price = int(listing.get("hp_price") or 0)
    cash_price = listing.get("cash_price")
    full_price = float(listing["charge_price"])
    balance = get_hp_balance(g.user_id)
    user_hp = balance.get("active", 0)
    hp_only = listing["hp_only"]
    if hp_only and user_hp < hp_price:
        return jsonify({
            "error": MSG.PURCHASE_INSUFFICIENT_HP,
            "hp_required": hp_price,
            "hp_available": user_hp,
        }), 400
    use_hp = hp_price > 0 and user_hp >= hp_price and (requested_use_hp or hp_only)
    hp_fallback = requested_use_hp and not use_hp
    if use_hp:
        cash_due = float(cash_price) if cash_price is not None else 0.0
    else:
        cash_due = full_price
    wallet_amount = 0.0
    if cash_due > 0:
        if payment_method == "wallet":
            wallet_amount = cash_due
        elif payment_method == "split":
            if not _non_negative_number(data.get("wallet_amount", 0)):
                return jsonify({"error": MSG.WALLET_AMOUNT_INVALID}), 400
            wallet_amount = min(float(data.get("wallet_amount", 0)), cash_due)
    card_amount = cash_due - wallet_amount
    if card_amount > 0:
        from app.services.payment_service import initialize_payment
        profile = db.table("profiles").select("email").eq("id", g.user_id).single().execute()
        user_email = profile.get("email") if isinstance(profile, dict) else (g.user.get("email") if getattr(g, "user", None) else None)
        if not user_email:
            return jsonify({"error": MSG.PROFILE_EMAIL_REQUIRED_FOR_PAYMENT}), 400
        pay_result = initialize_payment(
            email=user_email,
            amount_naira=card_amount,
            reference=f"MKT-{listing_id[:8]}-{uuid.uuid4().hex[:8]}",
            metadata={
                "type": "marketplace_purchase",
                "user_id": g.user_id,
                "listing_id": listing_id,
                "quantity": 1,
                "wallet_amount": wallet_amount,
                "pay_with_hp": use_hp,
            },
        )
        return jsonify({
            "payment_required": True,
            "authorization_url": pay_result["authorization_url"],
            "reference": pay_result.get("reference"),
            "amount_due": card_amount,
            "paid_with_hp": use_hp,
            "hp_fallback": hp_fallback,
        }), 200
    idempotency_key = str(data.get("idempotency_key") or "").strip()[:100] or None
    try:
        purchase_row, code_value, marketplace_hp = _complete_marketplace_purchase(
            user_id=g.user_id,
            listing_id=listing_id,
            quantity=1,
            wallet_amount=wallet_amount,
            pay_with_hp=use_hp,
            payment_reference=idempotency_key,
            card_amount_expected=0.0,
        )
    except Exception as exc:
        err = str(exc).lower()
        if "no_codes" in err:
            get_db().table("marketplace_listings").eq("id", listing_id).update({"is_out_of_stock": True}).execute()
            return jsonify({"error": MSG.LISTING_NO_CODES}), 400
        if "out of stock" in err or "insufficient inventory" in err:
            return jsonify({"error": MSG.LISTING_OUT_OF_STOCK}), 400
        if "not available yet" in err or "no longer available" in err or "not found or inactive" in err:
            return jsonify({"error": MSG.LISTING_NOT_AVAILABLE}), 400
        if "higher hp tier" in err:
            return jsonify({"error": MSG.LISTING_TIER_TOO_LOW}), 400
        if "insufficient hp" in err or "only be bought with hp" in err:
            return jsonify({"error": MSG.PURCHASE_INSUFFICIENT_HP}), 400
        if "insufficient wallet" in err:
            return jsonify({"error": MSG.PURCHASE_INSUFFICIENT_WALLET}), 400
        if "price changed" in err:
            return jsonify({"error": MSG.PURCHASE_PRICE_CHANGED}), 409
        current_app.logger.exception("marketplace purchase failed listing=%s user=%s", listing_id, g.user_id)
        return jsonify({"error": MSG.PURCHASE_FAILED}), 400
    return jsonify({
        "purchase": purchase_row,
        "code": code_value,
        "hp_earned": marketplace_hp,
        "paid_with_hp": use_hp,
        "hp_fallback": hp_fallback,
        "cash_charged": cash_due,
        "message": MSG.MARKETPLACE_PURCHASE_SUCCESS,
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
    db = get_user_client()
    page = _page_args(20, 100)
    if page is None:
        return jsonify({"error": MSG.PAGINATION_INVALID}), 400
    limit, offset = page
    rows = (
        db.table("marketplace_purchases")
        .select("id,listing_id,quantity,pay_with_hp,status,is_fulfilled,fulfilled_at,metadata,created_at,updated_at,payment_method,wallet_amount,card_amount,marketplace_listings(title,listing_type,image_url)")
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
    db = get_user_client()
    page = _page_args(50, 200)
    if page is None:
        return jsonify({"error": MSG.PAGINATION_INVALID}), 400
    limit, offset = page
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
@require_role("admin")
def admin_update_purchase(purchase_id):
    # Status change triggers actual refund — not just status update
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
    db = get_user_client()
    data = request.get_json(force=True) or {}
    new_status = (data.get("status") or "").strip()
    if new_status not in PURCHASE_STATUSES:
        return jsonify({"error": MSG.PURCHASE_STATUS_INVALID}), 400
    purchase = (
        db.table("marketplace_purchases")
        .select(PURCHASE_ADMIN_SELECT)
        .eq("id", purchase_id)
        .single()
        .execute()
    )
    if not purchase:
        return jsonify({"error": MSG.PURCHASE_NOT_FOUND}), 404
    old_status = purchase.get("status")
    if old_status == new_status:
        return jsonify({"message": MSG.PURCHASE_NO_CHANGE, "status": new_status}), 200
    if old_status in ("refunded", "cancelled"):
        return jsonify({"error": MSG.PURCHASE_STATUS_FINAL}), 400
    listing_info = purchase.get("marketplace_listings") or {}

    if new_status in ("refunded", "cancelled"):
        guard_err = guard_refund_eligibility(db, purchase, jsonify)
        if guard_err:
            return guard_err
        failure = _refund_marketplace_purchase(db, purchase, purchase_id, new_status)
        if failure:
            return jsonify(failure[0]), failure[1]

    update_payload = {"status": new_status}
    if data.get("admin_note"):
        update_payload["admin_note"] = str(data["admin_note"])[:1000]
    if new_status == "completed" and not purchase.get("is_fulfilled"):
        fulfill_marketplace_purchase(purchase_id)
    db.table("marketplace_purchases").eq("id", purchase_id).update(update_payload).execute()
    _log_marketplace_admin_action(
        "marketplace_purchase", purchase_id, "status_change",
        before={"status": old_status}, after={"status": new_status},
    )

    try:
        from app.services.notification_service import send_notification
        send_notification(
            user_id=purchase["user_id"],
            notif_type="marketplace_purchase_status",
            template_data={"title": listing_info.get("title") or "your purchase", "status": new_status},
            reference_id=purchase_id,
            reference_type="marketplace_purchase",
        )
    except Exception:
        current_app.logger.exception("marketplace status notification failed purchase=%s", purchase_id)
    return jsonify({
        "message": MSG.PURCHASE_UPDATED,
        "purchase_id": purchase_id,
        "old_status": old_status,
        "status": new_status,
    }), 200


@marketplace_bp.route("/purchases/<purchase_id>/report", methods=["POST"])
@require_auth
def report_purchase_problem(purchase_id):
    """
    Report that a delivered access code does not work (login required).
    ---
    tags: [Marketplace]
    parameters:
      - in: body
        name: body
        schema:
          properties:
            reason: {type: string}
    responses:
      201: {description: Report sent to the admins}
      404: {description: Purchase not found}
      409: {description: A report is already open for this purchase}
    """
    from app.db import SupabaseError
    db = get_user_client()
    data = request.get_json(force=True, silent=True) or {}
    reason = str(data.get("reason") or "").strip()
    if len(reason) < 5 or len(reason) > 500:
        return jsonify({"error": MSG.PURCHASE_REPORT_REASON_INVALID}), 400
    purchase = (
        db.table("marketplace_purchases")
        .select("id,status,campus_id,marketplace_listings(title)")
        .eq("id", purchase_id)
        .eq("user_id", g.user_id)
        .single()
        .execute()
    )
    if not purchase:
        return jsonify({"error": MSG.PURCHASE_NOT_FOUND}), 404
    if purchase.get("status") != "completed":
        return jsonify({"error": MSG.PURCHASE_REPORT_NOT_ALLOWED}), 400
    campus_id = purchase.get("campus_id") or getattr(g, "campus_id", None)
    try:
        result = db.table("marketplace_purchase_reports").insert({
            "purchase_id": purchase_id,
            "user_id": g.user_id,
            "campus_id": campus_id,
            "reason": reason,
        }).execute()
    except SupabaseError as exc:
        if "23505" in str(exc) or "duplicate" in str(exc).lower():
            return jsonify({"error": MSG.PURCHASE_REPORT_ALREADY_OPEN}), 409
        raise
    saved = result[0] if isinstance(result, list) and result else result
    title = (purchase.get("marketplace_listings") or {}).get("title") or "a purchase"
    _notify_campus_admins(
        campus_id,
        "marketplace_code_report",
        {"title": title},
        saved.get("id") if isinstance(saved, dict) else None,
        "marketplace_purchase_report",
    )
    return jsonify({"message": MSG.PURCHASE_REPORT_SENT, "report": saved}), 201


@marketplace_bp.route("/admin/reports", methods=["GET"])
@require_role("admin")
def admin_list_reports():
    """
    List reported access codes for review (admin only). ?status=open (default), replaced, refunded, rejected.
    ---
    tags: [Marketplace]
    security:
      - Bearer: []
    responses:
      200: {description: Reports}
    """
    db = get_user_client()
    page = _page_args(50, 200)
    if page is None:
        return jsonify({"error": MSG.PAGINATION_INVALID}), 400
    limit, offset = page
    q = db.table("marketplace_purchase_reports").select(
        "*,marketplace_purchases(id,user_id,listing_id,metadata,marketplace_listings(title)),profiles!user_id(full_name,email)"
    )
    status = request.args.get("status", "open")
    if status:
        q = q.eq("status", status)
    rows = q.order("created_at", ascending=False).limit(limit).offset(offset).execute() or []
    return jsonify({"reports": rows, "count": len(rows)}), 200


@marketplace_bp.route("/admin/reports/<report_id>", methods=["PATCH"])
@require_role("admin")
def admin_resolve_report(report_id):
    """
    Resolve a code report: action = replace | refund | reject (admin only).
    ---
    tags: [Marketplace]
    security:
      - Bearer: []
    parameters:
      - in: body
        name: body
        schema:
          properties:
            action: {type: string, enum: [replace, refund, reject]}
            admin_note: {type: string}
    responses:
      200: {description: Report resolved}
    """
    db = get_user_client()
    data = request.get_json(force=True, silent=True) or {}
    action = (data.get("action") or "").strip()
    if action not in ("replace", "refund", "reject"):
        return jsonify({"error": MSG.PURCHASE_REPORT_ACTION_INVALID}), 400
    report = (
        db.table("marketplace_purchase_reports")
        .select("id,status,purchase_id,user_id")
        .eq("id", report_id)
        .single()
        .execute()
    )
    if not report:
        return jsonify({"error": MSG.PURCHASE_REPORT_NOT_FOUND}), 404
    if report.get("status") != "open":
        return jsonify({"error": MSG.PURCHASE_REPORT_CLOSED}), 400
    purchase = (
        db.table("marketplace_purchases")
        .select(PURCHASE_ADMIN_SELECT)
        .eq("id", report["purchase_id"])
        .single()
        .execute()
    )
    if not purchase:
        return jsonify({"error": MSG.PURCHASE_NOT_FOUND}), 404
    title = (purchase.get("marketplace_listings") or {}).get("title") or "your purchase"
    svc = get_db()
    now_iso = datetime.now(timezone.utc).isoformat()
    old_code_id = (purchase.get("metadata") or {}).get("code_id")
    new_code = None

    if action in ("replace", "refund"):
        if action == "replace":
            fresh = (
                svc.table("marketplace_access_codes")
                .select("id,code")
                .eq("listing_id", purchase["listing_id"])
                .eq("status", "available")
                .limit(1)
                .execute()
            )
            if not fresh:
                return jsonify({"error": MSG.LISTING_NO_CODES}), 400
            new_code = fresh[0]
            svc.table("marketplace_access_codes").eq("id", new_code["id"]).update({
                "status": "assigned",
                "assigned_purchase_id": purchase["id"],
                "assigned_at": now_iso,
            }).execute()
            codes_left = (
                svc.table("marketplace_access_codes").select("id")
                .eq("listing_id", purchase["listing_id"]).eq("status", "available").limit(1).execute()
            )
            if not codes_left:
                svc.table("marketplace_listings").eq("id", purchase["listing_id"]).update({"is_out_of_stock": True}).execute()
        if old_code_id:
            svc.table("marketplace_access_codes").eq("id", old_code_id).update({
                "status": "revoked",
                "assigned_purchase_id": None,
            }).execute()
        if action == "replace":
            svc.table("marketplace_purchases").eq("id", purchase["id"]).update({
                "metadata": {"code": new_code["code"], "code_id": new_code["id"], "replaced_code_id": old_code_id},
            }).execute()
        else:
            failure = _refund_marketplace_purchase(db, purchase, purchase["id"], "refunded", restock=False)
            if failure:
                return jsonify(failure[0]), failure[1]
            db.table("marketplace_purchases").eq("id", purchase["id"]).update({"status": "refunded"}).execute()

    status_map = {"replace": "replaced", "refund": "refunded", "reject": "rejected"}
    db.table("marketplace_purchase_reports").eq("id", report_id).update({
        "status": status_map[action],
        "admin_note": (str(data.get("admin_note") or "")[:1000] or None),
        "resolved_by": g.user_id,
        "resolved_at": now_iso,
    }).execute()
    _log_marketplace_admin_action(
        "marketplace_report", report_id, action,
        before={"status": "open"}, after={"status": status_map[action], "purchase_id": purchase["id"]},
    )

    try:
        from app.services.notification_service import send_notification
        if action == "replace":
            send_notification(
                user_id=report["user_id"],
                notif_type="marketplace_code_replaced",
                template_data={"title": title, "code": new_code["code"]},
                reference_id=purchase["id"],
                reference_type="marketplace_purchase",
            )
        else:
            outcome = (
                "you were refunded to your wallet" if action == "refund"
                else "we could not confirm a problem with the code"
            )
            send_notification(
                user_id=report["user_id"],
                notif_type="marketplace_report_update",
                template_data={"title": title, "outcome": outcome},
                reference_id=purchase["id"],
                reference_type="marketplace_purchase",
            )
    except Exception:
        current_app.logger.exception("marketplace report notification failed report=%s", report_id)
    return jsonify({"message": MSG.PURCHASE_REPORT_RESOLVED, "status": status_map[action]}), 200


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
    db = get_user_client()
    listing = db.table("marketplace_listings").select("*,hp_tiers(name,slug)").eq("id", listing_id).limit(1).execute()
    listing = listing[0] if listing else None
    if not listing:
        return jsonify({"error": MSG.LISTING_NOT_FOUND}), 404
    def _count(table, **filters):
        query = db.table(table).select("id", count="exact")
        for column, value in filters.items():
            query = query.eq(column, value)
        counted = query.limit(1).execute()
        return (counted.get("count") or 0) if isinstance(counted, dict) else 0

    listing["codes_total"] = _count("marketplace_access_codes", listing_id=listing_id)
    listing["codes_remaining"] = _count("marketplace_access_codes", listing_id=listing_id, status="available")
    listing["purchase_count"] = _count("marketplace_purchases", listing_id=listing_id)
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
        enum: [pending, active, paused, rejected, archived, draft]
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
    db = get_user_client()
    page = _page_args(50, 200)
    if page is None:
        return jsonify({"error": MSG.PAGINATION_INVALID}), 400
    limit, offset = page
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
            listing_type: {type: string, enum: [code, manual, subscription, digital_code, voucher]}
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
    db = get_user_client()
    data = request.get_json(force=True) or {}
    for f in ["title", "listing_type", "price"]:
        if not data.get(f) and data.get(f) != 0:
            return jsonify({"error": MSG.AUTH_FIELD_REQUIRED.format(field=f)}), 400
    if not isinstance(data["title"], str) or not data["title"].strip():
        return jsonify({"error": MSG.FIELD_MUST_BE_NONEMPTY_STR.format(field="title")}), 400
    VALID_LISTING_TYPES = ("code", "manual", "subscription", "digital_code", "voucher")
    ok_lt, err_lt = validate_choice(data["listing_type"], VALID_LISTING_TYPES, "listing_type")
    if not ok_lt:
        return jsonify({"error": err_lt, "allowed_values": list(VALID_LISTING_TYPES)}), 400
    if data.get("status") and data["status"] not in LISTING_STATUSES:
        return jsonify({"error": MSG.MARKETPLACE_STATUS_INVALID}), 400
    for numeric_field in ("price", "hp_price", "cash_price", "total_value", "inventory_count", "low_inventory_threshold"):
        if data.get(numeric_field) is not None and not _non_negative_number(data[numeric_field]):
            return jsonify({"error": MSG.LISTING_INVALID_NUMBER.format(field=numeric_field)}), 400
    LISTING_COLS = {
        "title", "description", "listing_type", "price", "hp_price",
        "cash_price", "total_value", "image_url", "vendor_name", "vendor_contact_email",
        "min_tier_id", "is_featured", "sort_order", "status",
        "inventory_count", "low_inventory_threshold", "available_from", "available_until",
    }
    safe = {k: v for k, v in data.items() if k in LISTING_COLS}
    if safe.get("image_url") and not is_trusted_upload_url(safe["image_url"]):
        return jsonify({"error": MSG.UPLOAD_URL_INVALID}), 400
    for int_field in ("hp_price", "inventory_count", "low_inventory_threshold"):
        if safe.get(int_field) is not None:
            safe[int_field] = int(float(safe[int_field]))
    safe["campus_id"] = resolve_scoped_campus_id(data.get("campus_id"))
    safe.setdefault("status", "active")
    safe.setdefault("is_out_of_stock", False)
    safe.setdefault("vendor_name", current_app.config.get("MARKETPLACE_DEFAULT_VENDOR_NAME", "Holy Grills"))
    import re
    base_slug = re.sub(r"[^a-z0-9]+", "-", safe["title"].lower()).strip("-")[:54]
    safe["slug"] = f"{base_slug}-{uuid.uuid4().hex[:5]}"
    try:
        result = db.table("marketplace_listings").insert(safe).execute()
    except Exception as exc:
        from app.db import SupabaseError
        if isinstance(exc, SupabaseError):
            detail_str = (str(exc) + str(exc.details)).lower()
            if "listing_type" in detail_str and (
                "check" in detail_str or "constraint" in detail_str or "violates" in detail_str
            ):
                return jsonify({
                    "error": f"listing_type '{safe.get('listing_type')}' is not enabled in the database schema.",
                    "allowed_values": list(VALID_LISTING_TYPES),
                }), 400
        raise
    created = result[0] if isinstance(result, list) and result else result
    _log_marketplace_admin_action(
        "marketplace_listing", (created or {}).get("id"), "create",
        after={"title": safe["title"], "status": safe["status"], "campus_id": safe["campus_id"]},
    )
    return jsonify(created), 201


@marketplace_bp.route("/listings/<listing_id>/image", methods=["POST"])
@marketplace_bp.route("/admin/listings/<listing_id>/image", methods=["POST"])
@require_role("admin")
def update_listing_image(listing_id):
    """Update marketplace listing image with Cloudinary URL."""
    data = request.get_json(force=True, silent=True) or {}
    image_url = data.get("image_url")
    if not image_url:
        return jsonify({"error": MSG.LISTING_IMAGE_REQUIRED}), 400
    if not is_trusted_upload_url(image_url):
        return jsonify({"error": MSG.UPLOAD_URL_INVALID}), 400
    db = get_user_client()
    result = db.table("marketplace_listings").eq("id", listing_id).update({
        "image_url": image_url,
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }).execute()
    if not result:
        return jsonify({"error": MSG.LISTING_NOT_FOUND}), 404
    _log_marketplace_admin_action("marketplace_listing", listing_id, "update_image", after={"image_url": image_url})
    return jsonify({"image_url": image_url}), 200


@marketplace_bp.route("/admin/listings/<listing_id>/availability", methods=["PATCH"])
@require_role("admin")
def update_listing_availability(listing_id):
    db = get_user_client()
    data = request.get_json(force=True) or {}
    campus_id = resolve_scoped_campus_id(data.get("campus_id"))
    if not campus_id:
        return jsonify({"error": MSG.LISTING_CAMPUS_REQUIRED}), 400
    AVAILABILITY_FIELDS = {"inventory_count", "low_inventory_threshold", "is_out_of_stock", "price_override"}
    safe = {k: v for k, v in data.items() if k in AVAILABILITY_FIELDS}
    if not safe:
        return jsonify({"error": MSG.LISTING_AVAILABILITY_FIELD_REQUIRED}), 400
    for numeric_field in ("inventory_count", "low_inventory_threshold", "price_override"):
        if safe.get(numeric_field) is not None and not _non_negative_number(safe[numeric_field]):
            return jsonify({"error": MSG.LISTING_INVALID_NUMBER.format(field=numeric_field)}), 400
    for int_field in ("inventory_count", "low_inventory_threshold"):
        if safe.get(int_field) is not None:
            safe[int_field] = int(float(safe[int_field]))
    if "is_out_of_stock" in safe and not isinstance(safe["is_out_of_stock"], bool):
        return jsonify({"error": MSG.FIELD_MUST_BE_BOOLEAN.format(field="is_out_of_stock")}), 400
    listing = db.table("marketplace_listings").select("id").eq("id", listing_id).single().execute()
    if not listing:
        return jsonify({"error": MSG.LISTING_NOT_FOUND}), 404
    safe["updated_at"] = datetime.now(timezone.utc).isoformat()
    result = db.table("marketplace_listing_availability").upsert(
        {"listing_id": listing_id, "campus_id": campus_id, **safe},
        on_conflict="listing_id,campus_id",
    )
    _log_marketplace_admin_action(
        "marketplace_availability", listing_id, "update", after={"campus_id": campus_id, **safe},
    )
    return jsonify(result[0] if isinstance(result, list) and result else result), 200


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
    db = get_user_client()
    listing = db.table("marketplace_listings").select("id,title,status").eq("id", listing_id).single().execute()
    if not listing:
        return jsonify({"error": MSG.LISTING_NOT_FOUND}), 404
    data = request.get_json(force=True) or {}
    ALLOWED = {
        "status", "title", "description", "price", "hp_price",
        "cash_price", "total_value", "image_url", "is_featured", "sort_order",
        "is_out_of_stock", "rejection_reason",
        "min_tier_id", "inventory_count", "low_inventory_threshold",
        "available_from", "available_until",
    }
    safe = {k: v for k, v in data.items() if k in ALLOWED}
    if safe.get("image_url") and not is_trusted_upload_url(safe["image_url"]):
        return jsonify({"error": MSG.UPLOAD_URL_INVALID}), 400
    if not safe:
        return jsonify({"error": MSG.NO_VALID_FIELDS}), 400
    if "status" in safe:
        ok, err = validate_choice(safe["status"], LISTING_STATUSES, "status")
        if not ok:
            return jsonify({"error": err}), 400
        if safe["status"] == "rejected" and not (safe.get("rejection_reason") or "").strip():
            return jsonify({"error": MSG.MARKETPLACE_REJECTION_REASON_REQUIRED}), 400
    for numeric_field in ("price", "hp_price", "cash_price", "total_value", "inventory_count", "low_inventory_threshold"):
        if safe.get(numeric_field) is not None and not _non_negative_number(safe[numeric_field]):
            return jsonify({"error": MSG.LISTING_INVALID_NUMBER.format(field=numeric_field)}), 400
    for int_field in ("hp_price", "inventory_count", "low_inventory_threshold"):
        if safe.get(int_field) is not None:
            safe[int_field] = int(float(safe[int_field]))
    for bool_field in ("is_featured", "is_out_of_stock"):
        if bool_field in safe and not isinstance(safe[bool_field], bool):
            return jsonify({"error": MSG.FIELD_MUST_BE_BOOLEAN.format(field=bool_field)}), 400
    if "sort_order" in safe and safe["sort_order"] is not None:
        try:
            safe["sort_order"] = int(safe["sort_order"])
        except (TypeError, ValueError):
            return jsonify({"error": MSG.FIELD_MUST_BE_INTEGER.format(field="sort_order")}), 400
    if "title" in safe and (not isinstance(safe["title"], str) or not safe["title"].strip()):
        return jsonify({"error": MSG.FIELD_MUST_BE_NONEMPTY_STR.format(field="title")}), 400
    now_iso = datetime.now(timezone.utc).isoformat()
    if safe.get("status") == "active" and listing.get("status") != "active":
        safe["approved_by"] = g.user_id
        safe["approved_at"] = now_iso
    safe["updated_at"] = now_iso
    result = db.table("marketplace_listings").eq("id", listing_id).update(safe).execute()
    if not result:
        return jsonify({"error": MSG.LISTING_NOT_FOUND}), 404
    _log_marketplace_admin_action(
        "marketplace_listing", listing_id, "update",
        before={"status": listing.get("status"), "title": listing.get("title")},
        after={k: v for k, v in safe.items() if k != "updated_at"},
    )
    return jsonify(result[0]), 200


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
      400:
        description: Listing has purchase history
      404:
        description: Not found
    """
    db = get_user_client()
    listing = db.table("marketplace_listings").select("id,title").eq("id", listing_id).single().execute()
    if not listing:
        return jsonify({"error": MSG.LISTING_NOT_FOUND}), 404
    purchases = db.table("marketplace_purchases").select("id").eq("listing_id", listing_id).limit(1).execute()
    if purchases:
        return jsonify({"error": MSG.LISTING_HAS_PURCHASES}), 400
    db.table("marketplace_listings").eq("id", listing_id).delete().execute()
    _log_marketplace_admin_action("marketplace_listing", listing_id, "delete", before={"title": listing.get("title")})
    return jsonify({"message": MSG.LISTING_DELETED.format(title=listing.get("title") or listing_id)}), 200


@marketplace_bp.route("/requests", methods=["POST"])
@require_auth
def submit_listing_request():
    """
    Submit a vendor listing request for admin review (login required).
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
    db = get_user_client()
    data = request.get_json(force=True) or {}
    required = ["vendor_name", "vendor_email", "service_title", "category", "description", "proposed_price"]
    for f in required:
        if data.get(f) is None or data.get(f) == "":
            return jsonify({"error": MSG.AUTH_FIELD_REQUIRED.format(field=f)}), 400
    if not _non_negative_number(data["proposed_price"]):
        return jsonify({"error": MSG.LISTING_INVALID_NUMBER.format(field="proposed_price")}), 400
    vendor_email = str(data["vendor_email"]).strip()
    if "@" not in vendor_email or " " in vendor_email:
        return jsonify({"error": MSG.VENDOR_EMAIL_INVALID}), 400
    campus_id = getattr(g, "campus_id", None)
    record = {
        "vendor_name": data["vendor_name"],
        "vendor_email": vendor_email,
        "vendor_phone": data.get("vendor_phone"),
        "service_title": data["service_title"],
        "category": data["category"],
        "description": data["description"],
        "proposed_price": data["proposed_price"],
        "status": "pending",
        "requested_by": g.user_id,
        "campus_id": campus_id,
    }
    try:
        result = db.table("marketplace_requests").insert(record).execute()
    except Exception:
        current_app.logger.exception("marketplace request insert failed user=%s", g.user_id)
        return jsonify({"error": MSG.LISTING_VENDOR_UNAVAILABLE}), 503
    saved = result[0] if isinstance(result, list) and result else result
    request_id = saved.get("id") if isinstance(saved, dict) else None
    from app.services.notification_service import send_notification
    admins = get_db().table("profiles").select("id,campus_id").in_("role", list(ADMIN_ROLES)).execute() or []
    for admin in admins:
        if campus_id and admin.get("campus_id") and admin["campus_id"] != campus_id:
            continue
        send_notification(
            user_id=admin["id"],
            notif_type="marketplace_request",
            template_data={"vendor_name": data["vendor_name"], "service_title": data["service_title"]},
            reference_id=request_id,
            reference_type="marketplace_request",
        )
    send_notification(
        user_id=g.user_id,
        notif_type="vendor_request_submitted",
        template_data={},
        reference_id=request_id,
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
    db = get_user_client()
    page = _page_args(50, 200)
    if page is None:
        return jsonify({"error": MSG.PAGINATION_INVALID}), 400
    limit, offset = page
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
    db = get_user_client()
    row = db.table("marketplace_requests").select("id,status,requested_by").eq("id", request_id).single().execute()
    if not row:
        return jsonify({"error": MSG.MARKETPLACE_REQUEST_NOT_FOUND}), 404
    if row.get("status") != "pending":
        return jsonify({"error": MSG.MARKETPLACE_REQUEST_ALREADY_REVIEWED}), 400
    data = request.get_json(force=True) or {}
    status = data.get("status")
    if status not in ("approved", "rejected"):
        return jsonify({"error": MSG.MARKETPLACE_APPROVE_REJECT}), 400
    now_iso = datetime.now(timezone.utc).isoformat()
    update = {
        "status": status,
        "admin_notes": data.get("admin_notes"),
        "reviewed_by": g.user_id,
        "reviewed_at": now_iso,
        "updated_at": now_iso,
    }
    result = db.table("marketplace_requests").eq("id", request_id).update(update).execute()
    if not result:
        return jsonify({"error": MSG.MARKETPLACE_REQUEST_NOT_FOUND}), 404
    if row.get("requested_by"):
        from app.services.notification_service import send_notification
        send_notification(
            user_id=row["requested_by"],
            notif_type="vendor_request_approved" if status == "approved" else "vendor_request_rejected",
            template_data={},
            reference_id=request_id,
            reference_type="marketplace_request",
        )
    _log_marketplace_admin_action(
        "marketplace_request", request_id, status, before={"status": "pending"}, after={"status": status},
    )
    return jsonify(result[0]), 200


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
    db = get_user_client()
    data = request.get_json(force=True, silent=True) or {}
    raw_codes = data.get("codes")
    if not isinstance(raw_codes, list) or not raw_codes:
        return jsonify({"error": MSG.MARKETPLACE_CODES_REQUIRED}), 400
    if len(raw_codes) > 500:
        return jsonify({"error": MSG.LISTING_CODES_TOO_MANY}), 400
    codes = []
    for raw in raw_codes:
        if not isinstance(raw, str) or not raw.strip():
            return jsonify({"error": MSG.LISTING_CODES_INVALID}), 400
        cleaned = raw.strip()
        if cleaned not in codes:
            codes.append(cleaned)
    listing = db.table("marketplace_listings").select("id,listing_type").eq("id", listing_id).single().execute()
    if not listing:
        return jsonify({"error": MSG.LISTING_NOT_FOUND}), 404
    if listing.get("listing_type") not in CODE_LISTING_TYPES:
        return jsonify({"error": MSG.LISTING_NOT_CODE_TYPE}), 400
    existing_codes = set()
    for start in range(0, len(codes), 100):
        chunk = codes[start:start + 100]
        rows = (
            db.table("marketplace_access_codes")
            .select("code")
            .eq("listing_id", listing_id)
            .in_("code", chunk)
            .execute()
        ) or []
        existing_codes.update(r["code"] for r in rows)
    new_codes = [c for c in codes if c not in existing_codes]
    skipped_codes = [c for c in codes if c in existing_codes]
    if not new_codes:
        return jsonify({"error": MSG.LISTING_CODES_ALL_EXIST, "skipped": skipped_codes}), 400
    records = [{"listing_id": listing_id, "code": c, "status": "available"} for c in new_codes]
    try:
        db.table("marketplace_access_codes").insert(records).execute()
    except Exception:
        current_app.logger.exception("marketplace code upload failed listing=%s", listing_id)
        return jsonify({"error": MSG.LISTING_CODES_UPLOAD_FAILED}), 400
    db.table("marketplace_listings").eq("id", listing_id).update({
        "is_out_of_stock": False,
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }).execute()
    _log_marketplace_admin_action(
        "marketplace_codes", listing_id, "upload", after={"uploaded": len(records), "skipped": len(skipped_codes)},
    )
    return jsonify({"uploaded": len(records), "skipped_duplicates": skipped_codes}), 201


def guard_refund_eligibility(db, purchase, jsonify):
    """
    Call this FIRST in admin_update_purchase(), before any wallet/HP
    refund, when the target status is 'refunded' or 'cancelled'.
    """
    listing_id = purchase.get("listing_id")
    listing = db.table("marketplace_listings").select("listing_type").eq("id", listing_id).single().execute()
    is_code_listing = listing and listing.get("listing_type") in ("code", "digital_code", "voucher", "subscription")

    if is_code_listing:
        code_row = (
            db.table("marketplace_access_codes")
            .select("id, status").eq("assigned_purchase_id", purchase.get("id")).single().execute()
        )
        if code_row and code_row.get("status") == "assigned":
            return jsonify({"error": MSG.PURCHASE_CODE_DELIVERED_NO_REFUND}), 400
    return None


def _refund_marketplace_purchase(db, purchase, purchase_id, new_status, restock=True):
    """
    Pay a purchase back: wallet portion, the exact HP spent (no multiplier), then the card
    portion (all refunds go to the wallet), then restore stock. Every leg is safe to repeat.
    Returns None on success, or (json_body, status_code) on failure.
    """
    listing_info = purchase.get("marketplace_listings") or {}
    user_id = purchase.get("user_id")
    short_id = purchase_id[:8].upper()
    wallet_amt = float(purchase.get("wallet_amount") or 0)
    card_amt = float(purchase.get("card_amount") or 0)
    hp_refund = 0
    if purchase.get("pay_with_hp"):
        if purchase.get("hp_tx_id"):
            spent = get_db().table("hp_transactions").select("amount").eq("id", purchase["hp_tx_id"]).single().execute()
            hp_refund = int((spent or {}).get("amount") or 0)
        else:
            hp_refund = int(listing_info.get("hp_price") or 0)
    hp_already_refunded = False
    if hp_refund > 0 and user_id:
        done = (
            get_db().table("hp_transactions").select("id")
            .eq("user_id", user_id).eq("reference_type", "marketplace_refund").eq("reference_id", purchase_id)
            .limit(1).execute()
        )
        hp_already_refunded = bool(done)

    # 1. wallet portion
    if wallet_amt > 0 and user_id:
        try:
            from app.services.wallet_service import credit_wallet
            credit_wallet(
                user_id=user_id,
                amount=wallet_amt,
                payment_reference=f"REFUND-MKT-{short_id}",
                reference_id=purchase_id,
                reference_type="marketplace_refund",
                notes=f"Refund for marketplace purchase #{short_id}",
            )
        except Exception:
            current_app.logger.exception("marketplace wallet refund failed purchase=%s", purchase_id)
            return {"error": MSG.PURCHASE_REFUND_FAILED}, 400
    # 2. HP portion
    if hp_refund > 0 and user_id and not hp_already_refunded:
        try:
            award_active_hp(
                user_id=user_id,
                amount=hp_refund,
                txn_type="earn",
                reference_id=purchase_id,
                reference_type="marketplace_refund",
                source_type="marketplace",
                notes=f"HP refund for marketplace purchase #{short_id}",
                apply_multiplier=False,
            )
        except Exception:
            current_app.logger.exception("marketplace HP refund failed purchase=%s", purchase_id)
            if wallet_amt > 0 and user_id:
                try:
                    debit_wallet(
                        user_id=user_id,
                        amount=wallet_amt,
                        reference_id=purchase_id,
                        reference_type="marketplace_refund_reversal",
                        notes=f"Reversing wallet refund - HP refund leg failed for purchase #{short_id}",
                    )
                except Exception:
                    current_app.logger.error(
                        "marketplace refund reversal ALSO failed purchase=%s user=%s wallet_amt=%s",
                        purchase_id, user_id, wallet_amt, exc_info=True,
                    )
                    return {"error": MSG.PURCHASE_REFUND_MANUAL}, 500
            return {"error": MSG.PURCHASE_REFUND_FAILED}, 400
    # 3. card portion: all refunds credit the wallet
    if card_amt > 0 and user_id:
        try:
            from app.services.wallet_service import credit_wallet
            credit_wallet(
                user_id=user_id,
                amount=card_amt,
                payment_reference=f"REFUND-MKT-CARD-{short_id}",
                reference_id=purchase_id,
                reference_type="marketplace_refund_card",
                notes=f"Refund (card portion) for marketplace purchase #{short_id}: {new_status}",
            )
        except Exception:
            current_app.logger.exception("marketplace card-portion refund failed purchase=%s", purchase_id)
            return {"error": MSG.PURCHASE_REFUND_PARTIAL}, 500
    if restock:
        restore_inventory_on_refund(db, purchase, current_app.logger)
    return None


def _complete_marketplace_purchase(
    user_id: str,
    listing_id: str,
    quantity: int = 1,
    wallet_amount: float = 0.0,
    pay_with_hp: bool = False,
    payment_reference: str = None,
    card_amount_expected: float = 0.0,
):
    """
    Shared helper called for wallet/HP-only purchases, or from webhook for card purchases.
    """
    db = get_db()
    if payment_reference:
        # same buyer + same reference = a retry: hand back the original purchase, no second bonus or notification
        existing = (
            db.table("marketplace_purchases").select("*")
            .eq("user_id", user_id).eq("payment_reference", payment_reference).limit(1).execute()
        )
        if existing:
            return existing[0], (existing[0].get("metadata") or {}).get("code"), 0
    purchase_row = db.rpc("hg_purchase_marketplace_item", {
        "p_user_id": user_id,
        "p_listing_id": listing_id,
        "p_quantity": quantity,
        "p_pay_with_hp": pay_with_hp,
        "p_wallet_amount": wallet_amount,
        "p_payment_reference": payment_reference,
        "p_expected_card_amount": card_amount_expected,
    })
    if isinstance(purchase_row, dict) and purchase_row.get("error"):
        raise ValueError(str(purchase_row["error"]))

    purchase_id = purchase_row.get("id") if isinstance(purchase_row, dict) else str(purchase_row)
    code_value = (purchase_row.get("metadata") or {}).get("code") if isinstance(purchase_row, dict) else None

    from flask import current_app
    from app.services.notification_service import send_notification

    marketplace_hp = int(setting_or_config(
        db, "marketplace_purchase_hp", current_app.config.get("MARKETPLACE_PURCHASE_HP", 50),
        minimum=0, maximum=100000,
    ))
    if marketplace_hp > 0:
        try:
            award_active_hp(
                user_id=user_id,
                amount=marketplace_hp,
                reference_id=purchase_id,
                reference_type="marketplace_purchase",
                source_type="marketplace_purchase_reward",
                notes="HP earned on marketplace purchase",
            )
        except Exception as e:
            from app.utils.logger import get_logger
            get_logger(__name__).error("purchase: bonus HP award failed for %s, purchase %s: %s", user_id, purchase_id, e)
            marketplace_hp = 0

    listing = db.table("marketplace_listings").select("title,listing_type").eq("id", listing_id).single().execute()
    listing_title = listing.get("title", "Marketplace item") if listing else "item"
    try:
        _purchase_body = MSG.MARKETPLACE_PURCHASE_BODY.format(title=listing_title)
        if code_value:
            _purchase_body += MSG.MARKETPLACE_PURCHASE_CODE_SUFFIX.format(code=code_value)
        send_notification(
            user_id=user_id,
            notif_type="marketplace_purchase",
            title=MSG.MARKETPLACE_PURCHASE_TITLE,
            body=_purchase_body,
            reference_id=purchase_id,
            reference_type="marketplace_purchase",
            channels=["push", "in_app", "email"],
        )
        if isinstance(purchase_row, dict) and purchase_row.get("status") == "pending":
            _notify_campus_admins(
                purchase_row.get("campus_id"),
                "marketplace_purchase_pending",
                {"title": listing_title},
                purchase_id,
                "marketplace_purchase",
            )
        if listing and listing.get("listing_type") in CODE_LISTING_TYPES:
            codes_left = db.table("marketplace_access_codes").select("id").eq("listing_id", listing_id).eq("status", "available").execute()
            if len(codes_left or []) <= setting_or_config(
                db, "low_code_inventory_threshold",
                current_app.config.get("LOW_CODE_INVENTORY_THRESHOLD", 5),
                minimum=0, maximum=10000,
            ):
                _alert_admin_low_inventory(listing_id, listing_title, len(codes_left or []))
    except Exception:
        current_app.logger.exception("marketplace purchase side effects failed purchase=%s", purchase_id)

    return purchase_row, code_value, marketplace_hp


def fulfill_marketplace_purchase(purchase_id: str, reference: str = None):
    db = get_db()
    purchase = db.table("marketplace_purchases").select("id,listing_id,is_fulfilled,status").eq("id", purchase_id).single().execute()
    if not purchase or purchase.get("is_fulfilled"):
        return purchase

    update_payload = {
        "status": "completed",
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }
    if reference:
        update_payload["payment_reference"] = reference

    code_row = (
        db.table("marketplace_access_codes")
        .select("id,code")
        .eq("listing_id", purchase["listing_id"])
        .eq("status", "available")
        .limit(1)
        .execute()
    )
    code_row = code_row[0] if code_row else None
    if code_row:
        db.table("marketplace_access_codes").eq("id", code_row["id"]).update({
            "status": "assigned",
            "assigned_purchase_id": purchase_id,
            "assigned_at": datetime.now(timezone.utc).isoformat(),
        }).execute()
        update_payload["metadata"] = {"code": code_row["code"], "code_id": code_row["id"]}

    update_payload["is_fulfilled"] = True
    update_payload["fulfilled_at"] = datetime.now(timezone.utc).isoformat()

    db.table("marketplace_purchases").eq("id", purchase_id).update(update_payload).execute()
    return db.table("marketplace_purchases").eq("id", purchase_id).single().execute()


def restore_inventory_on_refund(db, purchase, logger):
    """
    Give stock back after a refund/cancel: the listing's own count (only when it has one),
    the buyer campus's availability count (only when it has one), and any code still tied
    to the purchase. Never marks a listing in stock just because a refund happened.
    """
    listing_id = purchase.get("listing_id")
    purchase_id = purchase.get("id")
    quantity = purchase.get("quantity", 1)
    if not listing_id:
        return
    listing = db.table("marketplace_listings").select("inventory_count,status").eq("id", listing_id).single().execute()
    if listing and listing.get("inventory_count") is not None:
        restored = {
            "inventory_count": listing["inventory_count"] + quantity,
            "is_out_of_stock": False,
        }
        # the database pauses a listing when its stock reaches 0; bring it back when stock returns
        if listing["inventory_count"] <= 0 and listing.get("status") == "paused":
            restored["status"] = "active"
        db.table("marketplace_listings").eq("id", listing_id).update(restored).execute()
    campus_id = purchase.get("campus_id")
    if campus_id:
        avail = (
            db.table("marketplace_listing_availability")
            .select("id,inventory_count")
            .eq("listing_id", listing_id)
            .eq("campus_id", campus_id)
            .single()
            .execute()
        )
        if avail and avail.get("inventory_count") is not None:
            db.table("marketplace_listing_availability").eq("id", avail["id"]).update({
                "inventory_count": avail["inventory_count"] + quantity,
                "is_out_of_stock": False,
            }).execute()
    if purchase_id:
        code_row = (
            db.table("marketplace_access_codes")
            .select("id")
            .eq("assigned_purchase_id", purchase_id)
            .single()
            .execute()
        )
        if code_row:
            db.table("marketplace_access_codes").eq("id", code_row["id"]).update({
                "status": "available",
                "assigned_purchase_id": None,
                "assigned_at": None,
            }).execute()


def _alert_admin_low_inventory(listing_id: str, title: str, remaining: int):
    from app.db import get_db
    from app.constants import ADMIN_ROLES
    db = get_db()
    admins = db.table("profiles").select("id,campus_id").in_("role", list(ADMIN_ROLES)).execute()
    from app.services.notification_service import send_notification
    listing_campus = db.table("marketplace_listings").select("campus_id").eq("id", listing_id).single().execute()
    listing_campus_id = listing_campus.get("campus_id") if listing_campus else None

    for admin in admins or []:
        if listing_campus_id and admin.get("campus_id") and admin["campus_id"] != listing_campus_id:
            continue
        send_notification(
            user_id=admin["id"],
            notif_type="low_inventory",
            template_data={"title": title, "remaining": remaining},
            reference_id=listing_id,
            reference_type="marketplace_listing",
        )


def complete_marketplace_card_purchase(user_id, listing_id, quantity, wallet_amount, pay_with_hp, payment_reference, amount_paid):
    """
    Card-payment entry point for the Paystack and Flutterwave webhooks.
    If the purchase cannot be completed after the card was charged (sold out, HP or wallet ran
    short, price changed), the amount paid goes back to the buyer's wallet and the buyer is told.
    The error is re-raised so the webhook is marked failed and the admins are alerted.
    """
    try:
        return _complete_marketplace_purchase(
            user_id=user_id,
            listing_id=listing_id,
            quantity=quantity,
            wallet_amount=wallet_amount,
            pay_with_hp=pay_with_hp,
            payment_reference=payment_reference,
            card_amount_expected=float(amount_paid),
        )
    except Exception:
        current_app.logger.exception(
            "marketplace card purchase failed after payment ref=%s user=%s", payment_reference, user_id
        )
        from app.services.wallet_service import credit_wallet
        from app.services.notification_service import send_notification
        credit_wallet(
            user_id=user_id,
            amount=float(amount_paid),
            payment_reference=f"MKTFAIL-{payment_reference}",
            reference_type="marketplace_refund",
            notes=f"Refund: marketplace purchase could not be completed ({payment_reference})",
        )
        listing = get_db().table("marketplace_listings").select("title").eq("id", listing_id).single().execute()
        send_notification(
            user_id=user_id,
            notif_type="marketplace_purchase_status",
            template_data={"title": (listing or {}).get("title") or "your purchase", "status": "refunded to your wallet"},
            reference_type="marketplace_purchase",
        )
        raise
