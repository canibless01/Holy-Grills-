"""Rewards store routes — list, redeem, flash sales."""

import math
from decimal import Decimal, ROUND_FLOOR
from flask import Blueprint, request, jsonify, g
from app.middleware.auth import require_auth, require_role, resolve_scoped_campus_id, optional_auth
from app.services.hp_service import get_hp_balance
from app.services.notification_service import send_notification
from app.db import get_db, get_user_client
from app.messages import MSG, resolve_msg
from app.utils.logger import get_logger
from datetime import datetime, timezone

logger = get_logger(__name__)

rewards_bp = Blueprint("rewards", __name__)

# Mirrors the DB CHECK rewards_fulfillment_type_check. Keep in sync.
_FULFILLMENT_TYPES = ("simple", "menu_item")
# hp_transactions.reference_type written by hg_redeem_flash_reward_atomic for every flash redemption.
_FLASH_REDEMPTION_REF = "flash_reward_redemption"


def _flash_redeemed_count(db, reward_id: str, window_starts_at: str) -> int:
    """
    Flash redemptions of this reward since the window opened. This is the same count
    hg_redeem_flash_reward_atomic uses to enforce quantity_limit (a redemption counts as a
    flash redemption when its HP transaction has reference_type 'flash_reward_redemption'),
    so the "is it still on?" flag here can never disagree with what the RPC will accept.
    Call with the service-role client: users can only read their own redemptions.
    """
    txns = (
        db.table("hp_transactions")
        .select("reference_id")
        .eq("reference_type", _FLASH_REDEMPTION_REF)
        .gte("created_at", window_starts_at)
        .execute()
    ) or []
    ids = [t["reference_id"] for t in txns if t.get("reference_id")]
    if not ids:
        return 0
    rows = (
        db.table("reward_redemptions")
        .select("id")
        .eq("reward_id", reward_id)
        .gte("created_at", window_starts_at)
        .in_("id", ids)
        .execute()
    ) or []
    return len(rows)


def _active_flash_windows(db, reward_ids: list) -> dict:
    """{reward_id: flash_redemptions row} for sales whose window is open right now."""
    if not reward_ids:
        return {}
    now = datetime.now(timezone.utc).isoformat()
    rows = (
        db.table("flash_redemptions")
        .select("*")
        .eq("is_active", "true")
        .lte("window_starts_at", now)
        .gte("window_ends_at", now)
        .in_("reward_id", reward_ids)
        .execute()
    ) or []
    windows = {}
    for row in rows:
        windows.setdefault(row["reward_id"], row)
    return windows


def _flash_if_available(db, reward_id: str, flash: dict):
    """(True, flash + slots_remaining) if the open window still has slots, else (False, None)."""
    limit = int(flash.get("quantity_limit") or 0)
    redeemed = _flash_redeemed_count(db, reward_id, flash["window_starts_at"])
    if redeemed >= limit:
        return False, None
    return True, {**flash, "slots_remaining": limit - redeemed}


def _is_flash_active(db, reward_id: str) -> tuple:
    """
    (is_active, flash_row_or_None). Flash sales live in the flash_redemptions table, which is what
    hg_redeem_flash_reward_atomic actually enforces; the rewards.flash_* columns are not connected to it.
    """
    flash = _active_flash_windows(db, [reward_id]).get(reward_id)
    if not flash:
        return False, None
    return _flash_if_available(db, reward_id, flash)


def _with_flash_status(reward: dict, flash: dict = None) -> dict:
    """
    Add is_flash_active. When a sale is live, also fill the flash_* fields the front end already reads from
    the flash_redemptions row, so the response shape is unchanged. The discounted cost uses the RPC's own
    formula: floor(hp_cost * (1 - discount_pct)).
    """
    result = dict(reward)
    result["is_flash_active"] = flash is not None
    if flash is not None:
        hp_cost = Decimal(str(result.get("hp_cost") or 0))
        discount = Decimal(str(flash.get("discount_pct") or 0))
        result["flash_hp_cost"] = int((hp_cost * (1 - discount)).to_integral_value(rounding=ROUND_FLOOR))
        result["flash_starts_at"] = flash.get("window_starts_at")
        result["flash_ends_at"] = flash.get("window_ends_at")
        result["flash_max_qty"] = flash.get("quantity_limit")
        result["flash_slots_remaining"] = flash.get("slots_remaining")
    return result


