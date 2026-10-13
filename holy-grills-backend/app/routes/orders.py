from flask import Blueprint, request, jsonify, g, current_app
from app.middleware.auth import require_auth, require_role, optional_auth
from app.middleware.rate_limit import rate_limit
from app.services import order_service
from app.services.hp_service import earn_pending_hp
from app.db import get_db, get_user_client
from app.messages import MSG, resolve_msg
from app.utils.tz import today_wat, WAT_OFFSET
from app.utils.logger import get_logger
from datetime import datetime, timezone
import hmac

logger = get_logger(__name__)
orders_bp = Blueprint("orders", __name__)
ORDER_STATUS_VALUES = set(order_service.VALID_TRANSITIONS)


def _assigned_rider_contact(db, order: dict) -> dict | None:
    """Resolve the assigned rider from the order's delivery batch.

    The API deliberately returns a tel URI rather than the raw phone number.
    The profile lookup is always keyed by the persisted batch rider_id; there
    is no fallback contact value.
    """
    batch = order.get("delivery_batches")
    if isinstance(batch, list):
        batch = batch[0] if batch else None
    if not isinstance(batch, dict) or not batch.get("rider_id"):
        return None

    profile = (
        db.table("profiles")
        .select("full_name,phone")
        .eq("id", batch["rider_id"])
        .single()
        .execute()
    )
    if not profile:
        return None

    phone = profile.get("phone")
    return {
        "name": profile.get("full_name"),
        "call_link": f"tel:{phone}" if phone else None,
    }


@orders_bp.route("", methods=["POST"])
@optional_auth
@rate_limit("RATE_LIMIT_ORDERS_REQUESTS", "RATE_LIMIT_ORDERS_WINDOW")
def create_order():
    data = request.get_json(force=True) or {}

    # Authenticated vs guest order identity override checks (Secure from client-supplied manipulation)
    user_id = g.user_id
    if user_id:
        # Authenticated checkout must always use the authenticated identity, client-supplied IDs ignored/overridden
        data["user_id"] = user_id
        # Authenticated users cannot accidentally or maliciously create guest orders by removing or passing empty guest values
        data.pop("guest_name", None)
        data.pop("guest_phone", None)
        data.pop("guest_email", None)
    else:
        # Guest orders cannot supply or hijack an authenticated user ID
        data.pop("user_id", None)
    """
    Create a new order. Supports authenticated and guest checkout.
    ---
    tags: [Orders]
    parameters:
      - in: body
        name: body
        required: true
        schema:
          required: [items, payment_method]
          properties:
            items:
              type: array
              items:
                type: object
                properties:
                  menu_item_id:
                    type: string
                  quantity:
                    type: integer
            payment_method:
              type: string
              enum: [wallet, card, split]
            delivery_type:
              type: string
              enum: [on_campus, off_campus]
              description: System decides delivery window; client selects hostel or gate for fee calculation.
            delivery_location_id:
              type: string
              description: Hostel UUID (on_campus) or Gate UUID (off_campus)
            delivery_location_lat:
              type: number
              description: Customer GPS latitude for off-campus distance fee
            delivery_location_lon:
              type: number
              description: Customer GPS longitude for off-campus distance fee
            delivery_address:
              type: object
              description: Optional free-text address snapshot stored for rider notes only
            promo_code:
              type: string
            notes:
              type: string
            squad_name:
              type: string
              description: Name for squad orders
            is_scheduled:
              type: boolean
            scheduled_for_window_id:
              type: string
              description: Explicit future window UUID; system auto-assigns if omitted
            scheduled_date:
              type: string
              format: date
              description: Date hint YYYY-MM-DD for scheduled orders (date only, no time)
            guest_name:
              type: string
            guest_phone:
              type: string
            guest_email:
              type: string
    responses:
      201:
        description: Order created
      400:
        description: Validation error
    """
    if not data.get("items"):
        return jsonify({"error": MSG.ORDER_ITEMS_REQUIRED}), 400
    if not data.get("payment_method"):
        return jsonify({"error": MSG.ORDER_PAYMENT_METHOD_REQUIRED}), 400
    # delivery_address is now optional — delivery fees are calculated from
    # delivery_type + delivery_location_id (hostel/gate). The free-text address
    # is stored as a snapshot for rider notes only.

    is_guest = user_id is None
    if is_guest:
        for field in ["guest_name", "guest_phone", "guest_email"]:
            if not data.get(field):
                return jsonify({"error": f"'{field}' required for guest checkout"}), 400
        if data.get("payment_method") in ("wallet", "split"):
            return jsonify({"error": MSG.ORDER_WALLET_LOGIN_REQUIRED}), 400
    from app.services.order_service import OrderingWindowUnavailable
    try:
        order = order_service.create_order(user_id, data)
        if isinstance(order, dict):
            order["message"] = MSG.ORDER_PLACED
        return jsonify(order), 201
    except OrderingWindowUnavailable as e:
        # Stable machine-readable code — the client decides "offer to schedule"
        # from this, never from the message text. next_available_date/next_opens_at
        # tell it which slot to offer.
        resp = {"error": str(e), "code": getattr(e, "code", None) or "ORDERING_WINDOW_CLOSED"}
        if getattr(e, "next_available_date", None):
            resp["next_available_date"] = e.next_available_date
        if getattr(e, "next_opens_at", None):
            resp["next_opens_at"] = e.next_opens_at
        return jsonify(resp), 409
    except ValueError as e:
        return jsonify({"error": str(e)}), 400
    except Exception as e:
        logger.error("create_order failed: %s", e)
        return jsonify({"error": MSG.ORDER_CREATE_FAILED}), 500


@orders_bp.route("", methods=["GET"])
@require_auth
def list_orders():
    """
    List authenticated user's orders.
    ---
    tags: [Orders]
    parameters:
      - in: query
        name: status
        type: string
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
        description: Order list
    """
    db = get_user_client()
    q = db.table("orders").select("*,order_items(*,order_addon_selections(name_snapshot,quantity))").eq("user_id", g.user_id)

    status = request.args.get("status")
    if status:
        from app.utils.validators import validate_choice
        valid, msg = validate_choice(status, ORDER_STATUS_VALUES, "status")
        if not valid:
            return jsonify({"error": msg}), 400
        q = q.eq("status", status)

    try:
        limit = min(max(int(request.args.get("limit", 20)), 1), 100)
        offset = max(int(request.args.get("offset", 0)), 0)
    except (TypeError, ValueError):
        return jsonify({"error": MSG.PAGINATION_PARAMS_INVALID}), 400

    orders = q.order("created_at", ascending=False).limit(limit).offset(offset).execute()
    return jsonify(orders), 200


