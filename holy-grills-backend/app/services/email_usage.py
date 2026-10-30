"""Daily per-provider email send accounting, used to pre-empt a known provider limit.

Why this exists
---------------
`send_email_routed` already fails over when a provider *says* it is out of quota
(HTTP 429, `daily_quota_exceeded`, "monthly email limit"). That is reactive and it
only works if the provider reports the rejection in a shape we recognise. Resend's
free plan is 100 messages/day; if a rejection is mis-shaped, rate-limited away or
simply never returned, every send after the limit fails and the user gets nothing.

So we also count our own accepted sends, per provider, per day (Africa/Lagos day —
the business day the rest of the backend uses). When the preferred provider has
already used its configured allowance, the router starts with the other one.

Rules that keep this honest
---------------------------
* **Fallback, not authority.** `EMAIL_DAILY_LIMIT_<PROVIDER>` of 0 (or unset, for
  OneSignal) means "unknown/unlimited" — no pre-emption, the old path decides.
* **Fail open.** A missing table (migration not applied), an RPC error or a read
  timeout must never stop an email. Every function here swallows its own failure
  and returns None/False.
* **Count only accepted sends.** An attempt the provider rejected is not counted,
  otherwise a broken provider would look "used up" and we would silently switch.
"""

import os
from datetime import date, datetime

from app.db import get_db
from app.utils.logger import get_logger
from app.utils.tz import today_wat

logger = get_logger(__name__)

PROVIDERS = ("resend", "onesignal")

# Hard ceilings are configuration, not policy: an operator with a paid plan raises
# or removes them. 0 disables pre-emption for that provider entirely.
_DEFAULT_LIMITS = {"resend": 100, "onesignal": 0}


def daily_limit(provider: str) -> int:
    """Configured sends/day for `provider`; 0 means unlimited/unknown."""
    if provider not in PROVIDERS:
        return 0
    raw = os.environ.get(f"EMAIL_DAILY_LIMIT_{provider.upper()}")
    if raw is None or str(raw).strip() == "":
        return _DEFAULT_LIMITS[provider]
    try:
        value = int(str(raw).strip())
    except (TypeError, ValueError):
        logger.warning("email usage: EMAIL_DAILY_LIMIT_%s is not a number — ignoring it", provider.upper())
        return _DEFAULT_LIMITS[provider]
    return max(0, value)


def _today() -> date:
    try:
        return today_wat()
    except Exception:                                             # noqa: BLE001
        return datetime.utcnow().date()


def sent_today(provider: str) -> int | None:
    """Accepted sends recorded for `provider` today, or None when unreadable."""
    try:
        counts = get_db().rpc("hg_email_send_counts", {"p_day": _today().isoformat()})
    except Exception as exc:                                      # noqa: BLE001
        logger.warning("email usage: counter read failed (%s) — limit check skipped", exc)
        return None
    if isinstance(counts, dict):
        try:
            return int(counts.get(provider) or 0)
        except (TypeError, ValueError):
            return None
    if isinstance(counts, list) and counts and isinstance(counts[0], dict):
        try:
            return int(counts[0].get(provider) or 0)              # RPC returned a row
        except (TypeError, ValueError):
            return None
    return 0


def _count_result(result) -> int | None:
    if isinstance(result, bool):                                  # bool is an int; it is not a count
        return None
    if isinstance(result, int):
        return result
    if isinstance(result, list) and result:
        first = result[0]
        if isinstance(first, int) and not isinstance(first, bool):
            return first
        if isinstance(first, dict):                               # RPC returned a row
            try:
                return int(first.get("hg_record_email_send") or first.get("sent_count") or 0)
            except (TypeError, ValueError):
                return None
    if isinstance(result, dict):
        try:
            return int(result.get("sent_count") or result.get("count") or 0)
        except (TypeError, ValueError):
            return None
    return None


def reserve(provider: str) -> int | None:
    """Claim one send slot for `provider` before sending.

    Returns the count *after* the claim, or None when the counter is unreadable (the
    caller then sends anyway — a bookkeeping outage must never stop mail).

    Reserving before the send is what makes the fallback hold under a burst: with a
    read-then-send, 200 simultaneous registrations can all read "98 of 100" and all
    pick the provider that has two slots left. Here the database decides.
    """
    if provider not in PROVIDERS:
        return None
    try:
        result = get_db().rpc("hg_record_email_send", {"p_provider": provider, "p_day": _today().isoformat()})
    except Exception as exc:                                      # noqa: BLE001
        logger.warning("email usage: could not reserve a %s slot: %s", provider, exc)
        return None
    return _count_result(result)


def release(provider: str) -> bool:
    """Give a claimed slot back after a send that definitely did not happen.

    Not for ambiguous failures (timeout, 5xx): that message may have been accepted,
    so it stays counted.
    """
    if provider not in PROVIDERS:
        return False
    try:
        get_db().rpc("hg_release_email_send", {"p_provider": provider, "p_day": _today().isoformat()})
        return True
    except Exception as exc:                                      # noqa: BLE001
        logger.warning("email usage: could not release a %s slot: %s", provider, exc)
        return False


def over_limit(provider: str, count: int | None) -> bool:
    """Is `count` (a claimed slot) past `provider`'s configured allowance?"""
    limit = daily_limit(provider)
    return bool(limit > 0 and count is not None and count > limit)


def reserve_slot(preferred: str) -> tuple[str, int | None]:
    """Claim a slot on `preferred`, or on the other provider when it is full.

    Returns (provider, count_after_claim). The slot is already counted, so the caller
    must `release()` it if the send definitely does not happen.

    When both providers are at their limit the preferred one is kept: an over-limit
    attempt can still succeed on a provider that counts differently from us, and
    pretending both are unusable would drop the mail entirely.
    """
    preferred = preferred if preferred in PROVIDERS else "resend"
    count = reserve(preferred)
    if not over_limit(preferred, count):
        return preferred, count
    alternate = "onesignal" if preferred == "resend" else "resend"
    alt_count = reserve(alternate)
    if over_limit(alternate, alt_count):
        release(alternate)                                        # that slot is not used
        logger.warning("email usage: both providers are at today's limit — keeping %s", preferred)
        return preferred, count
    release(preferred)
    logger.warning("email usage: %s is at %s/%s today — sending on %s instead",
                   preferred, count, daily_limit(preferred), alternate)
    return alternate, alt_count


def health() -> dict:
    """What the admin panel shows: today's counts, limits and whether each is configured."""
    from app.utils import email as email_utils
    today = _today().isoformat()
    counts = {}
    try:
        raw = get_db().rpc("hg_email_send_counts", {"p_day": today})
        counts = raw if isinstance(raw, dict) else {}
    except Exception as exc:                                      # noqa: BLE001
        logger.warning("email usage: health read failed: %s", exc)
    resend_key = bool(email_utils._resend_api_key())
    try:
        from app.services.notification_service import _get_onesignal_creds
        app_id, api_key = _get_onesignal_creds()
        onesignal_ready = bool(app_id and api_key)
    except Exception:                                             # noqa: BLE001
        onesignal_ready = False
    providers = []
    for provider in PROVIDERS:
        used = counts.get(provider)
        limit = daily_limit(provider)
        providers.append({
            "provider": provider,
            "configured": resend_key if provider == "resend" else onesignal_ready,
            "sent_today": used,
            "daily_limit": limit or None,
            "remaining": max(0, limit - int(used)) if limit and used is not None else None,
            # A provider at its limit is the one the router bypasses.
            "exhausted": bool(limit and used is not None and int(used) >= limit),
        })
    return {"date": today, "providers": providers, "counters_available": bool(counts)}