def _flash_for_rewards(rewards: list) -> dict:
    """{reward_id: available flash row} for a list of rewards, in one windows query. Never raises."""
    try:
        db = get_db()
        windows = _active_flash_windows(db, [r["id"] for r in rewards if r.get("id")])
        available = {}
        for reward_id, flash in windows.items():
            ok, info = _flash_if_available(db, reward_id, flash)
            if ok:
                available[reward_id] = info
        return available
    except Exception:
        logger.warning("flash status lookup failed; listing rewards without it", exc_info=True)
        return {}


@rewards_bp.route("", methods=["GET"])
@optional_auth
def list_rewards():
    """
    List active rewards for the current campus (guest or authenticated). Optionally filter by category.
    ---
    tags: [Rewards]
    security: []
    parameters:
      - in: query
        name: category
        type: string
      - in: query
        name: available_only
        type: boolean
        default: true
    responses:
      200:
        description: List of rewards
    """
    from app.routes.events import _get_campus_id

    db = get_user_client()
    now = datetime.now(timezone.utc).isoformat()
    q = db.table("rewards").select("*,hp_tiers(name,slug)").eq("is_active", "true")
    # Guests never had g.campus_id set at all (no auth ran), so this always fell through to
    # unscoped — every campus's rewards, mixed together, on the guest-facing list. Match the
    # same guest-campus-selection pattern already used by menu.py / events.py / storefront.py:
    # resolve from ?campus_id= / X-Campus-ID: / the logged-in session, then show that campus's
    # rewards plus any global (campus_id IS NULL) ones — never every campus at once.
    campus_id = _get_campus_id()
    if campus_id:
        q = q.or_(f"campus_id.eq.{campus_id},campus_id.is.null")

    reward_type = request.args.get("category") or request.args.get("reward_type")
    if reward_type:
        q = q.eq("reward_type", reward_type)

    q = q.order("hp_cost")
    rewards = q.execute()
    result = []
    for r in rewards:
        stock = r.get("stock_quantity")
        expires_at = r.get("expires_at")
        if stock is not None and stock <= 0:
            continue
        if expires_at and expires_at < now:
            continue
        result.append(r)
    flash_by_reward = _flash_for_rewards(result)
    return jsonify([_with_flash_status(r, flash_by_reward.get(r.get("id"))) for r in result]), 200


@rewards_bp.route("/<reward_id>", methods=["GET"])
def get_reward(reward_id):
    """
    Get reward detail.
    ---
    tags: [Rewards]
    security: []
    parameters:
      - in: path
        name: reward_id
        type: string
        required: true
    responses:
      200:
        description: Reward detail
      404:
        description: Not found
    """
    db = get_user_client()
    reward = db.table("rewards").select("*,hp_tiers(name,slug)").eq("id", reward_id).single().execute()
    if not reward:
        return jsonify({"error": MSG.REWARD_NOT_FOUND}), 404
    try:
        _, flash = _is_flash_active(get_db(), reward["id"])
    except Exception:
        logger.warning("flash status lookup failed for reward %s", reward_id, exc_info=True)
        flash = None
    return jsonify(_with_flash_status(reward, flash)), 200


