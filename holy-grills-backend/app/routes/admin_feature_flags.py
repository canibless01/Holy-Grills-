"""
Admin — Feature Flags + Leaderboard Prize Fulfilment + Hall of Fame Reward Fulfilment
+ Exclusive Spin Prize Fulfilment.

GET    /api/admin/feature-flags           — list all flags (global; any admin can view)
POST   /api/admin/feature-flags           — create a flag (super_admin only)
GET    /api/admin/feature-flags/<n>       — get one flag (any admin can view)
PATCH  /api/admin/feature-flags/<n>       — create-or-update a flag (super_admin only)

GET    /api/admin/leaderboard-prizes      — pending prize fulfilments (campus-scoped)
PATCH  /api/admin/leaderboard-prizes/<id> — mark one fulfilled

GET    /api/admin/hall-of-fame-rewards    — pending HoF box rewards (campus-scoped)
PATCH  /api/admin/hall-of-fame-rewards/<user_id> — update status

GET    /api/admin/exclusive-spin-prizes      — pending exclusive-spin physical prizes (campus-scoped)
PATCH  /api/admin/exclusive-spin-prizes/<id> — mark one fulfilled

NOTE: feature flags are global by design, not per-campus — confirmed live against
feature_flags_admin_write (super_admin-only write) and feature_flags_read_scoped (any
authenticated user may read a global flag). Any admin can view the list; only super_admin
can create or toggle one. The prize-fulfilment endpoints below are a separate, genuinely
campus-scoped concern and are unaffected by this.
"""

import re
from flask import Blueprint, request, jsonify, g
from app.middleware.auth import require_role, resolve_scoped_campus_id, fetch_or_403, update_or_403
from app.db import get_db, get_user_client, SupabaseError
from app.messages import MSG
from app.utils.logger import get_logger
from datetime import datetime, timezone

logger = get_logger(__name__)

admin_flags_bp = Blueprint("admin_feature_flags", __name__)

_FLAG_NAME_RE = re.compile(r"^[a-z0-9_]{1,64}$")
_PRIZE_STATUSES = ("pending", "fulfilled", "cancelled")
_HOF_STATUSES = ("pending", "box_prepared", "fulfilled", "cancelled")
_CLOSED_STATUSES = ("fulfilled", "cancelled")
_STATUS_WORDS = {"fulfilled": "fulfilled", "cancelled": "cancelled", "box_prepared": "ready (box prepared)"}
# exclusive_spin_fulfillments has no `notes` column, unlike its two sibling prize tables.
_NOTES_UNSUPPORTED_TABLES = {"exclusive_spin_fulfillments"}


def _json_body():
    """Request JSON as a dict, or None when missing / malformed / not an object."""
    data = request.get_json(force=True, silent=True)
    return data if isinstance(data, dict) else None


def _page():
    """limit (default 100, max 500) and offset from the query string."""
    try:
        limit = min(max(int(request.args.get("limit", 100)), 1), 500)
    except (TypeError, ValueError):
        limit = 100
    try:
        offset = max(int(request.args.get("offset", 0)), 0)
    except (TypeError, ValueError):
        offset = 0
    return limit, offset


def _audit_admin(entity_type, entity_id, action, before=None, after=None, campus_id=None):
    """Audit trail for admin changes. Written with the service role so it never depends on the admin's row security."""
    try:
        get_db().table("admin_audit_logs").insert({
            "actor_id": g.user_id,
            "actor_role": getattr(g, "user_role", None) or "admin",
            "entity_type": entity_type,
            "entity_id": str(entity_id),
            "action": action,
            "before_value": before,
            "after_value": after,
            "campus_id": campus_id,
        })
    except Exception as e:
        logger.error("_audit_admin: failed to log %s/%s/%s: %s", entity_type, entity_id, action, e)


# ── Feature Flags ─────────────────────────────────────────────────────────────

