"""Menu routes — categories, items, add-ons, variation groups, daily limits, kitchen capacity."""

from flask import Blueprint, request, jsonify, g
from app.middleware.auth import require_role
from app.db import get_db
from datetime import datetime, timezone

menu_bp = Blueprint("menu", __name__)


# ─────────────────────────────────────────────────────────────────────────────
# Internal helpers
# ─────────────────────────────────────────────────────────────────────────────

def _today_start_iso():
    """UTC midnight today as ISO string — used to filter today's orders."""
    return datetime.now(timezone.utc).replace(
        hour=0, minute=0, second=0, microsecond=0
    ).isoformat()


def _kitchen_stats(db):
    """
    Return (capacity, orders_today_count, is_at_capacity).
    capacity is None when the kitchen has no daily cap configured.
    """
    row = (
        db.table("kitchen_settings")
        .select("value")
        .eq("key", "daily_order_capacity")
        .single()
        .execute()
    )
    raw = row.get("value") if row else ""
    capacity = int(raw) if raw and raw.isdigit() else None

    today_orders = (
        db.table("orders")
        .select("id")
        .gte("created_at", _today_start_iso())
        .execute()
    )
    count = len(today_orders) if isinstance(today_orders, list) else 0
    at_capacity = capacity is not None and count >= capacity
    return capacity, count, at_capacity


def _daily_item_counts(db):
    """
    Return {menu_item_id: total_qty_ordered_today} for all of today's orders.
    Aggregation done in Python since the mock client doesn't support GROUP BY.
    """
    today_orders = (
        db.table("orders")
        .select("id")
        .gte("created_at", _today_start_iso())
        .execute()
    ) or []
    order_ids = {o["id"] for o in today_orders}
    counts = {}
    if order_ids:
        rows = db.table("order_items").select("menu_item_id,quantity,order_id").execute() or []
        for row in rows:
            if row.get("order_id") in order_ids and row.get("menu_item_id"):
                mid = row["menu_item_id"]
                counts[mid] = counts.get(mid, 0) + int(row.get("quantity", 1))
    return counts


def _enrich_item(item, counts, at_capacity):
    """Attach is_sold_out and daily_remaining fields to an item dict (mutates)."""
    daily_limit = item.get("daily_limit")
    count = counts.get(item.get("id"), 0)
    if at_capacity:
        item["is_sold_out"] = True
        item["daily_remaining"] = 0
    elif daily_limit is not None:
        remaining = max(0, int(daily_limit) - count)
        item["daily_remaining"] = remaining
        item["is_sold_out"] = remaining == 0
    else:
        item["daily_remaining"] = None
        item["is_sold_out"] = False
    return item


# ─────────────────────────────────────────────────────────────────────────────
# Categories
# ─────────────────────────────────────────────────────────────────────────────

@menu_bp.route("/categories", methods=["GET"])
def list_categories():
    """
    List all active menu categories.
    ---
    tags: [Menu]
    security: []
    responses:
      200:
        description: List of categories
    """
    db = get_db()
    cats = (
        db.table("menu_categories")
        .select("*")
        .eq("is_active", "true")
        .order("sort_order")
        .execute()
    )
    return jsonify(cats), 200


# ─────────────────────────────────────────────────────────────────────────────
# Menu Items
# ─────────────────────────────────────────────────────────────────────────────

@menu_bp.route("/items", methods=["GET"])
def list_items():
    """
    List menu items with availability, daily stock, and kitchen capacity metadata.
    Each item includes is_sold_out and daily_remaining.
    ---
    tags: [Menu]
    security: []
    parameters:
      - in: query
        name: category
        type: string
        description: Filter by category slug
      - in: query
        name: q
        type: string
        description: Search by item name
      - in: query
        name: available_only
        type: boolean
        default: true
    responses:
      200:
        description: |
          { items: [...], kitchen: { daily_order_capacity, orders_today, is_at_capacity } }
    """
    db = get_db()
    q = db.table("menu_items").select("*,menu_categories(name,slug)").eq("is_archived", "false")

    category_slug = request.args.get("category")
    if category_slug:
        cat = (
            db.table("menu_categories")
            .select("id")
            .eq("slug", category_slug)
            .single()
            .execute()
        )
        if cat:
            q = q.eq("category_id", cat["id"])

    search = request.args.get("q")
    if search:
        q = q.ilike("name", f"%{search}%")

    available_only = request.args.get("available_only", "true").lower() != "false"
    if available_only:
        q = q.eq("is_available", "true")

    items = q.order("name").execute() or []

    capacity, orders_today, at_capacity = _kitchen_stats(db)
    counts = _daily_item_counts(db)
    enriched = [_enrich_item(item, counts, at_capacity) for item in items]

    return jsonify({
        "items": enriched,
        "kitchen": {
            "daily_order_capacity": capacity,
            "orders_today": orders_today,
            "is_at_capacity": at_capacity,
        },
    }), 200