@rewards_bp.route("/<reward_id>/redeem", methods=["POST"])
@require_auth
def redeem_reward(reward_id):
    """
    Redeem a reward using HP via atomic hg_redeem_reward RPC.
    ---
    tags: [Rewards]
    parameters:
      - in: path
        name: reward_id
        type: string
        required: true
    responses:
      201:
        description: Redemption successful
      400:
        description: Insufficient HP or reward not available
    """
    db = get_user_client()
    now = datetime.now(timezone.utc).isoformat()

    # Pre-fetch reward name and cost for notification/response
    reward = db.table("rewards").select("id,name,hp_cost,is_active,stock_quantity,expires_at,min_tier_id").eq("id", reward_id).single().execute()
    if not reward or not reward.get("is_active", True):
        return jsonify({"error": MSG.REWARD_NOT_AVAILABLE}), 404

    now = datetime.now(timezone.utc).isoformat()
    expires_at = reward.get("expires_at")
    if expires_at and expires_at < now:
        return jsonify({"error": MSG.REWARD_EXPIRED}), 400

    stock = reward.get("stock_quantity")
    if stock is not None and stock <= 0:
        return jsonify({"error": MSG.REWARD_OUT_OF_STOCK}), 400

    if reward.get("min_tier_id"):
        from app.services.tier_service import can_access_tier_resource
        if not can_access_tier_resource(g.user_id, reward["min_tier_id"]):
            return jsonify({"error": MSG.REWARD_TIER_TOO_LOW}), 400

    hp_cost = reward.get("hp_cost", 0)

    try:
        rpc_res = get_db().rpc("hg_redeem_reward", {
            "p_user_id": g.user_id,
            "p_reward_id": reward_id,
        })
    except Exception as exc:
        err_str = str(exc)
        if "MAX_PER_USER" in err_str.upper():
            return jsonify({"error": MSG.REWARD_MAX_PER_USER_REACHED}), 400
        if "TIER_TOO_LOW" in err_str.upper():
            return jsonify({"error": MSG.REWARD_TIER_TOO_LOW}), 400
        if "INSUFFICIENT" in err_str.upper() or "BALANCE" in err_str.upper():
            balance = get_hp_balance(g.user_id)
            return jsonify({"error": resolve_msg(MSG.REWARD_INSUFFICIENT_HP, need=hp_cost, have=balance["active"])}), 400
        if "STOCK" in err_str.upper() or "OUT_OF_STOCK" in err_str.upper():
            return jsonify({"error": MSG.REWARD_OUT_OF_STOCK}), 400
        if "NOT_FOUND" in err_str.upper() or "INACTIVE" in err_str.upper():
            return jsonify({"error": MSG.REWARD_NOT_AVAILABLE}), 404
        if "EXPIRED" in err_str.upper():
            return jsonify({"error": MSG.REWARD_EXPIRED}), 400
        return jsonify({"error": err_str}), 400

    if isinstance(rpc_res, dict) and rpc_res.get("error"):
        err_str = str(rpc_res["error"])
        if "MAX_PER_USER" in err_str.upper():
            return jsonify({"error": MSG.REWARD_MAX_PER_USER_REACHED}), 400
        if "TIER_TOO_LOW" in err_str.upper():
            return jsonify({"error": MSG.REWARD_TIER_TOO_LOW}), 400
        if "INSUFFICIENT" in err_str.upper() or "BALANCE" in err_str.upper():
            balance = get_hp_balance(g.user_id)
            return jsonify({"error": resolve_msg(MSG.REWARD_INSUFFICIENT_HP, need=hp_cost, have=balance["active"])}), 400
        if "STOCK" in err_str.upper() or "OUT_OF_STOCK" in err_str.upper():
            return jsonify({"error": MSG.REWARD_OUT_OF_STOCK}), 400
        if "NOT_FOUND" in err_str.upper() or "INACTIVE" in err_str.upper():
            return jsonify({"error": MSG.REWARD_NOT_AVAILABLE}), 404
        if "EXPIRED" in err_str.upper():
            return jsonify({"error": MSG.REWARD_EXPIRED}), 400
        return jsonify({"error": err_str}), 400

    redemption_row = rpc_res if isinstance(rpc_res, dict) else {"id": str(rpc_res), "user_id": g.user_id, "reward_id": reward_id, "hp_cost_snapshot": hp_cost, "status": "pending"}
    redemption_id = redemption_row.get("id") or redemption_row.get("redemption_id") or str(rpc_res)

    try:
        send_notification(
            user_id=g.user_id,
            notif_type="reward_redeemed",
            template_data={"name": reward["name"], "hp": hp_cost},
            reference_id=redemption_id,
            reference_type="reward_redemption",
        )
    except Exception:
        pass

    return jsonify({"redemption": redemption_row, "hp_spent": hp_cost}), 201


