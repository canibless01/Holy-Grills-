"""
Admin routes — user management, orders, delivery/ordering windows, delivery batches,
promo codes, abandoned carts, audit log, cron control, HP bulk-grant/report, campuses,
reviews, exclusive-spin prize pool, webhook events.

NOTE: this file is being reassembled in sections (it is the largest file in the app).
This section covers: user management (list_users .. activate_user) and the shared
_audit() helper used across the rest of the file.
"""

import ipaddress
import re
import threading
import uuid
import hashlib
import json
import requests
from flask import Blueprint, request, jsonify, g, current_app, has_request_context
from app.middleware.auth import require_role, resolve_scoped_campus_id, assert_owns_campus, fetch_or_403, update_or_403
from app.services.notification_service import send_notification
from app.routes.auth import _revoke_supabase_sessions
from app.db import get_db, get_user_client, SupabaseError
from datetime import datetime, timezone, timedelta
from app.utils.tz import today_wat, wat_day_bounds_utc, wat_iso
from app.messages import MSG
from app.utils.logger import get_logger
from app.utils.admin_helpers import get_json_object, as_text, as_date, as_int, as_time, as_uuid, as_instant, as_number, page_args, db_error_response
from app.utils.campus_scope import as_campus_id, assert_can_modify, campus_or_global, resolve_write_campus
from app.utils.validators import (
    validate_choice, validate_datetime_order, validate_uuid, validate_hp_amount,
)
from app.services.order_service import _order_capacity_weight
from app.constants import VALID_ROLES

logger = get_logger(__name__)

admin_bp = Blueprint("admin", __name__)

# Mirrors the DB enum order_status. Keep in sync.
ORDER_STATUSES = (
    "received", "paid", "preparing", "ready", "assigned", "out_for_delivery",
    "delivered", "cancelled", "refunded", "delivery_attempted", "unclaimed",
)
_TOTAL_SPENT_CAP = 5000
# Campus admins manage only these roles; admin and super_admin accounts belong to super_admin.
_CAMPUS_ADMIN_MANAGED_ROLES = ("student", "kitchen", "rider")
# The same "no longer open" set the orders code already uses.
_TERMINAL_ORDER_STATUSES = ("delivered", "cancelled", "refunded")
_ANONYMIZED_EMAIL_SUFFIX = "@deleted.holygrills.com.ng"  # written by hg_anonymize_user

_USER_LIST_FIELDS = (
    "id,full_name,email,phone,nickname,role,is_active,created_at,referral_code,hp_balance,"
    "wallet_balance,current_tier_id,campus_id,academic_level,department,faculty"
)
_USER_DETAIL_FIELDS = {
    "id", "email", "full_name", "nickname", "role", "is_active", "phone", "date_of_birth", "photo_url",
    "faculty", "department", "department_id", "academic_level", "campus_id", "referral_code", "referred_by",
    "created_at", "updated_at", "last_activity_at", "hp_balance", "hp_earned_120day", "wallet_balance",
    "current_tier_id", "is_fraud_flagged", "graduation_claimed",
    "deactivated_at", "deactivated_by", "deactivation_reason",
}


def _search_term(raw):
    """Remove characters that would break a PostgREST or_ filter; None if nothing is left."""
    cleaned = re.sub(r"[,()*%\\]", " ", raw or "").strip()
    return cleaned[:100] or None


def _audit(actor_id, table, target_id, action, after_data=None, before_data=None, target_campus_id=None):
    """Append one row to admin_audit_logs. Returns True if it was written. Never raises."""
    ip = user_agent = None
    if has_request_context():
        try:
            ip = str(ipaddress.ip_address(request.remote_addr)) if request.remote_addr else None
        except ValueError:
            ip = None
        user_agent = (request.headers.get("User-Agent") or "")[:500] or None
    # Outside a request (a cron thread, Celery) there is no user JWT, so use the server client.
    db = get_user_client() if has_request_context() else get_db()
    try:
        db.table("admin_audit_logs").insert({
            "actor_id": actor_id,
            "actor_role": getattr(g, "user_role", None) or "admin",
            "entity_type": table,
            "entity_id": target_id,
            "action": action,
            "before_value": before_data,
            "after_value": after_data,
            "campus_id": target_campus_id or getattr(g, "campus_id", None),
            "ip_address": ip,
            "user_agent": user_agent,
        }).execute()
        return True
    except Exception as e:  # broad on purpose: an audit failure must never break the admin action
        logger.error("_audit: failed to log %s/%s/%s: %s", table, target_id, action, e)
        return False


# ---------------------------------------------------------------------------
# Users
# ---------------------------------------------------------------------------

@admin_bp.route("/users", methods=["GET"])
@require_role("admin")
def list_users():
    # ADM-13. `q` now matches name, email, phone and nickname.
    db = get_user_client()
    try:
        limit, offset = page_args()
        requested_campus = as_campus_id(request.args.get("campus_id"))
    except ValueError:
        return jsonify({"error": MSG.INVALID_INPUT}), 400
    role_filter = request.args.get("role")
    if role_filter:
        ok, message = validate_choice(role_filter, sorted(VALID_ROLES), "role")
        if not ok:
            return jsonify({"error": message}), 400
    campus_id = resolve_scoped_campus_id(requested_campus)
    try:
        q = db.table("profiles").select(_USER_LIST_FIELDS)
        if campus_id:
            q = q.eq("campus_id", campus_id)
        if role_filter:
            q = q.eq("role", role_filter)
        term = _search_term(request.args.get("q"))
        if term:
            q = q.or_(f"full_name.ilike.*{term}*,email.ilike.*{term}*,phone.ilike.*{term}*,nickname.ilike.*{term}*")
        users = q.order("created_at", ascending=False).limit(limit).offset(offset).execute() or []
    except (SupabaseError, requests.RequestException) as e:
        return db_error_response(e, "list_users")
    return jsonify(users), 200


@admin_bp.route("/users/<user_id>", methods=["GET"])
@require_role("admin")
def get_user(user_id):
    # ADM-14. Unknown id and other-campus id both return 404 (no existence leak).
    if not validate_uuid(user_id):
        return jsonify({"error": MSG.AUTH_USER_NOT_FOUND}), 404
    db = get_user_client()
    try:
        profile = db.table("profiles").select("*").eq("id", user_id).single().execute()
        if not profile:
            return jsonify({"error": MSG.AUTH_USER_NOT_FOUND}), 404
        assert_can_modify(profile.get("campus_id"))  # RLS already blocks this; app-level backup (NULL-campus = super_admin accounts, off-limits to campus admins)
        wallet = db.table("wallets").select("balance").eq("user_id", user_id).single().execute()
        recent_orders = (
            db.table("orders").select("id,status,total_amount,created_at")
            .eq("user_id", user_id).order("created_at", ascending=False).limit(10).execute()
        ) or []
    except (SupabaseError, requests.RequestException) as e:
        return db_error_response(e, "get_user")
    profile = {k: v for k, v in profile.items() if k in _USER_DETAIL_FIELDS}
    from app.services.hp_service import get_hp_balance, get_user_tier
    balance = get_hp_balance(user_id)
    tier = get_user_tier(user_id)
    return jsonify({
        "profile": profile,
        "hp_balance": balance,
        "tier": tier,
        "wallet_balance": float(wallet.get("balance", 0)) if wallet else 0,
        "recent_orders": recent_orders,
        "degraded": bool(balance.get("degraded")),
    }), 200


@admin_bp.route("/orders", methods=["GET"])
@require_role("admin")
def list_all_orders():
    # ADM-15. Dates are WAT calendar days; the filter converts them to UTC instants.
    db = get_user_client()
    try:
        limit, offset = page_args()
        requested_campus = as_campus_id(request.args.get("campus_id"))
        from_date = as_date(request.args["from_date"]) if request.args.get("from_date") else None
        to_date = as_date(request.args["to_date"]) if request.args.get("to_date") else None
    except ValueError:
        return jsonify({"error": MSG.INVALID_INPUT}), 400
    status = request.args.get("status")
    if status:
        ok, message = validate_choice(status, ORDER_STATUSES, "status")
        if not ok:
            return jsonify({"error": message}), 400
    payment_method = request.args.get("payment_method")
    if payment_method:
        ok, message = validate_choice(payment_method, ("wallet", "card"), "payment_method")
        if not ok:
            return jsonify({"error": message}), 400
    user_id = request.args.get("user_id")
    if user_id and not validate_uuid(user_id):
        return jsonify({"error": MSG.INVALID_INPUT}), 400
    campus_id = resolve_scoped_campus_id(requested_campus)
    try:
        q = db.table("orders").select("*,order_items(name_snapshot,quantity,price_snapshot,line_total)")
        if campus_id:
            q = q.eq("campus_id", campus_id)
        if status:
            q = q.eq("status", status)
        if user_id:
            q = q.eq("user_id", user_id)
        if payment_method == "wallet":
            q = q.gt("wallet_amount_used", 0)
        elif payment_method == "card":
            q = q.gt("card_amount_used", 0)
        if from_date:
            q = q.gte("created_at", wat_day_bounds_utc(from_date)[0])
        if to_date:
            q = q.lt("created_at", wat_day_bounds_utc(to_date)[1])
        orders = q.order("created_at", ascending=False).limit(limit).offset(offset).execute() or []
    except (SupabaseError, requests.RequestException) as e:
        return db_error_response(e, "list_all_orders")
    return jsonify({"orders": orders, "count": len(orders), "limit": limit, "offset": offset}), 200


@admin_bp.route("/users/<user_id>/orders", methods=["GET"])
@require_role("admin")
def user_order_history(user_id):
    # ADM-16. total_spent is now over ALL of the user's delivered orders, not just this page.
    if not validate_uuid(user_id):
        return jsonify({"error": MSG.AUTH_USER_NOT_FOUND}), 404
    try:
        limit, offset = page_args()
    except ValueError:
        return jsonify({"error": MSG.INVALID_INPUT}), 400
    status = request.args.get("status")
    if status:
        ok, message = validate_choice(status, ORDER_STATUSES, "status")
        if not ok:
            return jsonify({"error": message}), 400
    db = get_user_client()
    try:
        profile = db.table("profiles").select("id,full_name,campus_id").eq("id", user_id).single().execute()
        if not profile:
            return jsonify({"error": MSG.AUTH_USER_NOT_FOUND}), 404
        assert_can_modify(profile.get("campus_id"))  # RLS already blocks this; app-level backup (NULL-campus = super_admin accounts, off-limits to campus admins)
        q = (
            db.table("orders").select("*,order_items(name_snapshot,quantity,price_snapshot,line_total)")
            .eq("user_id", user_id)
        )
        if status:
            q = q.eq("status", status)
        orders = q.order("created_at", ascending=False).limit(limit).offset(offset).execute() or []
        delivered = (
            db.table("orders").select("total_amount").eq("user_id", user_id).eq("status", "delivered")
            .limit(_TOTAL_SPENT_CAP).execute()
        ) or []
    except (SupabaseError, requests.RequestException) as e:
        return db_error_response(e, "user_order_history")
    total_spent = sum(float(o.get("total_amount") or 0) for o in delivered)
    return jsonify({
        "user": {"id": profile["id"], "full_name": profile.get("full_name")},
        "orders": orders,
        "count": len(orders),
        "total_spent": round(total_spent, 2),
        "total_spent_truncated": len(delivered) >= _TOTAL_SPENT_CAP,
        "limit": limit,
        "offset": offset,
    }), 200


@admin_bp.route("/users/<user_id>/role", methods=["PATCH"])
@require_role("admin")
def change_user_role(user_id):
    # ADM-17
    if not validate_uuid(user_id):
        return jsonify({"error": MSG.AUTH_USER_NOT_FOUND}), 404
    if user_id == g.user_id:
        return jsonify({"error": MSG.ADMIN_CANNOT_CHANGE_OWN_ROLE}), 403
    data = get_json_object()
    if data is None:
        return jsonify({"error": MSG.JSON_OBJECT_REQUIRED}), 400
    invalid_role = jsonify({"error": MSG.ADMIN_INVALID_ROLE.format(roles=", ".join(sorted(VALID_ROLES)))}), 400
    try:
        new_role = as_text(data.get("role"), 30)
    except ValueError:
        return invalid_role
    if new_role not in VALID_ROLES:
        return invalid_role
    db = get_user_client()
    try:
        profile = db.table("profiles").select("id,full_name,role,campus_id").eq("id", user_id).single().execute()
    except (SupabaseError, requests.RequestException) as e:
        return db_error_response(e, "change_user_role.lookup")
    if not profile:
        return jsonify({"error": MSG.AUTH_USER_NOT_FOUND}), 404
    assert_can_modify(profile.get("campus_id"))
    caller_role = getattr(g, "user_role", None)
    if caller_role != "super_admin" and (
        profile.get("role") not in _CAMPUS_ADMIN_MANAGED_ROLES or new_role not in _CAMPUS_ADMIN_MANAGED_ROLES
    ):
        # Campus admins manage student, kitchen and rider accounts only; admin roles are super_admin's.
        return jsonify({"error": MSG.ADMIN_ROLE_CHANGE_SUPER_ONLY}), 403
    if profile.get("role") == new_role:
        return jsonify({"user_id": user_id, "role": new_role, "full_name": profile.get("full_name"), "unchanged": True}), 200

    patch = {"role": new_role}
    if new_role == "super_admin":
        patch["campus_id"] = None  # super_admin is global: no campus
    elif profile.get("role") == "super_admin" or not profile.get("campus_id"):
        # Every non-super_admin role needs a campus; leaving super_admin must say which one.
        try:
            target_campus = as_campus_id(data.get("campus_id"))
        except ValueError:
            return jsonify({"error": MSG.INVALID_CAMPUS_ID}), 400
        if not target_campus:
            return jsonify({"error": MSG.CAMPUS_ID_REQUIRED}), 400
        try:
            chosen = db.table("campuses").select("id").eq("id", target_campus).eq("is_active", True).single().execute()
        except (SupabaseError, requests.RequestException) as e:
            return db_error_response(e, "change_user_role.campus")
        if not chosen:
            return jsonify({"error": MSG.CAMPUS_NOT_AVAILABLE}), 400
        patch["campus_id"] = target_campus
    try:
        result = db.table("profiles").eq("id", user_id).update(patch)
    except (SupabaseError, requests.RequestException) as e:
        return db_error_response(e, "change_user_role")
    if not result:
        return jsonify({"error": MSG.UPDATE_NOT_PERMITTED}), 403
    audit_ok = _audit(
        g.user_id, "profiles", user_id, "change_role",
        {"role": new_role, "campus_id": patch.get("campus_id", profile.get("campus_id"))},
        before_data={"role": profile.get("role"), "campus_id": profile.get("campus_id")},
        target_campus_id=profile.get("campus_id"),
    )
    body = {"user_id": user_id, "role": new_role, "full_name": profile.get("full_name")}
    if not audit_ok:
        body["audit_logged"] = False
    return jsonify(body), 200