def _upsert_feature_flag(flag_name, data, create_status=200):
    """Shared create-or-update body for a feature flag. Used by both the POST and PATCH routes
    so the two never drift apart. create_status is 200 for the PATCH route (matches the fixes doc
    exactly — an upsert that happens to create still says 200) and 201 for the dedicated POST route.

    Feature flags are GLOBAL — there is no per-campus feature flag, and only super_admin may
    create/toggle one (both routes are gated @require_role("super_admin") below; a campus admin
    can view flags but never reaches this function). campus_id is never accepted from the request
    and is always written as NULL, so feature_name alone stays a genuine unique key and a plain
    .eq("feature_name", ...).single() is always safe — no per-campus lookup complexity needed."""
    if "is_active" in data and not isinstance(data["is_active"], bool):
        return jsonify({"error": MSG.FEATURE_FLAG_ACTIVE_INVALID}), 400
    if "description" in data and data["description"] is not None and (not isinstance(data["description"], str) or len(data["description"]) > 500):
        return jsonify({"error": MSG.FEATURE_FLAG_DESCRIPTION_INVALID}), 400

    db = get_user_client()
    existing = db.table("feature_flags").select("*").eq("feature_name", flag_name).single().execute()
    now_iso = datetime.now(timezone.utc).isoformat()

    def _update_existing(current):
        safe = {k: v for k, v in data.items() if k in {"is_active", "description"}}
        if not safe:
            return jsonify({"error": MSG.NO_VALID_FIELDS_TO_UPDATE}), 400
        safe["updated_at"] = now_iso
        safe["updated_by"] = g.user_id
        try:
            result = db.table("feature_flags").eq("feature_name", flag_name).update(safe)
        except SupabaseError as e:
            logger.info("update_feature_flag: rejected %s: %s", flag_name, e)
            return jsonify({"error": MSG.UPDATE_NOT_PERMITTED}), 403
        if not result:
            return jsonify({"error": MSG.UPDATE_NOT_PERMITTED}), 403
        updated = result[0] if isinstance(result, list) else result
        _audit_admin("feature_flags", flag_name, "update_feature_flag",
                     before={"is_active": current.get("is_active")}, after=safe)
        return jsonify({"message": MSG.FEATURE_FLAG_UPDATED, "flag": updated}), 200

    if existing:
        return _update_existing(existing)

    if not _FLAG_NAME_RE.match(flag_name):
        return jsonify({"error": MSG.FEATURE_FLAG_NAME_INVALID}), 400
    payload = {
        "feature_name": flag_name,
        "is_active": data.get("is_active", False),
        "description": data.get("description"),
        "campus_id": None,   # feature flags are global — always
        "updated_at": now_iso,
        "updated_by": g.user_id,
    }
    try:
        result = db.table("feature_flags").insert(payload)
    except SupabaseError as e:
        code = str((e.details or {}).get("code", "")) if isinstance(e.details, dict) else ""
        if code == "23505":   # two super_admins created the same flag at the same moment: the second becomes an update
            again = db.table("feature_flags").select("*").eq("feature_name", flag_name).single().execute()
            if again:
                return _update_existing(again)
        if e.status_code in (401, 403) or code == "42501":
            return jsonify({"error": MSG.UPDATE_NOT_PERMITTED}), 403
        logger.info("update_feature_flag: create rejected %s: %s", flag_name, e)
        return jsonify({"error": MSG.FEATURE_FLAG_NAME_INVALID}), 400
    created = result[0] if isinstance(result, list) else result
    _audit_admin("feature_flags", flag_name, "create_feature_flag", after=payload)
    return jsonify({"message": MSG.FEATURE_FLAG_UPDATED, "flag": created}), create_status


@admin_flags_bp.route("/feature-flags", methods=["POST"])
@require_role("super_admin")
def create_feature_flag():
    """
    Create a feature flag (super_admin only — flags are global, not per-campus).
    """
    data = _json_body()
    if data is None:
        return jsonify({"error": MSG.ADMIN_REQUEST_BODY_INVALID}), 400
    flag_name = (data.get("feature_name") or "").strip()
    if not flag_name:
        return jsonify({"error": MSG.FEATURE_FLAG_NAME_REQUIRED}), 400
    return _upsert_feature_flag(flag_name, data, create_status=201)


@admin_flags_bp.route("/feature-flags", methods=["GET"])
@require_role("admin")
def list_feature_flags():
    """
    List every feature flag (global — a campus admin can view, only super_admin can toggle).
    ---
    tags: [Admin]
    responses:
      200:
        description: Feature flag list
    """
    db = get_user_client()
    rows = db.table("feature_flags").select("*").order("feature_name").execute() or []
    return jsonify(rows), 200


@admin_flags_bp.route("/feature-flags/<flag_name>", methods=["GET"])
@require_role("admin")
def get_feature_flag(flag_name):
    """
    Get a specific feature flag (viewable by any admin; only super_admin can toggle it).
    ---
    tags: [Admin]
    parameters:
      - in: path
        name: flag_name
        type: string
        required: true
    responses:
      200:
        description: Flag detail
      404:
        description: Not found
    """
    db = get_user_client()
    row = db.table("feature_flags").select("*").eq("feature_name", flag_name).single().execute()
    if not row:
        return jsonify({"error": MSG.FEATURE_FLAG_NOT_FOUND}), 404
    return jsonify(row), 200