@rewards_bp.route("/admin/redemptions", methods=["GET"])
@require_role("admin")
def admin_list_redemptions():
    """
    List all reward redemptions across all users (admin only).
    ---
    tags: [Rewards]
    parameters:
      - in: query
        name: status
        type: string
        enum: [pending, fulfilled, rejected]
      - in: query
        name: reward_id
        type: string
        description: Filter by reward
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
        description: All redemptions for admin
    """
    db = get_user_client()
    try:
        limit = int(request.args.get("limit", 50))
    except (TypeError, ValueError):
        limit = 50
    limit = max(1, min(limit, 200))
    try:
        offset = int(request.args.get("offset", 0))
    except (TypeError, ValueError):
        offset = 0
    offset = max(0, offset)
    q = db.table("reward_redemptions").select(
        "*,rewards(name,reward_type,hp_cost,image_url),profiles!user_id(full_name,email)"
    )
    campus_id = resolve_scoped_campus_id(request.args.get("campus_id"))
    if campus_id:
        q = q.eq("campus_id", campus_id)
    status = request.args.get("status")
    if status:
        q = q.eq("status", status)
    reward_id = request.args.get("reward_id")
    if reward_id:
        q = q.eq("reward_id", reward_id)
    rows = q.order("created_at", ascending=False).limit(limit).offset(offset).execute() or []
    return jsonify({"redemptions": rows, "count": len(rows)}), 200


def _log_fulfilment_cost(redemption_id: str, row: dict, actual_cost) -> None:
    """
    Record what a fulfilled redemption cost the business (feeds the economics dashboard).
    An admin-supplied actual_cost is written as given; otherwise economics_service derives it from the reward's
    cost fields. Both write the same single row (redemption_cost_log.redemption_id is unique), so they are
    alternatives, never both. Never raises: a logging failure must not undo the fulfilment.
    """
    try:
        if actual_cost is not None:
            db = get_db()
            reward = db.table("rewards").select("reward_type").eq("id", row["reward_id"]).single().execute() or {}
            db.table("redemption_cost_log").insert({
                "redemption_id": redemption_id,
                "reward_id": row["reward_id"],
                "reward_type": reward.get("reward_type"),
                "hp_spent": int(row.get("hp_cost_snapshot") or 0),
                "actual_cost": actual_cost,
                "campus_id": row.get("campus_id"),
                "user_id": row.get("user_id"),
            })
        else:
            from app.services.economics_service import log_redemption_cost
            log_redemption_cost(redemption_id, row["reward_id"], row.get("hp_cost_snapshot") or 0,
                                row.get("campus_id"), row.get("user_id"))
    except Exception:
        logger.warning("redemption cost log failed for redemption %s", redemption_id, exc_info=True)