@orders_bp.route("/<order_id>", methods=["GET"])
@optional_auth
def get_order(order_id):
    """
    Get order detail. Authenticated users can only see their own orders.
    Guest orders accessible via claim_token query param.
    ---
    tags: [Orders]
    parameters:
      - in: path
        name: order_id
        type: string
        required: true
      - in: query
        name: claim_token
        type: string
    responses:
      200:
        description: Order detail
      403:
        description: Access denied
      404:
        description: Not found
    """
    import uuid as _uuid
    try:
        _uuid.UUID(order_id)
    except ValueError:
        return jsonify({"error": MSG.ORDER_NOT_FOUND}), 404

    claim_token = request.args.get("claim_token")
    _select = "*,order_items(*,order_addon_selections(name_snapshot,quantity)),delivery_windows(*),delivery_batches(rider_id,zone,status)"

    db = get_user_client()
    order = None
    if g.user_id:
        # A logged-in user's own orders are visible to them through row-level security.
        order = db.table("orders").select(_select).eq("id", order_id).single().execute()

    if not order:
        # Guest tracking: a guest order (user_id NULL) is invisible to the anon key and to other users, so
        # the lookup uses the service client. Nothing is returned unless the claim_token matches below.
        if not claim_token:
            return jsonify({"error": MSG.ORDER_NOT_FOUND}), 404
        db = get_db()
        order = db.table("orders").select(_select).eq("id", order_id).single().execute()
        if not order:
            return jsonify({"error": MSG.ORDER_NOT_FOUND}), 404
        if order.get("user_id"):
            # Already linked to an account: the token is no longer a valid way in. The owner logs in.
            return jsonify({"error": MSG.ORDER_ACCESS_DENIED}), 403

    if order.get("user_id"):
        if not g.user_id or order["user_id"] != g.user_id:
            return jsonify({"error": MSG.ORDER_ACCESS_DENIED}), 403
    else:
        # Guest order (user_id is None)
        if not claim_token or not hmac.compare_digest(str(order.get("claim_token") or ""), str(claim_token)):
            return jsonify({"error": MSG.ORDER_INVALID_CLAIM}), 403

    # Resolve the assigned rider from the persisted batch/profile relation.
    # No phone number is embedded in the response or codebase.
    if g.user_id or claim_token:
        rider = _assigned_rider_contact(db, order)
        if rider:
            order["assigned_rider"] = rider

    if order.get("is_squad_order"):
        members = db.table("squad_members").select("email,user_id,hp_share,is_registered").eq("order_id", order_id).execute() or []
        user_ids = [m["user_id"] for m in members if m.get("user_id")]
        names = {}
        if user_ids:
            profs = db.table("profiles").select("id,nickname,full_name,email,department,campus_id").in_("id", user_ids).execute() or []
            from app.services.squad_service import resolve_display_names_batch
            names = resolve_display_names_batch(profs)
        order["squad_members_detail"] = [
            {**m, "display_name": names.get(m.get("user_id"), m["email"])} for m in members
        ]

    return jsonify(order), 200


@orders_bp.route("/<order_id>/call-rider", methods=["GET"])
@require_auth
def call_assigned_rider(order_id):
    """Return a dynamic call link for the rider assigned to the order."""
    import uuid as _uuid

    try:
        _uuid.UUID(order_id)
    except (ValueError, AttributeError):
        return jsonify({"error": MSG.ORDER_NOT_FOUND}), 404

    db = get_user_client()
    order = (
        db.table("orders")
        .select("id,user_id,delivery_batches(rider_id,status)")
        .eq("id", order_id)
        .single()
        .execute()
    )
    if not order:
        return jsonify({"error": MSG.ORDER_NOT_FOUND}), 404
    if order.get("user_id") != g.user_id:
        is_squad_member = bool(
            db.table("squad_members").select("user_id").eq("order_id", order_id).eq("user_id", g.user_id).execute()
        )
        if not is_squad_member:
            return jsonify({"error": MSG.ORDER_ACCESS_DENIED}), 403

    rider = _assigned_rider_contact(db, order)
    if rider is None:
        return jsonify({"error": MSG.RIDER_NOT_ASSIGNED}), 404
    if rider.get("call_link") is None:
        return jsonify({"error": MSG.RIDER_NO_PHONE}), 404

    return jsonify({"rider": rider}), 200


@orders_bp.route("/<order_id>/status", methods=["PATCH"])
@require_role("admin", "kitchen", "rider")
def update_status(order_id):
    """
    Update order status (kitchen/rider/admin).
    ---
    tags: [Orders]
    parameters:
      - in: path
        name: order_id
        type: string
        required: true
      - in: body
        name: body
        required: true
        schema:
          required: [status]
          properties:
            status: {type: string}
            notes: {type: string}
    responses:
      200:
        description: Status updated
      400:
        description: Invalid transition
    """
    data = request.get_json(force=True) or {}
    new_status = data.get("status")
    if not new_status:
        return jsonify({"error": MSG.ORDER_STATUS_REQUIRED}), 400

    try:
        result = order_service.update_order_status(
            order_id=order_id,
            new_status=new_status,
            changed_by=g.user_id,
            notes=data.get("notes", ""),
        )
        return jsonify(result), 200
    except ValueError as e:
        return jsonify({"error": str(e)}), 400


@orders_bp.route("/<order_id>/walk", methods=["POST"])
@require_role("admin", "kitchen", "rider")
def walk_order_status(order_id):
    """
    Walk an order through all intermediate states to reach a target status in
    one request. The server resolves the shortest legal path through the state
    machine automatically (e.g. received → preparing → ready → assigned →
    out_for_delivery → delivered).

    Useful for kitchen staff who want to skip straight to 'delivered' without
    making five sequential PATCH calls.
    ---
    tags: [Orders]
    parameters:
      - in: path
        name: order_id
        type: string
        required: true
      - in: body
        name: body
        required: true
        schema:
          required: [target_status]
          properties:
            target_status:
              type: string
              example: delivered
            notes:
              type: string
    responses:
      200:
        description: Order walked to target status
        schema:
          properties:
            steps:
              type: array
              items: {type: string}
              example: [preparing, ready, assigned, out_for_delivery, delivered]
            final:
              type: object
      400:
        description: Invalid target or no path exists
    """
    data = request.get_json(force=True) or {}
    target_status = data.get("target_status")
    if not target_status:
        return jsonify({"error": MSG.ORDER_TARGET_STATUS_REQUIRED}), 400

    try:
        result = order_service.walk_order_to_status(
            order_id=order_id,
            target_status=target_status,
            changed_by=g.user_id,
            notes=data.get("notes", ""),
        )
        return jsonify(result), 200
    except ValueError as e:
        return jsonify({"error": str(e)}), 400