@admin_bp.route("/users/<user_id>/hp", methods=["GET"])
@require_role("admin")
def user_hp_history(user_id):
    # ADM-18
    if not validate_uuid(user_id):
        return jsonify({"error": MSG.AUTH_USER_NOT_FOUND}), 404
    try:
        limit, offset = page_args()
    except ValueError:
        return jsonify({"error": MSG.INVALID_INPUT}), 400
    db = get_user_client()
    try:
        profile = db.table("profiles").select("id,full_name,campus_id").eq("id", user_id).single().execute()
        if not profile:
            return jsonify({"error": MSG.AUTH_USER_NOT_FOUND}), 404
        assert_can_modify(profile.get("campus_id"))  # RLS already blocks this; app-level backup (NULL-campus = super_admin accounts, off-limits to campus admins)
        txns = (
            db.table("hp_transactions").select("*").eq("user_id", user_id)
            .order("created_at", ascending=False).limit(limit).offset(offset).execute()
        ) or []
    except (SupabaseError, requests.RequestException) as e:
        return db_error_response(e, "user_hp_history")
    from app.services.hp_service import get_hp_balance
    balance = get_hp_balance(user_id)
    return jsonify({
        "user": {"id": user_id, "full_name": profile.get("full_name")},
        "hp_balance": balance,
        "transactions": txns,
        "count": len(txns),
        "degraded": bool(balance.get("degraded")),
    }), 200


@admin_bp.route("/users/<user_id>/wallet", methods=["GET"])
@require_role("admin")
def user_wallet_history(user_id):
    # ADM-19
    if not validate_uuid(user_id):
        return jsonify({"error": MSG.AUTH_USER_NOT_FOUND}), 404
    try:
        limit, offset = page_args()
    except ValueError:
        return jsonify({"error": MSG.INVALID_INPUT}), 400
    db = get_user_client()
    try:
        profile = db.table("profiles").select("id,full_name,campus_id").eq("id", user_id).single().execute()
        if not profile:
            return jsonify({"error": MSG.AUTH_USER_NOT_FOUND}), 404
        assert_can_modify(profile.get("campus_id"))  # RLS already blocks this; app-level backup (NULL-campus = super_admin accounts, off-limits to campus admins)
        wallet = db.table("wallets").select("balance,currency").eq("user_id", user_id).single().execute()
        from app.services.wallet_service import get_wallet_transactions
        txns = get_wallet_transactions(user_id, limit=limit, offset=offset) or []
    except (SupabaseError, requests.RequestException) as e:
        return db_error_response(e, "user_wallet_history")
    return jsonify({
        "user": {"id": user_id, "full_name": profile.get("full_name")},
        "wallet_balance": float(wallet.get("balance", 0)) if wallet else 0,
        "currency": wallet.get("currency", "NGN") if wallet else "NGN",
        "transactions": txns,
        "count": len(txns),
    }), 200


@admin_bp.route("/users/<user_id>/deactivate", methods=["POST"])
@require_role("admin")
def deactivate_user(user_id):
    # ADM-20. Optional body: {"reason": "..."}. An admin may deactivate a user who still has open orders
    # (the orders carry on); the response says how many there are.
    if not validate_uuid(user_id):
        return jsonify({"error": MSG.AUTH_USER_NOT_FOUND}), 404
    if user_id == g.user_id:
        return jsonify({"error": MSG.ADMIN_CANNOT_DEACTIVATE_SELF}), 400
    data = get_json_object() or {}
    reason = None
    if data.get("reason") is not None:
        try:
            reason = as_text(data["reason"], 500)
        except ValueError:
            return jsonify({"error": MSG.INVALID_INPUT}), 400
    db = get_user_client()
    try:
        target = db.table("profiles").select("id,role,is_active,full_name,campus_id").eq("id", user_id).single().execute()
    except (SupabaseError, requests.RequestException) as e:
        return db_error_response(e, "deactivate_user.lookup")
    if not target:
        return jsonify({"error": MSG.AUTH_USER_NOT_FOUND}), 404
    assert_can_modify(target.get("campus_id"))
    if getattr(g, "user_role", None) != "super_admin" and target.get("role") not in _CAMPUS_ADMIN_MANAGED_ROLES:
        return jsonify({"error": MSG.ADMIN_ACCOUNT_CHANGE_SUPER_ONLY}), 403
    if not target.get("is_active"):
        return jsonify({"message": MSG.ADMIN_USER_ALREADY_DEACTIVATED, "user_id": user_id}), 200
    open_orders = 0
    try:
        open_rows = (
            db.table("orders").select("id").eq("user_id", user_id)
            .not_.in_("status", list(_TERMINAL_ORDER_STATUSES)).limit(50).execute()
        ) or []
        open_orders = len(open_rows)  # informational, capped at 50
    except (SupabaseError, requests.RequestException) as e:
        logger.error("deactivate_user: open-order count failed for %s: %s", user_id, e)
    try:
        result = db.table("profiles").eq("id", user_id).update({
            "is_active": False,
            "deactivated_at": datetime.now(timezone.utc).isoformat(),
            "deactivated_by": g.user_id,
            "deactivation_reason": reason,
        })
    except (SupabaseError, requests.RequestException) as e:
        return db_error_response(e, "deactivate_user")
    if not result:
        return jsonify({"error": MSG.UPDATE_NOT_PERMITTED}), 403

    # The account is now deactivated. Tell the user first (push needs the device tokens), then cut off access.
    try:
        send_notification(user_id, "account_deactivated", template_data={}, campus_id=target.get("campus_id"))
    except Exception as e:  # broad on purpose: never undo the deactivation because a message failed
        logger.error("deactivate_user: notification failed for %s: %s", user_id, e)
    sessions_revoked = False
    try:
        resp = _revoke_supabase_sessions(user_id)
        sessions_revoked = bool(resp is not None and resp.status_code < 300)
        get_db().table("device_tokens").eq("user_id", user_id).delete()
    except Exception as e:  # broad on purpose: report it, the deactivation itself stays in place
        logger.error("deactivate_user: session/device cleanup failed for %s: %s", user_id, e)
    if not sessions_revoked:
        logger.error("deactivate_user: sessions NOT revoked for %s", user_id)
    audit_ok = _audit(
        g.user_id, "profiles", user_id, "deactivate_account",
        {"is_active": False, "reason": reason}, before_data={"is_active": True},
        target_campus_id=target.get("campus_id"),
    )
    body = {
        "message": MSG.ADMIN_USER_DEACTIVATED, "user_id": user_id,
        "sessions_revoked": sessions_revoked, "open_orders": open_orders,
    }
    if not audit_ok:
        body["audit_logged"] = False
    return jsonify(body), 200


@admin_bp.route("/users/<user_id>/activate", methods=["POST"])
@require_role("admin")
def activate_user(user_id):
    # ADM-21
    if not validate_uuid(user_id):
        return jsonify({"error": MSG.AUTH_USER_NOT_FOUND}), 404
    db = get_user_client()
    try:
        profile = db.table("profiles").select("id,is_active,full_name,campus_id,role,email").eq("id", user_id).single().execute()
    except (SupabaseError, requests.RequestException) as e:
        return db_error_response(e, "activate_user.lookup")
    if not profile:
        return jsonify({"error": MSG.AUTH_USER_NOT_FOUND}), 404
    assert_can_modify(profile.get("campus_id"))
    if getattr(g, "user_role", None) != "super_admin" and profile.get("role") not in _CAMPUS_ADMIN_MANAGED_ROLES:
        return jsonify({"error": MSG.ADMIN_ACCOUNT_CHANGE_SUPER_ONLY}), 403
    if str(profile.get("email") or "").endswith(_ANONYMIZED_EMAIL_SUFFIX):
        # The user deleted their own account: the data is gone, so it cannot be brought back.
        return jsonify({"error": MSG.ADMIN_ACCOUNT_ANONYMIZED}), 409
    if profile.get("is_active"):
        return jsonify({"message": MSG.ADMIN_USER_ALREADY_ACTIVE, "user_id": user_id}), 200
    try:
        result = db.table("profiles").eq("id", user_id).update({
            "is_active": True, "deactivated_at": None, "deactivated_by": None, "deactivation_reason": None,
        })
    except (SupabaseError, requests.RequestException) as e:
        return db_error_response(e, "activate_user")
    if not result:
        return jsonify({"error": MSG.UPDATE_NOT_PERMITTED}), 403
    try:
        send_notification(user_id, "account_reactivated", template_data={}, campus_id=profile.get("campus_id"))
    except Exception as e:  # broad on purpose: never undo the reactivation because a message failed
        logger.error("activate_user: notification failed for %s: %s", user_id, e)
    audit_ok = _audit(
        g.user_id, "profiles", user_id, "activate_account",
        {"is_active": True}, before_data={"is_active": False},
        target_campus_id=profile.get("campus_id"),
    )
    body = {"message": MSG.ADMIN_USER_REACTIVATED, "user_id": user_id}
    if not audit_ok:
        body["audit_logged"] = False
    return jsonify(body), 200

# --- END OF SECTION 1 (users) ---


# ---------------------------------------------------------------------------
# Delivery windows and ordering windows
# ---------------------------------------------------------------------------

_DELIVERY_CLOSABLE = ("open", "full")


class _WindowInputError(ValueError):
    """A validation problem that carries its own user-facing message."""


def _clean_window_fields(data, delivery):
    """Validate the fields the two window tables share. Returns clean values for the keys that were sent.
    Raises ValueError(<message>) on the first problem."""
    out = {}
    if "label" in data:
        try:
            out["label"] = as_text(data["label"], 100)
        except ValueError:
            raise _WindowInputError(MSG.WINDOW_LABEL_INVALID)
    if data.get("weekday") is not None:
        try:
            out["weekday"] = as_int(data["weekday"], 0, 6)
        except ValueError:
            raise _WindowInputError(MSG.WINDOW_WEEKDAY_INVALID)
    if data.get("date") is not None:
        try:
            out["date"] = as_date(data["date"]).isoformat()
        except ValueError:
            raise _WindowInputError(MSG.WINDOW_DATE_INVALID)
    for key in ("opens_at", "closes_at"):
        if data.get(key) is not None:
            try:
                out[key] = as_time(data[key]).isoformat()
            except ValueError:
                raise _WindowInputError(MSG.WINDOW_TIME_INVALID)
    if data.get("capacity") is not None:
        try:
            out["capacity"] = as_int(data["capacity"], 1 if delivery else 0)
        except ValueError:
            raise _WindowInputError(MSG.WINDOW_CAPACITY_INVALID)
    for key in ("is_active", "is_closed"):
        if data.get(key) is not None:
            if not isinstance(data[key], bool):
                raise _WindowInputError(MSG.WINDOW_FLAG_INVALID.format(field=key))
            out[key] = data[key]
    if "reason" in data:
        out["reason"] = str(data["reason"] or "").strip()[:500] or None
    return out


def _window_campus(data):
    """Campus a new window belongs to. Campus admin: their own (403 if they name another).
    super_admin: must name one. Raises ValueError for a bad campus id."""
    requested = as_campus_id(data.get("campus_id"))
    assert_owns_campus(requested)
    if getattr(g, "user_role", None) == "super_admin":
        return requested
    return getattr(g, "campus_id", None)


@admin_bp.route("/delivery-windows", methods=["GET"])
@require_role("admin", "kitchen")
def list_windows():
    """
    List delivery windows (admin/kitchen). Scoped by campus for kitchen users.
    ---
    tags: [Admin]
    responses:
      200:
        description: Delivery windows
    """
    # ADM-22. order_count now ignores cancelled and refunded orders.
    db = get_user_client()
    try:
        requested = as_campus_id(request.args.get("campus_id"))
    except ValueError:
        return jsonify({"error": MSG.INVALID_CAMPUS_ID}), 400
    campus_id = resolve_scoped_campus_id(requested)
    try:
        q = db.table("delivery_windows").select("*")
        if campus_id:
            q = q.eq("campus_id", campus_id)
        windows = q.order("starts_at", ascending=False).limit(50).execute() or []
        for w in windows:
            oq = (
                db.table("orders").select("id", count="exact")
                .eq("delivery_window_id", w["id"]).not_.in_("status", ["cancelled", "refunded"]).limit(1)
            )
            if campus_id:
                oq = oq.eq("campus_id", campus_id)
            w["order_count"] = (oq.execute() or {}).get("count") or 0
    except (SupabaseError, requests.RequestException) as e:
        return db_error_response(e, "list_windows")
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
    # ADM-23. Either starts_at + ends_at (one-off), or opens_at + closes_at with exactly one of weekday / date.
    data = get_json_object()
    if data is None:
        return jsonify({"error": MSG.JSON_OBJECT_REQUIRED}), 400
    one_off = "starts_at" in data or "ends_at" in data
    times = ("starts_at", "ends_at") if one_off else ("opens_at", "closes_at")
    for f in ("label",) + times:
        if not data.get(f):
            return jsonify({"error": MSG.ADMIN_FIELD_REQUIRED.format(field=f)}), 400
    try:
        fields = _clean_window_fields(data, delivery=True)
        zone_id = as_uuid(data.get("zone_id"))
        if one_off:
            fields["starts_at"] = as_instant(data["starts_at"])
            fields["ends_at"] = as_instant(data["ends_at"])
            ok, message = validate_datetime_order(fields["starts_at"], fields["ends_at"])
            if not ok:
                raise _WindowInputError(message)
        else:
            if (fields.get("weekday") is None) == (fields.get("date") is None):
                raise _WindowInputError(MSG.WINDOW_DAY_REQUIRED)
            if fields["opens_at"] >= fields["closes_at"]:
                raise _WindowInputError(MSG.WINDOW_TIMES_ORDER)
        campus_id = _window_campus(data)
    except _WindowInputError as e:
        return jsonify({"error": str(e)}), 400
    except ValueError:
        return jsonify({"error": MSG.INVALID_INPUT}), 400
    if not campus_id:
        return jsonify({"error": MSG.CAMPUS_ID_REQUIRED}), 400
    payload = dict(fields, campus_id=campus_id, status="open", created_by=g.user_id)
    if zone_id:
        payload["zone_id"] = zone_id
    db = get_user_client()
    try:
        result = db.table("delivery_windows").insert(payload)
    except (SupabaseError, requests.RequestException) as e:
        return db_error_response(e, "create_window", MSG.WINDOW_EXISTS)
    created = result[0] if isinstance(result, list) and result else result
    _audit(g.user_id, "delivery_windows", created.get("id"), "create_window", after_data=payload, target_campus_id=campus_id)
    return jsonify(created), 201