@menu_bp.route("/items/<item_id>", methods=["GET"])
def get_item(item_id):
    """
    Get single menu item detail including variation groups, options, and daily stock.
    ---
    tags: [Menu]
    security: []
    parameters:
      - in: path
        name: item_id
        type: string
        required: true
    responses:
      200:
        description: Menu item with variation_groups and stock info
      404:
        description: Not found
    """
    db = get_db()
    item = (
        db.table("menu_items")
        .select("*,menu_categories(name,slug)")
        .eq("id", item_id)
        .eq("is_archived", "false")
        .single()
        .execute()
    )
    if not item:
        return jsonify({"error": "Menu item not found"}), 404

    groups = (
        db.table("menu_item_variation_groups")
        .select("*")
        .eq("menu_item_id", item_id)
        .order("sort_order")
        .execute()
    ) or []
    for group in groups:
        options = (
            db.table("menu_item_variation_options")
            .select("*")
            .eq("variation_group_id", group["id"])
            .order("sort_order")
            .execute()
        ) or []
        group["options"] = options
    item["variation_groups"] = groups

    capacity, _, at_capacity = _kitchen_stats(db)
    counts = _daily_item_counts(db)
    _enrich_item(item, counts, at_capacity)

    return jsonify(item), 200


@menu_bp.route("/items", methods=["POST"])
@require_role("admin")
def create_item():
    """
    Create a new menu item (admin only).
    ---
    tags: [Menu]
    parameters:
      - in: body
        name: body
        required: true
        schema:
          required: [name, category_id, price]
          properties:
            name: {type: string}
            category_id: {type: string}
            price: {type: number}
            hp_earn_value: {type: integer}
            description: {type: string}
            sku: {type: string}
            dietary_tags: {type: array, items: {type: string}}
            daily_limit: {type: integer, description: "Max servings per day (null = unlimited)"}
    responses:
      201:
        description: Item created
      400:
        description: Missing required field
    """
    db = get_db()
    data = request.get_json(force=True)
    for f in ["name", "category_id", "price"]:
        if data.get(f) is None:
            return jsonify({"error": f"'{f}' is required"}), 400

    data["is_available"] = data.get("is_available", True)
    data["is_archived"] = False
    data["last_edited_by"] = g.user_id
    result = db.table("menu_items").insert(data)
    return jsonify(result[0] if isinstance(result, list) else result), 201


@menu_bp.route("/items/<item_id>", methods=["PATCH"])
@require_role("admin")
def update_item(item_id):
    """
    Update a menu item (admin only). Supports setting or clearing daily_limit.
    ---
    tags: [Menu]
    parameters:
      - in: path
        name: item_id
        type: string
        required: true
      - in: body
        name: body
        schema:
          properties:
            name: {type: string}
            price: {type: number}
            hp_earn_value: {type: integer}
            is_available: {type: boolean}
            description: {type: string}
            daily_limit: {type: integer, description: "Set to null to remove daily limit"}
    responses:
      200:
        description: Item updated
    """
    db = get_db()
    data = request.get_json(force=True)
    data["last_edited_by"] = g.user_id
    data["updated_at"] = datetime.now(timezone.utc).isoformat()
    result = db.table("menu_items").eq("id", item_id).update(data)
    return jsonify(result[0] if isinstance(result, list) else result), 200


@menu_bp.route("/items/<item_id>/archive", methods=["POST"])
@require_role("admin")
def archive_item(item_id):
    """
    Soft-archive a menu item (admin only). Order history is preserved.
    ---
    tags: [Menu]
    parameters:
      - in: path
        name: item_id
        type: string
        required: true
    responses:
      200:
        description: Item archived
    """
    db = get_db()
    result = db.table("menu_items").eq("id", item_id).update({
        "is_archived": True,
        "is_available": False,
        "archived_at": datetime.now(timezone.utc).isoformat(),
        "archived_by": g.user_id,
    })
    return jsonify({"message": "Item archived", "item": result[0] if isinstance(result, list) else result}), 200


# ─────────────────────────────────────────────────────────────────────────────
# Variation Groups & Options  (combo side choices)
# ─────────────────────────────────────────────────────────────────────────────