@orders_bp.route("/<order_id>/review/images", methods=["POST"])
@require_auth
def add_review_images(order_id):
    """Add images to an order review."""
    data = request.get_json(force=True, silent=True) or {}
    image_urls = data.get("image_urls")

    if not image_urls or not isinstance(image_urls, list):
        return jsonify({"error": MSG.REVIEW_IMAGES_REQUIRED}), 400
    from app.utils.upload_urls import is_trusted_upload_url
    if not all(is_trusted_upload_url(u) for u in image_urls):
        return jsonify({"error": MSG.UPLOAD_URL_INVALID}), 400

    db = get_user_client()
    existing = db.table("order_reviews").select("id").eq("order_id", order_id).eq("user_id", g.user_id).execute()
    if not existing:
        return jsonify({"error": MSG.REVIEW_REQUIRED_BEFORE_IMAGES}), 400
    result = (
        db.table("order_reviews")
        .eq("order_id", order_id)
        .eq("user_id", g.user_id)
        .update({
            "image_urls": image_urls,
            "updated_at": datetime.now(timezone.utc).isoformat(),
        })
    )
    if hasattr(result, "execute"):
        result = result.execute()
    if not result:
        return jsonify({"error": MSG.ORDER_NOT_FOUND}), 404

    return jsonify({"image_urls": image_urls, "message": MSG.REVIEW_IMAGES_UPLOADED}), 200


@orders_bp.route("/<order_id>/review", methods=["POST"])
@require_auth
def submit_review(order_id):
    """
    Submit an order review with optional kitchen and rider star ratings (earns HP on every review).
    Feeds into kitchen/rider performance reports via kitchen_rating and rider_rating fields.
    ---
    tags: [Orders]
    parameters:
      - in: path
        name: order_id
        type: string
        required: true
      - in: body
        name: body
        required: true
        schema:
          required: [rating]
          properties:
            rating:         {type: integer, enum: [1,2,3,4,5], description: "Overall order rating"}
            kitchen_rating: {type: integer, enum: [1,2,3,4,5], description: "Food quality / preparation (optional)"}
            rider_rating:   {type: integer, enum: [1,2,3,4,5], description: "Delivery speed / professionalism (optional)"}
            comment:        {type: string}
    responses:
      201:
        description: Review submitted, HP earned
      400:
        description: Already reviewed or order not yet delivered
    """
    db = get_user_client()
    data = request.get_json(force=True) or {}

    order = db.table("orders").select("user_id,status,campus_id").eq("id", order_id).single().execute()
    if not order:
        return jsonify({"error": MSG.ORDER_NOT_FOUND}), 404
    if order.get("user_id") != g.user_id:
        return jsonify({"error": MSG.ORDER_ACCESS_DENIED}), 403
    if order.get("status") != "delivered":
        return jsonify({"error": MSG.ORDER_REVIEW_DELIVERED_ONLY}), 400

    existing_review = (
        db.table("order_reviews")
        .select("id")
        .eq("order_id", order_id)
        .eq("user_id", g.user_id)
        .execute()
    )
    if existing_review:
        return jsonify({"error": MSG.ORDER_ALREADY_REVIEWED}), 400

    def _clamp_rating(val):
        """Parse and clamp a rating value to 1–5, or return None if not provided."""
        if val is None:
            return None
        try:
            return max(1, min(5, int(val)))
        except (TypeError, ValueError):
            return None

    # Build review payload — kitchen_rating and rider_rating are optional columns
    # added in migration 16. Included only when the caller provides them so that
    # a missing column never causes an insert failure before the migration runs.
    from app.db import SupabaseError as _SupabaseError
    review_payload = {
        "order_id": order_id,
        "user_id": g.user_id,
        "rating": max(1, min(5, int(data.get("rating", 5)))),
        "comment": data.get("comment", ""),
        "hp_awarded": 0,
        "campus_id": order.get("campus_id"),
        "kitchen_rating": _clamp_rating(data.get("kitchen_rating")),
        "rider_rating":   _clamp_rating(data.get("rider_rating")),
    }

    try:
        review = db.table("order_reviews").insert(review_payload)
    except _SupabaseError as e:
        err_text = (str(e) + str(getattr(e, "details", ""))).lower()
        if "unique" in err_text or "duplicate" in err_text:
            # A second concurrent submit landed between our own existence check and this insert
            return jsonify({"error": MSG.ORDER_ALREADY_REVIEWED}), 400
        # Only fall back if the error is specifically about missing columns.
        # Re-raise anything else so real DB errors are not silently swallowed.
        if "column" not in err_text or "does not exist" not in err_text:
            raise
        fallback = {k: v for k, v in review_payload.items()
                    if k not in ("kitchen_rating", "rider_rating")}
        review = db.table("order_reviews").insert(fallback)

    review_row = review[0] if isinstance(review, list) else review
    review_id = review_row["id"]

    try:
        _row = db.table("system_settings").select("value").eq("key", "review_hp").is_("campus_id", "null").single().execute()
        hp_amount = int(_row["value"]) if _row and _row.get("value") is not None else current_app.config["REVIEW_HP"]
    except Exception:
        hp_amount = current_app.config["REVIEW_HP"]
    earn_pending_hp(
        user_id=g.user_id,
        amount=hp_amount,
        source_type="review",
        reference_id=review_id,
        notes="HP for leaving a review",
    )
    get_db().table("order_reviews").eq("id", review_id).update({"hp_awarded": hp_amount})

    return jsonify({"review": review_row, "hp_awarded": hp_amount, "message": MSG.REVIEW_SUBMITTED}), 201