@admin_flags_bp.route("/feature-flags/<flag_name>", methods=["PATCH"])
@require_role("super_admin")
def update_feature_flag(flag_name):
    """
    Create or update a feature flag (upsert; super_admin only — flags are global, not per-campus).
    Body: { "is_active": true }
    ---
    tags: [Admin]
    parameters:
      - in: path
        name: flag_name
        type: string
        required: true
      - in: body
        name: body
        schema:
          properties:
            is_active: {type: boolean}
            description: {type: string}
    responses:
      200:
        description: Flag updated (or created)
      400:
        description: Validation error
    """
    data = _json_body()
    if data is None:
        return jsonify({"error": MSG.ADMIN_REQUEST_BODY_INVALID}), 400
    return _upsert_feature_flag(flag_name, data)


# ── Shared prize-table helpers (B-30) ───────────────────────────────────────

def _list_prizes(table, order_col, profile_fields, allow_month=False):
    """Shared list for the prize tables: campus-scoped, paginated, enriched with the winner's name / contact."""
    db = get_user_client()
    limit, offset = _page()
    q = db.table(table).select("*").order(order_col, ascending=False)
    status = request.args.get("status")
    if status:
        q = q.eq("status", status)
    if allow_month and request.args.get("month"):
        q = q.eq("month", request.args.get("month"))
    campus_id = resolve_scoped_campus_id(request.args.get("campus_id"))
    if campus_id:
        q = q.eq("campus_id", campus_id)
    rows = q.limit(limit).offset(offset).execute() or []

    user_ids = list({r["user_id"] for r in rows if r.get("user_id")})
    profiles = {}
    if user_ids:
        prows = db.table("profiles").select("id," + profile_fields).in_("id", user_ids).execute() or []
        profiles = {p["id"]: p for p in prows}
    for r in rows:
        prof = profiles.get(r.get("user_id"), {})
        r["full_name"] = prof.get("full_name")
        r["phone"] = prof.get("phone")
        if "email" in profile_fields:
            r["email"] = prof.get("email")
    return jsonify(rows), 200


def _fulfil(table, record_id, allowed, not_found_msg, done_msg, label_fn):
    """Shared status change for the prize tables (validated, campus-safe, one-way, audited, winner notified)."""
    data = _json_body()
    if data is None:
        return jsonify({"error": MSG.ADMIN_REQUEST_BODY_INVALID}), 400
    patch = {}
    if "status" in data:
        status = data["status"]
        if not isinstance(status, str) or status not in allowed:
            return jsonify({"error": MSG.PRIZE_STATUS_INVALID}), 400
        patch["status"] = status
        if status == "fulfilled":
            patch["fulfilled_by"] = g.user_id
            patch["fulfilled_at"] = datetime.now(timezone.utc).isoformat()
    if "notes" in data:
        if table in _NOTES_UNSUPPORTED_TABLES:
            # exclusive_spin_fulfillments has no `notes` column — say so instead of a raw DB error,
            # and instead of silently dropping a note the admin typed expecting it to save.
            return jsonify({"error": MSG.PRIZE_NOTES_NOT_SUPPORTED}), 400
        notes = data["notes"]
        if notes is not None and (not isinstance(notes, str) or len(notes) > 1000):
            return jsonify({"error": MSG.PRIZE_NOTES_INVALID}), 400
        patch["notes"] = notes.strip() if isinstance(notes, str) and notes.strip() else None
    if not patch:
        return jsonify({"error": MSG.NO_VALID_FIELDS_TO_UPDATE}), 400

    db = get_user_client()
    record, err = fetch_or_403(db, table, record_id, "*", not_found_msg)   # 404 unknown / malformed id, 403 another campus
    if err:
        return err
    if "status" in patch and record.get("status") in _CLOSED_STATUSES and patch["status"] != record.get("status"):
        return jsonify({"error": MSG.PRIZE_ALREADY_CLOSED}), 409
    result, err = update_or_403(db, table, record_id, patch)
    if err:
        return err
    updated = result[0] if isinstance(result, list) else result

    changed_status = "status" in patch and patch["status"] != record.get("status")
    _audit_admin(table, record_id, "prize_" + (patch["status"] if changed_status else "notes_updated"),
                 before={"status": record.get("status"), "notes": record.get("notes")}, after=patch,
                 campus_id=record.get("campus_id"))
    if changed_status and patch["status"] in _STATUS_WORDS and record.get("user_id"):
        try:
            from app.services.notification_service import send_notification
            send_notification(
                user_id=record["user_id"],
                notif_type="prize_fulfilment_update",
                template_data={"prize": label_fn(record), "status": _STATUS_WORDS[patch["status"]]},
                campus_id=record.get("campus_id"),
            )
        except Exception as e:
            logger.warning("prize update: notification failed for %s: %s", record.get("user_id"), e)
    msg = done_msg if patch.get("status") == "fulfilled" else MSG.PRIZE_UPDATED
    return jsonify({"message": msg, "record": updated}), 200