def _delivery_window_payload(data, current):
    """Validate an edit to a delivery window. `current` is the stored row.
    One-off (starts_at/ends_at) and recurring-shaped (weekday/date + opens_at/closes_at)
    are mutually exclusive — sending fields from one clears the other, mirroring create_window."""
    fields = _clean_window_fields(data, delivery=True)
    if "starts_at" in data:
        try:
            fields["starts_at"] = as_instant(data["starts_at"])
        except ValueError:
            raise _WindowInputError(MSG.WINDOW_TIME_INVALID)
    if "ends_at" in data:
        try:
            fields["ends_at"] = as_instant(data["ends_at"])
        except ValueError:
            raise _WindowInputError(MSG.WINDOW_TIME_INVALID)
    if "zone_id" in data:
        zone_id = as_uuid(data["zone_id"])
        fields["zone_id"] = zone_id  # None clears it

    going_one_off = "starts_at" in fields or "ends_at" in fields
    going_recurring = any(k in fields for k in ("weekday", "date", "opens_at", "closes_at"))
    if going_one_off and going_recurring:
        raise _WindowInputError(MSG.WINDOW_MODE_CONFLICT)
    if going_one_off:
        fields["weekday"] = fields["date"] = fields["opens_at"] = fields["closes_at"] = None
    elif going_recurring:
        fields["starts_at"] = fields["ends_at"] = None

    merged = dict(current, **fields)
    is_one_off = merged.get("starts_at") is not None or merged.get("ends_at") is not None
    if is_one_off:
        if not merged.get("starts_at") or not merged.get("ends_at"):
            raise _WindowInputError(MSG.WINDOW_TIME_INVALID)
        ok, message = validate_datetime_order(merged["starts_at"], merged["ends_at"])
        if not ok:
            raise _WindowInputError(message)
    else:
        if (merged.get("weekday") is None) == (merged.get("date") is None):
            raise _WindowInputError(MSG.WINDOW_DAY_REQUIRED)
        if not merged.get("opens_at") or not merged.get("closes_at") or merged["opens_at"] >= merged["closes_at"]:
            raise _WindowInputError(MSG.WINDOW_TIMES_ORDER)
    return fields


@admin_bp.route("/delivery-windows/<window_id>", methods=["PATCH"])
@require_role("admin")
def update_window(window_id):
    """
    Edit a delivery window (admin only). Cannot change campus_id or status — use
    /close and /reopen for status. Sending starts_at/ends_at switches it to one-off and
    clears weekday/date/opens_at/closes_at; sending any of those switches it the other way.
    ---
    tags: [Admin]
    parameters:
      - in: path
        name: window_id
        type: string
        required: true
      - in: body
        name: body
        schema:
          properties:
            label: {type: string}
            starts_at: {type: string, format: date-time}
            ends_at: {type: string, format: date-time}
            weekday: {type: integer}
            date: {type: string, format: date}
            opens_at: {type: string}
            closes_at: {type: string}
            capacity: {type: integer}
            zone_id: {type: string}
    responses:
      200:
        description: Window updated
      404:
        description: Window not found
    """
    if not validate_uuid(window_id):
        return jsonify({"error": MSG.ADMIN_WINDOW_NOT_FOUND}), 404
    data = get_json_object()
    if data is None:
        return jsonify({"error": MSG.JSON_OBJECT_REQUIRED}), 400
    db = get_user_client()
    try:
        existing = db.table("delivery_windows").select("*").eq("id", window_id).single().execute()
    except (SupabaseError, requests.RequestException) as e:
        return db_error_response(e, "update_window.lookup")
    if not existing:
        return jsonify({"error": MSG.ADMIN_WINDOW_NOT_FOUND}), 404
    assert_can_modify(existing.get("campus_id"))
    allowed = {"label", "starts_at", "ends_at", "weekday", "date", "opens_at", "closes_at",
               "capacity", "zone_id", "is_active", "reason"}
    sent = {k: v for k, v in data.items() if k in allowed}
    if not sent:
        return jsonify({"error": MSG.NO_VALID_FIELDS}), 400
    try:
        safe = _delivery_window_payload(sent, existing)
    except _WindowInputError as e:
        return jsonify({"error": str(e)}), 400
    except ValueError:
        return jsonify({"error": MSG.INVALID_INPUT}), 400
    try:
        result = db.table("delivery_windows").eq("id", window_id).update(safe)
    except (SupabaseError, requests.RequestException) as e:
        return db_error_response(e, "update_window", MSG.WINDOW_EXISTS)
    if not result:
        return jsonify({"error": MSG.UPDATE_NOT_PERMITTED}), 403
    updated = result[0] if isinstance(result, list) else result
    audit_ok = _audit(g.user_id, "delivery_windows", window_id, "update", after_data=safe,
                      before_data={k: existing.get(k) for k in safe if k in existing},
                      target_campus_id=existing.get("campus_id"))
    body = dict(updated)
    if not audit_ok:
        body["audit_logged"] = False
    return jsonify(body), 200