@orders_bp.route("/<order_id>/claim", methods=["POST"])
@require_auth
def claim_guest_order(order_id):
    """
    Link a guest order to a newly created account.
    ---
    tags: [Orders]
    parameters:
      - in: path
        name: order_id
        type: string
        required: true
      - in: body
        name: body
        required: true
        schema:
          required: [claim_token]
          properties:
            claim_token: {type: string}
    responses:
      200:
        description: Order linked to account
    """
    import uuid as _uuid
    try:
        _uuid.UUID(order_id)
    except ValueError:
        return jsonify({"error": MSG.ORDER_NOT_FOUND}), 404

    data = request.get_json(force=True) or {}
    claim_token = data.get("claim_token")
    if not claim_token:
        return jsonify({"error": MSG.ORDER_CLAIM_TOKEN_REQUIRED}), 400

    # A guest order has user_id NULL, so the student's own token cannot even SELECT it (RLS), and the
    # orders trigger blocks a user changing user_id directly. The server therefore does the lookup and
    # the claim with the service client. This is safe because: (1) @require_auth already verified the
    # caller, (2) p_user_id is g.user_id from that verified token, never from the request body, and
    # (3) claim_guest_order() re-checks the claim token inside the database.
    admin_db = get_db()

    order = admin_db.table("orders").select("id,user_id,claim_token").eq("id", order_id).single().execute()
    if not order:
        return jsonify({"error": MSG.ORDER_NOT_FOUND}), 404

    if order.get("user_id"):
        return jsonify({"error": MSG.ORDER_ALREADY_CLAIMED}), 400

    if not order.get("claim_token") or not hmac.compare_digest(str(order["claim_token"]), str(claim_token)):
        return jsonify({"error": MSG.ORDER_INVALID_CLAIM}), 403

    try:
        result = admin_db.rpc("claim_guest_order", {
            "p_order_id": order_id,
            "p_user_id": g.user_id,
            "p_claim_token": claim_token,
        })
        if isinstance(result, dict) and result.get("success"):
            # After the claim the student owns the order, so the normal user client can read it back.
            claimed_order = get_user_client().table("orders").select("*").eq("id", order_id).single().execute()
            if claimed_order and claimed_order.get("status") == "delivered" and not claimed_order.get("hp_credited_at"):
                # A guest who was delivered before claiming would otherwise never get
                # the HP a logged-in customer earns automatically on delivery.
                from app.services.order_service import _handle_delivery_rewards
                _handle_delivery_rewards(claimed_order)
        if isinstance(result, dict):
            result["message"] = MSG.ORDER_CLAIMED
        return jsonify(result), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 400


def _atomic_refund_response(order_id, customer_cancel=False, scheduled_only=False):
    """Keep money, refund counters and terminal state in one database transaction."""
    from decimal import Decimal, InvalidOperation
    data = request.get_json(silent=True) or {}
    if not isinstance(data, dict):
        return jsonify({'error': MSG.JSON_OBJECT_REQUIRED}), 400
    reason = data.get('reason') or (MSG.ORDER_CUSTOMER_CANCEL_REASON if customer_cancel else '')
    if not isinstance(reason, str) or not reason.strip():
        return jsonify({'error': MSG.ORDER_REFUND_REASON_REQUIRED}), 400
    reason = reason.strip()
    request_key = 'customer-cancel' if customer_cancel else data.get('idempotency_key')
    if not isinstance(request_key, str) or not request_key.strip() or len(request_key) > 200:
        return jsonify({'error': MSG.ORDER_INTENT_INVALID}), 400
    amount = None
    if not customer_cancel and data.get('refund_amount') is not None:
        try:
            value = Decimal(str(data['refund_amount']))
            if isinstance(data['refund_amount'], bool) or not value.is_finite() or value <= 0:
                raise InvalidOperation()
            amount = float(value.quantize(Decimal('0.01')))
        except (InvalidOperation, ValueError, OverflowError):
            return jsonify({'error': MSG.REFUND_AMOUNT_INVALID}), 400
    before = get_user_client().table('orders').select('id,user_id,is_scheduled,status').eq('id', order_id).single().execute()
    if not before:
        return jsonify({'error': MSG.ORDER_NOT_FOUND}), 404
    if customer_cancel and before.get('user_id') != g.user_id:
        return jsonify({'error': MSG.ORDER_CANCEL_NOT_OWNER}), 403
    if scheduled_only and not before.get('is_scheduled'):
        return jsonify({'error': MSG.ORDER_NOT_SCHEDULED_PENDING}), 409
    try:
        result = get_db().rpc('hg_refund_order_atomic', {
            'p_order_id': order_id, 'p_actor_id': g.user_id, 'p_request_key': request_key,
            'p_requested_amount': amount, 'p_reason': reason, 'p_customer_cancel': customer_cancel,
        })
    except Exception:
        logger.exception('Atomic order refund unavailable for %s', order_id)
        return jsonify({'error': MSG.SERVICE_UNAVAILABLE}), 503
    failures = {
        'forbidden': (MSG.ORDER_ACCESS_DENIED, 403),
        'order_not_found': (MSG.ORDER_NOT_FOUND, 404),
        'cannot_cancel': (MSG.ORDER_CANCEL_WRONG_STATUS, 409),
        'invalid_intent': (MSG.ORDER_INTENT_INVALID, 400),
        'invalid_amount': (MSG.REFUND_AMOUNT_INVALID, 400),
        'guest_refund_manual_required': (MSG.GUEST_REFUND_MANUAL_REQUIRED, 400),
        'refund_conservation': (MSG.REFUND_ALREADY_FULL, 409),
    }
    if not isinstance(result, dict) or not result.get('success'):
        code = result.get('error') if isinstance(result, dict) else 'refund_failed'
        logger.warning('Atomic refund refused for %s: %s', order_id, code)
        message, status = failures.get(code, (MSG.SERVICE_UNAVAILABLE, 503))
        return jsonify({'error': message, 'code': code}), status
    result['message'] = MSG.ORDER_CANCELLED_OK if customer_cancel else MSG.ORDER_REFUND_SUCCESS
    result['refund_errors'] = []
    if not result.get('idempotent'):
        try:
            from app.services.notification_service import send_notification
            send_notification(user_id=before['user_id'], notif_type='order_refunded',
                title=MSG.ORDER_REFUND_TITLE,
                body=MSG.ORDER_REFUND_BODY_WALLET.format(amount=f"{result.get('refund_amount', 0):.0f}", reason=reason),
                reference_id=order_id, reference_type='order', channels=['push','in_app','email'])
        except Exception:
            logger.exception('Refund notification unavailable for order %s', order_id)
    return jsonify(result), 200


@orders_bp.route("/<order_id>/refund", methods=["POST"])
@require_role("admin")
def refund_order(order_id):
    """
    Initiate a refund for an order (admin only).
    Credits collected payments to the customer wallet atomically. Partial refunds retain
    preparation status; full refunds close the order. Retry with the same request key.
    ---
    tags: [Orders]
    parameters:
      - in: path
        name: order_id
        type: string
        required: true
      - in: body
        name: body
        required: true
        schema:
          required: [reason, idempotency_key]
          properties:
            idempotency_key: {type: string, description: "Stable key for this refund intent and its retries"}
            reason: {type: string, description: "Reason for the refund"}
            refund_amount: {type: number, description: "Partial refund amount in Naira. Defaults to remaining refundable amount."}
    responses:
      200:
        description: Refund processed
      400:
        description: Invalid state or amount
      404:
        description: Order not found
    """
    return _atomic_refund_response(order_id)