@rewards_bp.route("/admin/redemptions/<redemption_id>", methods=["PATCH"])
@require_role("admin")
def admin_update_redemption(redemption_id):
    # Rejection triggers HP refund — not just status update
    """
    Fulfil or reject a reward redemption (admin only).
    ---
    tags: [Rewards]
    parameters:
      - in: path
        name: redemption_id
        type: string
        required: true
      - in: body
        name: body
        required: true
        schema:
          required: [status]
          properties:
            status: {type: string, enum: [fulfilled, rejected]}
            admin_notes: {type: string}
            fulfilled_at: {type: string, format: date-time, description: "Defaults to now"}
    responses:
      200:
        description: Redemption updated
      400:
        description: Invalid status
      404:
        description: Redemption not found
    """
    db = get_user_client()
    q = db.table("reward_redemptions").select("id,status,user_id,reward_id,hp_cost_snapshot,campus_id").eq("id", redemption_id)
    campus_id = getattr(g, 'campus_id', None)
    if campus_id:
        q = q.eq("campus_id", campus_id)
    row = q.single().execute()
    if not row:
        return jsonify({"error": MSG.REWARD_REDEMPTION_NOT_FOUND}), 404
    data = request.get_json(force=True) or {}
    new_status = data.get("status", "").strip()
    if new_status not in ("fulfilled", "rejected"):
        return jsonify({"error": MSG.REWARD_REDEMPTION_INVALID_STATUS}), 400

    # Validate before anything changes, so a bad value can't fail after the status is already written.
    actual_cost = None
    if new_status == "fulfilled" and data.get("actual_cost") is not None:
        try:
            actual_cost = float(data["actual_cost"])
            if not math.isfinite(actual_cost) or actual_cost < 0:
                raise ValueError
        except (TypeError, ValueError):
            return jsonify({"error": MSG.REDEMPTION_ACTUAL_COST_INVALID}), 400

    old_status = row.get("status")
    if old_status == new_status:
        return jsonify({"message": "No change", "status": new_status}), 200

    if old_status == "fulfilled" and new_status == "rejected":
        return jsonify({"error": "Cannot reject an already-fulfilled redemption"}), 400

    # Before changing status to rejected: refund spent HP
    if new_status == "rejected" and old_status == "pending":
        hp_cost = int(row.get("hp_cost_snapshot") or 0)
        user_id = row.get("user_id")
        if hp_cost > 0 and user_id:
            try:
                from app.services.hp_service import award_active_hp
                award_active_hp(
                    user_id=user_id,
                    amount=hp_cost,
                    txn_type="earn",
                    reference_id=redemption_id,
                    reference_type="reward_rejection_refund",
                    source_type="reward_refund",
                    notes=f"HP refund for rejected reward redemption #{redemption_id[:8].upper()}",
                    apply_multiplier=False,           # a refund returns exactly what was spent, never x2 during a bonus event
                    campus_id=row.get("campus_id"),   # the redemption's campus, not the acting admin's
                )
            except Exception as e:
                return jsonify({"error": f"HP refund failed: {str(e)}"}), 400

        # Restore the stock unit this redemption had claimed. Compare-and-swap on the quantity we read, so two
        # concurrent rejections can't overwrite each other's +1 (lost update); re-read and retry on a conflict.
        try:
            reward_id = row.get("reward_id")
            for _attempt in range(3):
                current_reward = (
                    db.table("rewards").select("stock_quantity").eq("id", reward_id).single().execute()
                )
                if not current_reward or current_reward.get("stock_quantity") is None:
                    break  # unlimited stock (or reward gone): nothing to restore
                old_qty = current_reward["stock_quantity"]
                res = (
                    db.table("rewards").eq("id", reward_id).eq("stock_quantity", old_qty)
                    .update({"stock_quantity": old_qty + 1})
                )
                if res:
                    break
            else:
                logger.error("admin_update_redemption: stock restore conflicted 3 times for reward %s "
                             "(redemption %s); restore the unit by hand", reward_id, redemption_id)
        except Exception as e:
            return jsonify({"error": f"Stock restore failed: {str(e)}"}), 400

    update = {"status": new_status, "fulfilled_by": g.user_id}
    if new_status == "fulfilled":
        update["fulfilled_at"] = datetime.now(timezone.utc).isoformat()
    # Only move the row if it is still in the state we checked: two admins acting at once can both pass the
    # pending-state check above, but only one of them can win this write.
    result = db.table("reward_redemptions").eq("id", redemption_id).eq("status", old_status).update(update)
    if not result:
        return jsonify({"error": MSG.REDEMPTION_UPDATE_CONFLICT}), 409

    if new_status == "fulfilled":
        _log_fulfilment_cost(redemption_id, row, actual_cost)

    # Notify the user. On fulfilment they get the "choose how to receive it" prompt instead of the generic
    # status line, so one event never produces two notifications.
    try:
        reward = db.table("rewards").select("name").eq("id", row["reward_id"]).single().execute() or {}
        reward_name = reward.get("name", "reward")
        if new_status == "fulfilled":
            send_notification(
                user_id=row["user_id"],
                notif_type="reward_fulfilled_choose_delivery",
                template_data={"name": reward_name},
                reference_id=redemption_id,
                reference_type="reward_redemption",
            )
        else:
            send_notification(
                user_id=row["user_id"],
                notif_type="reward_status",
                template_data={"name": reward_name, "status": new_status},
            )
    except Exception:
        pass
    return jsonify(result[0] if isinstance(result, list) else result), 200


_ECONOMICS_FIELDS = ("food_cost", "packaging_cost", "menu_price", "production_cost", "perceived_value", "margin_share_pct")


def _apply_reward_economics(db, data: dict):
    """
    When a cost basis is supplied, derive reward_value (and hp_cost, if the admin didn't set one) with
    economics_service. Food rewards need food_cost + menu_price; merch needs production_cost + perceived_value.
    Returns an error message for bad input, else None. Mutates `data`.
    """
    try:
        for field in _ECONOMICS_FIELDS:
            if data.get(field) is not None:
                data[field] = float(data[field])
                if not math.isfinite(data[field]) or data[field] < 0:
                    raise ValueError
        if data.get("margin_share_pct") is not None and data["margin_share_pct"] > 1:
            raise ValueError
    except (TypeError, ValueError):
        return MSG.REWARD_ECONOMICS_INVALID

    packaging = data.get("packaging_cost") or 0.0
    if data.get("food_cost") is not None and data.get("menu_price") is not None:
        from app.services.economics_service import calculate_food_reward_value
        value = calculate_food_reward_value(db, data["food_cost"], packaging, data["menu_price"], data.get("margin_share_pct"))
    elif data.get("production_cost") is not None and data.get("perceived_value") is not None:
        from app.services.economics_service import calculate_merch_reward_value
        value = calculate_merch_reward_value(db, data["production_cost"], packaging, data["perceived_value"], data.get("margin_share_pct"))
    else:
        return None
    data["reward_value"] = round(value, 2)
    if not data.get("hp_cost"):
        from app.services.economics_service import calculate_hp_price
        data["hp_cost"] = calculate_hp_price(db, value)
    return None


