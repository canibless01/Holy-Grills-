"""
app/services/newsletter_service.py — per-campus newsletters.

  * signed unsubscribe tokens (no login needed, cannot be forged without SECRET_KEY)
  * plain-text -> safe HTML newsletter with an unsubscribe footer
  * delivery engine used by the Celery task `send_newsletter_campaigns` (runs every 5 minutes)

Delivery guarantees
  * one row per (campaign, subscriber) in newsletter_deliveries, UNIQUE(campaign_id, subscriber) — the row is
    INSERTED BEFORE the email is sent, so a retry, a crash or two overlapping runs can never email a person twice
  * a subscriber who unsubscribes while a campaign is running is skipped (the audience is re-read every batch)
  * a campaign can be cancelled while it is sending (checked every 10 emails)
  * a campaign is never sent unless the unsubscribe link can point at the real frontend
"""
import html as _html
import os
import time
from datetime import datetime, timedelta, timezone
from urllib.parse import quote

from flask import current_app
from itsdangerous import BadSignature, URLSafeSerializer

from app.db import SupabaseError, get_db
from app.messages import MSG
from app.utils.logger import get_logger

logger = get_logger(__name__)

_SALT = "newsletter-unsubscribe"
BATCH_SIZE = int(os.environ.get("NEWSLETTER_BATCH_SIZE", "100"))            # emails per campaign per run
STALE_DELIVERY_MINUTES = 15                                                 # a delivery stuck in 'sending' longer than this is treated as failed
PAGE_SIZE = 100                                                             # subscribers read per query (the id list goes in the URL: 200 ids = ~7,970 chars, right at the ~8 KB gateway limit; 100 = ~4,070)
SEND_INTERVAL_SECONDS = float(os.environ.get("NEWSLETTER_SEND_INTERVAL", "0.6"))   # Resend allows ~2 req/s
TIME_BUDGET_SECONDS = int(os.environ.get("NEWSLETTER_TIME_BUDGET", "240"))  # cron lock expires after 20 min


# ───────────────────────────── unsubscribe tokens ─────────────────────────────
def _serializer():
    return URLSafeSerializer(current_app.config["SECRET_KEY"], salt=_SALT)


def make_unsubscribe_token(email: str) -> str:
    return _serializer().dumps(str(email).strip().lower())


def read_unsubscribe_token(token: str):
    """Email inside a valid token, else None."""
    try:
        email = _serializer().loads(token)
    except BadSignature:
        return None
    return email if isinstance(email, str) and email else None


def frontend_base_ok() -> bool:
    base = (current_app.config.get("FRONTEND_URL") or "").strip()
    return bool(base) and "localhost" not in base and "127.0.0.1" not in base


def unsubscribe_links(token: str):
    """(page_url, one_click_api_url|None). page_url is the frontend page that POSTs the token back."""
    frontend = (current_app.config.get("FRONTEND_URL") or "").rstrip("/")
    page = f"{frontend}/newsletter/unsubscribe?token={quote(token, safe='')}"
    api = (os.environ.get("API_PUBLIC_URL") or "").rstrip("/")
    one_click = f"{api}/api/storefront/newsletter/unsubscribe?token={quote(token, safe='')}" if api else None
    return page, one_click


# ───────────────────────────── email body ─────────────────────────────
def build_newsletter_html(body_text: str, unsubscribe_url: str, app_name: str, tagline: str) -> str:
    safe_body = _html.escape(str(body_text or "").strip()).replace("\r\n", "\n").replace("\n", "<br>")
    safe_url = _html.escape(unsubscribe_url, quote=True)
    return (
        "<html><body style='font-family:sans-serif;max-width:600px;margin:auto;padding:20px'>"
        f"<div>{safe_body}</div><br>"
        f"<p style='color:#888;font-size:12px'>— {_html.escape(str(tagline or ''))}</p>"
        "<hr style='border:none;border-top:1px solid #eee'>"
        f"<p style='color:#888;font-size:12px'>{_html.escape(MSG.NEWSLETTER_UNSUBSCRIBE_FOOTER.format(app_name=str(app_name or 'Holy Grills')))} "
        f"<a href='{safe_url}'>{_html.escape(MSG.NEWSLETTER_UNSUBSCRIBE_LINK)}</a></p>"
        "</body></html>"
    )