@orders_bp.route("/scheduled", methods=["GET"])
@require_auth
def list_scheduled_orders():
    """
    List the authenticated user's upcoming scheduled orders.

    Returns orders placed with is_scheduled=True that are still in 'received'
    status (i.e. not yet promoted to preparing). Sorted by scheduled_for
    ascending so the soonest order appears first.
    ---
    tags: [Orders]
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
        description: User's pending scheduled orders
    """
    db = get_user_client()
    try:
        limit = min(max(int(request.args.get("limit", 20)), 1), 100)
        offset = max(int(request.args.get("offset", 0)), 0)
    except (TypeError, ValueError):
        return jsonify({"error": MSG.PAGINATION_PARAMS_INVALID}), 400
    orders = (
        db.table("orders")
        .select("*,order_items(name_snapshot,quantity,price_snapshot,line_total,selected_variations,options_snapshot,order_addon_selections(name_snapshot,quantity)),"
                "delivery_windows(label,starts_at,ends_at)")
        .eq("user_id", g.user_id)
        .eq("is_scheduled", "true")
        .in_("status", ["received", "paid"])
        .order("scheduled_for", ascending=True)
        .limit(limit)
        .offset(offset)
        .execute()
    ) or []
    return jsonify({"scheduled_orders": orders, "count": len(orders)}), 200


@orders_bp.route("/<order_id>/scheduled", methods=["DELETE"])
@require_auth
def cancel_scheduled_order(order_id):
    """
    Cancel a scheduled order before it is due for preparation.

    Only the order owner can cancel, and only while the order is still
    pending (is_scheduled=True, status='received'). If the order was paid
    via wallet, the amount is refunded back to the wallet.
    ---
    tags: [Orders]
    parameters:
      - in: path
        name: order_id
        type: string
        required: true
      - in: body
        name: body
        schema:
          properties:
            reason: {type: string}
    responses:
      200:
        description: Scheduled order cancelled
      403:
        description: Not the order owner
      409:
        description: Order is not a pending scheduled order
      404:
        description: Order not found
    """
    return _atomic_refund_response(order_id, customer_cancel=True, scheduled_only=True)


@orders_bp.route("/active", methods=["GET"])
@require_auth
def active_order():
    """
    Get the authenticated user's current active (in-progress) order, if any.
    ---
    tags: [Orders]
    responses:
      200:
        description: Active order or null
    """
    db = get_user_client()
    TERMINAL = ["delivered", "cancelled", "refunded"]
    rows = (
        db.table("orders")
        .select("*,order_items(id,menu_item_id,name_snapshot,quantity,price_snapshot,line_total,selected_variations,options_snapshot,order_addon_selections(name_snapshot,quantity))")
        .eq("user_id", g.user_id)
        .not_.in_("status", TERMINAL)
        .order("created_at", ascending=False)
        .limit(1)
        .execute()
    )
    order = rows[0] if rows else None
    return jsonify({"order": order}), 200


@orders_bp.route("/delivery-windows", methods=["GET"])
def list_delivery_windows():
    """
    List upcoming open delivery windows available for ordering.
    ---
    tags: [Orders]
    security: []
    responses:
      200:
        description: Available delivery windows
    """
    db = get_user_client()
    from app.routes.events import _get_campus_id
    campus_id = _get_campus_id()
    now = datetime.now(timezone.utc).isoformat()
    q = db.table("delivery_windows").select("*").gte("ends_at", now).eq("status", "open")
    if campus_id:
        q = q.eq("campus_id", campus_id)
    windows = q.order("starts_at").execute() or []
    return jsonify(windows), 200


@orders_bp.route("/delivery-windows/status", methods=["GET"])
@optional_auth
def delivery_windows_status():
    db = get_user_client()
    from app.routes.events import _get_campus_id
    campus_id = _get_campus_id()

    from app.services.order_service import get_ordering_window_status, find_next_available_ordering_slot
    status = get_ordering_window_status(get_db(), campus_id)

    # The next bookable slot is the answer to "when can I order?" — and it is
    # needed whenever ordering is not possible right now, not only when the
    # kitchen is at capacity. Search from TODAY so a kitchen that has not opened
    # yet offers today (find_next_available_ordering_slot skips windows that have
    # already closed, so after closing time this lands on the next open day).
    next_avail_date = None
    next_opens_at = None
    if not status.get("is_open"):
        from datetime import datetime, timezone, timedelta as _td
        _now_wat = datetime.now(timezone.utc) + _td(hours=1)
        next_slot = find_next_available_ordering_slot(get_db(), campus_id, start_date=_now_wat.date())
        if next_slot:
            next_avail_date = next_slot.get("date")
            next_opens_at = next_slot.get("opens_at")

    calendar = None
    if request.args.get("calendar", "").lower() == "true":
        calendar = []
        from datetime import datetime, timezone, timedelta as _td
        _now_wat_date = (datetime.now(timezone.utc) + _td(hours=1)).date()
        for i in range(7):
            d = _now_wat_date + _td(days=i)
            st = get_ordering_window_status(get_db(), campus_id, for_date=d)
            calendar.append({
                "date": st["date"],
                "is_open": st["is_open"],
                "any_capacity_remaining": st["any_capacity_remaining"],
            })

    return jsonify({
        "is_open": status.get("is_open", False),
        "reason": status.get("reason"),
        "windows": status.get("windows", []),
        "any_capacity_remaining": status.get("any_capacity_remaining", False),
        "next_available_date": next_avail_date,
        "next_opens_at": next_opens_at,
        "calendar": calendar,
    }), 200


@orders_bp.route("/delivery-zones", methods=["GET"])
def list_delivery_zones():
    """
    List delivery zones with fees and estimated delivery times.
    ---
    tags: [Orders]
    security: []
    responses:
      200:
        description: Delivery zones
    """
    db = get_user_client()
    from app.routes.events import _get_campus_id
    campus_id = _get_campus_id()
    q = db.table("delivery_zones").select("*").eq("is_active", "true")
    if campus_id:
        q = q.eq("campus_id", campus_id)
    zones = q.order("name").execute() or []
    return jsonify(zones), 200