@rewards_bp.route("", methods=["POST"])
@require_role("admin")
def create_reward():
    """
    Create a new reward (admin only).
    ---
    tags: [Rewards]
    parameters:
      - in: body
        name: body
        required: true
        schema:
          required: [name, hp_cost, category]
          properties:
            name: {type: string}
            hp_cost: {type: integer}
            category: {type: string, enum: [food, merch, experience, marketplace]}
            quantity_available: {type: integer}
            min_tier_id: {type: string}
            starts_at: {type: string, format: date-time}
            ends_at: {type: string, format: date-time}
    responses:
      201:
        description: Reward created
    """
    db = get_user_client()
    data = request.get_json(force=True)
    if data.get("name") is None:
        return jsonify({"error": MSG.AUTH_FIELD_REQUIRED.format(field="name")}), 400
    if data.get("fulfillment_type") is not None and data["fulfillment_type"] not in _FULFILLMENT_TYPES:
        return jsonify({"error": MSG.REWARD_FULFILLMENT_TYPE_INVALID}), 400
    # hp_cost may be left out when a cost basis is given: it is then derived from the economics settings.
    economics_error = _apply_reward_economics(db, data)
    if economics_error:
        return jsonify({"error": economics_error}), 400
    if data.get("hp_cost") is None:
        return jsonify({"error": MSG.AUTH_FIELD_REQUIRED.format(field="hp_cost")}), 400
    if "category" in data and "reward_type" not in data:
        data["reward_type"] = data.pop("category")
    # quantity_available is the API name; DB column is stock_quantity
    if "quantity_available" in data:
        data["stock_quantity"] = data.pop("quantity_available")
    data["is_active"] = data.get("is_active", True)
    data["campus_id"] = data.get("campus_id") or getattr(g, "campus_id", None)
    result = db.table("rewards").insert(data)
    created = result[0] if isinstance(result, list) else result

    # Notify all active users about the new reward
    try:
        reward_name = created.get("name") or data.get("name", "New reward")
        active_users_q = (
            db.table("profiles")
            .select("id")
            .eq("is_active", "true")
            .eq("role", "student")
        )
        # Only tell students on the reward's own campus (a global reward, campus NULL, goes to everyone).
        reward_campus = created.get("campus_id") or data.get("campus_id")
        if reward_campus:
            active_users_q = active_users_q.eq("campus_id", reward_campus)
        active_users = active_users_q.execute() or []
        for user in active_users:
            send_notification(
                user_id=user["id"],
                notif_type="new_reward",
                template_data={"name": reward_name},
                reference_id=created.get("id"),
                reference_type="reward",
            )
    except Exception:
        pass

    return jsonify(created), 201


@rewards_bp.route("/<reward_id>/image", methods=["POST"])
@require_role("admin")
def update_reward_image(reward_id):
    """Update reward image with Cloudinary URL."""
    data = request.get_json(force=True, silent=True) or {}
    image_url = data.get("image_url")

    if not image_url:
        return jsonify({"error": "image_url is required"}), 400

    db = get_user_client()
    q = db.table("rewards").eq("id", reward_id)
    campus_id = getattr(g, "campus_id", None)
    if campus_id:
        q = q.eq("campus_id", campus_id)
    result = q.update({
        "image_url": image_url,
        "updated_at": datetime.now(timezone.utc).isoformat(),
    })
    if not result:
        return jsonify({"error": MSG.REWARD_NOT_FOUND}), 404

    return jsonify({"image_url": image_url}), 200


