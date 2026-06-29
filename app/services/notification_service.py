"""
Notification Service — dispatches in-app, email, and push notifications.
All notification records written to the notifications table.
Email and push dispatch via OneSignal (fire-and-forget, never raises).
"""

import os
import threading
import requests as http_requests
from datetime import datetime, timezone
from app.db import get_db
from flask import current_app


_ONESIGNAL_BASE = os.environ.get("ONESIGNAL_BASE_URL", "https://api.onesignal.com")


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
    Write notification record(s) for each channel and dispatch externally.
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
            "metadata": {
                "reference_id": reference_id,
                "reference_type": reference_type,
            },
        }
        try:
            result = db.table("notifications").insert(record)
            saved = result[0] if isinstance(result, list) else result
            records.append(saved)

            if channel == "email":
                t = threading.Thread(
                    target=_dispatch_email_async,
                    args=(user_id, title, body, saved.get("id", "")),
                    daemon=True,
                )
                t.start()
            elif channel == "push":
                t = threading.Thread(
                    target=_dispatch_push_async,
                    args=(user_id, title, body, action_url, saved.get("id", "")),
                    daemon=True,
                )
                t.start()
        except Exception as e:
            print(f"[NotificationService] Error saving {channel} notification for {user_id}: {e}")

    return records


def send_blast(blast_id: str) -> dict:
    """
    Send a notification blast to a segment of users.
    """
    db = get_db()
    blast = db.table("notification_blasts").select("*").eq("id", blast_id).single().execute()
    if not blast:
        raise ValueError("Blast not found")

    segment = blast.get("segment") or {}
    profiles_query = db.table("profiles").select("id").eq("is_active", "true")
    if segment.get("tier_id"):
        user_tier_rows = (
            db.table("profiles")
            .select("id")
            .eq("current_tier_id", segment["tier_id"])
            .eq("is_active", "true")
            .execute()
        )
        user_ids = [r["id"] for r in user_tier_rows]
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

    db.table("notification_blasts").eq("id", blast_id).update({"status": "sent"})
    return {"sent_to": count}


def mark_read(notification_id: str, user_id: str) -> dict:
    db = get_db()
    updated = (
        db.table("notifications")
        .eq("id", notification_id)
        .eq("user_id", user_id)
        .update({"read_at": datetime.now(timezone.utc).isoformat()})
    )
    return updated[0] if isinstance(updated, list) else updated


# ─────────────────────────────────────────────────────────────────────────────
# External dispatch helpers — fire-and-forget, never raise
# ─────────────────────────────────────────────────────────────────────────────

def _get_onesignal_creds() -> tuple:
    """Return (app_id, api_key) from env. Returns ('','') if not configured."""
    app_id = os.environ.get("ONESIGNAL_APP_ID", "")
    api_key = os.environ.get("ONESIGNAL_API_KEY", "")
    return app_id, api_key


def _dispatch_email_async(user_id: str, subject: str, body: str, notification_id: str):
    """
    Send a transactional email via OneSignal to the user's registered email address.
    Looks up user email from profiles. Silently skips if credentials or email not found.
    """
    try:
        app_id, api_key = _get_onesignal_creds()
        if not app_id or not api_key:
            return

        from app.utils.email import get_user_email_and_name
        email, name = get_user_email_and_name(user_id)
        if not email:
            return

        from_email = os.environ.get("EMAIL_FROM", "noreply@holygrills.ng")
        from_name = os.environ.get("EMAIL_FROM_NAME", "Holy Grills")
        app_tagline = os.environ.get("APP_TAGLINE", "Holy Grills FUTA")

        body_html = body.replace("\n", "<br>")
        full_html = (
            f"<html><body style='font-family:sans-serif;max-width:600px;margin:auto;padding:20px'>"
            f"<p>Hi {name},</p>"
            f"<p>{body_html}</p>"
            f"<br><p style='color:#888;font-size:12px'>— {app_tagline}</p>"
            f"</body></html>"
        )

        payload = {
            "app_id": app_id,
            "include_email_tokens": [email],
            "email_subject": subject,
            "email_body": full_html,
            "email_from_name": from_name,
            "email_from_address": from_email,
        }

        resp = http_requests.post(
            f"{_ONESIGNAL_BASE}/notifications",
            headers={"Authorization": f"Key {api_key}", "Content-Type": "application/json"},
            json=payload,
            timeout=10,
        )
        if resp.status_code not in (200, 202):
            print(f"[NotificationService] OneSignal email error {resp.status_code}: {resp.text[:200]}")
    except Exception as e:
        print(f"[NotificationService] Email dispatch error for {user_id}: {e}")


def _dispatch_push_async(user_id: str, title: str, body: str, action_url: str, notification_id: str):
    """
    Send a push notification via OneSignal using user_id as external_id.
    Requires user to have a registered push subscription with their user_id as external_id.
    Silently skips if credentials not configured or user not subscribed.
    """
    try:
        app_id, api_key = _get_onesignal_creds()
        if not app_id or not api_key:
            return

        payload = {
            "app_id": app_id,
            "include_aliases": {"external_id": [user_id]},
            "target_channel": "push",
            "headings": {"en": title},
            "contents": {"en": body},
        }
        if action_url:
            payload["url"] = action_url

        resp = http_requests.post(
            f"{_ONESIGNAL_BASE}/notifications",
            headers={"Authorization": f"Key {api_key}", "Content-Type": "application/json"},
            json=payload,
            timeout=10,
        )
        if resp.status_code not in (200, 202):
            print(f"[NotificationService] OneSignal push error {resp.status_code}: {resp.text[:200]}")
    except Exception as e:
        print(f"[NotificationService] Push dispatch error for {user_id}: {e}")
