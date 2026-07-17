"""
Saved For Later routes — per-user wishlist separate from the active cart.

Users can:
  GET    /saved            — list all saved items
  POST   /saved            — save an item (from menu or move from cart)
  DELETE /saved/<id>       — remove a saved item
  POST   /saved/<id>/move-to-cart   — move a saved item into the cart
  POST   /cart/<cart_id>/save-for-later — move a cart item to saved-for-later

Saved items sync across devices because they live in the DB against the user_id.
"""

from flask import Blueprint, request, jsonify, g
from app.middleware.auth import require_auth
from app.db import get_db
from app.messages import MSG
from datetime import datetime, timezone

saved_bp = Blueprint("saved", __name__)


@saved_bp.route("", methods=["GET"])
@require_auth
def list_saved():
    """
    Get all items the authenticated user has saved for later.
    ---
    tags: [Saved For Later]
    responses:
      200:
        description: List of saved items with current menu details
        schema:
          properties:
            items: {type: array}
            count: {type: integer}
    """
    db = get_db()
    items = (
        db.table("saved_for_later")
        .select("*,menu_items(id,name,price,image_url,is_available,description)")
        .eq("user_id", g.user_id)
        .order("created_at", ascending=False)
        .execute()
    ) or []
    return jsonify({"items": items, "count": len(items)}), 200


@saved_bp.route("", methods=["POST"])
@require_auth
def save_item():
    """
    Save a menu item for later. If already saved, updates quantity.
    ---
    tags: [Saved For Later]
    parameters:
      - in: body
        name: body
        required: true
        schema:
          required: [menu_item_id]
          properties:
            menu_item_id: {type: string}
            quantity: {type: integer, default: 1}
            notes: {type: string}
    responses:
      201:
        description: Item saved for later
      200:
        description: Item already saved — quantity updated
      404:
        description: Menu item not found
    """
    db = get_db()
    data = request.get_json(force=True) or {}
    menu_item_id = (data.get("menu_item_id") or "").strip()
    if not menu_item_id:
        return jsonify({"error": MSG.CART_MENU_ITEM_REQUIRED}), 400

    quantity = max(1, int(data.get("quantity", 1)))
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
        db.table("saved_for_later")
        .select("id,quantity")
        .eq("user_id", g.user_id)
        .eq("menu_item_id", menu_item_id)
        .single()
        .execute()
    )

    if existing:
        update_payload = {"quantity": existing["quantity"] + quantity, "updated_at": now}
        if notes:
            update_payload["notes"] = notes
        db.table("saved_for_later").eq("id", existing["id"]).update(update_payload)
        return jsonify({"message": MSG.SAVED_ITEM_UPDATED, "quantity": update_payload["quantity"]}), 200

    insert_payload = {
        "user_id": g.user_id,
        "menu_item_id": menu_item_id,
        "quantity": quantity,
        "created_at": now,
        "updated_at": now,
    }
    if notes:
        insert_payload["notes"] = notes

    result = db.table("saved_for_later").insert(insert_payload)
    return jsonify({
        "message": MSG.SAVED_ITEM_ADDED,
        "item": result[0] if isinstance(result, list) else result,
    }), 201


@saved_bp.route("/<item_id>", methods=["PATCH"])
@require_auth
def update_saved_item(item_id):
    """
    Update quantity or notes on a saved-for-later item.
    ---
    tags: [Saved For Later]
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
        description: Item updated
      404:
        description: Saved item not found
    """
    db = get_db()
    data = request.get_json(force=True) or {}
    existing = (
        db.table("saved_for_later")
        .select("id,quantity")
        .eq("id", item_id)
        .eq("user_id", g.user_id)
        .single()
        .execute()
    )
    if not existing:
        return jsonify({"error": MSG.SAVED_ITEM_NOT_FOUND}), 404

    patch = {"updated_at": datetime.now(timezone.utc).isoformat()}
    if "quantity" in data:
        patch["quantity"] = max(1, int(data["quantity"]))
    if "notes" in data:
        patch["notes"] = data["notes"]

    db.table("saved_for_later").eq("id", item_id).update(patch)
    return jsonify({"message": MSG.SAVED_ITEM_UPDATED, **patch}), 200


