"""Cart routes — persistent per-user cart management."""

from flask import Blueprint, request, jsonify, g
from app.middleware.auth import require_auth
from app.db import get_db
from app.messages import MSG
from datetime import datetime, timezone

cart_bp = Blueprint("cart", __name__)


@cart_bp.route("", methods=["GET"])
@require_auth
def get_cart():
    """
    Get the authenticated user's cart with current item prices.
    ---
    tags: [Cart]
    responses:
      200:
        description: Cart contents and subtotal
        schema:
          properties:
            items: {type: array}
            subtotal: {type: number}
            item_count: {type: integer}
    """
    db = get_db()
    items = (
        db.table("cart_items")
        .select("*,menu_items(id,name,price,image_url,is_available,hp_earn_value,hp_earn)")
        .eq("user_id", g.user_id)
        .order("created_at")
        .execute()
    ) or []

    subtotal = 0.0
    hp_earn_preview = 0
    has_unavailable = False
    for item in items:
        menu = item.get("menu_items") or {}
        qty = float(item.get("quantity", 1))
        subtotal += qty * float(menu.get("price", 0))
        hp_earn_preview += int(qty) * int(menu.get("hp_earn_value") or menu.get("hp_earn") or 0)
        # Surface unavailability flag on each item
        item["is_unavailable"] = not bool(menu.get("is_available", True))
        if item["is_unavailable"]:
            has_unavailable = True

    return jsonify({
        "items": items,
        "subtotal": round(subtotal, 2),
        "item_count": len(items),
        "hp_earn_preview": hp_earn_preview,
        "has_unavailable_items": has_unavailable,
    }), 200


@cart_bp.route("", methods=["POST"])
@require_auth
def add_to_cart():
    """
    Add an item to the cart. If the item already exists, quantity is incremented.
    ---
    tags: [Cart]
    parameters:
      - in: body
        name: body
        required: true
        schema:
          required: [menu_item_id]
          properties:
            menu_item_id: {type: string}
            quantity: {type: integer, default: 1}
            notes: {type: string, description: "Special preparation notes"}
    responses:
      201:
        description: Item added
      200:
        description: Item already in cart — quantity updated
      404:
        description: Menu item not found
    """
    db = get_db()
    data = request.get_json(force=True) or {}
    menu_item_id = (data.get("menu_item_id") or "").strip()
    if not menu_item_id:
        return jsonify({"error": MSG.CART_MENU_ITEM_REQUIRED}), 400

    quantity = max(1, int(data.get("quantity", 1)))
    # Notes are stored inside the `options` jsonb column (cart_items has no `notes` column)
    notes = data.get("notes", "")

    menu_item = (
        db.table("menu_items")
        .select("id,name,price,is_available")
        .eq("id", menu_item_id)
        .is_("deleted_at", "null")
        .single()
        .execute()
    )
    if not menu_item:
        return jsonify({"error": MSG.MENU_ITEM_NOT_FOUND}), 404

    now = datetime.now(timezone.utc).isoformat()

    existing = (
        db.table("cart_items")
        .select("id,quantity,options")
        .eq("user_id", g.user_id)
        .eq("menu_item_id", menu_item_id)
        .single()
        .execute()
    )
    if existing:
        new_qty = existing["quantity"] + quantity
        existing_opts = existing.get("options") or {}
        if isinstance(existing_opts, str):
            import json as _json
            try:
                existing_opts = _json.loads(existing_opts)
            except Exception:
                existing_opts = {}
        update_payload = {"quantity": new_qty, "updated_at": now}
        if notes:
            existing_opts["notes"] = notes
            update_payload["options"] = existing_opts
        db.table("cart_items").eq("id", existing["id"]).update(update_payload)
        return jsonify({"message": MSG.CART_ITEM_UPDATED, "quantity": new_qty}), 200

    options_payload = {}
    if notes:
        options_payload["notes"] = notes

    insert_payload = {
        "user_id": g.user_id,
        "menu_item_id": menu_item_id,
        "quantity": quantity,
        "options": options_payload,
        "added_at": now,
        "created_at": now,
        "updated_at": now,
    }
    result = db.table("cart_items").insert(insert_payload)
    return jsonify({
        "message": MSG.CART_ITEM_ADDED,
        "item": result[0] if isinstance(result, list) else result,
    }), 201


@cart_bp.route("/<item_id>", methods=["PATCH"])
@require_auth
def update_cart_item(item_id):
    """
    Update quantity or notes for a cart item. Setting quantity to 0 removes it.
    ---
    tags: [Cart]
    parameters:
      - in: path
        name: item_id
        type: string
        required: true
      - in: body
        name: body
        schema:
          properties:
            quantity: {type: integer}
            notes: {type: string}
    responses:
      200:
        description: Cart item updated or removed
      404:
        description: Cart item not found
    """
    db = get_db()
    existing = (
        db.table("cart_items")
        .select("id,quantity,options")
        .eq("id", item_id)
        .eq("user_id", g.user_id)
        .single()
        .execute()
    )
    if not existing:
        return jsonify({"error": MSG.CART_ITEM_NOT_FOUND}), 404

    data = request.get_json(force=True) or {}
    if "quantity" in data:
        qty = int(data["quantity"])
        if qty <= 0:
            db.table("cart_items").eq("id", item_id).delete()
            return jsonify({"message": MSG.CART_ITEM_REMOVED}), 200

    update = {}
    if "quantity" in data:
        update["quantity"] = int(data["quantity"])
    # Notes are stored inside options jsonb (no `notes` column on cart_items)
    if "notes" in data:
        current = existing.get("options") or {}
        if isinstance(current, str):
            import json as _json
            try:
                current = _json.loads(current)
            except Exception:
                current = {}
        current["notes"] = data["notes"]
        update["options"] = current
    update["updated_at"] = datetime.now(timezone.utc).isoformat()

    result = db.table("cart_items").eq("id", item_id).update(update)
    return jsonify({
        "message": MSG.CART_ITEM_UPDATED,
        "item": result[0] if isinstance(result, list) else result,
    }), 200


@cart_bp.route("/<item_id>", methods=["DELETE"])
@require_auth
def remove_cart_item(item_id):
    """
    Remove a single item from the cart.
    ---
    tags: [Cart]
    parameters:
      - in: path
        name: item_id
        type: string
        required: true
    responses:
      200:
        description: Item removed
      404:
        description: Cart item not found
    """
    db = get_db()
    existing = (
        db.table("cart_items")
        .select("id")
        .eq("id", item_id)
        .eq("user_id", g.user_id)
        .single()
        .execute()
    )
    if not existing:
        return jsonify({"error": MSG.CART_ITEM_NOT_FOUND}), 404

    db.table("cart_items").eq("id", item_id).delete()
    return jsonify({"message": MSG.CART_ITEM_REMOVED}), 200


@cart_bp.route("", methods=["DELETE"])
@require_auth
def clear_cart():
    """
    Remove all items from the authenticated user's cart.
    ---
    tags: [Cart]
    responses:
      200:
        description: Cart cleared
    """
    db = get_db()
    db.table("cart_items").eq("user_id", g.user_id).delete()
    return jsonify({"message": MSG.CART_CLEARED}), 200