@rewards_bp.route("/<reward_id>", methods=["PATCH"])
@require_role("admin")
def update_reward(reward_id):
    """
    Update a reward (admin only).
    ---
    tags: [Rewards]
    parameters:
      - in: path
        name: reward_id
        type: string
        required: true
      - in: body
        name: body
        schema:
          properties:
            hp_cost: {type: integer}
            is_active: {type: boolean}
            quantity_available: {type: integer}
            ends_at: {type: string, format: date-time}
    responses:
      200:
        description: Reward updated
    """
    db = get_user_client()
    data = request.get_json(force=True)
    if data.get("fulfillment_type") is not None and data["fulfillment_type"] not in _FULFILLMENT_TYPES:
        return jsonify({"error": MSG.REWARD_FULFILLMENT_TYPE_INVALID}), 400
    data["updated_at"] = datetime.now(timezone.utc).isoformat()
    q = db.table("rewards").eq("id", reward_id)
    campus_id = getattr(g, "campus_id", None)
    if campus_id:
        q = q.eq("campus_id", campus_id)
    result = q.update(data)
    if not result:
        return jsonify({"error": MSG.REWARD_NOT_FOUND}), 404
    return jsonify(result[0] if isinstance(result, list) else result), 200


@rewards_bp.route("/<reward_id>", methods=["DELETE"])
@require_role("admin")
def delete_reward(reward_id):
    """
    Deactivate (soft-delete) a reward (admin only).
    ---
    tags: [Rewards]
    parameters:
      - in: path
        name: reward_id
        type: string
        required: true
    responses:
      200:
        description: Reward deactivated
      404:
        description: Reward not found
    """
    db = get_user_client()
    q = db.table("rewards").select("id").eq("id", reward_id)
    campus_id = getattr(g, "campus_id", None)
    if campus_id:
        q = q.eq("campus_id", campus_id)
    existing = q.limit(1).execute()
    if not existing:
        return jsonify({"error": MSG.REWARD_NOT_FOUND}), 404
    update_q = db.table("rewards").eq("id", reward_id)
    if campus_id:
        update_q = update_q.eq("campus_id", campus_id)
    update_q.update({
        "is_active": False,
        "updated_at": datetime.now(timezone.utc).isoformat(),
    })
    return jsonify({"message": MSG.REWARD_DEACTIVATED, "reward_id": reward_id}), 200


@rewards_bp.route("/redemptions", methods=["GET"])
@require_auth
def my_redemptions():
    """
    Get authenticated user's reward redemption history.
    ---
    tags: [Rewards]
    responses:
      200:
        description: Redemption history
    """
    db = get_user_client()
    redemptions = (
        db.table("reward_redemptions")
        .select("*,rewards(name,reward_type,hp_cost,image_url)")
        .eq("user_id", g.user_id)
        .order("created_at", ascending=False)
        .execute()
    )
    return jsonify(redemptions), 200


@rewards_bp.route("/admin/flash-sales", methods=["POST"])
@require_role("admin")
def create_flash_sale():
    """
    Open a flash sale (discounted HP price, first N redeemers, time-boxed) on a reward (admin only).
    ---
    tags: [Rewards]
    parameters:
      - in: body
        name: body
        required: true
        schema:
          required: [reward_id, window_ends_at]
          properties:
            reward_id: {type: string}
            window_starts_at: {type: string, format: date-time, description: "Defaults to now"}
            window_ends_at: {type: string, format: date-time}
            quantity_limit: {type: integer, default: 5}
            discount_pct: {type: number, description: "0-1 exclusive, default 0.5"}
    responses:
      201:
        description: Flash sale created
      400:
        description: Invalid input, or the window overlaps an active sale for this reward
      404:
        description: Reward not found
    """
    db = get_user_client()
    data = request.get_json(force=True, silent=True) or {}
    reward_id = data.get("reward_id")
    if not reward_id:
        return jsonify({"error": MSG.REWARD_ID_REQUIRED}), 400
    if not data.get("window_ends_at"):
        return jsonify({"error": MSG.FLASH_WINDOW_END_REQUIRED}), 400
    window_starts_at = data.get("window_starts_at") or datetime.now(timezone.utc).isoformat()
    window_ends_at = data["window_ends_at"]
    try:
        def _parse(value):
            parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
            return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)
        if _parse(window_ends_at) <= _parse(window_starts_at):
            raise ValueError
    except (TypeError, ValueError, OverflowError):
        return jsonify({"error": MSG.FLASH_WINDOW_INVALID}), 400
    try:
        quantity_limit = int(data.get("quantity_limit", 5))
        if quantity_limit < 1:
            raise ValueError
    except (TypeError, ValueError):
        return jsonify({"error": MSG.FLASH_QUANTITY_INVALID}), 400
    try:
        discount_pct = float(data.get("discount_pct", 0.5))
    except (TypeError, ValueError):
        return jsonify({"error": MSG.FLASH_DISCOUNT_RANGE_INVALID}), 400
    if not (0 < discount_pct < 1):
        return jsonify({"error": MSG.FLASH_DISCOUNT_RANGE_INVALID}), 400

    campus_id = getattr(g, "campus_id", None)
    reward = db.table("rewards").select("id,campus_id").eq("id", reward_id).single().execute()
    if not reward:
        return jsonify({"error": MSG.REWARD_NOT_FOUND}), 404
    if campus_id and reward.get("campus_id") not in (campus_id, None):
        return jsonify({"error": MSG.REWARD_NOT_FOUND}), 404

    overlap = (
        db.table("flash_redemptions").select("id")
        .eq("reward_id", reward_id).eq("is_active", "true")
        .lte("window_starts_at", window_ends_at).gte("window_ends_at", window_starts_at)
        .execute()
    )
    if overlap:
        return jsonify({"error": MSG.FLASH_SALE_WINDOW_OVERLAP}), 400

    result = db.table("flash_redemptions").insert({
        "reward_id": reward_id,
        "window_starts_at": window_starts_at,
        "window_ends_at": window_ends_at,
        "quantity_limit": quantity_limit,
        "discount_pct": discount_pct,
        "campus_id": reward.get("campus_id"),
    })
    return jsonify(result[0] if isinstance(result, list) else result), 201