def clean_subject(subject: str) -> str:
    return " ".join(str(subject or "").split())[:200]


def _default_sender(to_email, to_name, subject, html_body, headers=None) -> bool:
    from app.utils.email import send_email_raw
    return send_email_raw(to_email, to_name, subject, html_body, headers=headers)


def _compose(email, name, subject, body, app_name, tagline):
    token = make_unsubscribe_token(email)
    page, one_click = unsubscribe_links(token)
    headers = None
    if one_click:
        headers = {"List-Unsubscribe": f"<{one_click}>", "List-Unsubscribe-Post": "List-Unsubscribe=One-Click"}
    return clean_subject(subject), build_newsletter_html(body, page, app_name, tagline), headers


def send_test(email, name, subject, body, sender=None) -> bool:
    """One-off preview to the admin's own address. Nothing is stored."""
    sender = sender or _default_sender
    app_name = current_app.config.get("APP_NAME", "Holy Grills")
    tagline = current_app.config.get("APP_TAGLINE", "")
    subj, html, headers = _compose(email, name, subject, body, app_name, tagline)
    return bool(sender(email, name or "there", f"[TEST] {subj}", html, headers))


# ───────────────────────────── delivery engine ─────────────────────────────
def _now():
    return datetime.now(timezone.utc).isoformat()


def _campaign_status(db, campaign_id):
    row = db.table("newsletter_campaigns").select("status").eq("id", campaign_id).limit(1).execute()
    return row[0]["status"] if row else None


def _audience_page(db, campaign, last_id):
    q = (db.table("newsletter_subscriptions").select("id,email,full_name")
         .is_("unsubscribed_at", "null").eq("is_confirmed", "true"))
    if campaign.get("campus_id"):
        q = q.eq("campus_id", campaign["campus_id"])
    if campaign.get("created_at"):                     # people who subscribed after the campaign was queued are not part of it
        q = q.lte("created_at", campaign["created_at"])
    if last_id:
        q = q.gt("id", last_id)
    return q.order("id").limit(PAGE_SIZE).execute() or []