def _set_window_status(window_id, allowed_from, new_status, done_message, action, already_message=None):
    if not validate_uuid(window_id):
        return jsonify({"error": MSG.ADMIN_WINDOW_NOT_FOUND}), 404
    db = get_user_client()
    window, err = fetch_or_403(db, "delivery_windows", window_id,
                               select="id,status,ends_at,campus_id", not_found_msg=MSG.ADMIN_WINDOW_NOT_FOUND)
    if err:
        return err
    assert_can_modify(window.get("campus_id"))  # RLS already scopes this; app-level backup
    if window.get("status") == new_status:
        return jsonify({"message": already_message or done_message, "status": new_status}), 200
    if window.get("status") not in allowed_from:
        return jsonify({"error": MSG.WINDOW_CANNOT_CHANGE.format(current=window.get("status"))}), 409
    if new_status == "open" and window.get("ends_at"):
        try:
            ended = datetime.fromisoformat(str(window["ends_at"]).replace("Z", "+00:00")) < datetime.now(timezone.utc)
        except ValueError:
            ended = False
        if ended:
            return jsonify({"error": MSG.WINDOW_ALREADY_ENDED}), 409
    res, err = update_or_403(db, "delivery_windows", window_id, {"status": new_status})
    if err:
        return err
    _audit(g.user_id, "delivery_windows", window_id, action,
           after_data={"status": new_status}, before_data={"status": window.get("status")},
           target_campus_id=window.get("campus_id"))
    return jsonify({"message": done_message, "window_id": window_id, "status": new_status}), 200


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
      404:
        description: Window not found
    """
    # ADM-24. Only an open or full window can be closed.
    return _set_window_status(window_id, _DELIVERY_CLOSABLE, "closed", MSG.ADMIN_WINDOW_CLOSED, "close_window")


@admin_bp.route("/delivery-windows/<window_id>/reopen", methods=["POST"])
@require_role("admin")
def reopen_window(window_id):
    # ADM-25. Only a closed window can be reopened, and not after it has ended.
    return _set_window_status(window_id, ("closed",), "open", MSG.ADMIN_WINDOW_REOPENED, "reopen_window",
                              already_message=MSG.ADMIN_WINDOW_ALREADY_OPEN)


@admin_bp.route("/ordering-windows", methods=["GET"])
@require_role("admin")
def list_ordering_windows():
    # ADM-26
    db = get_user_client()
    try:
        requested = as_campus_id(request.args.get("campus_id"))
    except ValueError:
        return jsonify({"error": MSG.INVALID_CAMPUS_ID}), 400
    campus_id = resolve_scoped_campus_id(requested)
    try:
        q = db.table("ordering_windows").select("*")
        if campus_id:
            q = q.eq("campus_id", campus_id)
        rows = q.order("date", ascending=True).order("weekday", ascending=True).limit(500).execute() or []
    except (SupabaseError, requests.RequestException) as e:
        return db_error_response(e, "list_ordering_windows")
    return jsonify(rows), 200


def _ordering_payload(data, current=None):
    """Clean and cross-check ordering-window fields. `current` is the stored row when updating.
    Sending a date clears the weekday and the other way round."""
    fields = _clean_window_fields(data, delivery=False)
    if "linked_delivery_window_id" in data:
        fields["linked_delivery_window_id"] = as_uuid(data["linked_delivery_window_id"])
    if fields.get("weekday") is not None and fields.get("date") is not None:
        raise _WindowInputError(MSG.WINDOW_DAY_REQUIRED)  # ambiguous: give one of them
    if fields.get("date") is not None:
        fields["weekday"] = None
    if fields.get("weekday") is not None:
        fields["date"] = None
    merged = dict(current or {}, **fields)
    if (merged.get("weekday") is None) == (merged.get("date") is None):
        raise _WindowInputError(MSG.WINDOW_DAY_REQUIRED)
    if merged.get("opens_at") and merged.get("closes_at") and str(merged["opens_at"])[:8] >= str(merged["closes_at"])[:8]:
        raise _WindowInputError(MSG.WINDOW_TIMES_ORDER)
    return fields


@admin_bp.route("/ordering-windows", methods=["POST"])
@require_role("admin")
def create_ordering_window():
    # ADM-27
    data = get_json_object()
    if data is None:
        return jsonify({"error": MSG.JSON_OBJECT_REQUIRED}), 400
    for f in ("opens_at", "closes_at"):
        if not data.get(f):
            return jsonify({"error": MSG.ADMIN_FIELD_REQUIRED.format(field=f)}), 400
    try:
        safe = _ordering_payload(data)
        campus_id = _window_campus(data)
    except _WindowInputError as e:
        return jsonify({"error": str(e)}), 400
    except ValueError:
        return jsonify({"error": MSG.INVALID_INPUT}), 400
    if not campus_id:
        return jsonify({"error": MSG.CAMPUS_ID_REQUIRED}), 400
    safe.pop("is_active", None)  # ordering_windows has no is_active column
    safe["campus_id"] = campus_id
    safe["created_by"] = g.user_id
    db = get_user_client()
    try:
        res = db.table("ordering_windows").insert(safe)
    except (SupabaseError, requests.RequestException) as e:
        return db_error_response(e, "create_ordering_window", MSG.WINDOW_EXISTS)
    created = res[0] if isinstance(res, list) and res else res
    _audit(g.user_id, "ordering_windows", created.get("id"), "create", after_data=safe, target_campus_id=campus_id)
    return jsonify(created), 201


def _move_up_deferred_orders(db, before, updated):
    """After a capacity increase, move waiting orders from this campus into the window, oldest request first.
    Never raises; returns how many orders were moved."""
    moved = 0
    try:
        old_cap = int(before.get("capacity") or 0)
        new_cap = int(updated.get("capacity") or 0)
        target_date = updated.get("date")
        if new_cap <= old_cap or not target_date:
            return 0
        candidates = (
            db.table("orders")
            .select("id,user_id,squad_item_count,is_squad_order,originally_requested_date")
            .eq("campus_id", updated["campus_id"]).eq("capacity_deferred", True).eq("status", "received")
            .lte("originally_requested_date", target_date)
            .order("originally_requested_date", ascending=True).execute()
        ) or []
        deliv_start = updated.get("opens_at") or "18:00:00"
        deliv_end = updated.get("closes_at") or "19:00:00"
        if updated.get("linked_delivery_window_id"):
            deliv = (
                db.table("delivery_windows").select("opens_at,closes_at")
                .eq("id", updated["linked_delivery_window_id"]).single().execute()
            )
            if deliv:
                deliv_start = deliv.get("opens_at") or deliv_start
                deliv_end = deliv.get("closes_at") or deliv_end
        for c in candidates:
            existing = (
                db.table("orders").select("id,is_squad_order,squad_item_count")
                .eq("ordering_window_id", updated["id"]).not_.in_("status", ["cancelled", "refunded"]).execute()
            ) or []
            room = new_cap - sum(_order_capacity_weight(o) for o in existing)
            if room < _order_capacity_weight(c):
                continue
            # Conditional update: an order another admin already moved (or that changed state) is skipped.
            result = (
                db.table("orders").eq("id", c["id"]).eq("capacity_deferred", True).eq("status", "received")
                .update({
                    "ordering_window_id": updated["id"],
                    "scheduled_for": wat_iso(target_date, str(deliv_start)),
                    "capacity_deferred": False,
                })
            )
            if not result:
                continue
            moved += 1
            try:
                send_notification(
                    c["user_id"], "order_moved_up",
                    template_data={
                        "originally_requested_date": c.get("originally_requested_date"),
                        "target_date": target_date,
                        "deliv_start": str(deliv_start)[:5],
                        "deliv_end": str(deliv_end)[:5],
                    },
                    reference_id=c["id"], reference_type="order",
                )
            except Exception as e:  # broad on purpose: the order is already moved; a failed message is logged
                logger.error("update_ordering_window: order_moved_up notification failed for %s: %s", c["id"], e)
    except Exception as e:  # broad on purpose: the window update already succeeded
        logger.error("update_ordering_window: moving deferred orders failed: %s", e)
    return moved


@admin_bp.route("/ordering-windows/<window_id>", methods=["PATCH"])
@require_role("admin")
def update_ordering_window(window_id):
    # ADM-28
    if not validate_uuid(window_id):
        return jsonify({"error": MSG.ORDERING_WINDOW_NOT_FOUND}), 404
    data = get_json_object()
    if data is None:
        return jsonify({"error": MSG.JSON_OBJECT_REQUIRED}), 400
    db = get_user_client()
    try:
        before = db.table("ordering_windows").select("*").eq("id", window_id).single().execute()
    except (SupabaseError, requests.RequestException) as e:
        return db_error_response(e, "update_ordering_window.lookup")
    if not before:
        return jsonify({"error": MSG.ORDERING_WINDOW_NOT_FOUND}), 404
    assert_can_modify(before.get("campus_id"))
    allowed = {"weekday", "date", "opens_at", "closes_at", "capacity", "label", "linked_delivery_window_id", "is_closed", "reason"}
    sent = {k: v for k, v in data.items() if k in allowed}
    if not sent:
        return jsonify({"error": MSG.NO_VALID_FIELDS}), 400
    try:
        safe = _ordering_payload(sent, current=before)
    except _WindowInputError as e:
        return jsonify({"error": str(e)}), 400
    except ValueError:
        return jsonify({"error": MSG.INVALID_INPUT}), 400
    safe["updated_at"] = datetime.now(timezone.utc).isoformat()
    try:
        res = db.table("ordering_windows").eq("id", window_id).update(safe)
    except (SupabaseError, requests.RequestException) as e:
        return db_error_response(e, "update_ordering_window", MSG.WINDOW_EXISTS)
    if not res:
        return jsonify({"error": MSG.UPDATE_NOT_PERMITTED}), 403
    updated = res[0] if isinstance(res, list) else res
    audit_ok = _audit(g.user_id, "ordering_windows", window_id, "update",
                      after_data=safe, before_data=before, target_campus_id=before.get("campus_id"))
    moved = _move_up_deferred_orders(db, before, updated)
    body = dict(updated, orders_moved_up=moved)
    if not audit_ok:
        body["audit_logged"] = False
    return jsonify(body), 200

# --- END OF SECTION 2 (delivery/ordering windows) ---


# ---------------------------------------------------------------------------
# Delivery batches
# ---------------------------------------------------------------------------

BATCH_STATUSES = ("open", "assigned", "in_progress", "completed", "cancelled")  # mirrors delivery_batches_status_check
_MAX_BATCH_ORDERS = 100
_ORDER_DONE = ("delivered", "cancelled", "refunded", "unclaimed")
_BATCH_FLOW = {"open": ("assigned",), "assigned": ("completed",), "in_progress": ("completed",)}
_BATCH_SELECT = "*,delivery_windows!window_id(label,starts_at,ends_at),profiles!rider_id(full_name,phone)"


def _check_rider(db, rider_id, campus_id):
    """None if rider_id is an active rider of that campus, else a ready-made error response."""
    try:
        rider = db.table("profiles").select("id,role,is_active,campus_id").eq("id", rider_id).single().execute()
    except (SupabaseError, requests.RequestException) as e:
        return db_error_response(e, "check_rider")
    if not rider:
        return jsonify({"error": MSG.RIDER_NOT_FOUND}), 404
    if not rider.get("is_active"):
        return jsonify({"error": MSG.RIDER_DEACTIVATED}), 400
    if rider.get("role") != "rider":
        return jsonify({"error": MSG.RIDER_ROLE_REQUIRED}), 400
    if campus_id and rider.get("campus_id") != campus_id:
        return jsonify({"error": MSG.RIDER_CAMPUS_MISMATCH}), 400
    return None


def _notify_rider_of_batch(rider_id, batch_id, campus_id):
    try:
        send_notification(rider_id, "rider_batch_assigned",
                          template_data={"batch_id": str(batch_id)[:8].upper()}, campus_id=campus_id)
    except Exception as e:  # broad on purpose: the batch is already saved; a failed message is logged
        logger.error("batch %s: rider notification failed: %s", batch_id, e)


@admin_bp.route("/delivery-batches", methods=["GET"])
@require_role("admin")
def list_batches():
    # ADM-29
    db = get_user_client()
    try:
        limit, offset = page_args()
        requested_campus = as_campus_id(request.args.get("campus_id"))
        window_id = as_uuid(request.args.get("window_id"))
    except ValueError:
        return jsonify({"error": MSG.INVALID_INPUT}), 400
    status = request.args.get("status")
    if status:
        ok, message = validate_choice(status, BATCH_STATUSES, "status")
        if not ok:
            return jsonify({"error": message}), 400
    campus_id = resolve_scoped_campus_id(requested_campus)
    try:
        q = db.table("delivery_batches").select(_BATCH_SELECT)
        if campus_id:
            q = q.eq("campus_id", campus_id)
        if window_id:
            q = q.eq("window_id", window_id)
        if status:
            q = q.eq("status", status)
        batches = q.order("created_at", ascending=False).limit(limit).offset(offset).execute() or []
        # One query for the whole page instead of one per batch (this was N+1: a page of
        # 50 batches cost 51 REST round-trips). Same response shape — `order_count` is
        # still set on every batch, and a batch with no orders still reports 0.
        batch_ids = [b["id"] for b in batches if b.get("id")]
        counts: dict = {}
        if batch_ids:
            rows = (db.table("orders").select("batch_id")
                    .in_("batch_id", batch_ids).limit(10000).execute()) or []
            for r in rows:
                bid = r.get("batch_id")
                counts[bid] = counts.get(bid, 0) + 1
        for b in batches:
            b["order_count"] = counts.get(b.get("id"), 0)
    except (SupabaseError, requests.RequestException) as e:
        return db_error_response(e, "list_batches")
    return jsonify({"batches": batches, "count": len(batches), "limit": limit, "offset": offset}), 200


@admin_bp.route("/delivery-batches/<batch_id>", methods=["GET"])
@require_role("admin")
def get_batch(batch_id):
    # ADM-30
    if not validate_uuid(batch_id):
        return jsonify({"error": MSG.ADMIN_BATCH_NOT_FOUND}), 404
    db = get_user_client()
    try:
        batch = db.table("delivery_batches").select(_BATCH_SELECT).eq("id", batch_id).single().execute()
        if not batch:
            return jsonify({"error": MSG.ADMIN_BATCH_NOT_FOUND}), 404
        assert_can_modify(batch.get("campus_id"))  # RLS already scopes this; app-level backup
        orders = db.table("orders").select(
            "id,status,delivery_address_snapshot,total_amount,created_at,"
            "delivery_location_lat,delivery_location_lon,"
            "order_items(name_snapshot,quantity)"
        ).eq("batch_id", batch_id).execute() or []
        gate = None
        if batch.get("gate_id"):
            gate = db.table("gates").select("lat,lon").eq("id", batch["gate_id"]).single().execute()
    except (SupabaseError, requests.RequestException) as e:
        return db_error_response(e, "get_batch")
    if gate and gate.get("lat") is not None and gate.get("lon") is not None and orders:
        from app.routes.delivery import haversine_km
        with_coords = [o for o in orders if o.get("delivery_location_lat") is not None and o.get("delivery_location_lon") is not None]
        without_coords = [o for o in orders if o not in with_coords]
        sequenced = []
        cur_lat, cur_lon = gate["lat"], gate["lon"]
        remaining = with_coords[:]
        while remaining:
            nearest = min(remaining, key=lambda o: haversine_km(cur_lat, cur_lon, o["delivery_location_lat"], o["delivery_location_lon"]))
            sequenced.append(nearest)
            cur_lat, cur_lon = nearest["delivery_location_lat"], nearest["delivery_location_lon"]
            remaining.remove(nearest)
        orders = sequenced + without_coords
    else:
        orders = sorted(orders, key=lambda o: o.get("created_at") or "")
    batch["orders"] = orders
    return jsonify(batch), 200


@admin_bp.route("/delivery-batches", methods=["POST"])
@require_role("admin")
def create_batch():
    # ADM-31. Only orders that are "ready" can be batched (that is the only status the state machine lets become "assigned").
    data = get_json_object()
    if data is None:
        return jsonify({"error": MSG.JSON_OBJECT_REQUIRED}), 400
    try:
        window_id = as_uuid(data.get("window_id"))
        rider_id = as_uuid(data.get("rider_id"))
        zone = as_text(data["zone"], 100) if data.get("zone") else ""
        raw_ids = data.get("order_ids") or []
        if not isinstance(raw_ids, list) or len(raw_ids) > _MAX_BATCH_ORDERS:
            raise ValueError("order_ids")
        order_ids = list(dict.fromkeys(as_uuid(x) for x in raw_ids))
        if None in order_ids:
            raise ValueError("order_ids")
    except ValueError:
        return jsonify({"error": MSG.INVALID_INPUT}), 400
    if not window_id or not rider_id:
        return jsonify({"error": MSG.REQUIRED_FIELD_MISSING}), 400
    db = get_user_client()
    try:
        window = db.table("delivery_windows").select("id,campus_id").eq("id", window_id).single().execute()
    except (SupabaseError, requests.RequestException) as e:
        return db_error_response(e, "create_batch.window")
    if not window:
        return jsonify({"error": MSG.ADMIN_WINDOW_NOT_FOUND}), 404
    assert_can_modify(window.get("campus_id"))
    campus_id = window["campus_id"]
    error = _check_rider(db, rider_id, campus_id)
    if error:
        return error
    if order_ids:
        try:
            orders = db.table("orders").select("id,delivery_window_id,status,batch_id,campus_id").in_("id", order_ids).execute() or []
        except (SupabaseError, requests.RequestException) as e:
            return db_error_response(e, "create_batch.orders")
        found = {o["id"]: o for o in orders}
        missing = [i for i in order_ids if i not in found]
        if missing:
            return jsonify({"error": MSG.BATCH_ORDERS_NOT_FOUND, "orders": missing}), 404
        problems = []
        for o in orders:
            if o.get("delivery_window_id") and o["delivery_window_id"] != window_id:
                problems.append({"id": o["id"], "reason": "other_window"})
            elif o.get("campus_id") != campus_id:
                problems.append({"id": o["id"], "reason": "other_campus"})
            elif o.get("batch_id"):
                problems.append({"id": o["id"], "reason": "already_batched"})
            elif o.get("status") != "ready":
                problems.append({"id": o["id"], "reason": "not_ready", "status": o.get("status")})
        if problems:
            return jsonify({"error": MSG.BATCH_ORDERS_NOT_ELIGIBLE, "orders": problems}), 409
    try:
        created = db.table("delivery_batches").insert({
            "window_id": window_id, "rider_id": rider_id, "zone": zone, "status": "assigned", "campus_id": campus_id,
        })
    except (SupabaseError, requests.RequestException) as e:
        return db_error_response(e, "create_batch")
    batch_row = created[0] if isinstance(created, list) and created else created
    batch_id = batch_row["id"]

    assigned, failed = [], []
    if order_ids:
        try:
            # One conditional write: only orders that are still ready and unbatched are taken.
            taken = db.table("orders").in_("id", order_ids).eq("status", "ready").is_("batch_id", "null").update({"batch_id": batch_id})
        except (SupabaseError, requests.RequestException) as e:
            db.table("delivery_batches").eq("id", batch_id).update({"status": "cancelled"})
            return db_error_response(e, "create_batch.attach")
        taken_ids = [o["id"] for o in (taken or [])]
        if len(taken_ids) != len(order_ids):
            # Another admin changed one of the orders in the meantime: undo and report.
            if taken_ids:
                db.table("orders").in_("id", taken_ids).update({"batch_id": None})
            db.table("delivery_batches").eq("id", batch_id).update({"status": "cancelled"})
            return jsonify({"error": MSG.BATCH_ORDERS_CHANGED}), 409
        from app.services.order_service import update_order_status
        for oid in taken_ids:
            try:
                update_order_status(oid, "assigned", changed_by=g.user_id)
                assigned.append(oid)
            except Exception as e:  # broad on purpose: isolate one bad order from the rest
                logger.error("create_batch: assigning order %s failed: %s", oid, e)
                now_status = db.table("orders").select("status").eq("id", oid).single().execute() or {}
                if now_status.get("status") == "assigned":
                    assigned.append(oid)  # the change did go through; keep it in the batch
                else:
                    db.table("orders").eq("id", oid).update({"batch_id": None})
                    failed.append(oid)
    _notify_rider_of_batch(rider_id, batch_id, campus_id)
    audit_ok = _audit(g.user_id, "delivery_batches", batch_id, "create_batch",
                      after_data={"window_id": window_id, "rider_id": rider_id, "orders": assigned},
                      target_campus_id=campus_id)
    body = dict(batch_row, orders_assigned=len(assigned), orders_failed=failed)
    if not audit_ok:
        body["audit_logged"] = False
    return jsonify(body), 201


@admin_bp.route("/delivery-batches/<batch_id>", methods=["PATCH"])
@require_role("admin")
def update_batch(batch_id):
    # ADM-32. Cancelling goes through DELETE (it must release the orders). completed needs every order finished.
    if not validate_uuid(batch_id):
        return jsonify({"error": MSG.ADMIN_BATCH_NOT_FOUND}), 404
    data = get_json_object()
    if data is None:
        return jsonify({"error": MSG.JSON_OBJECT_REQUIRED}), 400
    db = get_user_client()
    try:
        existing = db.table("delivery_batches").select("id,status,rider_id,campus_id").eq("id", batch_id).single().execute()
    except (SupabaseError, requests.RequestException) as e:
        return db_error_response(e, "update_batch.lookup")
    if not existing:
        return jsonify({"error": MSG.ADMIN_BATCH_NOT_FOUND}), 404
    assert_can_modify(existing.get("campus_id"))
    sent = {k: v for k, v in data.items() if k in {"status", "rider_id", "zone", "notes"}}
    if not sent:
        return jsonify({"error": MSG.ADMIN_BATCH_NO_FIELDS}), 400
    safe = {}
    try:
        if "zone" in sent:
            safe["zone"] = as_text(sent["zone"], 100) if sent["zone"] else ""
        if "notes" in sent:
            safe["notes"] = as_text(sent["notes"], 500) if sent["notes"] else None
        new_rider = as_uuid(sent["rider_id"]) if "rider_id" in sent else None
        if "rider_id" in sent and not new_rider:
            raise ValueError("rider_id")
    except ValueError:
        return jsonify({"error": MSG.INVALID_INPUT}), 400
    current = existing.get("status")
    if "status" in sent:
        new_status = sent["status"]
        if new_status not in ("assigned", "completed", "cancelled"):
            return jsonify({"error": MSG.ADMIN_BATCH_INVALID_STATUS}), 400
        if new_status == "cancelled":
            return jsonify({"error": MSG.BATCH_USE_DELETE}), 409
        if new_status != current:
            if new_status not in _BATCH_FLOW.get(current, ()):
                return jsonify({"error": MSG.BATCH_STATUS_INVALID_TRANSITION.format(current=current, new=new_status)}), 409
            if new_status == "completed":
                try:
                    open_rows = (
                        db.table("orders").select("id").eq("batch_id", batch_id)
                        .not_.in_("status", list(_ORDER_DONE)).limit(1).execute()
                    )
                except (SupabaseError, requests.RequestException) as e:
                    return db_error_response(e, "update_batch.orders")
                if open_rows:
                    return jsonify({"error": MSG.BATCH_HAS_OPEN_ORDERS}), 409
                safe["completed_at"] = datetime.now(timezone.utc).isoformat()
            safe["status"] = new_status
    if new_rider and new_rider != existing.get("rider_id"):
        if current in ("completed", "cancelled"):
            return jsonify({"error": MSG.BATCH_ALREADY_FINISHED}), 409
        error = _check_rider(db, new_rider, existing.get("campus_id"))
        if error:
            return error
        safe["rider_id"] = new_rider
    if not safe:
        return jsonify(existing), 200
    try:
        result = db.table("delivery_batches").eq("id", batch_id).update(safe)
    except (SupabaseError, requests.RequestException) as e:
        return db_error_response(e, "update_batch")
    if not result:
        return jsonify({"error": MSG.UPDATE_NOT_PERMITTED}), 403
    if "rider_id" in safe:
        _notify_rider_of_batch(safe["rider_id"], batch_id, existing.get("campus_id"))
    audit_ok = _audit(g.user_id, "delivery_batches", batch_id, "update_batch", after_data=safe,
                      before_data={k: existing.get(k) for k in safe if k in existing},
                      target_campus_id=existing.get("campus_id"))
    body = dict(result[0] if isinstance(result, list) else result)
    if not audit_ok:
        body["audit_logged"] = False
    return jsonify(body), 200


def _unassign_order(db, order_id):
    """assigned -> ready and detach from the batch, logged. True if the order was released."""
    from app.services.order_service import _log_status_change
    res = db.table("orders").eq("id", order_id).eq("status", "assigned").update(
        {"status": "ready", "batch_id": None, "assigned_at": None}
    )
    if not res:
        return False
    _log_status_change(order_id, "assigned", "ready", g.user_id, "Delivery batch cancelled")
    return True


@admin_bp.route("/delivery-batches/<batch_id>", methods=["DELETE"])
@require_role("admin")
def cancel_batch(batch_id):
    # ADM-33. Orders still "assigned" go back to "ready". A batch with orders already out for delivery
    # (or finished) cannot be cancelled.
    if not validate_uuid(batch_id):
        return jsonify({"error": MSG.ADMIN_BATCH_NOT_FOUND}), 404
    db = get_user_client()
    try:
        existing = db.table("delivery_batches").select("id,status,campus_id").eq("id", batch_id).single().execute()
        if not existing:
            return jsonify({"error": MSG.ADMIN_BATCH_NOT_FOUND}), 404
        assert_can_modify(existing.get("campus_id"))
        if existing.get("status") == "cancelled":
            return jsonify({"message": MSG.ADMIN_BATCH_CANCELLED, "batch_id": batch_id, "orders_unassigned": 0}), 200
        if existing.get("status") == "completed":
            return jsonify({"error": MSG.BATCH_ALREADY_FINISHED}), 409
        orders = db.table("orders").select("id,status").eq("batch_id", batch_id).execute() or []
    except (SupabaseError, requests.RequestException) as e:
        return db_error_response(e, "cancel_batch")
    on_the_road = [o["id"] for o in orders if o.get("status") != "assigned"]
    if on_the_road:
        return jsonify({"error": MSG.BATCH_IN_PROGRESS, "orders": on_the_road}), 409
    released, failed = 0, []
    for o in orders:
        try:
            if _unassign_order(db, o["id"]):
                released += 1
            else:
                failed.append(o["id"])
        except (SupabaseError, requests.RequestException) as e:
            logger.error("cancel_batch: releasing order %s failed: %s", o["id"], e)
            failed.append(o["id"])
    if failed:
        return jsonify({"error": MSG.BATCH_RELEASE_FAILED, "orders": failed, "orders_unassigned": released}), 409
    try:
        db.table("delivery_batches").eq("id", batch_id).update({"status": "cancelled"})
    except (SupabaseError, requests.RequestException) as e:
        return db_error_response(e, "cancel_batch.status")
    audit_ok = _audit(g.user_id, "delivery_batches", batch_id, "cancel_batch",
                      after_data={"orders_unassigned": released}, before_data={"status": existing.get("status")},
                      target_campus_id=existing.get("campus_id"))
    body = {"message": MSG.ADMIN_BATCH_CANCELLED, "batch_id": batch_id, "orders_unassigned": released}
    if not audit_ok:
        body["audit_logged"] = False
    return jsonify(body), 200


@admin_bp.route("/delivery-batches/<batch_id>/orders", methods=["GET"])
@require_role("admin")
def list_batch_orders(batch_id):
    # ADM-34
    if not validate_uuid(batch_id):
        return jsonify({"error": MSG.ADMIN_BATCH_NOT_FOUND}), 404
    db = get_user_client()
    try:
        batch = db.table("delivery_batches").select("id,campus_id").eq("id", batch_id).single().execute()
        if not batch:
            return jsonify({"error": MSG.ADMIN_BATCH_NOT_FOUND}), 404
        assert_can_modify(batch.get("campus_id"))  # RLS already scopes this; app-level backup
        orders = db.table("orders").select(
            "id,status,delivery_address_snapshot,total_amount,created_at,"
            "order_items(name_snapshot,quantity)"
        ).eq("batch_id", batch_id).execute() or []
    except (SupabaseError, requests.RequestException) as e:
        return db_error_response(e, "list_batch_orders")
    return jsonify({"batch_id": batch_id, "orders": orders, "count": len(orders)}), 200

# --- END OF SECTION 3 (delivery batches) ---


# ---------------------------------------------------------------------------
# Promo codes
# ---------------------------------------------------------------------------

PROMO_TYPES = ("percentage", "flat")
PROMO_SCOPES = ("cart", "item")
_PROMO_ALIASES = {"valid_from": "starts_at", "valid_until": "ends_at"}  # the names the API docs used
_PROMO_FIELDS = {
    "code", "description", "discount_type", "discount_value", "min_order_amount", "max_uses",
    "max_uses_per_user", "scope", "starts_at", "ends_at", "campus_id",
    "applicable_item_ids", "applicable_category_ids", "is_active",
}
_PROMO_CODE_RE = re.compile(r"^[A-Z0-9_-]{3,40}$")


class _PromoInputError(ValueError):
    """A validation problem that carries its own user-facing message."""


def _promo_body(data):
    """Rename the documented aliases and reject anything the table cannot store (no silent dropping)."""
    body = {_PROMO_ALIASES.get(k, k): v for k, v in data.items()}
    unknown = sorted(k for k in body if k not in _PROMO_FIELDS)
    if unknown:
        raise _PromoInputError(MSG.PROMO_UNKNOWN_FIELDS.format(fields=", ".join(unknown)))
    return body


def _clean_promo(body, current=None):
    """Validate promo fields. `current` is the stored row when updating. Returns clean values for the keys sent."""
    cur = current or {}
    out = {}
    if "description" in body:
        out["description"] = str(body["description"] or "").strip()[:500] or None
    for key, choices in (("discount_type", PROMO_TYPES), ("scope", PROMO_SCOPES)):
        if key in body:
            ok, message = validate_choice(body[key], choices, key)
            if not ok:
                raise _PromoInputError(message)
            out[key] = body[key]
    if "discount_value" in body:
        try:
            out["discount_value"] = as_number(body["discount_value"], 0.01)
        except ValueError:
            raise _PromoInputError(MSG.PROMO_VALUE_INVALID)
    dtype = out.get("discount_type", cur.get("discount_type"))
    value = out.get("discount_value", cur.get("discount_value"))
    if ("discount_type" in out or "discount_value" in out) and dtype == "percentage" and value is not None and float(value) > 100:
        raise _PromoInputError(MSG.PROMO_PERCENT_TOO_HIGH)
    if "min_order_amount" in body:
        try:
            out["min_order_amount"] = as_number(body["min_order_amount"] or 0, 0)
        except ValueError:
            raise _PromoInputError(MSG.PROMO_MIN_ORDER_INVALID)
    for key in ("max_uses", "max_uses_per_user"):
        if key in body:
            if body[key] is None:
                out[key] = None
                continue
            try:
                out[key] = as_int(body[key], 1, 10_000_000)
            except ValueError:
                raise _PromoInputError(MSG.ADMIN_FIELD_MUST_BE_POSITIVE.format(field=key))
    if out.get("max_uses") is not None and int(cur.get("used_count") or 0) > out["max_uses"]:
        raise _PromoInputError(MSG.PROMO_MAX_USES_BELOW_USED.format(used=int(cur.get("used_count") or 0)))
    for key in ("starts_at", "ends_at"):
        if key in body:
            try:
                out[key] = as_instant(body[key]) if body[key] else None
            except ValueError:
                raise _PromoInputError(MSG.PROMO_DATE_INVALID.format(field=key))
    starts, ends = out.get("starts_at", cur.get("starts_at")), out.get("ends_at", cur.get("ends_at"))
    if starts and ends:
        ok, message = validate_datetime_order(as_instant(starts), as_instant(ends))
        if not ok:
            raise _PromoInputError(message)
    for key in ("applicable_item_ids", "applicable_category_ids"):
        if key in body:
            ids = body[key] or []
            if not isinstance(ids, list) or len(ids) > 200:
                raise _PromoInputError(MSG.PROMO_IDS_INVALID.format(field=key))
            try:
                cleaned = []
                for i in ids:
                    parsed = as_uuid(i)
                    if not parsed:
                        raise ValueError("id")
                    cleaned.append(parsed)
            except ValueError:
                raise _PromoInputError(MSG.PROMO_IDS_INVALID.format(field=key))
            out[key] = cleaned
    if "is_active" in body:
        if not isinstance(body["is_active"], bool):
            raise _PromoInputError(MSG.WINDOW_FLAG_INVALID.format(field="is_active"))
        out["is_active"] = body["is_active"]
    return out


@admin_bp.route("/promo-codes", methods=["GET"])
@require_role("admin")
def list_promos():
    # ADM-35. A campus admin also sees the global (all-campus) codes that apply to their students.
    db = get_user_client()
    try:
        limit, offset = page_args(default_limit=100)
        requested = as_campus_id(request.args.get("campus_id"))
    except ValueError:
        return jsonify({"error": MSG.INVALID_INPUT}), 400
    campus_id = resolve_scoped_campus_id(requested)
    try:
        q = campus_or_global(db.table("promo_codes").select("*"), campus_id, none_means_all=True)
        codes = q.order("created_at", ascending=False).limit(limit).offset(offset).execute() or []
    except (SupabaseError, requests.RequestException) as e:
        return db_error_response(e, "list_promos")
    return jsonify(codes), 200


@admin_bp.route("/promo-codes", methods=["POST"])
@require_role("admin")
def create_promo():
    # ADM-36. Campus admin: a code for their own campus. super_admin: a campus code, or a global code (no campus_id).
    data = get_json_object()
    if data is None:
        return jsonify({"error": MSG.JSON_OBJECT_REQUIRED}), 400
    try:
        body = _promo_body(data)
        for f in ("code", "discount_type", "discount_value"):
            if body.get(f) is None:
                raise _PromoInputError(MSG.ADMIN_FIELD_REQUIRED.format(field=f))
        code = body["code"].strip().upper() if isinstance(body["code"], str) else ""
        if not _PROMO_CODE_RE.match(code):
            raise _PromoInputError(MSG.PROMO_CODE_INVALID)
        clean = _clean_promo(dict(body, is_active=True))
        campus_id = resolve_write_campus(as_campus_id(body.get("campus_id")))
    except _PromoInputError as e:
        return jsonify({"error": str(e)}), 400
    except ValueError:
        return jsonify({"error": MSG.INVALID_INPUT}), 400
    payload = dict(clean, code=code, used_count=0, created_by=g.user_id, campus_id=campus_id)
    db = get_user_client()
    try:
        result = db.table("promo_codes").insert(payload)
    except (SupabaseError, requests.RequestException) as e:
        return db_error_response(e, "create_promo", MSG.PROMO_CODE_EXISTS)
    created = result[0] if isinstance(result, list) and result else result
    audit_ok = _audit(g.user_id, "promo_codes", created.get("id"), "create_promo",
                      after_data={k: payload[k] for k in payload if k != "created_by"}, target_campus_id=campus_id)
    body_out = dict(created)
    if not audit_ok:
        body_out["audit_logged"] = False
    return jsonify(body_out), 201


@admin_bp.route("/promo-codes/<promo_id>", methods=["PATCH"])
@require_role("admin")
def update_promo(promo_id):
    # ADM-37. Global codes can only be changed by super_admin; a code's campus and text cannot be changed.
    if not validate_uuid(promo_id):
        return jsonify({"error": MSG.ADMIN_PROMO_NOT_FOUND}), 404
    data = get_json_object()
    if data is None:
        return jsonify({"error": MSG.JSON_OBJECT_REQUIRED}), 400
    db = get_user_client()
    try:
        existing = db.table("promo_codes").select("*").eq("id", promo_id).single().execute()
    except (SupabaseError, requests.RequestException) as e:
        return db_error_response(e, "update_promo.lookup")
    if not existing:
        return jsonify({"error": MSG.ADMIN_PROMO_NOT_FOUND}), 404
    assert_can_modify(existing.get("campus_id"))
    try:
        body = _promo_body(data)
        for f in ("code", "campus_id"):
            if f in body:
                raise _PromoInputError(MSG.PROMO_FIELD_LOCKED.format(field=f))
        if not body:
            return jsonify({"error": MSG.ERR_BAD_REQUEST}), 400
        safe = _clean_promo(body, current=existing)
    except _PromoInputError as e:
        return jsonify({"error": str(e)}), 400
    except ValueError:
        return jsonify({"error": MSG.INVALID_INPUT}), 400
    try:
        result = db.table("promo_codes").eq("id", promo_id).update(safe)
    except (SupabaseError, requests.RequestException) as e:
        return db_error_response(e, "update_promo")
    if not result:
        return jsonify({"error": MSG.UPDATE_NOT_PERMITTED}), 403
    updated = result[0] if isinstance(result, list) else result
    audit_ok = _audit(g.user_id, "promo_codes", promo_id, "update_promo", after_data=safe,
                      before_data={k: existing.get(k) for k in safe}, target_campus_id=existing.get("campus_id"))
    body_out = {"message": MSG.ADMIN_PROMO_UPDATED, "promo_code": updated}
    if not audit_ok:
        body_out["audit_logged"] = False
    return jsonify(body_out), 200


@admin_bp.route("/promo-codes/<promo_id>/uses", methods=["GET"])
@require_role("admin")
def promo_uses(promo_id):
    # ADM-38. used_count on the code is the running counter; total_uses is what the history table holds.
    if not validate_uuid(promo_id):
        return jsonify({"error": MSG.ADMIN_PROMO_NOT_FOUND}), 404
    db = get_user_client()
    try:
        limit, offset = page_args(default_limit=100, max_limit=500)
    except ValueError:
        return jsonify({"error": MSG.INVALID_INPUT}), 400
    try:
        promo = db.table("promo_codes").select("*").eq("id", promo_id).single().execute()
        if not promo:
            return jsonify({"error": MSG.ADMIN_PROMO_NOT_FOUND}), 404
        # A campus admin sees uses of their own campus's codes; a global code's uses span every campus's
        # users, so those are super_admin-only (promo_code_uses' RLS is campus-scoped the same way).
        assert_can_modify(promo.get("campus_id"))
        uses = (
            db.table("promo_code_uses")
            .select("id,user_id,order_id,discount_amount,created_at,profiles!user_id(full_name,email)")
            .eq("promo_code_id", promo_id)
            .order("created_at", ascending=False)
            .limit(limit).offset(offset)
            .execute()
        ) or []
        total = (
            db.table("promo_code_uses").select("discount_amount", count="exact").eq("promo_code_id", promo_id).limit(1).execute()
        ) or {}
        all_amounts = (
            db.table("promo_code_uses").select("discount_amount").eq("promo_code_id", promo_id).limit(10000).execute()
        ) or []
    except (SupabaseError, requests.RequestException) as e:
        return db_error_response(e, "promo_uses")
    total_discount_given = round(sum(float(u.get("discount_amount") or 0) for u in all_amounts), 2)
    return jsonify({
        "promo_code": promo,
        "total_uses": total.get("count") or 0,
        "total_discount_given": total_discount_given,
        "uses": uses,
        "limit": limit,
        "offset": offset,
    }), 200

# --- END OF SECTION 4 (promo codes) ---


# ---------------------------------------------------------------------------
# Abandoned carts, audit log, cron
# ---------------------------------------------------------------------------

_NUDGE_COOLDOWN_HOURS = 24

# job name -> (expected run interval in minutes, description). Keep in step with celery_app.conf.beat_schedule.
_CRON_INTERVAL_MINUTES = {
    "birthday-hp":                   (1440, "daily @ 08:00 WAT"),
    "monthly-birthday-report":       (44640, "1st of month @ 07:00 WAT"),
    "tier-grace-period-check":       (1440, "daily @ 03:00 WAT"),
    "recalculate-120day-hp":         (1440, "daily @ 02:00 WAT"),
    "hp-decay-check":                (1440, "daily @ 05:00 WAT"),
    "reset-monthly-leaderboard":     (44640, "1st of month @ 00:01 WAT"),
    "reset-weekly-leaderboard":      (10080, "every Monday @ 00:01 WAT"),
    "scan-abandoned-carts":          (30, "every 30 minutes"),
    "win-back-notifications":        (1440, "daily @ 10:00 WAT"),
    "check-order-locks":             (1440, "daily @ 09:00 WAT"),
    "reset-monthly-hp-tracker":      (44640, "1st of month @ 00:05 WAT"),
    "membership-anniversary-awards": (1440, "daily @ 06:00 WAT"),
    "send-scheduled-notifications":  (15, "every 15 minutes"),
    "send-scheduled-blasts":         (15, "every 15 minutes"),
    "process-scheduled-orders":      (5, "every 5 minutes"),
    "check-post-delivery-nudges":    (30, "every 30 minutes"),
    "grant-monthly-tier-perks":      (44640, "1st of month @ 00:05 WAT"),
    "send-newsletter-campaigns":     (5, "every 5 minutes"),
}


def _age_minutes(iso_value, now):
    try:
        return (now - datetime.fromisoformat(str(iso_value).replace("Z", "+00:00"))).total_seconds() / 60
    except ValueError:
        return float("inf")


@admin_bp.route("/abandoned-carts", methods=["GET"])
@require_role("admin")
def abandoned_carts():
    # ADM-39. Only carts that have not been recovered (A-15 marks a cart recovered when the user orders).
    db = get_user_client()
    try:
        limit, offset = page_args(default_limit=100)
        requested = as_campus_id(request.args.get("campus_id"))
    except ValueError:
        return jsonify({"error": MSG.INVALID_INPUT}), 400
    campus_id = resolve_scoped_campus_id(requested)
    try:
        q = db.table("abandoned_carts").select("*,profiles(full_name,email,phone)").eq("is_recovered", False)
        if campus_id:
            q = q.eq("campus_id", campus_id)
        carts = q.order("last_active_at", ascending=False).limit(limit).offset(offset).execute() or []
    except (SupabaseError, requests.RequestException) as e:
        return db_error_response(e, "abandoned_carts")
    return jsonify(carts), 200


@admin_bp.route("/abandoned-carts/<cart_id>/nudge", methods=["POST"])
@require_role("admin")
def nudge_cart(cart_id):
    # ADM-40. One nudge per user per 24 hours, counting the automatic ones; never for a recovered cart or an inactive user.
    if not validate_uuid(cart_id):
        return jsonify({"error": MSG.ADMIN_CART_NOT_FOUND}), 404
    db = get_user_client()
    try:
        cart = db.table("abandoned_carts").select("*").eq("id", cart_id).single().execute()
    except (SupabaseError, requests.RequestException) as e:
        return db_error_response(e, "nudge_cart.lookup")
    if not cart:
        return jsonify({"error": MSG.ADMIN_CART_NOT_FOUND}), 404
    assert_can_modify(cart.get("campus_id"))  # RLS already scopes this; app-level backup (this one also sends a notification)
    if cart.get("is_recovered"):
        return jsonify({"error": MSG.ADMIN_CART_ALREADY_RECOVERED}), 409
    user_id = cart.get("user_id")
    if not user_id:
        return jsonify({"error": MSG.ADMIN_CART_GUEST_NO_NUDGE}), 409
    svc = get_db()
    since = (datetime.now(timezone.utc) - timedelta(hours=_NUDGE_COOLDOWN_HOURS)).isoformat()
    try:
        owner = svc.table("profiles").select("is_active").eq("id", user_id).single().execute()
        recent = (
            svc.table("notifications").select("id").eq("user_id", user_id).eq("type", "abandoned_cart")
            .gte("created_at", since).limit(1).execute()
        )
    except (SupabaseError, requests.RequestException) as e:
        return db_error_response(e, "nudge_cart.checks")
    if not owner or not owner.get("is_active"):
        return jsonify({"error": MSG.ADMIN_CART_USER_INACTIVE}), 409
    if recent:
        return jsonify({"error": MSG.ADMIN_NUDGE_TOO_SOON}), 409
    # Claim the nudge first (conditional on nothing having been sent since we read the row), so a double
    # click or two admins cannot send it twice.
    previous_sent = cart.get("last_recovery_sent_at")
    attempts = int(cart.get("recovery_attempts") or 0)
    claim = db.table("abandoned_carts").eq("id", cart_id).eq("is_recovered", False)
    claim = claim.eq("last_recovery_sent_at", previous_sent) if previous_sent else claim.is_("last_recovery_sent_at", "null")
    try:
        claimed = claim.update({
            "recovery_attempts": attempts + 1,
            "last_recovery_sent_at": datetime.now(timezone.utc).isoformat(),
        })
    except (SupabaseError, requests.RequestException) as e:
        return db_error_response(e, "nudge_cart.claim")
    if not claimed:
        return jsonify({"error": MSG.ADMIN_NUDGE_TOO_SOON}), 409
    try:
        send_notification(user_id=user_id, notif_type="abandoned_cart", template_data={},
                          action_url="/cart", campus_id=cart.get("campus_id"))
    except Exception as e:  # broad on purpose: give the claim back so the nudge can be retried
        logger.error("nudge_cart: sending failed for cart %s: %s", cart_id, e)
        db.table("abandoned_carts").eq("id", cart_id).update(
            {"recovery_attempts": attempts, "last_recovery_sent_at": previous_sent}
        )
        return jsonify({"error": MSG.ADMIN_NUDGE_FAILED}), 502
    _audit(g.user_id, "abandoned_carts", cart_id, "nudge_cart", after_data={"user_id": user_id},
           target_campus_id=cart.get("campus_id"))
    return jsonify({"message": MSG.ADMIN_RECOVERY_NUDGE_SENT}), 200


@admin_bp.route("/audit-log", methods=["GET"])
@require_role("admin")
def audit_log():
    """
    View admin audit log with pagination and filters (admin only).
    ---
    tags: [Admin]
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
        name: entity_type
        type: string
      - in: query
        name: entity_id
        type: string
      - in: query
        name: action
        type: string
      - in: query
        name: actor_id
        type: string
      - in: query
        name: from_date
        type: string
        format: date
      - in: query
        name: to_date
        type: string
        format: date
      - in: query
        name: campus_id
        type: string
        description: super_admin only — a campus admin is always scoped to their own campus
    responses:
      200:
        description: Audit log entries with pagination metadata
    """
    # ADM-41. Filters: entity_type, entity_id, action, actor_id, from_date, to_date (WAT days), campus_id (super_admin).
    db = get_user_client()
    try:
        limit, offset = page_args()
        requested = as_campus_id(request.args.get("campus_id"))
        actor_id = as_uuid(request.args.get("actor_id"))
        from_date = as_date(request.args["from_date"]) if request.args.get("from_date") else None
        to_date = as_date(request.args["to_date"]) if request.args.get("to_date") else None
    except ValueError:
        return jsonify({"error": MSG.INVALID_INPUT}), 400
    campus_id = resolve_scoped_campus_id(requested)
    try:
        q = db.table("admin_audit_logs").select("*")
        if campus_id:
            q = q.eq("campus_id", campus_id)
        for key in ("entity_type", "entity_id", "action"):
            value = (request.args.get(key) or "").strip()[:100]
            if value:
                q = q.eq(key, value)
        if actor_id:
            q = q.eq("actor_id", actor_id)
        if from_date:
            q = q.gte("created_at", wat_day_bounds_utc(from_date)[0])
        if to_date:
            q = q.lt("created_at", wat_day_bounds_utc(to_date)[1])
        logs = q.order("created_at", ascending=False).limit(limit).offset(offset).execute() or []
    except (SupabaseError, requests.RequestException) as e:
        return db_error_response(e, "audit_log")
    return jsonify({"logs": logs, "count": len(logs), "limit": limit, "offset": offset}), 200


@admin_bp.route("/cron/<job_name>", methods=["POST"])
@require_role("super_admin")
def run_cron_job(job_name):
    """
    Manually trigger a scheduled cron job (super_admin only).
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
          - reset-weekly-leaderboard
          - recalculate-120day-hp
          - tier-grace-period-check
          - hp-decay-check
          - scan-abandoned-carts
          - monthly-birthday-report
          - win-back-notifications
          - check-order-locks
          - reset-monthly-hp-tracker
          - membership-anniversary-awards
          - send-scheduled-notifications
          - send-scheduled-blasts
          - process-scheduled-orders
          - check-post-delivery-nudges
          - grant-monthly-tier-perks
    responses:
      202:
        description: Job started in the background
      404:
        description: Unknown job name
    """
    # ADM-42. The manual-trigger audit row is now written here (request context, real actor) instead of
    # inside the background thread, where it had no request and was silently denied by RLS.
    from app.tasks.scheduled import (
        birthday_hp_awards,
        reset_monthly_leaderboard,
        reset_weekly_leaderboard,
        recalculate_120day_hp,
        tier_grace_period_check,
        scan_abandoned_carts,
        monthly_birthday_report,
        hp_decay_check,
        win_back_notifications,
        check_order_locks,
        reset_monthly_hp_tracker,
        membership_anniversary_awards,
        send_scheduled_notifications,
        send_scheduled_blasts,
        process_scheduled_orders,
    )
    from app.tasks.scheduled import check_post_delivery_nudges, grant_monthly_tier_perks

    task_map = {
        "birthday-hp":                   birthday_hp_awards,
        "reset-monthly-leaderboard":     reset_monthly_leaderboard,
        "reset-weekly-leaderboard":      reset_weekly_leaderboard,
        "recalculate-120day-hp":         recalculate_120day_hp,
        "tier-grace-period-check":       tier_grace_period_check,
        "scan-abandoned-carts":          scan_abandoned_carts,
        "monthly-birthday-report":       monthly_birthday_report,
        "hp-decay-check":                hp_decay_check,
        "win-back-notifications":        win_back_notifications,
        "check-order-locks":             check_order_locks,
        "reset-monthly-hp-tracker":      reset_monthly_hp_tracker,
        "membership-anniversary-awards": membership_anniversary_awards,
        "send-scheduled-notifications":  send_scheduled_notifications,
        "send-scheduled-blasts":         send_scheduled_blasts,
        "process-scheduled-orders":      process_scheduled_orders,
        "check-post-delivery-nudges":    check_post_delivery_nudges,
        "grant-monthly-tier-perks":      grant_monthly_tier_perks,
    }

    task_fn = task_map.get(job_name)
    if not task_fn:
        return jsonify({
            "error": MSG.ADMIN_UNKNOWN_CRON_JOB.format(job=job_name),
            "available_jobs": sorted(task_map.keys()),
        }), 404

    import threading
    triggered_by = g.user_id
    flask_app = current_app._get_current_object()
    # Recorded here, in the request, where the actor is known. (The old call inside the thread had no user or
    # request, was denied by the audit table's row-level security and was swallowed, so no manual run was ever recorded.)
    audit_ok = _audit(triggered_by, "cron_jobs", job_name, "manual_trigger", after_data={"source": "manual"})

    def _run():
        # The job records its own outcome (success, failed or skipped) through with_cron_logging.
        with flask_app.app_context():
            try:
                task_fn.apply().get(timeout=300)
            except Exception as exc:
                logger.error("cron/%s background run failed: %s", job_name, exc)

    t = threading.Thread(target=_run, daemon=True)
    t.start()
    body = {"job": job_name, "status": "started", "triggered_by": triggered_by, "note": MSG.ADMIN_JOB_RUNNING}
    if not audit_ok:
        body["audit_logged"] = False
    return jsonify(body), 202


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
    # ADM-43. status now distinguishes ok / failed / overdue / never_run using the *last success*,
    # not just the last trigger (a job that keeps failing every run used to show as "ok").
    db = get_db()
    KNOWN_JOBS = list(_CRON_INTERVAL_MINUTES)
    try:
        now = datetime.now(timezone.utc)
        status_map = {}
        for job in KNOWN_JOBS:
            rows = (
                db.table("admin_audit_logs")
                .select("entity_id,action,created_at,after_value,actor_id")
                .eq("entity_type", "cron_jobs").eq("entity_id", job)
                .order("created_at", ascending=False).limit(20).execute()
            ) or []
            last = rows[0] if rows else None
            last_success = next((r for r in rows if r.get("action") == "scheduled_execution_success"), None)
            interval, cadence = _CRON_INTERVAL_MINUTES[job]
            if not last:
                status = "never_run"
            elif str(last.get("action", "")).endswith("_failed"):
                status = "failed"
            elif not last_success or _age_minutes(last_success["created_at"], now) > 2 * interval:
                status = "overdue"
            else:
                status = "ok"
            status_map[job] = {
                "status": status,
                "last_triggered": last["created_at"] if last else None,
                "last_action": last.get("action") if last else None,
                "last_success": last_success["created_at"] if last_success else None,
                "triggered_by": last.get("actor_id") if last else None,
                "last_result": last.get("after_value") if last else None,
                "cadence": cadence,
            }
    except (SupabaseError, requests.RequestException) as e:
        return db_error_response(e, "cron_status")
    counts = {s: sum(1 for v in status_map.values() if v["status"] == s) for s in ("ok", "failed", "overdue", "never_run")}
    return jsonify({
        "checked_at": now.isoformat(),
        "jobs": status_map,
        "summary": dict(counts, total=len(KNOWN_JOBS)),
    }), 200

# --- END OF SECTION 5 (abandoned carts, audit log, cron) ---


# ---------------------------------------------------------------------------
# HP bulk grant, HP report, campuses, reviews
# ---------------------------------------------------------------------------

_BULK_GRANT_MAX = 500
_GRANT_NAMESPACE = uuid.UUID("6b1a0d9e-5a3c-4c55-9f0e-2b6f7b1c9a10")
_GRANT_WINDOW_SECONDS = 600


class _GrantInputError(ValueError):
    """A validation problem that carries its own user-facing message."""


def _grant_id(actor_id, amount, reason, recipient_ids):
    """One id per bulk grant. It becomes the HP transaction's reference id, and the database refuses a
    second transaction with the same (user, type, reference), so repeating the same request within ten
    minutes credits nobody twice. The client may send its own `grant_id` to make a retry safe for longer."""
    bucket = int(datetime.now(timezone.utc).timestamp() // _GRANT_WINDOW_SECONDS)
    raw = json.dumps([str(actor_id), amount, reason, sorted(recipient_ids), bucket])
    return str(uuid.uuid5(_GRANT_NAMESPACE, hashlib.sha256(raw.encode()).hexdigest()))


def _notify_grant(recipients, amount, reason, flask_app):
    """Tell each credited user, off the request thread. A failed message never affects the grant."""
    def _run():
        with flask_app.app_context():
            for uid, campus in recipients:
                try:
                    send_notification(uid, "hp_admin_grant", template_data={"hp": amount, "reason": reason}, campus_id=campus)
                except Exception as e:  # broad on purpose: the HP is already credited
                    logger.error("bulk_grant_hp: notification failed for %s: %s", uid, e)
    threading.Thread(target=_run, daemon=True).start()


def _hp_grant_denied(exc) -> bool:
    """True when the database refused the segment query for want of admin rights.

    hg_hp_grant_segment now requires the caller to be an admin of p_campus or a
    super_admin. That refusal must read as 403, not as a generic failure.
    """
    details = getattr(exc, "details", None)
    code = str((details or {}).get("code") or "") if isinstance(details, dict) else ""
    if code == "42501" or getattr(exc, "status_code", None) == 403:
        return True
    text = str(exc).lower()
    return any(m in text for m in (
        "not an admin", "must be an admin", "admin of p_campus", "admin of the campus",
        "requires an admin", "only admin", "insufficient privilege",
        "insufficient_privilege",                      # the live wording (SQLSTATE 42501)
        "permission denied",
    ))


@admin_bp.route("/hp/bulk-grant", methods=["POST"])
@require_role("admin")
def bulk_grant_hp():
    """
    Grant HP to a segment of users, or an explicit list (admin only).
    Send dry_run: true first — the response carries the grant_id to reuse for a safe retry.
    ---
    tags: [Admin]
    parameters:
      - in: body
        name: body
        required: true
        schema:
          required: [amount, reason]
          properties:
            amount: {type: integer}
            reason: {type: string}
            dry_run: {type: boolean, default: false}
            grant_id: {type: string, description: Optional — reuse the grant_id from a dry run to retry safely}
            user_ids: {type: array, items: {type: string}, description: Explicit recipients (max 500)}
            tier_slug: {type: string, description: Segment by tier instead of an explicit list}
            last_order_before: {type: string, format: date}
            last_order_after: {type: string, format: date}
            campus_id: {type: string}
    responses:
      200:
        description: Grant result (or dry-run preview)
      400:
        description: Validation error
    """
    # ADM-44
    from app.services.hp_service import award_active_hp
    data = get_json_object()
    if data is None:
        return jsonify({"error": MSG.JSON_OBJECT_REQUIRED}), 400
    try:
        if isinstance(data.get("amount"), bool):
            raise _GrantInputError(MSG.ADMIN_AMOUNT_POSITIVE)
        ok, message = validate_hp_amount(data.get("amount"))
        if not ok:
            raise _GrantInputError(message)
        amount = int(data["amount"])
        try:
            reason = as_text(data.get("reason"), 200)
        except ValueError:
            raise _GrantInputError(MSG.ADMIN_REASON_REQUIRED)
        dry_run = data.get("dry_run", False)
        if not isinstance(dry_run, bool):
            raise _GrantInputError(MSG.WINDOW_FLAG_INVALID.format(field="dry_run"))
        explicit = data.get("user_ids")
        if explicit is not None:
            if not isinstance(explicit, list) or len(explicit) > _BULK_GRANT_MAX:
                raise _GrantInputError(MSG.BULK_GRANT_TOO_MANY.format(max=_BULK_GRANT_MAX))
            explicit = list(dict.fromkeys(as_uuid(i) for i in explicit))
            if None in explicit:
                raise ValueError("user_ids")
        tier_slug = data.get("tier_slug")
        if tier_slug is not None:
            tier_slug = as_text(tier_slug, 50).lower()
        before = as_date(data["last_order_before"]) if data.get("last_order_before") else None
        after = as_date(data["last_order_after"]) if data.get("last_order_after") else None
        supplied_grant_id = as_uuid(data.get("grant_id"))
        requested_campus = as_campus_id(data.get("campus_id"))
    except _GrantInputError as e:
        return jsonify({"error": str(e)}), 400
    except ValueError:
        return jsonify({"error": MSG.INVALID_INPUT}), 400
    db = get_user_client()
    campus_id = resolve_scoped_campus_id(requested_campus)
    # A campus admin must never run an unscoped segment: hg_hp_grant_segment now
    # rejects it on the database side, but a clean 400 beats an opaque RPC error.
    if campus_id is None and getattr(g, "user_role", None) != "super_admin":
        return jsonify({"error": MSG.ACCOUNT_NO_CAMPUS}), 400
    skipped = []
    try:
        if explicit:
            q = db.table("profiles").select("id,full_name,campus_id").in_("id", explicit).eq("is_active", True).neq("id", g.user_id)
            if campus_id:
                q = q.eq("campus_id", campus_id)
            profiles = q.execute() or []
            found = {p["id"] for p in profiles}
            skipped = [i for i in explicit if i not in found]
        else:
            tier_id = None
            if tier_slug:
                tier_row = db.table("hp_tiers").select("id").eq("slug", tier_slug).single().execute()
                if not tier_row:
                    return jsonify({"error": MSG.ADMIN_TIER_NOT_FOUND.format(slug=tier_slug)}), 400
                tier_id = tier_row["id"]
            profiles = db.rpc("hg_hp_grant_segment", {
                "p_campus": campus_id,
                "p_tier": tier_id,
                "p_last_order_before": wat_day_bounds_utc(before)[0] if before else None,
                "p_last_order_after": wat_day_bounds_utc(after)[0] if after else None,
                "p_exclude": g.user_id,
                "p_limit": _BULK_GRANT_MAX + 1,
            }) or []
    except (SupabaseError, requests.RequestException) as e:
        if _hp_grant_denied(e):
            logger.warning("bulk_grant_hp: segment query refused — %s", e)
            return jsonify({"error": MSG.RESOURCE_ACCESS_DENIED}), 403
        return db_error_response(e, "bulk_grant_hp.segment")
    if len(profiles) > _BULK_GRANT_MAX:
        return jsonify({"error": MSG.BULK_GRANT_TOO_MANY.format(max=_BULK_GRANT_MAX)}), 400
    grant_id = supplied_grant_id or _grant_id(g.user_id, amount, reason, [p["id"] for p in profiles])
    if dry_run:
        return jsonify({
            "dry_run": True,
            "grant_id": grant_id,
            "matched_count": len(profiles),
            "matched_user_ids": [p["id"] for p in profiles],
            "skipped_user_ids": skipped,
            "amount_per_user": amount,
            "total_hp_to_award": amount * len(profiles),
            "reason": reason,
        }), 200
    if not profiles:
        return jsonify({"error": MSG.BULK_GRANT_NO_RECIPIENTS, "skipped_user_ids": skipped}), 400

    awarded, replayed, failed = [], [], []
    for p in profiles:
        try:
            result = award_active_hp(
                user_id=p["id"], amount=amount, txn_type="earn",
                reference_id=grant_id, reference_type="admin_grant", source_type="admin_grant",
                notes=f"Bulk grant: {reason}", issued_by_admin_id=g.user_id,
                apply_multiplier=False, campus_id=p.get("campus_id"),
            )
            (replayed if result.get("replayed") else awarded).append(p)
        except Exception as exc:  # broad on purpose: one user's failure must not stop the others
            logger.error("bulk_grant_hp: %s failed for %s: %s", grant_id, p["id"], exc)
            failed.append({"user_id": p["id"], "error": MSG.BULK_GRANT_USER_FAILED})
    audit_ok = _audit(g.user_id, "profiles", grant_id, "bulk_hp_grant", after_data={
        "grant_id": grant_id, "amount": amount, "reason": reason,
        "awarded": [p["id"] for p in awarded], "already_granted": [p["id"] for p in replayed],
        "failed": [f["user_id"] for f in failed],
    }, target_campus_id=campus_id)
    if awarded:
        _notify_grant([(p["id"], p.get("campus_id")) for p in awarded], amount, reason, current_app._get_current_object())
    body = {
        "grant_id": grant_id,
        "awarded_count": len(awarded),
        "already_granted_count": len(replayed),
        "failed_count": len(failed),
        "amount_per_user": amount,
        "total_hp_awarded": amount * len(awarded),
        "reason": reason,
        "skipped_user_ids": skipped,
        "failed": failed,
    }
    if not audit_ok:
        body["audit_logged"] = False
    return jsonify(body), (502 if failed and not awarded and not replayed else 200)


@admin_bp.route("/hp/report", methods=["GET"])
@require_role("admin")
def hp_report():
    """
    HP program summary: total issued/spent/expired, net in system, top earners (admin only).
    ---
    tags: [Admin]
    responses:
      200:
        description: HP program report
    """
    # ADM-45. Totals come from get_hp_program_report_summary (A-17): earned, spent and expired are counted by type.
    db = get_user_client()
    try:
        summary = db.rpc("get_hp_program_report_summary", {"p_today_date": today_wat().isoformat()}) or {}
        top_rows = (
            db.table("profiles").select("id,full_name,hp_balance,current_tier_id,campus_id")
            .order("hp_balance", ascending=False).limit(10).execute()
        ) or []
    except (SupabaseError, requests.RequestException) as e:
        return db_error_response(e, "hp_report")
    issued = int(summary.get("total_issued") or 0)
    spent = int(summary.get("total_spent") or 0)
    expired = int(summary.get("total_expired") or 0)
    return jsonify({
        "total_hp_issued": issued,
        "total_hp_spent": spent,
        "total_hp_expired": expired,
        "net_hp_in_system": issued - spent - expired,
        "hp_issued_today": int(summary.get("issued_today") or 0),
        "users_by_tier": summary.get("users_by_tier") or {},
        "top_earners": top_rows,
    }), 200


@admin_bp.route("/campuses", methods=["GET"])
@require_role("admin")
def list_campuses():
    """
    List all campuses, including inactive ones (admin only).
    ---
    tags: [Admin]
    responses:
      200:
        description: Campuses
    """
    # ADM-46. Campus details are public (the sign-up list); this admin list also shows inactive campuses.
    db = get_user_client()
    try:
        campuses = db.table("campuses").select("*").order("name").execute() or []
    except (SupabaseError, requests.RequestException) as e:
        return db_error_response(e, "list_campuses")
    return jsonify(campuses), 200


@admin_bp.route("/reviews", methods=["GET"])
@require_role("admin")
def list_reviews():
    """
    List order reviews with filters (admin only).
    ---
    tags: [Admin]
    parameters:
      - in: query
        name: rating
        type: integer
      - in: query
        name: kitchen_rating
        type: integer
      - in: query
        name: rider_rating
        type: integer
      - in: query
        name: is_flagged
        type: boolean
      - in: query
        name: campus_id
        type: string
        description: super_admin only
    responses:
      200:
        description: Reviews
    """
    # ADM-47. Filters: rating, kitchen_rating, rider_rating (1-5), is_flagged, campus_id (super_admin).
    db = get_user_client()
    try:
        limit, offset = page_args()
        requested = as_campus_id(request.args.get("campus_id"))
        ratings = {}
        for key in ("rating", "kitchen_rating", "rider_rating"):
            if request.args.get(key):
                ratings[key] = as_int(request.args[key], 1, 5)
    except ValueError:
        return jsonify({"error": MSG.INVALID_INPUT}), 400
    flagged = request.args.get("is_flagged")
    if flagged not in (None, "", "true", "false"):
        return jsonify({"error": MSG.INVALID_INPUT}), 400
    campus_id = resolve_scoped_campus_id(requested)
    try:
        q = db.table("order_reviews").select(
            "*,profiles!user_id(full_name,email),orders!order_id(id,status,total_amount)", count="exact"
        )
        if campus_id:
            q = q.eq("campus_id", campus_id)
        for key, value in ratings.items():
            q = q.eq(key, value)
        if flagged:
            q = q.eq("is_flagged", flagged == "true")
        res = q.order("created_at", ascending=False).limit(limit).offset(offset).execute() or {}
    except (SupabaseError, requests.RequestException) as e:
        return db_error_response(e, "list_reviews")
    reviews = res.get("data") or []
    return jsonify({"reviews": reviews, "total": res.get("count") or 0, "limit": limit, "offset": offset}), 200

# --- END OF SECTION 6 (HP bulk-grant/report, campuses, reviews) ---


# ---------------------------------------------------------------------------
# Exclusive spin prize pool
# ---------------------------------------------------------------------------
# NOTE: these 4 handlers were flagged "file not identified" in the fixes doc (audited
# from the flow description, not a known file) — confirmed they live here, in this same
# admin_bp blueprint block. The doc explicitly scopes their fix to 3 small patches
# (B-34/B-35/B-36), not a full rewrite, so the rest of each handler is left as it was.

@admin_bp.route("/exclusive-spin-pool", methods=["GET"])
@require_role("admin")
def list_spin_pool():
    """List all exclusive spin prize-pool entries (odds/weights), not fulfilment records."""
    # No change needed here (confirmed correct against live RLS).
    db = get_user_client()
    campus_id = resolve_scoped_campus_id(request.args.get("campus_id"))
    q = db.table("exclusive_spin_prizes").select("*").order("weight", ascending=False)
    if campus_id:
        q = q.or_(f"campus_id.eq.{campus_id},campus_id.is.null")
    prizes = q.execute() or []
    return jsonify({"prizes": prizes}), 200


@admin_bp.route("/exclusive-spin-pool", methods=["POST"])
@require_role("admin")
def create_spin_pool_prize():
    """Create a new exclusive spin prize-pool entry."""
    db = get_user_client()
    data = request.get_json(force=True) or {}

    if not data.get("name"):
        return jsonify({"error": MSG.SPIN_POOL_NAME_REQUIRED}), 400

    weight = data.get("weight", 1)
    if not isinstance(weight, int) or weight <= 0:
        return jsonify({"error": MSG.SPIN_POOL_WEIGHT_INVALID}), 400

    # B-35: a super_admin's own campus_id is None, so before this fix every prize they
    # created was global regardless of intent — let them name a specific campus instead.
    if getattr(g, "user_role", None) == "super_admin" and data.get("campus_id"):
        campus_id = as_campus_id(data.get("campus_id"))
    else:
        campus_id = getattr(g, "campus_id", None)
    result = db.table("exclusive_spin_prizes").insert({
        "name": data["name"],
        "weight": weight,
        "is_active": bool(data.get("is_active", True)),
        "campus_id": campus_id,
    }).execute()

    row = result[0] if isinstance(result, list) else result
    return jsonify(row), 201


@admin_bp.route("/exclusive-spin-grant", methods=["POST"])
@require_role("admin")
def grant_exclusive_spins():
    """
    Grant exclusive-spin credits to one user (admin only).
    Body: { "user_id": "<uuid>", "spins": 1, "validity_days": 60, "reason": "..." }
    ---
    tags: [Admin]
    parameters:
      - in: body
        name: body
        required: true
        schema:
          required: [user_id]
          properties:
            user_id: {type: string, format: uuid}
            spins: {type: integer, default: 1, description: 1-10}
            validity_days: {type: integer}
            reason: {type: string}
    responses:
      201:
        description: Spins granted
      400:
        description: Invalid user or spin count
      404:
        description: User not found in your campus
    """
    from app.middleware.auth import fetch_or_403
    from app.services.notification_service import send_notification

    db = get_user_client()
    data = get_json_object()
    if data is None:
        return jsonify({"error": MSG.JSON_OBJECT_REQUIRED}), 400

    user_id = as_uuid(data.get("user_id"))
    if not user_id:
        return jsonify({"error": MSG.AUTH_FIELD_REQUIRED.format(field="user_id")}), 400
    try:
        spins = int(data.get("spins", 1))
    except (TypeError, ValueError):
        return jsonify({"error": "spins must be a whole number"}), 400
    if not 1 <= spins <= 10:
        return jsonify({"error": "spins must be between 1 and 10"}), 400

    target, err = fetch_or_403(db, "profiles", user_id, select="id,campus_id",
                               not_found_msg=MSG.RESOURCE_NOT_FOUND)
    if err:
        return err

    validity_days = data.get("validity_days")
    if validity_days is None:
        try:
            row = db.table("system_settings").select("value").eq("key", "exclusive_spin_validity_days").is_("campus_id", "null").single().execute()
            validity_days = int((row or {}).get("value") or 60)
        except Exception:                                    # noqa: BLE001 - a setting, not a guard
            validity_days = 60
    try:
        validity_days = int(validity_days)
    except (TypeError, ValueError):
        return jsonify({"error": "validity_days must be a whole number"}), 400
    if not 1 <= validity_days <= 365:
        return jsonify({"error": "validity_days must be between 1 and 365"}), 400

    reason = as_text(data.get("reason"), 200) or "Admin grant"
    expires_at = (datetime.now(timezone.utc) + timedelta(days=validity_days)).isoformat()
    month = datetime.now(timezone.utc).strftime("%Y-%m")

    # source='admin_grant' is accepted on read (see SPIN_GRANT_SOURCES in
    # app/routes/exclusive_spin.py) — without that entry this row would be invisible.
    result = db.table("exclusive_spins").insert({
        "user_id": user_id,
        "spin_count": spins,
        "source": "admin_grant",
        "month": month,
        "expires_at": expires_at,
        "campus_id": target.get("campus_id") or getattr(g, "campus_id", None),
    }).execute()
    row = result[0] if isinstance(result, list) else result

    _audit(g.user_id, "exclusive_spins", (row or {}).get("id"), "grant",
           after_data={"user_id": user_id, "spins": spins, "expires_at": expires_at, "reason": reason},
           target_campus_id=target.get("campus_id"))
    try:
        send_notification(
            user_id=user_id,
            notif_type="exclusive_spin_granted",
            template_data={"spins": spins, "expires_at": expires_at[:10]},
            campus_id=target.get("campus_id") or getattr(g, "campus_id", None),
        )
    except Exception as exc:                                 # noqa: BLE001 - the grant already happened
        logger.warning("grant_exclusive_spins: notify failed for %s: %s", user_id, exc)

    return jsonify({
        "message": "Exclusive spins granted",
        "spin_id": (row or {}).get("id"),
        "user_id": user_id,
        "spins": spins,
        "expires_at": expires_at,
    }), 201


@admin_bp.route("/exclusive-spin-pool/<prize_id>", methods=["PATCH"])
@require_role("admin")
def update_spin_pool_prize(prize_id):
    """Update an exclusive spin prize-pool entry."""
    db = get_user_client()
    data = request.get_json(force=True) or {}

    # B-34: the pre-check had no campus filter, so a campus admin was told a prize
    # "exists" even when it belonged to another campus (the write was still RLS-blocked,
    # but the response was a misleading "found, then update failed" instead of not-found).
    campus_id = getattr(g, "campus_id", None)
    existing_q = db.table("exclusive_spin_prizes").select("id")
    if campus_id:
        existing_q = existing_q.eq("campus_id", campus_id)
    existing = existing_q.eq("id", prize_id).single().execute()
    if not existing:
        return jsonify({"error": MSG.SPIN_POOL_PRIZE_NOT_FOUND}), 404

    allowed = {"name", "weight", "is_active"}
    safe = {k: v for k, v in data.items() if k in allowed}
    if "weight" in safe and (not isinstance(safe["weight"], int) or safe["weight"] <= 0):
        return jsonify({"error": MSG.SPIN_POOL_WEIGHT_INVALID}), 400
    if not safe:
        return jsonify({"error": MSG.SPIN_POOL_NO_VALID_FIELDS}), 400

    safe["updated_at"] = datetime.now(timezone.utc).isoformat()
    result = db.table("exclusive_spin_prizes").eq("id", prize_id).update(safe).execute()
    if not result:
        return jsonify({"error": MSG.SPIN_POOL_UPDATE_FAILED}), 404

    row = result[0] if isinstance(result, list) else result
    return jsonify(row), 200


@admin_bp.route("/exclusive-spin-pool/<prize_id>", methods=["DELETE"])
@require_role("admin")
def delete_spin_pool_prize(prize_id):
    """Soft-delete (deactivate) an exclusive spin prize-pool entry."""
    db = get_user_client()

    # B-34 (see update_spin_pool_prize above for the same fix, applied here too)
    campus_id = getattr(g, "campus_id", None)
    existing_q = db.table("exclusive_spin_prizes").select("id")
    if campus_id:
        existing_q = existing_q.eq("campus_id", campus_id)
    existing = existing_q.eq("id", prize_id).single().execute()
    if not existing:
        return jsonify({"error": MSG.SPIN_POOL_PRIZE_NOT_FOUND}), 404

    result = db.table("exclusive_spin_prizes").eq("id", prize_id).update({
        "is_active": False,
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }).execute()
    if not result:
        return jsonify({"error": MSG.SPIN_POOL_DEACTIVATION_FAILED}), 404

    return jsonify({"message": "Prize deactivated"}), 200


# ---------------------------------------------------------------------------
# Webhook events
# ---------------------------------------------------------------------------

@admin_bp.route("/webhook-events", methods=["GET"])
@require_role("admin")
def list_webhook_events():
    """
    List webhook event logs (admin only).
    Uses service-role client (get_db()) because RLS is enabled on webhook_events.
    ---
    tags: [Admin]
    parameters:
      - in: query
        name: provider
        type: string
      - in: query
        name: status
        type: string
      - in: query
        name: from_date
        type: string
        format: date
      - in: query
        name: to_date
        type: string
        format: date
      - in: query
        name: campus_id
        type: string
        description: super_admin only — a campus admin is always scoped to their own campus
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
        description: Webhook events list
    """
    # B-24 · P0: this was a real, tested-live cross-campus payment-data leak — get_db() is
    # service-role, so RLS doesn't scope it at all, and there was no app-level campus filter
    # either. A campus-1 admin could see every other campus's raw payment webhook payloads.
    db = get_db()  # still service role — the app does the campus scoping explicitly below
    campus_id = resolve_scoped_campus_id(request.args.get("campus_id"))

    # B-25: limit/offset were parsed with plain int() and no bounds — bad input 500'd.
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

    q = db.table("webhook_events").select("*")
    if campus_id:
        q = q.eq("campus_id", campus_id)

    provider = request.args.get("provider")
    if provider:
        q = q.eq("provider", provider)

    status = request.args.get("status")
    if status:
        q = q.eq("status", status)

    from_date = request.args.get("from_date")
    if from_date:
        q = q.gte("created_at", from_date)

    to_date = request.args.get("to_date")
    if to_date:
        q = q.lte("created_at", to_date + ("T23:59:59Z" if "T" not in to_date else ""))

    rows = q.order("created_at", ascending=False).limit(limit).offset(offset).execute() or []
    return jsonify({"webhook_events": rows, "count": len(rows)}), 200

# --- END OF SECTION 7 (exclusive spin pool, webhook events) ---


# ---------------------------------------------------------------------------
# Campus centre point (delivery radius)
# ---------------------------------------------------------------------------
# Sets the ONE point per campus that `is_within_delivery_area` measures max_delivery_radius_km from.
# `campuses` has NO update policy for authenticated users at all (confirmed live — only a public SELECT
# policy exists), so unlike everywhere else in this file, RLS gives no defense-in-depth on this write:
# _may_manage_campus() below is the only thing standing between an admin and another campus's location.

_NIGERIA_LAT = (4.0, 14.0)
_NIGERIA_LON = (2.5, 15.0)


def _parse_coord(value, low, high):
    """float within [low, high] from a number or numeric string; None if it is not one."""
    if isinstance(value, bool) or value is None:
        return None
    try:
        number = float(str(value).strip().replace(",", ".")) if isinstance(value, str) else float(value)
    except (TypeError, ValueError):
        return None
    if number != number or number in (float("inf"), float("-inf")) or not (low <= number <= high):
        return None
    return round(number, 6)


def _may_manage_campus(campus_id):
    """super_admin: any campus. admin: only the campus stored on their own profile."""
    if getattr(g, "user_role", None) == "super_admin":
        return True
    row = get_db().table("profiles").select("campus_id").eq("id", g.user_id).single().execute()
    return bool(row and row.get("campus_id") and str(row["campus_id"]) == str(campus_id))


def _campus_radius_km(campus_id):
    try:
        rows = (get_db().table("kitchen_settings").select("value")
                .eq("key", "max_delivery_radius_km").eq("campus_id", campus_id).limit(1).execute()) or []
        if rows and rows[0].get("value"):
            return float(rows[0]["value"])
    except Exception:
        logger.warning("campus location: max_delivery_radius_km unreadable for %s — showing default", campus_id, exc_info=True)
    return 15.0


def _campus_location_body(campus):
    lat, lon = campus.get("lat"), campus.get("lon")
    configured = lat is not None and lon is not None
    return {
        "campus_id": campus["id"],
        "name": campus["name"],
        "lat": lat,
        "lon": lon,
        "is_configured": configured,
        "max_delivery_radius_km": _campus_radius_km(campus["id"]),
        "map_url": f"https://www.google.com/maps?q={lat},{lon}" if configured else None,
    }


@admin_bp.route("/campuses/<campus_id>/location", methods=["GET"])
@require_role("admin")
def get_campus_location(campus_id):
    """
    Current centre point of a campus (admin: own campus, super_admin: any).
    ---
    tags: [Admin]
    parameters:
      - in: path
        name: campus_id
        type: string
        required: true
    responses:
      200:
        description: "{campus_id, name, lat, lon, is_configured, max_delivery_radius_km, map_url}"
      403:
        description: Not your campus
      404:
        description: Campus not found
    """
    if not validate_uuid(campus_id):
        return jsonify({"error": MSG.CAMPUS_NOT_FOUND}), 404
    campus = get_db().table("campuses").select("id,name,lat,lon").eq("id", campus_id).single().execute()
    if not campus:
        return jsonify({"error": MSG.CAMPUS_NOT_FOUND}), 404
    if not _may_manage_campus(campus_id):
        return jsonify({"error": MSG.RESOURCE_ACCESS_DENIED}), 403
    return jsonify(_campus_location_body(campus)), 200


@admin_bp.route("/campuses/<campus_id>/location", methods=["PATCH"])
@require_role("admin")
def set_campus_location(campus_id):
    """
    Set (or clear) the campus centre point used for the delivery radius.
    Send {"lat": 7.3021, "lon": 5.1391}, or {"coordinates": "7.3021, 5.1391"} (pasted from Google Maps),
    or {"lat": null, "lon": null} to clear it. Coordinates outside Nigeria are refused unless "force": true.
    ---
    tags: [Admin]
    parameters:
      - in: path
        name: campus_id
        type: string
        required: true
      - in: body
        name: body
        required: true
        schema:
          properties:
            lat: {type: number, example: 7.3021}
            lon: {type: number, example: 5.1391}
            coordinates: {type: string, example: "7.3021, 5.1391"}
            force: {type: boolean}
    responses:
      200:
        description: Location saved
      400:
        description: Invalid coordinates
      403:
        description: Not your campus
      404:
        description: Campus not found
    """
    if not validate_uuid(campus_id):
        return jsonify({"error": MSG.CAMPUS_NOT_FOUND}), 404
    data = request.get_json(force=True, silent=True)
    if not isinstance(data, dict):
        return jsonify({"error": MSG.ERR_BAD_REQUEST}), 400
    campus = get_db().table("campuses").select("id,name,lat,lon").eq("id", campus_id).single().execute()
    if not campus:
        return jsonify({"error": MSG.CAMPUS_NOT_FOUND}), 404
    if not _may_manage_campus(campus_id):
        return jsonify({"error": MSG.RESOURCE_ACCESS_DENIED}), 403

    if isinstance(data.get("coordinates"), str):                  # "7.3021, 5.1391" as copied from Google Maps
        parts = [p for p in data["coordinates"].replace(",", " ").split() if p]
        if len(parts) != 2:
            return jsonify({"error": MSG.CAMPUS_LOCATION_INVALID}), 400
        raw_lat, raw_lon = parts
    elif "lat" in data and "lon" in data:
        raw_lat, raw_lon = data["lat"], data["lon"]
    else:
        return jsonify({"error": MSG.CAMPUS_LOCATION_INVALID}), 400

    if raw_lat is None and raw_lon is None:
        lat = lon = None                                          # clearing
    else:
        lat, lon = _parse_coord(raw_lat, -90, 90), _parse_coord(raw_lon, -180, 180)
        if lat is None or lon is None:
            return jsonify({"error": MSG.CAMPUS_LOCATION_INVALID}), 400
        outside = not (_NIGERIA_LAT[0] <= lat <= _NIGERIA_LAT[1] and _NIGERIA_LON[0] <= lon <= _NIGERIA_LON[1])
        if outside and data.get("force") is not True:
            return jsonify({"error": MSG.CAMPUS_LOCATION_OUTSIDE_NIGERIA}), 400

    updated = get_db().table("campuses").eq("id", campus_id).update(
        {"lat": lat, "lon": lon, "updated_at": datetime.now(timezone.utc).isoformat()})
    row = updated[0] if isinstance(updated, list) and updated else None
    if row is None:
        return jsonify({"error": MSG.CAMPUS_NOT_FOUND}), 404
    _audit(g.user_id, "campuses", campus_id, "set_location" if lat is not None else "clear_location",
           {"lat": lat, "lon": lon, "before": {"lat": campus.get("lat"), "lon": campus.get("lon")}})
    body = _campus_location_body({**campus, "lat": lat, "lon": lon})
    body["message"] = MSG.CAMPUS_LOCATION_SAVED if lat is not None else MSG.CAMPUS_LOCATION_CLEARED
    return jsonify(body), 200

# --- END OF SECTION 8 (campus centre point). All admin.py sections are now in —
# next is one full consistency pass over the whole combined file. ---