@orders_bp.route("/validate-promo", methods=["POST"])
@optional_auth
def validate_promo():
    """
    Validate a promo code against an order subtotal without applying it.
    Thin wrapper around the same promo logic used at checkout, so
    discount previews shown pre-checkout always match what create_order applies.
    ---
    tags: [Orders]
    security: []
    parameters:
      - in: body
        name: body
        required: true
        schema:
          required: [code, order_subtotal]
          properties:
            code: {type: string}
            order_subtotal: {type: number}
    responses:
      200:
        description: Promo code valid with discount info
      400:
        description: Invalid, expired, or inapplicable code
    """
    data = request.get_json(force=True) or {}
    code = (data.get("code") or "").strip()
    try:
        subtotal = float(data.get("order_subtotal", 0))
    except (TypeError, ValueError):
        return jsonify({"error": MSG.ERR_BAD_REQUEST}), 400

    if not code:
        return jsonify({"error": MSG.AUTH_FIELD_REQUIRED.format(field="code")}), 400

    # _apply_promo (order_service.py) only ever reads g.campus_id, which is never set
    # for a guest — so a guest's campus selection (via ?campus_id=/X-Campus-ID, same as
    # every other guest-facing route in this file) would otherwise be silently ignored,
    # letting them validate a promo that isn't actually theirs to use. Check it here first.
    from app.routes.events import _get_campus_id
    campus_id = _get_campus_id()
    if campus_id:
        db = get_user_client()
        promo_campus = db.table("promo_codes").select("campus_id").eq("code", code.upper()).eq("is_active", "true").single().execute()
        if promo_campus and promo_campus.get("campus_id") and promo_campus["campus_id"] != campus_id:
            return jsonify({"error": MSG.ORDER_PROMO_INVALID.format(code=code)}), 400

    try:
        result = order_service._apply_promo(getattr(g, "user_id", None), code, subtotal)
    except ValueError as e:
        return jsonify({"error": str(e)}), 400

    return jsonify({
        "valid": True,
        "code": code.upper(),
        "calculated_discount": result["discount"],
        "promo_code_id": result["promo_code_id"],
        "message": MSG.PROMO_CODE_VALID,
    }), 200


@orders_bp.route("/<order_id>/cancel", methods=["POST"])
@require_auth
def cancel_order(order_id):
    """
    Cancel an order. Only the order owner can cancel, and only while status is 'received'.
    ---
    tags: [Orders]
    parameters:
      - in: path
        name: order_id
        type: string
        required: true
      - in: body
        name: body
        schema:
          properties:
            reason: {type: string}
    responses:
      200:
        description: Order cancelled
      403:
        description: Not the order owner
      409:
        description: Order cannot be cancelled at this stage
      404:
        description: Order not found
    """
    return _atomic_refund_response(order_id, customer_cancel=True)


@orders_bp.route("/<order_id>/reorder", methods=["POST"])
@require_auth
def reorder(order_id):
    """
    Fetch items from a past order to pre-populate a new order (reorder helper).
    Returns items with current menu prices — does not create an order.
    ---
    tags: [Orders]
    parameters:
      - in: path
        name: order_id
        type: string
        required: true
    responses:
      200:
        description: Reorder item list with current prices
      403:
        description: Not the order owner
      404:
        description: Order not found
    """
    import uuid as _uuid
    try:
        _uuid.UUID(order_id)
    except (ValueError, AttributeError):
        return jsonify({"error": MSG.ORDER_NOT_FOUND}), 404

    db = get_user_client()
    order = (
        db.table("orders")
        .select("id,user_id")
        .eq("id", order_id)
        .single()
        .execute()
    )
    if not order:
        return jsonify({"error": MSG.ORDER_NOT_FOUND}), 404
    if order.get("user_id") != g.user_id:
        return jsonify({"error": MSG.ORDER_ACCESS_DENIED}), 403

    past_items = (
        db.table("order_items")
        .select("menu_item_id,name_snapshot,quantity,price_snapshot")
        .eq("order_id", order_id)
        .execute()
    ) or []

    from app.routes.events import _get_campus_id
    campus_id = _get_campus_id()

    enriched = []
    for item in past_items:
        current_price = item.get("price_snapshot")
        is_available = False
        try:
            menu = (
                db.table("menu_items")
                .select("price,is_available,name")
                .eq("id", item["menu_item_id"])
                .is_("deleted_at", "null")
                .single()
                .execute()
            )
            if menu:
                current_price = float(menu.get("price", current_price))
                is_available = bool(menu.get("is_available", False))
                # mirror create_order's per-campus override (menu_item_availability)
                availability = None
                if campus_id:
                    try:
                        availability = (
                            db.table("menu_item_availability")
                            .select("is_available,price_override")
                            .eq("menu_item_id", item["menu_item_id"])
                            .eq("campus_id", campus_id)
                            .single()
                            .execute()
                        )
                    except Exception as exc:
                        # Falls back to the base menu price. If the override existed, the
                        # customer is now charged a different amount than intended.
                        logger.warning("reorder: availability/price_override read failed for item %s: %s",
                                       item["menu_item_id"], exc)
                        availability = None
                if availability:
                    is_available = is_available and bool(availability.get("is_available"))
                    if availability.get("price_override") is not None:
                        current_price = float(availability["price_override"])
        except Exception as exc:
            # Not the override lookup itself (that one logs above) but the price read
            # around it. Silent here means the item's price quietly changes.
            logger.warning("reorder: pricing failed for item %s, using the snapshot price: %s",
                           item.get("menu_item_id"), exc)

        enriched.append({
            "menu_item_id": item["menu_item_id"],
            "name": item.get("name_snapshot"),
            "quantity": item.get("quantity", 1),
            "current_price": current_price,
            "is_available": is_available,
        })

    return jsonify({"message": MSG.ORDER_REORDER_ITEMS, "items": enriched, "original_order_id": order_id}), 200


@orders_bp.route("/<order_id>/share", methods=["POST"])
@require_auth
def record_order_share(order_id):
    """
    Record that the user shared their order confirmation (e.g. on WhatsApp).
    Awards 25 HP (pending) — max once per day across all orders.
    ---
    tags: [Orders]
    parameters:
      - in: path
        name: order_id
        type: string
        required: true
      - in: body
        name: body
        schema:
          properties:
            platform: {type: string, description: "Share platform. Default: whatsapp"}
    responses:
      200:
        description: Share recorded and HP awarded (or already claimed today)
      404:
        description: Order not found
    """
    db = get_user_client()
    order = (
        db.table("orders")
        .select("id,user_id,status")
        .eq("id", order_id)
        .eq("user_id", g.user_id)
        .single()
        .execute()
    )
    if not order:
        return jsonify({"error": MSG.SHARE_PROMPT_ORDER_NOT_FOUND}), 404

    share_date_val = today_wat()
    today_start = (datetime.combine(share_date_val, datetime.min.time(), tzinfo=timezone.utc) - WAT_OFFSET).isoformat()

    already_today = (
        db.table("order_share_events")
        .select("id")
        .eq("user_id", g.user_id)
        .gte("created_at", today_start)
        .limit(1)
        .execute()
    )
    if already_today:
        return jsonify({"message": MSG.SHARE_PROMPT_ALREADY_TODAY, "hp_awarded": 0}), 200

    try:
        _row = db.table("system_settings").select("value").eq("key", "share_prompt_hp").is_("campus_id", "null").single().execute()
        hp_to_award = int(_row["value"]) if _row and _row.get("value") is not None else current_app.config.get("SHARE_PROMPT_HP", 25)
    except Exception:
        hp_to_award = current_app.config.get("SHARE_PROMPT_HP", 25)

    from app.services.streak_service import check_monthly_cap, update_monthly_tracker
    cap_check = check_monthly_cap(g.user_id, hp_to_award)
    actual_hp = cap_check["capped_amount"] if cap_check["allowed"] else 0

    now = datetime.now(timezone.utc).isoformat()
    platform = (request.get_json(force=True) or {}).get("platform", "whatsapp")

    from app.db import SupabaseError
    try:
        db.table("order_share_events").insert({
            "user_id": g.user_id,
            "order_id": order_id,
            "platform": platform,
            "hp_awarded": actual_hp,
            "created_at": now,
            "share_date": share_date_val.isoformat(),
        })
    except SupabaseError as e:
        # test 2 currently carries two identical unique indexes on (user_id, share_date)
        # (order_share_events_user_day_uniq and _user_date_key) — Postgres reports whichever
        # is older, so both names are matched here rather than trusting the doc's exact string.
        err_text = str(e) + str(getattr(e, "details", ""))
        if "order_share_events_user_day_uniq" in err_text or "order_share_events_user_date_key" in err_text:
            return jsonify({"message": MSG.SHARE_PROMPT_ALREADY_TODAY, "hp_awarded": 0}), 200
        raise

    if actual_hp > 0:
        from app.services.hp_service import earn_pending_hp
        earn_pending_hp(
            user_id=g.user_id,
            amount=actual_hp,
            source_type="social",
            reference_id=order_id,
            notes=f"Order share on {platform} — {actual_hp} HP pending",
        )
        update_monthly_tracker(g.user_id, actual_hp)

    return jsonify({
        "message": resolve_msg(MSG.SHARE_PROMPT_HP_TITLE, hp=actual_hp) if actual_hp else MSG.SHARE_PROMPT_ALREADY_TODAY,
        "hp_awarded": actual_hp,
        "platform": platform,
    }), 200