@menu_bp.route("/items/<item_id>/variation-groups", methods=["POST"])
@require_role("admin")
def create_variation_group(item_id):
    """
    Create a variation group on a menu item (admin only).
    Use this when a combo lets customers pick which side accompanies their meal.
    ---
    tags: [Menu]
    parameters:
      - in: path
        name: item_id
        type: string
        required: true
      - in: body
        name: body
        required: true
        schema:
          required: [name]
          properties:
            name: {type: string, example: "Choose your side"}
            is_required: {type: boolean, default: false}
            min_selections: {type: integer, default: 0}
            max_selections: {type: integer, default: 1}
            sort_order: {type: integer, default: 0}
    responses:
      201:
        description: Variation group created
      400:
        description: Missing required field
    """
    db = get_db()
    data = request.get_json(force=True)
    if not data.get("name"):
        return jsonify({"error": "'name' is required"}), 400

    record = {
        "menu_item_id": item_id,
        "name": data["name"],
        "is_required": bool(data.get("is_required", False)),
        "min_selections": int(data.get("min_selections", 0)),
        "max_selections": int(data.get("max_selections", 1)),
        "sort_order": int(data.get("sort_order", 0)),
    }
    result = db.table("menu_item_variation_groups").insert(record)
    return jsonify(result[0] if isinstance(result, list) else result), 201


@menu_bp.route("/items/<item_id>/variation-groups/<group_id>", methods=["PATCH"])
@require_role("admin")
def update_variation_group(item_id, group_id):
    """
    Update a variation group (admin only).
    ---
    tags: [Menu]
    parameters:
      - in: path
        name: item_id
        type: string
        required: true
      - in: path
        name: group_id
        type: string
        required: true
    responses:
      200:
        description: Group updated
    """
    db = get_db()
    data = request.get_json(force=True)
    allowed = {"name", "is_required", "min_selections", "max_selections", "sort_order"}
    update = {k: v for k, v in data.items() if k in allowed}
    result = (
        db.table("menu_item_variation_groups")
        .eq("id", group_id)
        .eq("menu_item_id", item_id)
        .update(update)
    )
    return jsonify(result[0] if isinstance(result, list) else result), 200


@menu_bp.route("/items/<item_id>/variation-groups/<group_id>/options", methods=["POST"])
@require_role("admin")
def create_variation_option(item_id, group_id):
    """
    Add a choice option to a variation group (admin only).
    E.g. "Coleslaw" (free), "Plantain" (+₦200).
    ---
    tags: [Menu]
    parameters:
      - in: path
        name: item_id
        type: string
        required: true
      - in: path
        name: group_id
        type: string
        required: true
      - in: body
        name: body
        required: true
        schema:
          required: [name]
          properties:
            name: {type: string, example: "Coleslaw"}
            price_delta: {type: number, default: 0, description: "Extra charge for this choice"}
            is_available: {type: boolean, default: true}
            sort_order: {type: integer, default: 0}
    responses:
      201:
        description: Option created
      400:
        description: Missing required field
    """
    db = get_db()
    data = request.get_json(force=True)
    if not data.get("name"):
        return jsonify({"error": "'name' is required"}), 400

    record = {
        "variation_group_id": group_id,
        "name": data["name"],
        "price_delta": float(data.get("price_delta", 0)),
        "is_available": bool(data.get("is_available", True)),
        "sort_order": int(data.get("sort_order", 0)),
    }
    result = db.table("menu_item_variation_options").insert(record)
    return jsonify(result[0] if isinstance(result, list) else result), 201


@menu_bp.route("/items/<item_id>/variation-groups/<group_id>/options/<option_id>", methods=["PATCH"])
@require_role("admin")
def update_variation_option(item_id, group_id, option_id):
    """
    Update a variation option (admin only).
    ---
    tags: [Menu]
    responses:
      200:
        description: Option updated
    """
    db = get_db()
    data = request.get_json(force=True)
    allowed = {"name", "price_delta", "is_available", "sort_order"}
    update = {k: v for k, v in data.items() if k in allowed}
    result = (
        db.table("menu_item_variation_options")
        .eq("id", option_id)
        .eq("variation_group_id", group_id)
        .update(update)
    )
    return jsonify(result[0] if isinstance(result, list) else result), 200


# ─────────────────────────────────────────────────────────────────────────────
# Add-Ons  (optional extras for any order)
# ─────────────────────────────────────────────────────────────────────────────

@menu_bp.route("/addons", methods=["GET"])
def list_addons():
    """
    List available add-on items — optional extras customers can append to any order
    (not tied to a specific combo or main item).
    ---
    tags: [Menu]
    security: []
    responses:
      200:
        description: List of add-ons
    """
    db = get_db()
    addons = (
        db.table("menu_addons")
        .select("*")
        .eq("is_archived", "false")
        .eq("is_available", "true")
        .order("sort_order")
        .execute()
    )
    return jsonify(addons or []), 200