def _process_one(db, campaign, deadline, sender):
    cid = campaign["id"]
    out = {"sent": 0, "failed": 0, "done": False}

    if not frontend_base_ok():
        db.table("newsletter_campaigns").eq("id", cid).update({
            "status": "failed", "completed_at": _now(),
            "last_error": MSG.NEWSLETTER_FRONTEND_URL_MISSING})
        logger.error("newsletter campaign %s not sent: FRONTEND_URL missing/localhost", cid)
        out["done"] = True
        return out

    if campaign["status"] == "queued":
        claimed = db.table("newsletter_campaigns").eq("id", cid).eq("status", "queued").update(
            {"status": "sending", "started_at": _now()})
        if not claimed:                       # cancelled (or claimed elsewhere) between read and claim
            return out

    app_name = current_app.config.get("APP_NAME", "Holy Grills")
    tagline = current_app.config.get("APP_TAGLINE", "")
    sent_now = failed_now = 0
    stale_cut = (datetime.now(timezone.utc) - timedelta(minutes=STALE_DELIVERY_MINUTES)).isoformat()
    stale = (db.table("newsletter_deliveries").eq("campaign_id", cid).eq("status", "sending").lt("created_at", stale_cut)
             .update({"status": "failed", "error": "interrupted before the send was confirmed"}))
    failed_now += len(stale) if isinstance(stale, list) else 0     # a worker died mid-send: counted as failed, never re-sent (no double email)
    attempted = 0
    last_id = None
    exhausted = False
    stopped = False

    while True:
        page = _audience_page(db, campaign, last_id)
        if not page:
            exhausted = True
            break
        last_id = page[-1]["id"]
        ids = [s["id"] for s in page]
        done_rows = (db.table("newsletter_deliveries").select("subscription_id")
                     .eq("campaign_id", cid).in_("subscription_id", ids).execute()) or []
        already = {r["subscription_id"] for r in done_rows}

        for sub in page:
            if sub["id"] in already:
                continue
            if attempted >= BATCH_SIZE or time.monotonic() > deadline:
                stopped = True
                break
            if attempted and attempted % 10 == 0 and _campaign_status(db, cid) == "cancelled":
                stopped = True
                break
            try:                                                   # claim BEFORE sending: unique(campaign, subscriber)
                delivery = db.table("newsletter_deliveries").insert(
                    {"campaign_id": cid, "subscription_id": sub["id"], "status": "sending"})
            except SupabaseError as e:
                if str((e.details or {}).get("code")) == "23505":
                    continue                                       # another run already owns this recipient
                raise
            attempted += 1
            ok, err = False, "send failed"
            try:
                subj, html, headers = _compose(sub["email"], sub.get("full_name"), campaign["subject"], campaign["body"], app_name, tagline)
                ok = bool(sender(sub["email"], sub.get("full_name") or "there", subj, html, headers))
            except Exception as e:                                 # a bad address / provider hiccup must not stop the campaign
                err = f"{type(e).__name__}: {e}"[:300]
                logger.error("newsletter %s: send to subscriber %s raised: %s", cid, sub["id"], e)
            row_id = (delivery[0] if isinstance(delivery, list) and delivery else delivery or {}).get("id")
            upd = {"status": "sent", "sent_at": _now()} if ok else {"status": "failed", "error": err}
            if row_id:
                db.table("newsletter_deliveries").eq("id", row_id).update(upd)
            if ok:
                sent_now += 1
            else:
                failed_now += 1
            time.sleep(SEND_INTERVAL_SECONDS)
        if stopped:
            break
        if len(page) < PAGE_SIZE:
            exhausted = True
            break

    fresh = db.table("newsletter_campaigns").select("status,sent_count,failed_count").eq("id", cid).limit(1).execute()
    cur = fresh[0] if fresh else {"status": None, "sent_count": 0, "failed_count": 0}
    sent_total = (cur.get("sent_count") or 0) + sent_now
    failed_total = (cur.get("failed_count") or 0) + failed_now
    patch = {"sent_count": sent_total, "failed_count": failed_total}
    if cur.get("status") == "cancelled":
        patch["completed_at"] = _now()
        out["done"] = True
    elif exhausted:
        patch.update({"status": "sent" if failed_total == 0 else "partial", "completed_at": _now(),
                      "total_recipients": sent_total + failed_total})
        out["done"] = True
    db.table("newsletter_campaigns").eq("id", cid).update(patch)
    out["sent"], out["failed"] = sent_now, failed_now
    return out


def process_campaigns(sender=None, max_seconds=None) -> dict:
    """Deliver the next batch of every queued / sending campaign. Called by the Celery task (under a cron lock)."""
    sender = sender or _default_sender
    db = get_db()
    deadline = time.monotonic() + (max_seconds if max_seconds is not None else TIME_BUDGET_SECONDS)
    campaigns = (db.table("newsletter_campaigns").select("*").in_("status", ["queued", "sending"])
                 .order("created_at").limit(20).execute()) or []
    summary = {"campaigns": 0, "sent": 0, "failed": 0, "completed": 0}
    for c in campaigns:
        if time.monotonic() > deadline:
            break
        try:
            r = _process_one(db, c, deadline, sender)
        except Exception as e:                                     # one broken campaign must not block the others
            logger.error("newsletter campaign %s failed: %s", c.get("id"), e, exc_info=True)
            try:
                db.table("newsletter_campaigns").eq("id", c["id"]).update({"last_error": str(e)[:300]})
            except Exception as exc:
                logger.warning("newsletter: could not record last_error for campaign %s: %s",
                                c.get("id"), exc)
            continue
        summary["campaigns"] += 1
        summary["sent"] += r["sent"]
        summary["failed"] += r["failed"]
        summary["completed"] += 1 if r["done"] else 0
    return summary
