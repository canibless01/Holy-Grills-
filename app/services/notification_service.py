"""
Notification Service — dispatches in-app, email, and push notifications.
All notification records written to the notifications table.
Email and push are fire-and-forget (async via Celery in production).
"""

import requests as http_requests
from datetime import datetime, timezone
from app.db import get_db
from flask import current_app


def send_notification(
    user_id: str,
    notif_type: str,
    title: str,
    body: str,
    reference_id: str = None,
    reference_type: str = None,
    action_url: str = None,
    channels: list = None,
) -> list:
    """
    Write notification record(s) for each channel.
    channels: list of 'in_app' | 'email' | 'push'
    """
    if channels is None:
        channels = ["in_app"]

    db = get_db()
    records = []
    now = datetime.now(timezone.utc).isoformat()

    for channel in channels:
        record = {
            "user_id": user_id,
            "type": notif_type,
            "channel": channel,
            "title": title,
            "body": body,
            "action_url": action_url,
            "reference_id": reference_id,
            "reference_type": reference_type,
            "is_read": False,
            "is_delivered": False,
        }
        try:
            result = db.table("notifications").insert(record)
            saved = result[0] if isinstance(result, list) else result
            records.append(saved)

            if channel == "email":
                _dispatch_email_async(user_id, title, body, saved["id"])
            elif channel == "push":
                _dispatch_push_async(user_id, title, body, action_url, saved["id"])
        except Exception as e:
            print(f"[NotificationService] Error saving {channel} notification: {e}")

    return records


def send_blast(blast_id: str) -> dict:
    """
    Send a notification blast to a segment of users.
    Reads from notification_blasts table, dispatches to all matching users.
    """
    db = get_db()
    blast = db.table("notification_blasts").select("*").eq("id", blast_id).single().execute()
    if not blast:
        raise ValueError("Blast not found")

    segment = blast.get("target_segment") or {}
    profiles_query = db.table("profiles").select("id").eq("is_active", "true")
    if segment.get("tier_id"):
        user_tier_rows = (
            db.table("user_tiers")
            .select("user_id")
            .eq("tier_id", segment["tier_id"])
            .eq("is_current", "true")
            .execute()
        )
        user_ids = [r["user_id"] for r in user_tier_rows]
        profiles_query = profiles_query.in_("id", user_ids)

    profiles = profiles_query.execute()
    channels = blast.get("channels", ["in_app"])
    count = 0

    for profile in profiles:
        send_notification(
            user_id=profile["id"],
            notif_type="blast",
            title=blast["title"],
            body=blast["body"],
            channels=channels,
        )
        count += 1

    db.table("notification_blasts").eq("id", blast_id).update({
        "is_sent": True,
        "sent_at": datetime.now(timezone.utc).isoformat(),
        "recipient_count": count,
    })
    return {"sent_to": count}


def mark_read(notification_id: str, user_id: str) -> dict:
    db = get_db()
    updated = (
        db.table("notifications")
        .eq("id", notification_id)
        .eq("user_id", user_id)
        .update({"is_read": True, "read_at": datetime.now(timezone.utc).isoformat()})
    )
    return updated[0] if isinstance(updated, list) else updated


def _dispatch_email_async(user_id: str, subject: str, body: str, notification_id: str):
    """Placeholder for async email dispatch via Celery/SendGrid."""
    pass


def _dispatch_push_async(user_id: str, title: str, body: str, action_url: str, notification_id: str):
    """Placeholder for async Web Push dispatch via VAPID."""
    pass