@menu_bp.route("/addons", methods=["POST"])
@require_role("admin")
def create_addon():
    """
    Create an add-on item (admin only).
    ---
    tags: [Menu]
    parameters:
      - in: body
        name: body
        required: true
        schema:
          required: [name, price]
          properties:
            name: {type: string, example: "Extra Sauce"}
            description: {type: string}
            price: {type: number}
            is_available: {type: boolean, default: true}
            sort_order: {type: integer, default: 0}
    responses:
      201:
        description: Add-on created
      400:
        description: Missing required field
    """
    db = get_db()
    data = request.get_json(force=True)
    for f in ["name", "price"]:
        if data.get(f) is None:
            return jsonify({"error": f"'{f}' is required"}), 400

    record = {
        "name": data["name"],
        "description": data.get("description", ""),
        "price": float(data["price"]),
        "is_available": bool(data.get("is_available", True)),
        "is_archived": False,
        "sort_order": int(data.get("sort_order", 0)),
    }
    result = db.table("menu_addons").insert(record)
    return jsonify(result[0] if isinstance(result, list) else result), 201


@menu_bp.route("/addons/<addon_id>", methods=["PATCH"])
@require_role("admin")
def update_addon(addon_id):
    """
    Update an add-on item (admin only).
    ---
    tags: [Menu]
    parameters:
      - in: path
        name: addon_id
        type: string
        required: true
    responses:
      200:
        description: Add-on updated
    """
    db = get_db()
    data = request.get_json(force=True)
    allowed = {"name", "description", "price", "is_available", "sort_order"}
    update = {k: v for k, v in data.items() if k in allowed}
    update["updated_at"] = datetime.now(timezone.utc).isoformat()
    result = db.table("menu_addons").eq("id", addon_id).update(update)
    return jsonify(result[0] if isinstance(result, list) else result), 200


@menu_bp.route("/addons/<addon_id>/archive", methods=["POST"])
@require_role("admin")
def archive_addon(addon_id):
    """
    Archive an add-on item (admin only).
    ---
    tags: [Menu]
    responses:
      200:
        description: Add-on archived
    """
    db = get_db()
    result = db.table("menu_addons").eq("id", addon_id).update({
        "is_archived": True,
        "is_available": False,
        "updated_at": datetime.now(timezone.utc).isoformat(),
    })
    return jsonify({"message": "Add-on archived", "addon": result[0] if isinstance(result, list) else result}), 200


# ─────────────────────────────────────────────────────────────────────────────
# Kitchen Capacity  (daily order cap)
# ─────────────────────────────────────────────────────────────────────────────

@menu_bp.route("/kitchen-capacity", methods=["GET"])
def get_kitchen_capacity():
    """
    Get the kitchen's current daily order capacity and today's order count.
    ---
    tags: [Menu]
    security: []
    responses:
      200:
        description: Kitchen capacity info
    """
    db = get_db()
    capacity, orders_today, at_capacity = _kitchen_stats(db)
    return jsonify({
        "daily_order_capacity": capacity,
        "orders_today": orders_today,
        "is_at_capacity": at_capacity,
    }), 200


@menu_bp.route("/kitchen-capacity", methods=["PATCH"])
@require_role("admin")
def set_kitchen_capacity():
    """
    Set the kitchen's daily order capacity (admin only).
    Pass null to remove the limit entirely.
    ---
    tags: [Menu]
    parameters:
      - in: body
        name: body
        required: true
        schema:
          properties:
            daily_order_capacity:
              type: integer
              description: "Max orders the kitchen will accept today. null = no cap."
    responses:
      200:
        description: Capacity updated
      400:
        description: Invalid value
    """
    db = get_db()
    data = request.get_json(force=True)
    cap = data.get("daily_order_capacity")

    if cap is None:
        db.table("kitchen_settings").eq("key", "daily_order_capacity").update({
            "value": "",
            "updated_at": datetime.now(timezone.utc).isoformat(),
            "updated_by": g.user_id,
        })
        return jsonify({"daily_order_capacity": None, "message": "Daily capacity limit removed"}), 200

    if not isinstance(cap, int) or cap < 1:
        return jsonify({"error": "daily_order_capacity must be a positive integer"}), 400

    db.table("kitchen_settings").eq("key", "daily_order_capacity").update({
        "value": str(cap),
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "updated_by": g.user_id,
    })
    _, orders_today, at_capacity = _kitchen_stats(db)
    return jsonify({
        "daily_order_capacity": cap,
        "orders_today": orders_today,
        "is_at_capacity": at_capacity,
    }), 200