@orders_bp.route("/<order_id>/squad-members", methods=["POST"])
@require_auth
def add_squad_members(order_id):
    """
    Add squad members to a squad order for HP splitting.
    Non-registered emails receive an auto-invite for referral attribution.
    ---
    tags: [Orders]
    parameters:
      - in: path
        name: order_id
        type: string
        required: true
      - in: body
        name: body
        required: true
        schema:
          required: [emails]
          properties:
            emails:
              type: array
              items: {type: string}
              description: Email addresses of squad participants
            split_hp:
              type: boolean
              description: Whether to split HP with squad. Default true.
    responses:
      200:
        description: Squad members recorded, HP split queued
      400:
        description: Validation error
      404:
        description: Order not found or not yours
    """
    db = get_user_client()
    order = (
        db.table("orders")
        .select("id,user_id,status,hp_earned,campus_id,squad_id")
        .eq("id", order_id)
        .eq("user_id", g.user_id)
        .single()
        .execute()
    )
    if not order:
        return jsonify({"error": MSG.ORDER_NOT_FOUND}), 404

    # B-8: refuse to add members to an already delivered order (true split would overpay)
    if order.get("status") == "delivered":
        return jsonify({"error": "Cannot add squad members to a delivered order"}), 409

    data = request.get_json(force=True) or {}
    emails = [e.strip().lower() for e in (data.get("emails") or []) if e and e.strip()]
    user_ids = [u.strip() for u in (data.get("user_ids") or []) if u and u.strip()]
    if user_ids:
        try:
            # Use service client for user_id -> email lookup (privacy + RLS)
            u_profiles = get_db().table("profiles").select("id,email,campus_id").in_("id", user_ids).execute() or []
            for p in (u_profiles if isinstance(u_profiles, list) else []):
                if p.get("email"):
                    # Same-campus check for user_ids as well
                    if order.get("campus_id") and p.get("campus_id") and p.get("campus_id") != order.get("campus_id"):
                        continue
                    emails.append(p["email"].strip().lower())
        except Exception as exc:
            logger.warning("squad invite: profile lookup failed for %s, those users are not invited: %s",
                           user_ids, exc)
    emails = list(dict.fromkeys(emails))
    if not emails:
        return jsonify({"error": "At least one email or user_id is required"}), 400

    split_hp = data.get("split_hp", True)
    organizer_profile = (
        db.table("profiles").select("id,nickname,full_name,email,department,campus_id,referral_code").eq("id", g.user_id).single().execute()
    ) or {}
    from app.services.squad_service import resolve_display_name
    organizer_name = resolve_display_name(profile=organizer_profile) if organizer_profile else "Someone"
    order_campus_id = order.get("campus_id")
    squad_id_for_order = order.get("squad_id")
    frontend_url = current_app.config.get("FRONTEND_URL", "")

    from app.services.notification_service import send_notification
    results = []
    successfully_added_names = []
    now = datetime.now(timezone.utc).isoformat()

    for email in emails:
        existing_member = (
            db.table("squad_members")
            .select("id")
            .eq("order_id", order_id)
            .eq("email", email)
            .single()
            .execute()
        )
        if existing_member:
            results.append({"email": email, "status": "already_added"})
            continue

        # B-7: profile lookup must use service client, only id and campus_id, same-campus only
        profile = None
        try:
            svc = get_db()
            prof_row = svc.table("profiles").select("id,campus_id").eq("email", email).single().execute()
            if prof_row:
                # Same-campus guard: accept only if profile campus matches order campus
                if order_campus_id and prof_row.get("campus_id") and prof_row.get("campus_id") != order_campus_id:
                    profile = None  # treat as not found for privacy / campus isolation
                else:
                    profile = prof_row
        except Exception as exc:
            logger.warning("squad invite: service lookup failed for %s: %s", email, exc)
            profile = None

        member_payload = {
            "order_id": order_id,
            "email": email,
            "hp_share": 0,
            "invite_sent": False,
            "is_registered": bool(profile),
            "referral_attributed": False,
            "created_at": now,
            "campus_id": order_campus_id,
        }
        if profile:
            member_payload["user_id"] = profile["id"]

        try:
            db.table("squad_members").insert(member_payload).execute()
        except Exception:
            results.append({"email": email, "status": "error"})
            continue

        # For display, resolve via service client without leaking to caller
        display_name = email
        if profile:
            try:
                # Resolve display name via service client (nickname-first)
                from app.services.squad_service import resolve_display_name as _resolve
                full_prof = get_db().table("profiles").select("id,nickname,full_name,email,department,campus_id").eq("id", profile["id"]).single().execute()
                display_name = _resolve(profile=full_prof) if full_prof else email
            except Exception:
                display_name = email
        successfully_added_names.append(display_name)

        if squad_id_for_order:
            try:
                db.table("squad_roster").insert({
                    "squad_id": squad_id_for_order, "email": email,
                    "user_id": profile["id"] if profile else None,
                }).execute()
            except Exception as exc:
                logger.warning("squad roster: insert failed for %s on order %s: %s", email, order_id, exc)

        if not profile:
            # Send auto-invite for referral vector — only for truly unregistered emails after B-7 fix
            ref_code = organizer_profile.get("referral_code", "")
            invite_link = f"{frontend_url}/register?ref={ref_code}&email={email}" if ref_code else f"{frontend_url}/register?email={email}"
            try:
                from app.utils.email import send_email
                send_email(
                    to_email=email,
                    to_name="",
                    template_key="squad_invite",
                    data={
                        "organizer": organizer_name,
                        "invite_link": invite_link,
                    },
                )
                db.table("squad_members").eq("order_id", order_id).eq("email", email).update({"invite_sent": True}).execute()
            except Exception:
                pass
            results.append({"email": email, "status": "invited"})
        else:
            # Notify registered user
            try:
                send_notification(
                    user_id=profile["id"],
                    notif_type="squad_order",
                    template_data={"organizer": organizer_name},
                )
            except Exception:
                pass
            results.append({"email": email, "status": "notified"})

    if successfully_added_names:
        member_desc = (
            successfully_added_names[0] if len(successfully_added_names) == 1
            else f"{len(successfully_added_names)} people"
        )
        try:
            send_notification(
                user_id=g.user_id, notif_type="squad_member_added",
                template_data={"member_desc": member_desc}, channels=["push"],
            )
        except Exception:
            pass

    # If order is already delivered and split_hp is enabled, distribute HP now
    # Note: delivered check above already returns 409, so this branch is now only for race safety
    if split_hp and order.get("status") == "delivered" and order.get("hp_earned", 0) > 0:
        from app.services.squad_service import distribute_squad_hp
        distribute_squad_hp(order_id, order["hp_earned"], g.user_id, campus_id=order_campus_id)

    return jsonify({"message": "Squad members recorded", "results": results}), 200


