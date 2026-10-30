"""Keep OneSignal's *email* subscriptions in step with our own accounts.

Why this exists
---------------
Push and email are different OneSignal subscriptions. The web SDK creates the push
one when the visitor allows notifications, and `initOneSignal()` links it to the
account with `login(external_id)`. **Nothing ever created an email subscription** —
so a OneSignal app that sent a campaign to "all users" had almost no email
recipients: the dashboard shows them as email subscribers, and ours were not.

The email address is ours (it lives on `profiles`), so the backend registers it:

    POST /apps/{app_id}/users                      (create the user, external_id = profile id)
    POST /apps/{app_id}/users/by/external_id/{id}/subscriptions
         {"subscription": {"type": "Email", "token": "<address>", "enabled": true}}

Both calls are best-effort. Registration must never fail because OneSignal is down,
misconfigured or slow, so every failure is logged and swallowed, and the profile row
stays the source of truth for who we may email (the app's own `email_notifications`
and `promotions` preferences still gate every send).
"""

import os

import requests

from app.utils.logger import get_logger

logger = get_logger(__name__)

_ONESIGNAL_BASE = os.environ.get("ONESIGNAL_BASE_URL", "https://api.onesignal.com")
_TIMEOUT = 8


def _creds():
    from app.services.notification_service import _get_onesignal_creds
    return _get_onesignal_creds()


def _headers(api_key):
    return {"Authorization": f"Key {api_key}", "Content-Type": "application/json"}


def _ensure_user(app_id, api_key, external_id):
    """Create the OneSignal user if it is new. 409 means it already exists."""
    try:
        response = requests.post(
            f"{_ONESIGNAL_BASE}/apps/{app_id}/users",
            headers=_headers(api_key),
            json={"identity": {"external_id": str(external_id)}},
            timeout=_TIMEOUT,
        )
    except requests.RequestException as exc:
        logger.warning("onesignal: create user %s failed: %s", external_id, type(exc).__name__)
        return False
    if response.status_code in (200, 201, 202, 409):
        return True
    # 404 app id / 401 key: nothing to retry, and saying so once is enough.
    logger.warning("onesignal: create user %s rejected (%s): %s",
                   external_id, response.status_code, response.text[:200])
    return False


def ensure_email_subscription(user_id, email, enabled=True):
    """Link `email` to the OneSignal user `user_id`. Returns True when linked.

    `enabled=False` marks an existing subscription unsubscribed (the user opted out
    of email in the app), which stops OneSignal mailing them even if a send slips
    through. No-op when OneSignal is not configured.
    """
    if not user_id or not email or "@" not in str(email):
        return False
    try:
        app_id, api_key = _creds()
    except Exception as exc:                                      # noqa: BLE001
        logger.warning("onesignal: credentials unavailable: %s", exc)
        return False
    if not app_id or not api_key:
        return False
    if not _ensure_user(app_id, api_key, user_id):
        return False
    try:
        response = requests.post(
            f"{_ONESIGNAL_BASE}/apps/{app_id}/users/by/external_id/{user_id}/subscriptions",
            headers=_headers(api_key),
            json={"subscription": {"type": "Email", "token": str(email), "enabled": bool(enabled)}},
            timeout=_TIMEOUT,
        )
    except requests.RequestException as exc:
        logger.warning("onesignal: email subscription for %s failed: %s", user_id, type(exc).__name__)
        return False
    if response.status_code in (200, 201, 202):
        logger.info("onesignal: email subscription %s for user %s", "enabled" if enabled else "disabled", user_id)
        return True
    logger.warning("onesignal: email subscription for %s rejected (%s): %s",
                   user_id, response.status_code, response.text[:200])
    return False


def sync_email_subscription_async(user_id, email, enabled=True):
    """Fire-and-forget wrapper: registration and preference changes never wait on it."""
    import threading
    threading.Thread(
        target=lambda: ensure_email_subscription(user_id, email, enabled),
        daemon=True,
    ).start()


def enabled_from_preferences(prefs):
    """Is the account still willing to receive mail at all?

    OneSignal's `enabled` flag is the coarse switch: transactional mail is sent with
    `include_unsubscribed`, so it still arrives when this is False, while marketing
    mail respects it. We only keep it on when the user has not opted out of email or
    of promotions.
    """
    prefs = prefs or {}
    return prefs.get("email_enabled") is not False and prefs.get("promotions") is not False


def sync_from_preferences(user_id, email, prefs):
    """Apply a saved preference change to OneSignal (fire-and-forget)."""
    return sync_email_subscription_async(user_id, email, enabled=enabled_from_preferences(prefs))


def backfill_email_subscriptions(limit=500, offset=0):
    """Register the email subscription for accounts that predate this sync.

    New sign-ups and logins are covered already; this is for the accounts that never
    sign in again — the reason OneSignal reported 0 email subscribers on an app with
    plenty of active accounts. Returns a small summary; never raises.
    """
    summary = {"checked": 0, "linked": 0, "failed": 0, "skipped": 0}
    try:
        from app.db import get_db
        rows = (get_db().table("profiles")
                .select("id,email,is_active,email_notifications,notification_preferences(promotions,email_enabled)")
                .range(offset, offset + max(0, int(limit)) - 1)
                .execute() or [])
    except Exception as exc:                                      # noqa: BLE001
        logger.warning("onesignal: backfill could not read profiles: %s", exc)
        return summary
    for row in rows:
        if not isinstance(row, dict):
            continue
        summary["checked"] += 1
        email = row.get("email")
        user_id = row.get("id")
        # Deactivated accounts and profiles without an address are not subscribers.
        if not user_id or not email or row.get("is_active") is False:
            summary["skipped"] += 1
            continue
        # Register everyone, but only leave the address subscribed when the account
        # has not opted out — the backfill must not quietly re-subscribe an opt-out.
        prefs = row.get("notification_preferences")
        if isinstance(prefs, list):
            prefs = prefs[0] if prefs else {}
        prefs = dict(prefs or {})
        if row.get("email_notifications") is False:
            prefs["email_enabled"] = False
        if ensure_email_subscription(user_id, email, enabled=enabled_from_preferences(prefs)):
            summary["linked"] += 1
        else:
            summary["failed"] += 1
    logger.info("onesignal: email subscription backfill %s", summary)
    return summary
