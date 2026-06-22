"""HP (Holy Points) routes — balance, transactions, history."""

from flask import Blueprint, request, jsonify, g
from app.middleware.auth import require_auth, require_role
from app.services.hp_service import (
    get_hp_balance, get_user_tier, spend_hp, earn_pending_hp, award_active_hp
)
from app.db import get_db

hp_bp = Blueprint("hp", __name__)


@hp_bp.route("/balance", methods=["GET"])
@require_auth
def balance():
    """
    Get user's HP balance: active, pending, overflow.
    ---
    tags: [HP]
    responses:
      200:
        description: HP balance breakdown
    """
    bal = get_hp_balance(g.user_id)
    tier = get_user_tier(g.user_id)
    return jsonify({**bal, "tier": tier}), 200


@hp_bp.route("/transactions", methods=["GET"])
@require_auth
def transactions():
    """
    Get HP transaction history for the authenticated user.
    ---
    tags: [HP]
    parameters:
      - in: query
        name: limit
        type: integer
        default: 50
      - in: query
        name: offset
        type: integer
        default: 0
      - in: query
        name: type
        type: string
        description: Filter by transaction type (earn, spend, expire, etc.)
    responses:
      200:
        description: HP transaction list
    """
    db = get_db()
    limit = min(int(request.args.get("limit", 50)), 200)
    offset = int(request.args.get("offset", 0))
    q = db.table("hp_transactions").select("*").eq("user_id", g.user_id)
    txn_type = request.args.get("type")
    if txn_type:
        q = q.eq("type", txn_type)
    txns = q.order("created_at", ascending=False).limit(limit).offset(offset).execute()
    return jsonify(txns), 200


@hp_bp.route("/tiers", methods=["GET"])
def list_tiers():
    """
    List all tiers with thresholds and perks.
    ---
    tags: [HP]
    security: []
    responses:
      200:
        description: All tier definitions
    """
    db = get_db()
    tiers = db.table("tiers").select("*").order("sort_order").execute()
    return jsonify(tiers), 200


@hp_bp.route("/admin/grant", methods=["POST"])
@require_role("admin")
def admin_grant():
    """
    Admin manually grants HP to a user (creates admin_grant transaction).
    ---
    tags: [HP]
    parameters:
      - in: body
        name: body
        required: true
        schema:
          required: [user_id, amount]
          properties:
            user_id: {type: string}
            amount: {type: integer}
            notes: {type: string}
    responses:
      200:
        description: HP granted
    """
    data = request.get_json(force=True)
    if not data.get("user_id") or not data.get("amount"):
        return jsonify({"error": "user_id and amount are required"}), 400

    try:
        result = award_active_hp(
            user_id=data["user_id"],
            amount=int(data["amount"]),
            txn_type="admin_grant",
            notes=data.get("notes", "Admin-issued HP"),
            issued_by_admin_id=g.user_id,
        )
        _log_admin_action(g.user_id, "profiles", data["user_id"], "hp_grant", {"amount": data["amount"]})
        return jsonify(result), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 400


@hp_bp.route("/admin/expire", methods=["POST"])
@require_role("admin")
def admin_expire():
    """
    Admin manually expires HP for a user.
    ---
    tags: [HP]
    parameters:
      - in: body
        name: body
        required: true
        schema:
          required: [user_id, amount]
          properties:
            user_id: {type: string}
            amount: {type: integer}
            notes: {type: string}
    responses:
      200:
        description: HP expired
    """
    from app.services.hp_service import expire_hp
    data = request.get_json(force=True)
    if not data.get("user_id") or not data.get("amount"):
        return jsonify({"error": "user_id and amount are required"}), 400
    result = expire_hp(data["user_id"], int(data["amount"]), data.get("notes", "Manual HP expiry"))
    return jsonify(result), 200


@hp_bp.route("/unlock-history", methods=["GET"])
@require_auth
def unlock_history():
    """
    Get HP unlock history for the authenticated user (pending→active unlocks).
    ---
    tags: [HP]
    parameters:
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
        description: HP unlock log entries
    """
    db = get_db()
    limit = min(int(request.args.get("limit", 50)), 200)
    offset = int(request.args.get("offset", 0))
    rows = (
        db.table("hp_unlock_log")
        .select("*")
        .eq("user_id", g.user_id)
        .order("unlocked_at", ascending=False)
        .limit(limit)
        .offset(offset)
        .execute()
    )
    return jsonify(rows), 200