@saved_bp.route("/<item_id>", methods=["DELETE"])
@require_auth
def remove_saved_item(item_id):
    """
    Remove a saved-for-later item.
    ---
    tags: [Saved For Later]
    parameters:
      - in: path
        name: item_id
        type: string
        required: true
    responses:
      200:
        description: Item removed from saved list
      404:
        description: Saved item not found
    """
    db = get_db()
    existing = (
        db.table("saved_for_later")
        .select("id")
        .eq("id", item_id)
        .eq("user_id", g.user_id)
        .single()
        .execute()
    )
    if not existing:
        return jsonify({"error": MSG.SAVED_ITEM_NOT_FOUND}), 404

    db.table("saved_for_later").eq("id", item_id).delete()
    return jsonify({"message": MSG.SAVED_ITEM_REMOVED}), 200


@saved_bp.route("/<item_id>/move-to-cart", methods=["POST"])
@require_auth
def move_saved_to_cart(item_id):
    """
    Move a saved-for-later item into the active cart.
    The saved-for-later entry is removed and a cart_items row is created.
    ---
    tags: [Saved For Later]
    parameters:
      - in: path
        name: item_id
        type: string
        required: true
    responses:
      200:
        description: Item moved to cart
      404:
        description: Saved item not found
    """
    db = get_db()
    saved = (
        db.table("saved_for_later")
        .select("id,menu_item_id,quantity,notes")
        .eq("id", item_id)
        .eq("user_id", g.user_id)
        .single()
        .execute()
    )
    if not saved:
        return jsonify({"error": MSG.SAVED_ITEM_NOT_FOUND}), 404

    now = datetime.now(timezone.utc).isoformat()
    menu_item_id = saved["menu_item_id"]

    existing_cart = (
        db.table("cart_items")
        .select("id,quantity")
        .eq("user_id", g.user_id)
        .eq("menu_item_id", menu_item_id)
        .single()
        .execute()
    )

    if existing_cart:
        new_qty = existing_cart["quantity"] + saved.get("quantity", 1)
        db.table("cart_items").eq("id", existing_cart["id"]).update({
            "quantity": new_qty, "updated_at": now
        })
    else:
        cart_payload = {
            "user_id": g.user_id,
            "menu_item_id": menu_item_id,
            "quantity": saved.get("quantity", 1),
            "added_at": now,
            "created_at": now,
            "updated_at": now,
        }
        # cart_items has no notes column — store in options jsonb
        if saved.get("notes"):
            cart_payload["options"] = {"notes": saved["notes"]}
        db.table("cart_items").insert(cart_payload)

    db.table("saved_for_later").eq("id", item_id).delete()
    return jsonify({"message": MSG.SAVED_MOVED_TO_CART}), 200


@saved_bp.route("/from-cart/<cart_item_id>", methods=["POST"])
@require_auth
def move_cart_to_saved(cart_item_id):
    """
    Move an active cart item to the saved-for-later list.
    The cart_items row is removed and a saved_for_later row is created.
    ---
    tags: [Saved For Later]
    parameters:
      - in: path
        name: cart_item_id
        type: string
        required: true
    responses:
      200:
        description: Item moved to saved-for-later
      404:
        description: Cart item not found
    """
    db = get_db()
    cart_item = (
        db.table("cart_items")
        .select("id,menu_item_id,quantity")
        .eq("id", cart_item_id)
        .eq("user_id", g.user_id)
        .single()
        .execute()
    )
    if not cart_item:
        return jsonify({"error": MSG.CART_ITEM_NOT_FOUND}), 404

    now = datetime.now(timezone.utc).isoformat()
    menu_item_id = cart_item["menu_item_id"]

    existing_saved = (
        db.table("saved_for_later")
        .select("id,quantity")
        .eq("user_id", g.user_id)
        .eq("menu_item_id", menu_item_id)
        .single()
        .execute()
    )

    if existing_saved:
        new_qty = existing_saved["quantity"] + cart_item.get("quantity", 1)
        db.table("saved_for_later").eq("id", existing_saved["id"]).update({
            "quantity": new_qty, "updated_at": now
        })
    else:
        save_payload = {
            "user_id": g.user_id,
            "menu_item_id": menu_item_id,
            "quantity": cart_item.get("quantity", 1),
            "created_at": now,
            "updated_at": now,
        }
        db.table("saved_for_later").insert(save_payload)

    db.table("cart_items").eq("id", cart_item_id).delete()
    return jsonify({"message": MSG.CART_MOVED_TO_SAVED}), 200
