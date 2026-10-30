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
        logger.info("onesignal: user %s ready (%s)", external_id, response.status_code)
        return True
    # 404 app id / 401 key: nothing to retry, and saying so once is enough. The body
    # is the only place OneSignal says *why*, so keep it in the log.
    logger.warning("onesignal: create user %s rejected (%s): %s",
                   external_id, response.status_code, response.text[:300])
    return False


def ensure_email_subscription(user_id, email, enabled=True, details=None):
    """Link `email` to the OneSignal user `user_id`. Returns True when linked.

    Pass a dict as `details` to collect what OneSignal actually answered, which the
    admin endpoint returns so a failure can be diagnosed without reading server logs.

    `enabled=False` marks an existing subscription unsubscribed (the user opted out
    of email in the app), which stops OneSignal mailing them even if a send slips
    through. No-op when OneSignal is not configured.
    """
    if details is None:
        details = {}
    details.setdefault("user_id", user_id)
    details.setdefault("email", email)
    if not user_id or not email or "@" not in str(email):
        details.update({"linked": False, "reason": "missing_user_or_email"})
        return False
    try:
        app_id, api_key = _creds()
    except Exception as exc:                                      # noqa: BLE001
        logger.warning("onesignal: credentials unavailable: %s", exc)
        details.update({"linked": False, "reason": "credentials_unavailable"})
        return False
    if not app_id or not api_key:
        details.update({"linked": False, "reason": "onesignal_not_configured"})
        return False
    if not _ensure_user(app_id, api_key, user_id):
        details.update({"linked": False, "reason": "user_create_failed"})
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
        details.update({"linked": False, "reason": f"network_{type(exc).__name__}"})
        return False
    body = {}
    try:
        parsed = response.json()
        if isinstance(parsed, dict):
            body = parsed
    except (ValueError, TypeError):
        body = {}
    subscription = body.get("subscription") if isinstance(body.get("subscription"), dict) else {}
    details.update({
        "http_status": response.status_code,
        "subscription_id": subscription.get("id") or body.get("id"),
        "subscription_type": subscription.get("type"),
        "enabled": subscription.get("enabled", enabled),
        "errors": body.get("errors") or (None if response.ok else response.text[:300]),
    })
    if response.status_code in (200, 201, 202):
        logger.info("onesignal: email subscription %s for user %s", "enabled" if enabled else "disabled", user_id)
        details["linked"] = True
        return True
    logger.warning("onesignal: email subscription for %s rejected (%s): %s",
                   user_id, response.status_code, response.text[:200])
    details["linked"] = False
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

    Every signed-up account is an email subscriber, whatever it answered about
    promotions: OneSignal will not deliver to an address it does not know, so an
    unregistered address means the order confirmation, the QR code and the password
    reset never arrive either. Promotions are a *separate* decision, enforced by
    `notification_preferences.category_for_notification`/`permitted_channels` before
    anything is dispatched, and by `include_unsubscribed=False` on marketing sends.

    So the only thing that switches the subscription off is the master email switch
    (`email_enabled = False`, i.e. "no email from us at all").
    """
    prefs = prefs or {}
    return prefs.get("email_enabled") is not False


def _preferences_by_user(user_ids):
    """email_enabled per account, best effort.

    Read separately rather than as an embedded relation: this client's PostgREST
    query builder has no nested select support, and an embedded select that fails
    took the whole sweep down with it (see the .range() bug below).
    """
    if not user_ids:
        return {}
    try:
        from app.db import get_db
        rows = (get_db().table("notification_preferences")
                .select("user_id,email_enabled")
                .in_("user_id", list(user_ids))
                .limit(len(user_ids)).execute() or [])
    except Exception as exc:                                      # noqa: BLE001
        logger.warning("onesignal: backfill could not read preferences (defaulting to on): %s", exc)
        return {}
    return {row.get("user_id"): row for row in rows if isinstance(row, dict) and row.get("user_id")}


def backfill_email_subscriptions(limit=500, offset=0):
    """Register the email subscription for accounts that predate this sync.

    New sign-ups and logins are covered already; this is for the accounts that never
    sign in again — the reason OneSignal reported 0 email subscribers on an app with
    plenty of active accounts. Returns a small summary; never raises.

    Paging uses limit/offset: `TableQuery` in app/db.py implements those, not
    `range()` — the first version of this function called `.range()` and every sweep
    died with `'TableQuery' object has no attribute 'range'` before reading a row.
    """
    summary = {"checked": 0, "linked": 0, "failed": 0, "skipped": 0}
    try:
        from app.db import get_db
        rows = (get_db().table("profiles")
                .select("id,email,is_active,email_notifications")
                .order("created_at")
                .limit(max(1, int(limit)))
                .offset(max(0, int(offset)))
                .execute() or [])
    except Exception as exc:                                      # noqa: BLE001
        logger.warning("onesignal: backfill could not read profiles: %s", exc)
        return summary
    rows = [row for row in rows if isinstance(row, dict)]
    preferences = _preferences_by_user([row.get("id") for row in rows if row.get("id")])
    for row in rows:
        summary["checked"] += 1
        email = row.get("email")
        user_id = row.get("id")
        # Deactivated accounts and profiles without an address are not subscribers.
        if not user_id or not email or row.get("is_active") is False:
            summary["skipped"] += 1
            continue
        # Everyone is registered as a subscriber; only the master email opt-out
        # leaves it switched off. Promotion preferences do not gate this — they gate
        # which messages we ask OneSignal to send.
        prefs = dict(preferences.get(user_id) or {})
        if row.get("email_notifications") is False:
            prefs["email_enabled"] = False
        details = {}
        if ensure_email_subscription(user_id, email, enabled=enabled_from_preferences(prefs),
                                     details=details):
            summary["linked"] += 1
        else:
            summary["failed"] += 1
            # One line per failure with the provider's answer: a sweep that silently
            # reports "0 linked" is what sent us to the server logs in the first place.
            logger.warning("onesignal: backfill could not link %s: %s", user_id,
                           details.get("errors") or details.get("reason") or details)
    logger.info("onesignal: email subscription backfill %s", summary)
    return summary