@orders_bp.route("/<order_id>/squad-members", methods=["GET"])
@require_auth
def get_order_squad_members(order_id):
    db = get_user_client()
    order = db.table("orders").select("id,user_id").eq("id", order_id).eq("user_id", g.user_id).single().execute()
    if not order:
        return jsonify({"error": MSG.ORDER_NOT_FOUND}), 404
    members = db.table("squad_members").select("*").eq("order_id", order_id).execute() or []
    return jsonify(members), 200


@orders_bp.route("/<order_id>/squad-members/<member_id>", methods=["DELETE"])
@require_auth
def remove_order_squad_member(order_id, member_id):
    """Order-scoped trim only — roster untouched."""
    db = get_user_client()
    order = db.table("orders").select("id,user_id,status").eq("id", order_id).eq("user_id", g.user_id).single().execute()
    if not order:
        return jsonify({"error": MSG.ORDER_NOT_FOUND}), 404
    if order.get("status") == "delivered":
        return jsonify({"error": "Cannot modify squad members after delivery"}), 400
    db.table("squad_members").eq("id", member_id).eq("order_id", order_id).delete()
    return jsonify({"message": "Removed from this order"}), 200


@orders_bp.route("/<order_id>/squad-members/<member_id>/resend", methods=["POST"])
@require_auth
def resend_squad_invite(order_id, member_id):
    """Force-resend, always allowed."""
    db = get_user_client()
    order = db.table("orders").select("id,user_id").eq("id", order_id).eq("user_id", g.user_id).single().execute()
    if not order:
        return jsonify({"error": MSG.ORDER_NOT_FOUND}), 404
    member = db.table("squad_members").select("email,is_registered").eq("id", member_id).eq("order_id", order_id).single().execute()
    if not member or member.get("is_registered"):
        return jsonify({"error": "Nothing to resend"}), 400
    organizer_profile = db.table("profiles").select("nickname,full_name,email,department,campus_id,referral_code").eq("id", g.user_id).single().execute() or {}
    from app.services.squad_service import resolve_display_name
    from app.utils.email import send_email
    frontend_url = current_app.config.get("FRONTEND_URL", "")
    ref_code = organizer_profile.get("referral_code", "")
    invite_link = f"{frontend_url}/register?ref={ref_code}&email={member['email']}" if ref_code else f"{frontend_url}/register"
    try:
        send_email(to_email=member["email"], to_name="", template_key="squad_invite",
                   data={"organizer": resolve_display_name(profile=organizer_profile), "invite_link": invite_link})
    except Exception as exc:
        logger.warning("resend_squad_invite: send_email failed for %s: %s", member["email"], exc)
        return jsonify({"error": MSG.SQUAD_INVITE_RESEND_FAILED}), 502
    db.table("squad_members").eq("id", member_id).update({"invite_sent": True})
    return jsonify({"message": "Invite resent"}), 200


@orders_bp.route("/<order_id>/history", methods=["GET"])
@require_auth
def order_status_history(order_id):
    """
    Get the full status change history for an order.
    ---
    tags: [Orders]
    parameters:
      - in: path
        name: order_id
        type: string
        required: true
    responses:
      200:
        description: List of status transitions with timestamps and actor info
      404:
        description: Order not found or not accessible
    """
    import uuid as _uuid
    try:
        _uuid.UUID(order_id)
    except (ValueError, AttributeError):
        return jsonify({"error": MSG.ORDER_NOT_FOUND}), 404

    db = get_user_client()
    order = (
        db.table("orders")
        .select("id,user_id,campus_id,delivery_batches(rider_id)")
        .eq("id", order_id)
        .single()
        .execute()
    )
    if not order:
        return jsonify({"error": MSG.ORDER_NOT_FOUND}), 404

    role = getattr(g, "user_role", None)
    has_access = False
    if role == "super_admin":
        has_access = True
    elif role == "admin":
        order_campus_id = order.get("campus_id")
        user_campus_id = getattr(g, "campus_id", None)
        has_access = not order_campus_id or (order_campus_id == user_campus_id)
    elif role == "rider":
        batch = order.get("delivery_batches")
        if isinstance(batch, list):
            batch = batch[0] if batch else None
        rider_id = batch.get("rider_id") if isinstance(batch, dict) else None
        has_access = bool(rider_id and rider_id == g.user_id)
    elif role == "kitchen":
        order_campus_id = order.get("campus_id")
        user_campus_id = getattr(g, "campus_id", None)
        has_access = bool(order_campus_id and user_campus_id and order_campus_id == user_campus_id)
    else:
        has_access = bool(order.get("user_id") and order.get("user_id") == g.user_id)

    if not has_access:
        return jsonify({"error": MSG.ORDER_ACCESS_DENIED}), 403

    history = (
        db.table("order_status_logs")
        .select("*")
        .eq("order_id", order_id)
        .order("created_at", ascending=True)
        .execute()
    )
    return jsonify(history), 200
