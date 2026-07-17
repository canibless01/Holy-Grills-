"""
Gift Service — first-order hot dog gift logic.

Called by order_service when a user's first order reaches 'delivered' status.
Checks system_settings for the toggle and launch window, then inserts a
first_order_gifts row and flags the order with gift_included=True.

Notification timeline:
  - On grant (delivered): user notified, kitchen notified, gift row inserted
  - On rider assignment: user notified (GIFT_ASSIGNED)
  - On return (failed delivery): status → 'returned', user notified

Gift is also inserted into order_items with is_gift=True and price=0.
"""

from datetime import datetime, timezone, date
from app.db import get_db
from app.utils.logger import get_logger
from app.messages import MSG

logger = get_logger(__name__)


def _get_setting(db, key: str, default: str) -> str:
    try:
        row = db.table("system_settings").select("value").eq("key", key).single().execute()
        return row.get("value", default) if row else default
    except Exception:
        return default


def maybe_grant_first_order_gift(user_id: str, order_id: str) -> dict:
    """
    Check if user qualifies for the first-order hot dog gift and grant it.

    Conditions:
    1. first_order_gift_enabled = 'true' in system_settings
    2. Today is on or before launch_window_end_date in system_settings
    3. User has no prior completed orders (this is their FIRST)
    4. No existing first_order_gifts row for this user

    On grant:
    - Inserts first_order_gifts row (status='pending')
    - Inserts gift into order_items (is_gift=True, price=0)
    - Flags the order with gift_included=True
    - Notifies the user (push+in_app)
    - Notifies kitchen staff (push+in_app)

    Returns {"granted": bool, "reason": str}
    """
    db = get_db()
    try:
        enabled = _get_setting(db, "first_order_gift_enabled", "false")
        if enabled.lower() != "true":
            return {"granted": False, "reason": "gift_disabled"}

        end_date_str = _get_setting(db, "launch_window_end_date", "")
        if end_date_str:
            try:
                end_date = date.fromisoformat(end_date_str)
                if date.today() > end_date:
                    return {"granted": False, "reason": "launch_window_closed"}
            except ValueError:
                pass

        # Check if user already has a gift record
        existing_gift = (
            db.table("first_order_gifts")
            .select("id")
            .eq("user_id", user_id)
            .single()
            .execute()
        )
        if existing_gift:
            return {"granted": False, "reason": "already_granted"}

        # Verify this is truly their first completed order
        prior_orders = (
            db.table("orders")
            .select("id")
            .eq("user_id", user_id)
            .eq("status", "delivered")
            .neq("id", order_id)
            .limit(1)
            .execute()
        )
        if prior_orders:
            return {"granted": False, "reason": "not_first_order"}

        now = datetime.now(timezone.utc).isoformat()

        # Insert gift record
        db.table("first_order_gifts").insert({
            "user_id": user_id,
            "order_id": order_id,
            "status": "pending",
            "created_at": now,
        })

        # Insert gift as an order_item (is_gift=True, price=0) so it appears on the receipt
        gift_item_name = _get_setting(db, "first_order_gift_item_name", "First-Order Gift — Hot Dog")
        try:
            # NOTE: order_items has no `is_gift` column in the live schema (schema
            # drift vs. this file's original design) — the gift marker is stored
            # in options_snapshot (jsonb) instead so it still round-trips on the
            # receipt without requiring a DB migration.
            db.table("order_items").insert({
                "order_id": order_id,
                "name_snapshot": gift_item_name,
                "quantity": 1,
                "price_snapshot": 0.0,
                "line_total": 0.0,
                "options_snapshot": {"is_gift": True},
                "hp_earn_snapshot": 0,
                "is_addon": False,
            })
        except Exception as e:
            logger.warning("maybe_grant_first_order_gift: order_items insert failed for order %s: %s", order_id, e)

        # Flag the order
        db.table("orders").eq("id", order_id).update({"gift_included": True})

        from app.services.notification_service import send_notification

        # Notify the user
        send_notification(
            user_id=user_id,
            notif_type="first_order_gift",
            template_data={},
        )

        # Notify kitchen/admin staff
        try:
            short_id = order_id[:8].upper()
            kitchen_staff = (
                db.table("profiles")
                .select("id")
                .in_("role", ["admin", "kitchen"])
                .eq("is_active", "true")
                .execute()
            ) or []
            for member in kitchen_staff:
                send_notification(
                    user_id=member["id"],
                    notif_type="gift_granted",
                    template_data={"order_id": short_id},
                )
        except Exception as e:
            logger.warning("maybe_grant_first_order_gift: kitchen notify failed: %s", e)

        logger.info("first_order_gift: granted to user %s for order %s", user_id, order_id)
        return {"granted": True, "reason": "ok"}

    except Exception as e:
        logger.error("maybe_grant_first_order_gift: error for user %s: %s", user_id, e)
        return {"granted": False, "reason": str(e)}


def notify_gift_rider_assigned(user_id: str, order_id: str) -> None:
    """
    Called when a rider is assigned to deliver a first-order gift.
    Sends push+in_app notification to the user.
    """
    try:
        from app.services.notification_service import send_notification
        send_notification(
            user_id=user_id,
            notif_type="gift_rider_assigned",
            template_data={},
            reference_id=order_id,
            reference_type="order",
        )
    except Exception as e:
        logger.error("notify_gift_rider_assigned: error for user %s: %s", user_id, e)


def mark_gift_returned(user_id: str, order_id: str) -> dict:
    """
    Mark a first-order gift as 'returned' (failed delivery).
    Sends push+in_app notification to the user.
    """
    db = get_db()
    try:
        # NOTE: first_order_gifts has no `updated_at` column in the live schema
        # (only `created_at`) — drop it from the update payload to avoid a
        # hard failure on every gift-return.
        db.table("first_order_gifts").eq("order_id", order_id).update({
            "status": "returned",
        })
        from app.services.notification_service import send_notification
        send_notification(
            user_id=user_id,
            notif_type="gift_returned",
            template_data={},
        )
        return {"marked_returned": True}
    except Exception as e:
        logger.error("mark_gift_returned: error for user %s: %s", user_id, e)
        return {"marked_returned": False, "error": str(e)}