@rewards_bp.route("/redemptions/<redemption_id>/delivery-choice", methods=["POST"])
@require_auth
def choose_redemption_delivery(redemption_id):
    """
    Choose how to receive a fulfilled reward: right now at checkout, or attached to the next order.
    ---
    tags: [Rewards]
    parameters:
      - in: path
        name: redemption_id
        type: string
        required: true
      - in: body
        name: body
        required: true
        schema:
          required: [delivery_mode]
          properties:
            delivery_mode: {type: string, enum: [instant, next_order]}
    responses:
      200:
        description: Choice saved
      400:
        description: Invalid mode, reward not fulfilled yet, or delivery already chosen
      404:
        description: Redemption not found
    """
    db = get_user_client()
    data = request.get_json(force=True, silent=True) or {}
    mode = data.get("delivery_mode")
    if mode not in ("instant", "next_order"):
        return jsonify({"error": MSG.DELIVERY_MODE_INVALID}), 400

    # Ownership is checked with the user's own session (RLS + explicit user_id filter).
    row = (
        db.table("reward_redemptions")
        .select("id,user_id,status,reward_id,delivery_mode,attached_order_id")
        .eq("id", redemption_id).eq("user_id", g.user_id)
        .single().execute()
    )
    if not row:
        return jsonify({"error": MSG.REWARD_REDEMPTION_NOT_FOUND}), 404
    if row.get("status") != "fulfilled":
        return jsonify({"error": MSG.REWARD_NOT_READY_FOR_DELIVERY}), 400
    # 'instant' is the column default, so it means "not chosen yet"; anything else, or an order already
    # holding this reward, means the choice is made.
    if row.get("attached_order_id") or row.get("delivery_mode") != "instant":
        return jsonify({"error": MSG.DELIVERY_ALREADY_CHOSEN}), 400

    # reward_redemptions has no UPDATE policy for the owner (only admins), so a write through the user's
    # session would silently change nothing. The write goes through the service role, pinned to the same
    # owner / state that was just verified.
    updated = (
        get_db().table("reward_redemptions")
        .eq("id", redemption_id).eq("user_id", g.user_id)
        .eq("status", "fulfilled").eq("delivery_mode", row["delivery_mode"]).eq("attached_order_id", None)
        .update({"delivery_mode": mode})
    )
    if not updated:
        return jsonify({"error": MSG.REDEMPTION_UPDATE_CONFLICT}), 409

    if mode == "instant":
        return jsonify({"delivery_mode": mode, "next_step": "checkout", "reward_redemption_id": redemption_id}), 200
    return jsonify({"delivery_mode": mode, "message": MSG.REWARD_DELIVERY_NEXT_ORDER}), 200
