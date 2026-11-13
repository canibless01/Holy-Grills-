"""
app/services/newsletter_service.py — per-campus newsletters.

  * signed unsubscribe tokens (no login needed, cannot be forged without SECRET_KEY)
  * plain-text -> safe HTML newsletter with an unsubscribe footer
  * delivery engine used by the Celery task `send_newsletter_campaigns` (uses the configured campaign scan interval)

Delivery guarantees
  * one row per (campaign, subscriber) in newsletter_deliveries, UNIQUE(campaign_id, subscriber) — the row is
    INSERTED BEFORE the email is sent, so a retry, a crash or two overlapping runs can never email a person twice
  * a subscriber who unsubscribes while a campaign is running is skipped (the audience is re-read every batch)
  * campaign cancellation and subscriber eligibility are checked atomically for each handoff
  * a campaign is never sent unless the unsubscribe link can point at the real frontend
"""
import html as _html
import os
import time
from datetime import datetime, timedelta, timezone
from urllib.parse import quote

from flask import current_app
from itsdangerous import BadSignature, URLSafeSerializer

from app.db import get_db
from app.messages import MSG
from app.utils.logger import get_logger

logger = get_logger(__name__)

_SALT = "newsletter-unsubscribe"
BATCH_SIZE = int(os.environ.get("NEWSLETTER_BATCH_SIZE", "100"))            # emails per campaign per run
STALE_DELIVERY_MINUTES = 15                                                 # a delivery stuck in 'sending' longer than this is treated as uncertain
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
    from app.utils.email import public_api_base
    one_click = f"{public_api_base()}/storefront/newsletter/unsubscribe?token={quote(token, safe='')}" if api else None
    return page, one_click


# ───────────────────────────── email body ─────────────────────────────
def build_newsletter_html(body_text: str, unsubscribe_url: str, app_name: str, tagline: str) -> str:
    """Build a branded newsletter HTML using the shared email layout."""
    from app.utils.email import _build_html
    # Newsletters are marketing emails, so we keep the "Thank you" message
    # but skip the shared brand sign-off since newsletters have their own tone
    # inside the campaign body
    return _build_html(
        "there",  # Newsletter doesn't have personal name
        body_text,
        tagline,
        skip_greeting=True,  # Newsletters have their own greeting in body
        skip_signoff=True,  # Newsletters have their own sign-off in body
        skip_thank_you=False,  # Keep the "Thank you for being part of our community!"
        unsubscribe_url=unsubscribe_url,
    )


def clean_subject(subject: str) -> str:
    return " ".join(str(subject or "").split())[:200]


def _default_sender(to_email, to_name, subject, html_body, headers=None) -> bool:
    from app.utils.email import send_email_routed
    receipt={}
    accepted=send_email_routed(to_email,to_name,subject,html_body,provider='resend',headers=headers,transactional=False,receipt=receipt)
    final=receipt.get('fallback') or receipt
    status=final.get('http_status') or 0
    if not accepted and (final.get('state')=='unknown' or status>=500 or status in (200,201,408)):
        raise RuntimeError(MSG.NEWSLETTER_SEND_UNCERTAIN)
    return accepted


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
    try:return bool(sender(email, name or "there", f"[TEST] {subj}", html, headers))
    except Exception:return False


# ───────────────────────────── delivery engine ─────────────────────────────
def _now():
    return datetime.now(timezone.utc).isoformat()


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
        db.table("newsletter_campaigns").eq("id", cid).in_("status",["queued","sending"]).update({
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
    (db.table("newsletter_deliveries").eq("campaign_id", cid).eq("status", "sending").lt("created_at", stale_cut)
             .update({"status": "uncertain", "error": MSG.NEWSLETTER_SEND_UNCERTAIN}))
    # Unconfirmed handoffs are not counted as confirmed provider failures or retried.
    attempted = 0
    last_id = None
    stopped = False

    while True:
        page = _audience_page(db, campaign, last_id)
        if not page:
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
            # Prepare before claiming so cancellation/unsubscribe changes during
            # rendering are rechecked at the last durable provider boundary.
            subj, html, headers = _compose(sub["email"], sub.get("full_name"), campaign["subject"], campaign["body"], app_name, tagline)
            delivery=db.rpc('hg_claim_newsletter_delivery',{'p_campaign':cid,'p_subscription':sub['id'],'p_email':sub['email']})
            if not delivery:
                continue
            if not isinstance(delivery,dict) or not delivery.get('id'):
                raise RuntimeError('Invalid newsletter handoff receipt')
            attempted += 1
            ok, err = False, "send failed"
            uncertain=False
            try:
                ok = bool(sender(sub["email"], sub.get("full_name") or "there", subj, html, headers))
            except Exception as e:                                 # a bad address / provider hiccup must not stop the campaign
                uncertain=True
                err=MSG.NEWSLETTER_SEND_UNCERTAIN
                logger.error("newsletter %s: send to subscriber %s raised: %s", cid, sub["id"], e)
            row_id = (delivery[0] if isinstance(delivery, list) and delivery else delivery or {}).get("id")
            upd = {"status": "sent", "sent_at": _now()} if ok else {"status": "uncertain" if uncertain else "failed", "error": err}
            if row_id:
                db.table("newsletter_deliveries").eq("id", row_id).update(upd)
            if ok:
                sent_now += 1
            elif not uncertain:
                failed_now += 1
            time.sleep(SEND_INTERVAL_SECONDS)
        if stopped:
            break
        if len(page) < PAGE_SIZE:
            break

    saved=db.rpc('hg_refresh_newsletter_summary',{'p_campaign':cid,'p_uncertain_notice':MSG.NEWSLETTER_SEND_UNCERTAIN})
    out['done']=bool((saved or {}).get('done'))
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