# ── Leaderboard Prize Fulfilment (B-27) ─────────────────────────────────────

@admin_flags_bp.route("/leaderboard-prizes", methods=["GET"])
@require_role("admin")
def list_leaderboard_prizes():
    """
    List leaderboard prize fulfilment records.
    ---
    tags: [Admin]
    parameters:
      - in: query
        name: status
        type: string
        enum: [pending, fulfilled, cancelled]
      - in: query
        name: month
        type: string
    responses:
      200:
        description: Prize list
    """
    return _list_prizes("leaderboard_reward_fulfillments", "month", "full_name,phone", allow_month=True)


@admin_flags_bp.route("/leaderboard-prizes/<record_id>", methods=["PATCH"])
@require_role("admin")
def fulfil_leaderboard_prize(record_id):
    """
    Mark a leaderboard prize as fulfilled.
    Body: { "status": "fulfilled", "notes": "..." }
    ---
    tags: [Admin]
    parameters:
      - in: path
        name: record_id
        type: string
        required: true
      - in: body
        name: body
        schema:
          properties:
            status: {type: string, enum: [pending, fulfilled, cancelled]}
            notes: {type: string}
    responses:
      200:
        description: Updated
      404:
        description: Not found
    """
    return _fulfil("leaderboard_reward_fulfillments", record_id, _PRIZE_STATUSES, MSG.LEADERBOARD_REWARD_NOT_FOUND,
                   MSG.LEADERBOARD_PRIZE_FULFILLED,
                   lambda r: "#%s leaderboard prize (%s)" % (r.get("rank"), r.get("month")))


# ── Hall of Fame Reward Fulfilment (B-28) ───────────────────────────────────

@admin_flags_bp.route("/hall-of-fame-rewards", methods=["GET"])
@require_role("admin")
def list_hof_rewards():
    """
    List Hall of Fame box reward records.
    ---
    tags: [Admin]
    parameters:
      - in: query
        name: status
        type: string
        enum: [pending, box_prepared, fulfilled, cancelled]
    responses:
      200:
        description: HoF reward list
    """
    return _list_prizes("hall_of_fame_rewards", "inducted_at", "full_name,phone,email")


@admin_flags_bp.route("/hall-of-fame-rewards/<record_id>", methods=["PATCH"])
@require_role("admin")
def fulfil_hof_reward(record_id):
    """
    Update a Hall of Fame reward record status.
    Body: { "status": "fulfilled", "notes": "..." }
    ---
    tags: [Admin]
    parameters:
      - in: path
        name: record_id
        type: string
        required: true
      - in: body
        name: body
        schema:
          properties:
            status: {type: string, enum: [pending, box_prepared, fulfilled, cancelled]}
            notes: {type: string}
    responses:
      200:
        description: Updated
      404:
        description: Not found
    """
    return _fulfil("hall_of_fame_rewards", record_id, _HOF_STATUSES, MSG.HOF_REWARD_NOT_FOUND,
                   MSG.HOF_REWARD_FULFILLED, lambda r: "Hall of Fame box")


# ── Exclusive Spin Prize Fulfilment (B-29) ──────────────────────────────────

@admin_flags_bp.route("/exclusive-spin-prizes", methods=["GET"])
@require_role("admin")
def list_exclusive_spin_prizes():
    """
    List exclusive-spin physical prize fulfilment records.
    ---
    tags: [Admin]
    parameters:
      - in: query
        name: status
        type: string
        enum: [pending, fulfilled, cancelled]
    responses:
      200:
        description: Prize list
    """
    return _list_prizes("exclusive_spin_fulfillments", "created_at", "full_name,phone")


@admin_flags_bp.route("/exclusive-spin-prizes/<record_id>", methods=["PATCH"])
@require_role("admin")
def fulfil_exclusive_spin_prize(record_id):
    """
    Mark an exclusive-spin physical prize as fulfilled.
    Body: { "status": "fulfilled" }  (this table has no notes column)
    ---
    tags: [Admin]
    parameters:
      - in: path
        name: record_id
        type: string
        required: true
    responses:
      200:
        description: Updated
      404:
        description: Not found
    """
    return _fulfil("exclusive_spin_fulfillments", record_id, _PRIZE_STATUSES, MSG.SPIN_PRIZE_NOT_FOUND,
                   MSG.SPIN_PRIZE_FULFILLED, lambda r: r.get("prize_name") or "exclusive spin prize")