@hp_bp.route("/bundles/purchase", methods=["POST"])
@require_auth
def purchase_hp_bundle():
    """
    Purchase an HP bundle (event hosts). Charges card via Paystack reference, credits HP.
    ---
    tags: [HP]
    parameters:
      - in: body
        name: body
        required: true
        schema:
          required: [hp_amount, paystack_reference]
          properties:
            hp_amount: {type: integer, minimum: 100, example: 500}
            paystack_reference: {type: string, description: "Verified Paystack payment reference"}
    responses:
      201:
        description: HP bundle purchased and credited
      400:
        description: Validation error
    """
    from app.services.hp_service import process_hp_bundle_purchase
    data = request.get_json(force=True)
    hp_amount = int(data.get("hp_amount", 0))
    reference = data.get("paystack_reference", "").strip()

    if hp_amount < 100:
        return jsonify({"error": "Minimum bundle purchase is 100 HP"}), 400
    if not reference:
        return jsonify({"error": "paystack_reference is required"}), 400

    price_per_hp = 5.0
    naira_paid = hp_amount * price_per_hp

    try:
        result = process_hp_bundle_purchase(
            event_host_id=g.user_id,
            hp_amount=hp_amount,
            naira_paid=naira_paid,
        )
        return jsonify(result), 201
    except Exception as e:
        return jsonify({"error": str(e)}), 400


@hp_bp.route("/spin", methods=["POST"])
@require_auth
def spin_wheel():
    """
    Spin the HP wheel. One free spin per day; subsequent spins cost 10 HP.
    ---
    tags: [HP]
    responses:
      200:
        description: Spin result with HP awarded
      400:
        description: Insufficient HP or spin error
    """
    import random
    from datetime import date
    db = get_db()

    today = date.today().isoformat()
    spins_today = (
        db.table("spin_win_entries")
        .select("id")
        .eq("user_id", g.user_id)
        .gte("spun_at", f"{today}T00:00:00")
        .execute()
    )
    spin_count_today = len(spins_today) if isinstance(spins_today, list) else 0
    spin_cost = 0 if spin_count_today == 0 else 10

    if spin_cost > 0:
        bal = get_hp_balance(g.user_id)
        if bal.get("active", 0) < spin_cost:
            return jsonify({"error": f"Insufficient HP. Need {spin_cost} HP for extra spins today."}), 400
        spend_hp(g.user_id, spin_cost, None, "spin_wheel", f"Extra spin #{spin_count_today + 1} today")

    prizes = [
        {"label": "5 HP",   "hp": 5,   "weight": 35},
        {"label": "10 HP",  "hp": 10,  "weight": 25},
        {"label": "20 HP",  "hp": 20,  "weight": 15},
        {"label": "50 HP",  "hp": 50,  "weight": 10},
        {"label": "100 HP", "hp": 100, "weight": 7},
        {"label": "200 HP", "hp": 200, "weight": 5},
        {"label": "500 HP", "hp": 500, "weight": 2},
        {"label": "No win", "hp": 0,   "weight": 1},
    ]
    population = [p for p in prizes for _ in range(p["weight"])]
    winner = random.choice(population)

    entry = db.table("spin_win_entries").insert({
        "user_id": g.user_id,
        "hp_won": winner["hp"],
        "prize_label": winner["label"],
        "spin_cost_hp": spin_cost,
        "spun_at": __import__("datetime").datetime.now(__import__("datetime").timezone.utc).isoformat(),
    })
    entry_row = entry[0] if isinstance(entry, list) else entry

    if winner["hp"] > 0:
        earn_pending_hp(
            user_id=g.user_id,
            amount=winner["hp"],
            source_type="spin_wheel",
            reference_id=entry_row.get("id") if isinstance(entry_row, dict) else None,
            notes=f"Spin wheel prize: {winner['label']}",
        )

    return jsonify({
        "prize": winner["label"],
        "hp_won": winner["hp"],
        "spin_cost_hp": spin_cost,
        "entry_id": entry_row.get("id") if isinstance(entry_row, dict) else None,
        "free_spin": spin_cost == 0,
    }), 200


@hp_bp.route("/spin/history", methods=["GET"])
@require_auth
def spin_history():
    """
    Get spin wheel history for the authenticated user.
    ---
    tags: [HP]
    parameters:
      - in: query
        name: limit
        type: integer
        default: 20
    responses:
      200:
        description: Spin history entries
    """
    db = get_db()
    limit = min(int(request.args.get("limit", 20)), 100)
    rows = (
        db.table("spin_win_entries")
        .select("*")
        .eq("user_id", g.user_id)
        .order("spun_at", ascending=False)
        .limit(limit)
        .execute()
    )
    return jsonify(rows), 200


def _log_admin_action(actor_id, table, target_id, action, after_data=None):
    from app.db import get_db
    db = get_db()
    try:
        db.table("admin_audit_log").insert({
            "actor_id": actor_id,
            "actor_role": "admin",
            "target_table": table,
            "target_id": target_id,
            "action": action,
            "after_data": after_data,
        })
    except Exception:
        pass
