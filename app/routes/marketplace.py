"""Marketplace routes — listings, purchases, code redemption."""

from flask import Blueprint, request, jsonify, g
from app.middleware.auth import require_auth, require_role
from app.services.hp_service import spend_hp, get_hp_balance, award_active_hp
from app.services.wallet_service import debit_wallet
from app.db import get_db
from datetime import datetime, timezone
import uuid

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
    q = db.table("marketplace_listings").select("*,tiers(name,slug)").eq("is_active", "true").eq("is_out_of_stock", "false")
    category = request.args.get("category")
    if category:
        q = q.eq("category", category)
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
    listing = db.table("marketplace_listings").select("*,tiers(name,slug)").eq("id", listing_id).single().execute()
    if not listing:
        return jsonify({"error": "Listing not found"}), 404
    codes_available = db.table("marketplace_codes").select("id").eq("listing_id", listing_id).eq("status", "available").execute()
    listing["codes_remaining"] = len(codes_available)
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
    listing = db.table("marketplace_listings").select("*").eq("id", listing_id).eq("is_active", "true").single().execute()
    if not listing:
        return jsonify({"error": "Listing not available"}), 404
    if listing.get("is_out_of_stock"):
        return jsonify({"error": "Listing is out of stock"}), 400

    use_hp = data.get("use_hp_pricing", False)
    payment_method = data.get("payment_method", "wallet")

    if use_hp:
        hp_to_spend = listing.get("hp_price_points", 0)
        naira_to_pay = float(listing.get("hp_price_naira", 0))
    else:
        hp_to_spend = 0
        naira_to_pay = float(listing.get("standard_price", 0))

    if hp_to_spend > 0:
        balance = get_hp_balance(g.user_id)
        if balance["active"] < hp_to_spend:
            return jsonify({"error": f"Insufficient HP: need {hp_to_spend}, have {balance['active']}"}), 400

    wallet_amount = 0.0
    card_amount = 0.0
    if payment_method == "wallet":
        wallet_amount = naira_to_pay
        debit_wallet(g.user_id, wallet_amount, listing_id, "marketplace", f"Purchase: {listing['title']}")
    elif payment_method == "card":
        card_amount = naira_to_pay
    elif payment_method == "split":
        wallet_amount = float(data.get("wallet_amount", 0))
        card_amount = naira_to_pay - wallet_amount
        if wallet_amount > 0:
            debit_wallet(g.user_id, wallet_amount, listing_id, "marketplace", f"Wallet portion: {listing['title']}")

    purchase_record = {
        "user_id": g.user_id,
        "listing_id": listing_id,
        "standard_price": listing.get("standard_price"),
        "amount_paid_naira": naira_to_pay,
        "hp_spent": hp_to_spend,
        "used_hp_pricing": use_hp,
        "payment_method": payment_method,
        "wallet_amount": wallet_amount,
        "card_amount": card_amount,
        "payment_reference": data.get("payment_reference", ""),
        "is_fulfilled": False,
    }

    if listing.get("listing_type") == "code":
        result = db.rpc("claim_marketplace_code", {
            "p_listing_id": listing_id,
            "p_user_id": g.user_id,
        })
        if result and isinstance(result, dict) and result.get("code_id"):
            purchase_record["code_id"] = result["code_id"]
            purchase_record["is_fulfilled"] = True
        else:
            db.table("marketplace_listings").eq("id", listing_id).update({"is_out_of_stock": True})
            return jsonify({"error": "No codes available. Listing is now out of stock."}), 400

    if hp_to_spend > 0:
        spend_hp(g.user_id, hp_to_spend, listing_id, "marketplace_purchase", f"HP discount on: {listing['title']}")

    saved = db.table("marketplace_purchases").insert(purchase_record)
    purchase_row = saved[0] if isinstance(saved, list) else saved

    award_active_hp(
        user_id=g.user_id,
        amount=50,
        txn_type="earn",
        reference_id=purchase_row["id"],
        reference_type="marketplace_purchase",
        notes="HP earned on marketplace purchase",
    )

    code_value = None
    if purchase_record.get("code_id"):
        code_row = db.table("marketplace_codes").select("code").eq("id", purchase_record["code_id"]).single().execute()
        code_value = code_row.get("code") if code_row else None

    from app.services.notification_service import send_notification
    body = f"Purchase confirmed: {listing['title']}."
    if code_value:
        body += f" Your access code: {code_value}"
    send_notification(
        user_id=g.user_id,
        notif_type="marketplace_purchase",
        title="Purchase Confirmed",
        body=body,
        reference_id=purchase_row["id"],
        reference_type="marketplace_purchase",
        channels=["in_app", "email"],
    )

    codes_left = db.table("marketplace_codes").select("id").eq("listing_id", listing_id).eq("status", "available").execute()
    from flask import current_app
    if len(codes_left) <= current_app.config.get("LOW_CODE_INVENTORY_THRESHOLD", 5):
        _alert_admin_low_inventory(listing_id, listing["title"], len(codes_left))

    return jsonify({
        "purchase": purchase_row,
        "code": code_value,
        "hp_earned": 50,
    }), 201


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
    """
    db = get_db()
    data = request.get_json(force=True)
    required = ["vendor_name", "vendor_email", "service_title", "category", "description", "proposed_price"]
    for f in required:
        if not data.get(f):
            return jsonify({"error": f"'{f}' is required"}), 400
    data["status"] = "pending"
    result = db.table("marketplace_listing_requests").insert(data)
    return jsonify(result[0] if isinstance(result, list) else result), 201


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
        return jsonify({"error": "codes list is required"}), 400

    records = [{"listing_id": listing_id, "code": c, "status": "available", "uploaded_by": g.user_id} for c in codes]
    db.table("marketplace_codes").insert(records)

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
            title="Low Code Inventory",
            body=f"'{title}' has only {remaining} code(s) left.",
            reference_id=listing_id,
            reference_type="marketplace_listing",
            channels=["in_app"],
        )
