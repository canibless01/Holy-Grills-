# Forensic audit — business logic, code quality, security

Scope: the whole backend (`app/`, 41 blueprints, ~405 routes), re-verified against the
live test-2 database where a claim could not be settled from code alone.

Method: `pyflakes` over `app/` (68 warnings, triaged), a scripted pass that lists every
route with no auth decorator, targeted greps for secrets/leaks/swallowed exceptions,
and manual reading of the money paths. Everything below is quoted from the file at the
line shown. Items already fixed in this session are **not** repeated — see the last
section for that list, so nothing gets fixed twice.

**Status of this document: current.** Every item carries its state — 🔴 CRITICAL, all
four 🟠 HIGH, 🟡 M1/M2/M3/M4/M5 and the whole 🔵 LOW table are closed as of `0481333`
(which also wires the operating-hour overrides into the ordering gate); `pyflakes`
reports **zero** warnings for `app/` and `scripts/live_test.py`. The ledger answers
"what is left", and the **Go-live status** section at the end is the summary to read
before shipping.

Severity here means: 🔴 ships broken / loses money or data · 🟠 hurts users or
support · 🟡 debt that will bite · 🔵 cosmetics.

---

## 🔴 CRITICAL

### C1. `POST /api/exclusive-spin/spin` raised `NameError` for every caller — FIXED
`app/routes/exclusive_spin.py:191` (before the fix)

```python
def do_spin():
    user_id = g.user_id
    if not is_feature_enabled("exclusive_spin"):     # NameError: name is not defined
```

The import lived inside a *different* function (`my_spins`, line 165), so the name was
never bound in `do_spin`. Every spin attempt returned **500 before reading a single
credit** — the whole exclusive-spin feature was dead, and pyflakes reports it as
`undefined name`. Nothing in the repo tested this route, which is why it survived.

**Fixed:** module-level import, inner import removed. `pyflakes` now reports no
undefined names in the file; the route is present and the app boots (health 200).

Verified: `python -m pyflakes app/ | grep "undefined name"` → only this one existed, and
it now returns 0 across `app/`. The route is reachable and the app boots (health 200).

---

## 🟠 HIGH

### H1. A failed event insert was retried with columns silently dropped, for *any* error — FIXED
`app/routes/events.py:1140-1146`

```python
try:
    result = db.table("events").insert(safe).execute()
except Exception as _exc:
    # New columns may not exist yet — strip them and retry
    PHASE2_COLS = {"hp_per_attendee", "funding_source", "max_attendees", "hp_required", "total_value", "is_paid"}
    safe2 = {k: v for k, v in safe.items() if k not in PHASE2_COLS}
    result = db.table("events").insert(safe2).execute()
```

**Why:** the retry is meant for "column does not exist" (PostgREST `PGRST204`) but fires
on *every* exception — RLS denial, unique violation, network blip, malformed value. When
that happens the second insert succeeds **without** `hp_per_attendee`, `is_paid`,
`max_attendees`… so an event is created with the HP-per-attendee silently zeroed, and the
original error (`_exc`, never read) is discarded. That is silent data loss in the events
money path.

**Fixed.** The classification lives in one place now — `app/db.py::is_missing_column_error()`
— so no other strip-and-retry path can drift into the same bug:

```python
def is_missing_column_error(exc) -> bool:
    """True only for "that column/table does not exist" errors."""
    details = getattr(exc, "details", None)
    code = str((details or {}).get("code") or "") if isinstance(details, dict) else ""
    if code in ("PGRST204", "42703", "42P01"):
        return True
    text = str(exc)
    return ("PGRST204" in text
            or "does not exist" in text.lower() and "column" in text.lower())
```

and `create_event` now re-raises anything that is not a schema mismatch, logging the
retry when it does happen:

```python
    except SupabaseError as exc:
        if not is_missing_column_error(exc):
            raise
        logger.warning("create_event: %s — retrying without the phase-2 columns", exc)
        PHASE2_COLS = {"hp_per_attendee", "funding_source", "max_attendees",
                       "hp_required", "total_value", "is_paid"}
        safe2 = {k: v for k, v in safe.items() if k not in PHASE2_COLS}
        result = db.table("events").insert(safe2).execute()
```

Verified against eight exception shapes: PGRST204, 42703, 42P01 → retry; RLS denial
(42501), unique violation (23505), not-null (23502), a network failure and a bad value
→ re-raise. The original error is no longer discarded, and no event can be created with
`hp_per_attendee` / `is_paid` silently zeroed.

### H2. A paid customer could receive no ticket email, with no log line — FIXED
`app/routes/events.py:881-888`

```python
        send_qr_ticket_email(
            email=email, name=name, event_title=event.get("title", ""), ...
        )
    except Exception:
        pass
```

**Why:** the customer has already paid by this point. If Resend is down, the address is
bad, or the QR render fails, the ticket email never arrives and **nothing anywhere
records it** — no log, no retry, no admin visibility. Support finds out only when the
customer complains at the door.

**Fixed** — and one trap worth recording: `confirm_event_ticket_payment` is **called by
the payment webhook**, not by a route, so it must keep returning the ticket dict. The
first draft of this fix returned `(jsonify(...), 200)`, which the webhook would have
passed straight back to Paystack as its response body. It now logs and records the
outcome on the row it was already returning:

```python
        send_qr_ticket_email(...)
        email_sent = True
    except Exception as exc:
        logger.error("confirm_event_ticket_payment: QR ticket email failed for ticket %s (%s): %s",
                     ticket_id, locals().get("email"), exc)
        email_sent = False

    if isinstance(updated, dict):
        updated["email_sent"] = email_sent     # callers can see the email did not go out
    return updated
```

The other four sites now log too, each naming what was lost and what was already
committed:

| Site | Was | Now |
|------|-----|-----|
| `events.py:267` | `except Exception: pass` | `logger.warning` with user + event id — the HP was credited, only the badge trigger was lost |
| `admin_gifts.py:212` | `pass` | `logger.warning` per user — the multiplier is live, only the announcement was lost |
| `graduation.py:112` | `pass` | `logger.warning` — HP credited, badge lost |
| `exclusive_spin.py:244` | `pass` | `logger.warning` — credit spent and prize recorded, only the message lost |

### H3. `get_user_client()` could silently hand a route the service-role client — FIXED
`app/db.py:530-547`

```python
    try:
        caller_frame = sys._getframe(1)
        caller_get_db = caller_frame.f_globals.get("get_db", get_db)
        db = caller_get_db()
    except Exception:
        db = get_db()                      # ← service-role client

    try:
        from flask import g, has_app_context
        if has_app_context():
            jwt = getattr(g, "jwt_token", None)
            if not isinstance(db, SupabaseClient):
                return db
            return UserSupabaseClient(db, jwt, paginate=paginate)
    except Exception:
        pass                               # ← returns the raw service-role client
    return db
```

**Why:** both handlers are bare and the fallback is the most privileged client in the
process. I verified the normal path is sound — `UserSupabaseClient.table()` calls
`.with_jwt()`, and `TableQuery` at `db.py:328` then sends the **anon** key when there is
no user JWT, so RLS does apply. But `except Exception: pass` means that if wrapping ever
fails (a stray `g` access outside an app context, a mock in tests), the caller receives
service-role access and every RLS policy is bypassed with no warning.

**Fixed** — fail closed, never fail privileged:

```python
        if not isinstance(db, SupabaseClient):
            return db
        return UserSupabaseClient(db, jwt, paginate=paginate)
    except Exception as exc:
        # FAIL CLOSED. An unauthenticated caller must get the anon client (RLS applies),
        # never the raw service-role client — returning `db` here would silently bypass
        # every RLS policy for a route that only meant to read its own rows.
        logger.error("get_user_client: could not scope to the caller (%s) — falling back to anon", exc)
        try:
            return UserSupabaseClient(db, None, paginate=paginate)
        except Exception:
            return db
```

Verified: the fail-closed client resolves to the **anon** key for both `apikey` and
`Authorization` (asserted, not eyeballed), so RLS applies on that path. The outer
`except` also now logs — a client-lookup failure is no longer invisible.

### H4. Cancelling an unpaid *scheduled* order refunded a card payment that was never collected — FIXED
`app/routes/orders.py:884` (before the fix; the block lives in `cancel_scheduled_order`)

```python
    card_amount_used = float(order.get("card_amount_used") or 0)
    if card_amount_used > 0:
        from app.services.wallet_service import credit_wallet
        credit_wallet(
            user_id=g.user_id, amount=card_amount_used,
            payment_reference=f"scheduled-cancel-card-{order_id[:8].upper()}",
            reference_id=order_id, reference_type="refund",
            notes=f"Card-portion refund for cancelled scheduled order #{order_id[:8].upper()}",
        )
        wallet_refunded += card_amount_used
```

Every order is written with `payment_status='pending'` and `card_amount_used` already set
(`app/services/order_service.py:917`); the card half only becomes real money when the
webhook confirms it. This block refunded the card half **unconditionally**, so cancelling
an unpaid scheduled order credited the wallet for money that was never collected —
repeatable, and the same defect that was fixed on the plain cancel path. The regression
test written for that fix (`orders.cancel_unpaid_no_refund`) drives
`POST /api/orders/<id>/cancel` only, so this sibling was never exercised.

**Fixed** — the card half is refunded only once the payment is actually paid; the wallet
half above it is still always refunded, because it *is* debited at creation:

```python
    # The card half is only real money once the webhook confirms it — every order is
    # created payment_status='pending' with card_amount_used already set — so refunding it
    # here refunded money that was never collected, repeatably. Same bug the plain cancel
    # path had. The wallet half above is always refunded: it is debited at creation.
    card_amount_used = float(order.get("card_amount_used") or 0)
    if card_amount_used > 0 and str(order.get("payment_status") or "").lower() != "paid":
        logger.warning(
            "cancel_scheduled_order: order %s cancelled with payment_status=%r — the card "
            "half (%s) was never collected and is not refunded",
            order_id, order.get("payment_status"), card_amount_used)
        card_amount_used = 0.0
```

Verified with a decision table over both cancel routes (card-only / split / wallet-only,
each paid and unpaid): no unpaid scenario can refund more than the wallet half, and every
paid scenario still refunds both halves.

The suite now covers the whole class rather than the single route that was fixed first —
`orders.cancel_unpaid_scheduled_no_refund` (this route) and
`orders.cancel_split_refunds_wallet_half` (a positive test for O2: the wallet half must
come back, exactly, and nothing more). Both declared routes resolve against the app
(`make selfcheck`: 71 steps). **They have not been executed** — see the network note at the
end of this section.

---

## 🟡 MEDIUM

### M1. 90 `except Exception:` handlers — the user-visible ones are FIXED, the rest are *open*
Verified sample, each genuinely hiding a failure: `events.py:885`, `events.py:267`,
`events.py:723`, `events.py:1693`, `db.py:545`, `admin_gifts.py:212`, `admin_gifts.py:214`,
`exclusive_spin.py:244`, `graduation.py:112`.

`db.py:545` and the two `events.py` ones were the ones that mattered — all five
user-visible sites are fixed (H2/H3 above). The rule for the remainder: **a swallowed
exception is only acceptable if the code that follows it records why.**

**All 88 sites are now triaged.** Routes first, then services/tasks/utils — see
below for the second half. Correcting a number I gave earlier: the remainder outside
`routes/` was **64**, not 59 (routes 18 · services 38 · tasks 23 · utils 3 = 83 counted
after the routes fixes, with one site re-classified by the body-aware scan).

**Routes: triaged and mostly closed this pass.** I re-counted with a body-aware scan
rather than the earlier two-line pattern, because the first count under-reported blocks
whose body is a bare comment. Current measurement, excluding already-fixed sites:
`app/routes` 18 · `app/services` 38 · `app/tasks` 23 · `app/utils` 3.

All 18 remaining route sites were classified, not waved at:

**Fixed this pass — 13 sites, each logging at the level the failure deserves:**

| Site | What was swallowed | New level |
|------|-------------------|-----------|
| `menu.py:41` | `admin_audit_logs` insert — the admin action happened, its record did not | `error` |
| `hp.py:530` | same audit-trail insert in `hp.py` | `error` |
| `orders.py` `cancel_scheduled_order` | order lock not restored (customer paid for it) | `error` |
| `orders.py` `cancel_order` | same lock restore on the other cancel path | `error` |
| `orders.py` `reorder` (inner) | `menu_item_availability` read → silent fall-back to base price | `warning` |
| `orders.py` `reorder` (outer) | pricing for the item → silent snapshot-price fall-back | `warning` |
| `orders.py` squad invite | profile lookup failed → those users silently uninvited | `warning` |
| `orders.py` squad roster | insert failed → every failure read as "already on roster" | `warning` |
| `events.py:1711` | `get_event_tier_comparison` RPC → silent fallback for guests | `warning` |
| `kitchen.py:597` | unparseable timestamps → sample dropped, kitchen metric skewed | `debug` |
| `webhooks.py:611` | the webhook-failure alert itself | `error` |
| `admin_gifts.py:188` | multiplier broadcast failed → nobody told it went live | `warning` |
| `admin_gifts.py:217` | same broadcast, whole-run failure | `error` |

**14 sites are already covered one layer down — verified, not assumed.** Every one of
these calls a helper that logs its own failure before returning:

* `send_notification` — `notification_service.py:335` (profile lookup), `:406` (row
  save), `:853/857` (OneSignal email), `:883/884` (email dispatch), `:920/922` (push).
  Sites: `events`-side none, `graduation.py:131`, `hp.py:493`, `orders.py:756/1241/1608/
  1619/1633`, `referrals.py:244`, `rewards.py:304/528/638`.
* `send_qr_ticket_email` / `send_email` — `utils/email.py:346`, `:391/392`, `:435`.
  Sites: `events.py:634`, `events.py:724`.
* `check_milestone_trigger` — `milestone_service.py:320-321`. Site: `hp.py:503`.

Adding a log line at the route would produce the same event twice, so these stay as they
are. The triage rule: **log it when the swallowed failure changes what the caller
believes happened.**

**services / tasks / utils — 64 sites, triaged in `e874c98`.** 42 now log; 22 were left
silent deliberately, each for a stated reason. The ones worth naming:

| Site | What the silence hid | New level |
|------|---------------------|-----------|
| `order_service.py:1194`, `:1397` | caller-role lookup fails → `caller_role` stays `None` → **the rider/kitchen/admin scoping checks are skipped**. Fail-open, so it logs at `error`. Behaviour deliberately unchanged: denying on a transient read error would block roles from their own paths. | `error` |
| `wallet_service.py:69` | top-up HP bonus never awarded, silently | `error` |
| `hp_service.py:686` | `recalculate_tier` computes a tier the profile never gets | `error` |
| `order_service.py:753` | hostel `delivery_fee` unreadable → order charges ₦0 delivery | `warning` |
| `order_service.py:876/881` | tier and `next_order_hp_multiplier` lost at checkout | `warning` |
| `order_service.py:1010/1021` | squad member rows not written; the customer is told the squad is set up | `warning` |
| `order_service.py:1061` | delivery window unreadable → the customer is shown the 18:00-19:00 default | `warning` |
| `gift_service.py:71` | unreadable launch-window end date *grants the gift anyway* | `warning` |
| `notification_service.py:464` | unparseable `level_department` → a blast can reach the wrong audience | `warning` |
| `streak_service.py:558`, `wallet_service.py:76` | streak activity / reclaim silently unsaved | `warning` |
| `squad_service.py:198` | a member's HP share not recorded | `warning` |
| `tier_service.py:96` | perk resolution falls back to the default perk | `warning` |
| `newsletter_service.py:248`, `notification_service.py:826` | `last_error` not recorded; email provider defaulted | `warning` |
| 18 × `db.rpc("release_cron_lock")` in `scheduled.py` | the lock is not released, so **the job may skip its next run** — the same class as the webhook alert path | `warning` |
| `scheduled.py:1359` | unreadable `reminder_sent_at` → a duplicate reminder can go out | `warning` |

Left silent, with reasons: six settings/format fall-backs that have a sane default and no
behavioural surprise (`gift_service._get_setting`, `hp_service._setting_raw`,
`_ambient_campus_id`, notification throttle settings, tier value coercion,
`admin_helpers.as_time`, `utils.settings.get_validated_setting`, `retry.with_retry`);
`_log_notification` (its docstring says *Never raises* — throttle bookkeeping only); the
backward-compatibility transaction fetches in `credit_wallet`/`debit_wallet`, whose
fallback returns the caller an equivalent shape; and five `send_notification` call sites
whose service logs internally (same reasoning as the route sites above).

I checked the three `webhooks.py` sites rather than assuming, and the interesting one is
**not** what I first wrote:

* `webhooks.py:112` and `:206` swallow only the *bookkeeping* write that records a
  failure. The outer handler still calls `_notify_admin_webhook_failure(...)` and returns
  **500**, so the provider is not told "OK" — these are the least urgent of the 88.
* `webhooks.py:611` is inside `_notify_admin_webhook_failure` itself: it is the alert
  path. If that notification fails, a failed webhook produces **no alert at all** — the
  one place where a silent swallow hides the failure of the failure-reporting. **Fixed**
  this pass with a `logger.error`; `:112`/`:206` stay as they are, because the handler
  around them still returns 500 and the 500 is the signal.

### M2. N+1 queries: 121 database round-trips inside loops — worst case FIXED, rest *open*
Worst verified case — `app/routes/admin.py:1100-1103`:

```python
        for b in batches:
            counted = db.table("orders").select("id", count="exact").eq("batch_id", b["id"]).limit(1).execute()
            b["order_count"] = (counted or {}).get("count") or 0
```

One extra HTTP round-trip **per batch** on every page of the batch list (limit up to
hundreds). At 100 batches that is 101 REST calls to render one screen.

**Fixed** — one query for the page, grouped in Python:

```python
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
```

A 50-batch page goes from 51 REST calls to 2. `.limit(10000)` bounds the read; the
response shape is unchanged, and a batch with no orders still reports `order_count: 0`
(diffed against the old implementation on four cases, including zero-order batches).

(`analytics.py:532` looks like the same shape but is actually chunked `in_()` batching —
that one is correct.)

### M3. `change_password` logged the provider exception verbatim — FIXED
`app/routes/auth.py:709`

```python
    except Exception as e:
        logger.error("change_password: update failed for %s: %s", g.user_id, e)
```

The call immediately above it carries `{"password": new_password}`. Supabase client
exceptions can echo the request body, which puts the new password in the log file.
**Fixed:** logs `type(e).__name__` and `status_code` only.

### M4. Development-only switches could be enabled in production — FIXED
`app/config.py:135-137`, `app/routes/webhooks.py:43,141`, `app/routes/wallet.py:182`

`ALLOW_UNSIGNED_WEBHOOKS=true` makes the payment webhooks accept **unsigned** payloads —
anyone could POST a forged `charge.success` and create orders/wallet credit.
`PAYSTACK_SANDBOX_MOCK_NUBAN=true` stores a fake account number (`0000000000`) as the
user's real one. Both default to false, but neither was guarded, unlike
`SECRET_KEY`/`JWT_SECRET`.

**Fixed:** `create_app()` now refuses to build a non-DEBUG/TESTING app with either set;
verified by an attempted production boot with `ALLOW_UNSIGNED_WEBHOOKS=true`, which now
raises.

### M5. A helper was shadowed by a route function of the same name — FIXED
`app/routes/free_sides.py:132` (new route) vs `:375` (existing helper)

```python
def grant_free_side_credits(write_db, user_id: str, count: int, campus_id, source: str, validity_days: int = 30) -> list:
```

I introduced a Flask view with the same name. Nothing imports the helper today, so
nothing broke — but the next `from app.routes.free_sides import grant_free_side_credits`
in `scheduled.py` would have received the view function and raised `TypeError`.
**Fixed:** route renamed `admin_grant_free_side_credits`, with a comment on why.

### M6. Two endpoints answer without authentication — *resolved: kept public, by design*
`app/routes/menu.py` (`GET /api/menu/kitchen-capacity`) and `app/routes/hp.py`
(`GET /api/hp/bundles`).

**Decision (yours):** both stay public. `kitchen-capacity` is the pre-login "how busy are
we" signal and is documented `security: []` in its own docstring; `/api/hp/bundles` is
the price list a guest must see *before* buying, and the purchase itself
(`POST /api/hp/bundles/purchase`, `hp.py:287`) keeps `@require_auth`. Withdrawing the
recommendation below rather than leaving it as a standing finding.

Guests must reach their path and each role its own; nothing was gated in this pass. Only
two auth decorators were added in the whole audit — both `@require_role("admin")`, both
on the **new** admin grant routes from `418f655`; no pre-existing route gained a gate.

For the record, the original question, answered from the running app rather than by
reading back the intent:

```bash
curl -s /api/menu/kitchen-capacity   # 503 from the upstream TLS failure, NOT 401/403 — no auth gate
curl -s /api/hp/bundles              # 200, returns the bundle price list
```

Verified this pass against a locally booted app: neither endpoint returns 401/403 to an
anonymous caller.

---

## 🔵 LOW

All ten are closed in `e874c98`; `pyflakes` reports **zero** warnings for `app/` and
`scripts/live_test.py`.

| # | Location | Finding | How it was closed |
|---|----------|---------|-------------------|
| L1 | `app/db.py:435` | `f-string is missing placeholders` | `f` prefix dropped |
| L2 | `app/routes/events.py` | local `import uuid` shadowing the module import | both bindings were unused and are gone |
| L3 | `app/routes/events.py` | `_exc` bound and never read | closed with H1 — the retry path reads it |
| L4 | `app/routes/graduation.py` | `except Exception as e:` with `e` unused | closed earlier: it logs `exc` |
| L5 | `app/routes/hp.py:515` | `get_db` imported, unused | import trimmed |
| L6 | `app/services/hp_service.py` | `update_monthly_tracker` imported twice | the first import now takes only `check_monthly_cap` |
| L7 | `app/services/order_service.py` | `squad_delivery_discount` assigned, never read | **two** dead bindings removed (the second surfaced once the first was gone); the discount itself is applied through `squad_delivery_discount_dec`, untouched |
| L8 | `app/services/streak_service.py` | `action` assigned, never used | removed |
| L9 | `app/tasks/scheduled.py` | `is_feature_enabled` re-imported, shadowing the first | inner import removed; the earlier one serves the call |
| L10 | 30 files | 56 unused imports | all removed — re-export guard applied, proven by 63/63 modules importing and the app booting with 405 routes |

---

## Verified clean (so nobody re-audits these)

| Area | Evidence |
|------|----------|
| Hardcoded secrets | grep for `sk_live`, `pk_`, `AIza`, JWTs, `Bearer <20+>` → **none** in `app/` or `scripts/` |
| Secrets in logs | no `logger.*` call interpolates a secret/password/token (the one that did was M3, now fixed) |
| Webhook signatures | both providers verify with `hmac.compare_digest`, and **fail closed** when the secret is unset (`webhooks.py:40-45`, `:138-142`) |
| RLS enforcement on the user path | `UserSupabaseClient.table()` → `.with_jwt()`, and `TableQuery` (`db.py:328`) sends the anon key when there is no JWT — RLS applies. Service-role access only via explicit `get_db()` |
| Public config dump | `storefront.get_public_config` filters `system_settings` on `is_public=True` — no secret can be returned |
| Unauthenticated routes | 41 total; all are auth entry points, public catalogue/reference reads, signed webhooks, or documented public writes (newsletter, catering intake). No admin route lacks a decorator |
| External HTTP timeouts | all 5 `requests.*` calls set a timeout; the Supabase client carries `timeout=15` (`db.py:8`) |
| SQL injection | no SQL string building anywhere — all access is PostgREST query builders; the only `or_()` with interpolation takes server-derived ids |
| TODO/FIXME/HACK | exactly 1 (`gift_service.py:205`), and it is a deliberate product decision awaiting the owner, not unfinished code |

---

## Fixed in this session, before this report (not repeated above)

Cancel-refund money bug (unpaid orders refunding wallet) · `is_feature_enabled`
NameError (C1) · free-side consumption + E2E test · reward claim inside
`hg_create_order_atomic` · registrant email filter (paid/not_required, excludes
cancelled/expired) · Python ticket-expiry job removed (DB owns it) · `register`/
`refresh_token` error leakage · `fetch_or_403` bare excepts · `optional_auth` failure
classification · `hp_service` recalculate_tier logging · admin grant routes for free
sides and exclusive spins · 403 responses carrying the real message in `error` ·
anon-key audit finding split into public-by-design vs exposed · `WRITE_EXISTING` and
the suite's campus pinning.

**Then, in this pass:** H1 (schema-mismatch-only retry, shared helper), H2 (five silent
side-effect failures now logged, `email_sent` on the ticket row), H3 (`get_user_client`
fails closed to anon) — plus the verification that `confirm_event_ticket_payment` must
not return a Flask response, since the webhook passes its return value straight back to
Paystack.

**And two mistakes of mine, caught by re-running the scanner after the edits** — recorded
rather than quietly fixed, because it is the reason the rule below exists:

1. The H2 patch added `logger.warning(...)` to `admin_gifts.py` and `graduation.py`,
   neither of which wires a logger. Both would have raised `NameError` **inside an
   except block** — turning a handled failure into a 500. Fixed by importing and
   defining `logger` in both modules.
2. The H2 fix for the ticket email first returned `(jsonify(...), 200)`. That function
   is called by the webhook, not by a route, so the tuple would have been handed back
   to Paystack as the webhook response. Caught by reading the caller before committing.

**Rule this establishes: run `python -m pyflakes app/` after every batch of edits, not
just once per session.** Both mistakes were visible in one command. The final state is
0 undefined names and 35/35 route modules importing cleanly.

## Ledger — the one place that answers "what is left"

Updated at the end of every working pass. If an item is not here, it is not open.

### Open — needs the project owner

| # | Item | Why it is theirs |
|---|------|------------------|
| O1 | **`SUPABASE_DB_URL`** | RLS policies, table/function grants and per-role row visibility have never been read. **Everything in this repo is code-level; the database posture is unverified.** Add the pooler URI to `.env`, then `make audit` |
| O2 | ~~Does `hg_create_order_atomic` debit the wallet half at creation?~~ **Answered: yes — `debit_wallet_atomic`, same transaction.** `refund_wallet_when_unpaid` is now `True`, capped at `wallet_amount_used` | closed in `9001c19` |
| O3 | ~~Does anything restore `hp_redeemed` / a claimed reward on cancel?~~ **Answered: nothing did.** Both are now restored on `received -> cancelled`, HP at the exact amount with no multiplier | closed in `9001c19` |
| O4 | `docs/audit-report.md` + the truncated tail of the ecosystem map ("Admin grant routes missing …") | Not in this checkout; can't be actioned blind |
| O5 | ~~Three `operating_hour_overrides` rows~~ **Answered: intentional — per-date overrides of the recurring schedule.** Nothing is deleted; the feature is now wired into the ordering gate (`0481333`) | closed in `0481333` |
| O6 | `migrations/schema.sql`, `scripts/seed.py`, `scripts/seed.sql` | Referenced by docs, absent from the repo — send them or drop the references |

### Open — mine, no decision needed

| # | Item | Where |
|---|------|-------|
| ~~O7~~ | closed in `e874c98` — 83 sites triaged in total: 29 routes, 42 services/tasks/utils logged, the rest documented with reasons | M1 section |
| ~~O10~~ | closed in `e874c98` — 56 unused imports removed, L1–L9 fixed; `pyflakes` clean | 🔵 LOW table |

### Closed

| Item | Evidence |
|------|----------|
| Cancel-refund money bug (unpaid order → wallet credit) | `418f655`; regression step `orders.cancel_unpaid_no_refund` in the suite |
| `do_spin` NameError (every spin 500'd) | `7c76f8e`; `pyflakes app/` reports 0 undefined names |
| H1 silent column-stripping on event create | `is_missing_column_error()` + 8-case decision table |
| H2 ticket email / four other silent side-effect failures | Each now logs; `email_sent` recorded on the returned row |
| H3 `get_user_client` could fall back to service-role | Asserted: the fallback resolves to the **anon** key |
| `change_password` logging the provider error verbatim | `7c76f8e` |
| Dev-only switches unguarded in production | `create_app` refuses to boot with either set (verified) |
| Route shadowing a service helper | renamed `admin_grant_free_side_credits` |
| Free-side consumption, reward double-use, registrant filter, ticket expiry ownership | earlier passes — see the session list below |
| Admin grants for free sides and exclusive spins | `418f655` |
| H1/H2/H3 (this report's HIGH items) | this pass — schema-mismatch-only retry, five silent failures logged, `get_user_client` fails closed |
| Two `NameError`s introduced while fixing H2, caught by re-running pyflakes | fixed in the same pass; see above |
| O8 — N+1 in the delivery-batch list (51 REST calls per 50-batch page) | one query per page; old vs new diffed on four cases |
| O9 — the two unauthenticated endpoints | kept public **by decision**; both still reachable anonymously (503 from the unreachable upstream, not 401) |
| O7 — 13 of the 18 remaining silent route-swallows | each now logs; the other 14 verified covered inside `notification_service` / `utils/email` / `milestone_service` |
| O7 (remainder) — 64 silent swallows in services/tasks/utils | 42 now log at a level matched to the failure; 22 left silent with a stated reason |
| O10 — 56 unused imports and LOW L1–L9 | all removed/fixed; pyflakes reports zero warnings |
| Reward release now clears `used_at` as well as `attached_order_id` | `_restore_order_consumables`; re-running matches no row |
| Operating-hour overrides ignored by the ordering gate (storefront said "closed", checkout accepted orders) | one shared helper, `app/utils/schedule.py`, used by both readers; 20 precedence assertions + 11 storefront cases; 3 e2e steps |
| No permission sweep — a route losing its decorator would ship quietly | `security.permissions_matrix`: 29 admin routes × customer token |
| Forged webhooks untested | `security.webhook_forgery_rejected`: both providers, no side effects asserted |
| O2 — the wallet half of a cancelled split order was never returned | `refund_wallet_when_unpaid = True`, capped at `wallet_amount_used`; card half still only when paid |
| O3 — HP and a claimed reward stayed spent after a cancel | `_restore_order_consumables()` on `received -> cancelled` in `update_order_status` (one choke point, fires once); the duplicate HP restore in `cancel_scheduled_order` removed |
| H4 — unpaid *scheduled* order refunded an uncollected card half | card half gated on `payment_status='paid'`; decision table over both cancel routes |
| `_hp_grant_denied` missed the real refusal wording | the live message is `insufficient_privilege` (underscore); the text branch now matches it, not only the 42501 code |

### Session note — money paths, closed on your live-DB answers

Three things came out of applying the answers rather than assuming them:

1. The refund flag was a one-line change, but the *reason* it was off is worth keeping:
   it was disabled pending exactly this answer. The comment now records the answer.
2. Looking for the sibling of the already-fixed money bug paid off — the scheduled
   cancel route refunded both halves unconditionally (H4). It had been missed because
   the regression test for the first bug covers only the non-scheduled route; a
   regression test protects the route it names, not the class of bug it names.
3. The HP restore existed in **one** of the two cancel paths already (the scheduled one,
   with `apply_multiplier=False`) — so the rule you asked for was already the house
   style. Putting it in `update_order_status`, the single compare-and-set choke point,
   both covers every cancel path and removes the risk of the two paths drifting.

Reward release goes through the service role deliberately: `reward_redemptions` has no
UPDATE policy for owners (`routes/rewards.py:899` says so), so a user-scoped write would
have silently changed nothing.

**What could not be run here:** the sandbox has no route to the internet, so every
Supabase call fails with `SSLError` before it leaves the box. `make contract` reports
"every table, column and RPC the code uses exists" but every check is marked *unreachable*;
`make smoke` / `make e2e` stop at `preflight.health: Supabase not connected`. The refund
table and the restore-path fakes above run entirely offline, which is why they are the
evidence used — the two new suite steps are yours to run where the database is reachable.

### Session note — the O7/O10 pass, and two mistakes worth keeping

Both mistakes are recorded for the same reason the earlier two were: they are precisely
the failure mode this pass exists to remove.

1. **The site patch used the wrong indentation.** It gave the `except` line the indent of
   the `pass` line it replaced — one level too deep — and broke the syntax of eleven files
   at once. Caught by parsing every file with `ast` immediately after applying. Fixed by
   restoring the pre-patch backup and correcting the rule: the `except` keeps its own
   indent, its body gets the deeper one.
2. **The import remover edited files while iterating over line numbers it had already
   invalidated.** A removed line shifts every later one, so the second import flagged in a
   file would have pointed at the wrong line. Caught because the affected edits were
   reported as "not an import", not because the tool complained. Rewritten to edit each
   file once, bottom-up.

The pattern in both: the *edit* was mechanical, the *verification* is what caught it —
`ast.parse` for syntax, an import-all plus boot for structure, `pyflakes` for names.

### Session note — operating-hour overrides, and a comment that said "intended"

The suite carried this line, written in an earlier pass:

> `operating_hour_overrides` is the *storefront* schedule and has no effect on ordering

That was true, and it was the whole problem: a campus could be told "closed today" on the
storefront while checkout kept accepting orders, because only the storefront read the
table. The comment is corrected, and both readers now go through one helper.

Three things worth keeping from this one:

1. The precedence is written down **once**, in `app/utils/schedule.py`, and the ordering
   functions call it. `find_next_available_ordering_slot` and the 7-day calendar became
   override-aware for free, because they are built on `get_ordering_window_status`, which
   now resolves through the helper. A second copy of these rules would have drifted.
2. A closed override returns **one closed row**, not an empty list — "no rows" already
   means "fall through to the next rule" in this code, and conflating the two would have
   reopened the day through the config fallback.
3. The override's identity inheritance is deliberately narrow: id/capacity/delivery link
   come from the weekday row only when exactly **one** such row exists. With two, there is
   no single window for the capacity counter to belong to, so the override stands alone
   with no cap rather than silently sharing one row's counter.

### Session note — silent-except pass

Triage rule applied: log when the failure changes what the caller believes happened.
First draft of the `reorder` log line referenced `item_id_ref`, which does not exist —
a `NameError` inside an `except` block, i.e. exactly the class of bug this pass is meant
to remove. Caught because a `pyflakes` run had silently failed (`No module named
pyflakes` piped into a `grep`, so the empty match read as "clean"). Reinstalled, then
re-ran with a planted-error control to prove the check actually fires. Both notes are
here because the earlier rounds' two `NameError`s were recorded the same way.

---

## Go-live status

Read this before shipping. It is written to be honest about what has *not* been proven,
because the expensive failures are the ones nobody checked.

### Verified, with the evidence

| Area | Evidence | Verified where |
|------|----------|----------------|
| Names, imports, structure | `pyflakes` **0 warnings** for `app/` + `scripts/live_test.py` (control-gated with a planted undefined name); 70/70 route-bearing modules import (all of `app/`, `__init__.py` excluded); app boots with 405 routes | this sandbox |
| Routes the suite calls | `make selfcheck` — 154 declared routes all exist | this sandbox |
| Order follow-up steps | `flow.order_followups` + `flow.squad_members` executed against a canned API/DB harness: they call the intended routes, refuse wrongly-shaped responses, delete the rows they cause and restore the account's HP counters | this sandbox |
| Permission gates | 29 admin routes enumerated from the live URL map and swept by `security.permissions_matrix` | the suite, at run time |
| Cancel refunds | decision table, 6 scenarios × both cancel routes: no unpaid case can refund more than the wallet half, paid cases refund both halves | this sandbox |
| HP + reward restore on cancel | fake-run of `_restore_order_consumables`: exact HP, `apply_multiplier=False`, release pinned to the order, clears `attached_order_id` **and** `used_at`, failures logged not raised, guest orders skipped | this sandbox |
| Override precedence | 20 assertions through the real `effective_ordering_windows` / `resolve_ordering_window` / `get_ordering_window_status`: dated row wins, closed closes, open replaces, inheritance rule, campus beats global, NULL times, unreadable table falls back | this sandbox |
| Storefront `is_open` | 11 cases incl. the NULL-times change | this sandbox |
| DB contract shape | `make contract` — reports every table/column/RPC the code uses exists, **but every check is marked unreachable** (no network) | partially |
| The live database | **not verified here** — the sandbox cannot open a connection to Supabase; every request fails with `SSLError` | ❌ |

### Not verified here — the commands to close them

```bash
make contract                  # real pass, not the "unreachable" shell
make smoke  BASE_URL=http://localhost:5000
make flow   BASE_URL=http://localhost:5000 WEBHOOK_SECRET=<paystack secret> \
            WRITE_EXISTING=1 LOGIN_EMAIL=claude.audit.test1@holygrills.test \
            LOGIN_PASSWORD='ClaudeAudit!Test1'     # money in + kitchen -> rider -> delivered
                                                   # then reorder / share / review / squad
make e2e    BASE_URL=http://localhost:5000 WRITE_EXISTING=1 \
            LOGIN_EMAIL=claude.audit.test1@holygrills.test LOGIN_PASSWORD='ClaudeAudit!Test1' \
            E2E_ARGS=--with-cron                   # optional: invoke all 17 scheduled jobs
```

Notes for that run:

* The authorization sweeps add ~480 requests (241 routes × customer + rider). Expect the
  run to take noticeably longer; that is the price of covering the admin surface.
* The four `concurrency.*` steps **skip without `BASE_URL`** and they need the guarded
  test server, not just any server: two requests must be in flight at once.
* `--with-cron` accepts the side effects of the scheduled jobs (HP, leaderboards,
  notifications, email, scheduled orders). Without it, only the canary job runs.
* `scheduled.trigger_contract` and `scheduled.jobs_run_safe` create a throwaway
  super_admin account each and delete it; the audit rows they cause are deleted too.
* The `surface.*` steps run on their own with `E2E_ARGS="--only surface"`. They need a
  working campus read and a finished `auth.login`; squads additionally needs the
  `squad_orders` feature flag on, and the spin and graduation happy paths skip when the
  feature is off or no eligible academic level exists.
* The order follow-ups run with `--only flow.order_followups` (or as part of `make flow`);
  `--only` pulls the whole chain they depend on, so that one command places, pays, advances
  and delivers an order before it tests what the customer does with it.

The e2e run now covers the whole cancel/refund/override surface (the two refund
regressions, both ticket/event flows, the three override probes) plus the flow steps above.
**None of these steps has ever executed against the live database** — they were written and
route-checked here, nothing more. Treat the first green run as the real sign-off.

One thing to check on that first run: **the order-payment webhooks compare the charged amount
to `orders.total_amount`, not to the card half.** Both providers do it the same way —
`app/routes/webhooks.py:256` (Flutterwave) and `:385` (Paystack) — while the *event ticket*
branches two functions over compare to `card_amount_used` (`:411`). For a pure card order
`total_amount == card_amount_used`, which is why `flow.webhook_pays_order` passes. For a
**split** order the customer's card is charged only `card_amount_used`, so if the front end
initialises the charge for that amount (the consistent reading of the ticket branches), the
webhook is rejected with "Amount mismatch" and the card half of a split order never confirms.
Not proven from here (the front end is not in this repo, and the sandbox cannot read the
data): worth **one manual split order** before launch. If it reproduces, the fix is to compare
against `card_amount_used` when it is greater than zero.

### Still open

| Owner | Item | Why it matters |
|-------|------|----------------|
| you | **O1 — `SUPABASE_DB_URL`** | RLS policies, grants and per-role visibility have never been read. Every claim in this document is code-level. This is the largest remaining unknown by far |
| you | **migration bodies** | the three live functions aren't mirrored in the repo; the file is a record, the database is the source of truth. The paste arrived truncated — re-send as an attachment or split across two messages |
| you | **O4** | `docs/audit-report.md` + the ecosystem-map tail aren't in this checkout |
| you | **O6** | `migrations/schema.sql`, `scripts/seed.py`, `scripts/seed.sql` referenced but absent |
| me | nothing | O7 and O10 are closed; the remaining work is the live run above |

### What the test suite does and does not cover

Measured, not estimated — the app's live URL map against every path the suite calls:

405 method × path pairs are registered, `/static/<filename>` included; the figures below use
that full base, so they can be read directly against `make selfcheck` ("405 app routes").

| | |
|---|---|
| routes the suite **reaches** | **392 (96.8%)** — 66 before the flow pass, 68 before the authorization sweeps, 385 before the order follow-ups |
| of those, routes **no test had ever touched before this round** | **325** — 241 with a permission assertion, 32 by the read sweep, 52 functionally (the 8 order follow-ups among them) |
| routes that stay uncovered, and why | **13** — see the list below |
| blueprints with **zero** exercised routes | **none** — all 43 are exercised (was 35 of 43) |
| coverage is *reachable*, not guaranteed per run | steps skip by design when a feature is off, a secret is absent or a fixture does not exist — a run's real number is in its own summary |
| role/permission assertions before this round | **1** (a wrong-password 401) → now 241 gated routes × 2 attacker roles |
| routes the surface pass added | **19** (the eight blueprints that had none) |
| webhook calls before the flow pass | **0** |
| scheduled jobs invoked before this round | **0** |

**What it does cover well:** the customer order loop — auth, cart, order creation,
wallet/Hp reads, the cancel/refund regressions from this audit, the free-side and reward
consumption fixes, and now the override precedence. Those are the paths the audit's own
findings lived in, which is why they have tests.

**What it structurally cannot catch:**

1. **Payments arriving by webhook.** Nothing called `/api/webhooks/*`, so signature
   handling, idempotency and the confirm-payment path were unverified end to end — the
   path money actually enters through. *Closed for Paystack by the flow pass below;
   Flutterwave and the virtual-account branch are still unexercised.*
2. **Permissions.** Nothing asserted that a customer is refused an admin route. A route
   losing its decorator would have shipped silently (this is exactly the class the audit
   found by reading code, not by testing). *Closed by `authz.admin_routes_refuse_customer`
   and `authz.admin_routes_refuse_rider`, which walk all 241 staff-gated route-pairs with a
   customer token and a rider token and fail on any 2xx.*
3. **Scheduled jobs** (`app/tasks/scheduled.py`: 18 task functions, 17 in the beat
   schedule, 1 deliberately unscheduled) — never invoked. *Partly closed: the wiring of
   every job is now asserted offline (`scheduled.jobs_wired`), and one job runs for real
   against an isolated canary row (`scheduled.jobs_run_safe`). Invoking all 17 remains
   opt-in (`--with-cron`) because they mutate shared data and message real users.*
4. **The kitchen → rider → delivery lifecycle** — the suite stops at order creation, so
   `received → preparing → ready → assigned → delivered`, the HP award on delivery, and
   rider payouts are untested. *Closed by the flow pass below for the happy path; refunds,
   attempts and unclaimed orders on that path are still untested.*
5. **Concurrency** — single-threaded, so a double-spend race (free sides, reward reuse,
   order locks, capacity) cannot be observed. *Four races are now covered
   (`concurrency.*`: idempotency replay, wallet overdraft, reward double-claim, free-side
   double-spend), but they need real HTTP — they skip unless `BASE_URL` is set, because an
   in-process Flask test client serialises requests and would prove nothing.*
6. **Notifications and email** — fire-and-forget to OneSignal/Resend; the suite can only
   see that a call did not 500.
7. **Database posture** (RLS, grants) — O1, invisible from the application side.
8. **Production configuration** — the suite runs against the dev config.

**Added in this pass** (the two highest-risk gaps that need no new fixtures):

* `security.permissions_matrix` — walks **29 parameterless admin GET routes** with a
  customer token and requires 401/403 from every one, checks 3 customer-only routes refuse
  an anonymous caller, and asserts the 5 public-by-design routes **still** serve guests
  (the standing rule: no fix may block a guest from their path).
* `security.webhook_forgery_rejected` — posts a forged Paystack and a forged Flutterwave
  webhook with a unique throwaway reference and requires 401/403, then asserts no
  `webhook_events` row was created and no wallet balance moved. If a forged signature is
  ever *accepted*, the step fails loudly and deletes the row it caused.

**Added in the flow pass** — the two gaps above that are observable without touching
production money, run as a single flow (`make flow`, or the same steps inside `make e2e`;
the webhook steps need `--webhook-secret` or `PAYSTACK_SECRET_KEY` in `.env`):

* `flow.webhook_wallet_topup` — a **validly signed** `charge.success` (wallet top-up)
  credits the wallet, writes exactly one `wallet_transactions` row, and a **replay of the
  identical event is a no-op** (the classic double-credit bug). Restores the wallet's
  prior values and deletes its rows in a `finally`.
* `flow.place_order` — the flow's own order, pinned to a private kitchen batch key so an
  advance can never touch an order the run does not own.
* `flow.webhook_pays_order` — a signed `charge.success` with `metadata.type=order_payment`
  drives `hg_mark_order_paid` and the order reaches `payment_status=paid`.
* `flow.kitchen_advances_order` — a throwaway **kitchen** session advances the batch
  `received → preparing → ready` and asserts both timestamps are stamped.
* `flow.rider_delivers_order` — a throwaway **rider** (real `delivery_assignments` row)
  picks up and delivers; asserts `delivered` + `delivered_at`, the HP award, and that the
  rider earnings endpoint answers. Restores the customer's HP/tier fields and deletes the
  order's ledger rows.

**Added in the tier pass** (authorization / concurrency / scheduled), all inside `make e2e`
or on their own with `--only authz|concurrency|scheduled`:

* `authz.admin_routes_refuse_customer` / `authz.admin_routes_refuse_rider` — every
  staff-gated route (241 route-pairs, loaded from the live URL map, parameterised routes
  included) must refuse a customer token and a rider token. They attack with a fresh UUID
  so a route that turns out to be missing its gate cannot touch a row, and any
  `/api/admin/...` path with no gate at all is a failure rather than a silent exclusion.
  This is what moved coverage from 68 to 299 route-pairs.
* `authz.cross_campus_kitchen_scope` — a kitchen session on campus B cannot advance campus
  A's order, with or without `?campus_id=<A>`; the order's status must not move.
* `authz.rider_cannot_touch_another_riders_order` — two riders, one `delivery_assignments`
  row: the rider who is not assigned must be refused pickup, delivery and the order read.
* `concurrency.replay_guard` — the same idempotency key fired three times at once creates
  exactly one order.
* `concurrency.wallet_no_overdraft` — the wallet is trimmed to exactly one order's worth,
  two wallet orders race it, exactly one may win and the balance may never go negative.
  The wallet is restored column-by-column afterwards, including on a real account.
* `concurrency.reward_single_use` — one fulfilled redemption, two simultaneous checkouts:
  at most one order, and the claim must be attached to the order that won.
* `concurrency.free_side_single_use` — one credit, two simultaneous checkouts:
  `credits_remaining` lands on 0 and never goes negative.
* `scheduled.jobs_wired` — every beat entry resolves to a real task function, every
  scheduled job logs its outcome under a name `/api/admin/cron/status` watches, and every
  manual trigger is visible on that page. **This caught a real defect** (below).
* `scheduled.trigger_contract` — an unknown job name is refused (404) and the returned
  `available_jobs` matches the trigger map exactly.
* `scheduled.jobs_run_safe` — `check-order-locks` runs for real against an overdue canary
  lock (skipped if any other active lock exists, so it cannot expire a user's), proving the
  lock expires, an audit row is written and the cron lock is released.
* `scheduled.jobs_run_all` — every triggerable job invoked once, none may record a failure.
  **Opt-in** (`--with-cron`): these jobs award HP, reset leaderboards, place scheduled
  orders and send push/email to real users.

### Defect found and fixed in this pass

`send-newsletter-campaigns` runs on the beat schedule every five minutes, but its name was
absent from `_CRON_INTERVAL_MINUTES` — the table `/api/admin/cron/status` reads. It also had
no entry in the manual trigger map. The result: a job running 288 times a day whose
successes and **failures were both invisible**, and which nobody could re-run by hand. Fixed
by adding it to the interval table (`app/routes/admin.py`); adding it to the manual trigger
map as well is a product decision left to you. `scheduled.jobs_wired` fails if this class of
divergence ever appears again.

**Added in the surface pass** — the last eight blueprints with no coverage at all
(`--only surface`):

* `surface.docs_endpoints` — flasgger's five routes: the HTML page, the machine-readable
  spec (asserted to contain the app's own order route and the Paystack webhook, and to
  carry a title), a static asset, and both redirect pages.
* `surface.measurement_units` — anonymous callers refused; the authenticated call returns
  rows that have an id and a name.
* `surface.users_search` — `/api/users/search` is service-role underneath, so its campus
  filter is the security boundary: every returned user is checked against the caller's
  campus in the database, and empty/nonsense queries must return nothing.
* `surface.push_roundtrip` — subscribe then unsubscribe on a throwaway account, asserting
  the row is **soft-deleted** (`is_active=false`) rather than removed.
* `surface.squads_lifecycle` — all six routes: create, list, read, add member, remove
  member (soft), read squad orders. Skips cleanly when `squad_orders` is off.
* `surface.exclusive_spin` — a credit granted to a throwaway account is consumed exactly
  once (the row's counter must reach 0) and a second spin is refused with 400. The prize is
  random; HP, free-delivery and physical-prize outcomes all land on the throwaway account,
  which is deleted afterwards, so a real account is never spun against.
* `surface.graduation_claim` — the ineligible branch (400), then, only if a level at or
  above `graduation_min_level` exists, the eligible branch on a throwaway profile: HP
  awarded, `graduation_claimed` set, an `hp_transactions` row with `reference_type=graduation`,
  and a repeat claim refused with 400.
* `surface.upload_signature` — a non-admin asking for `folder: "general"` must be given
  `profile_photos/<their own id>`; anonymous callers are refused; 503 (Cloudinary not
  configured) is treated as a legitimate configuration.

Steps can now declare `routes=(...)` alongside `route=`, so `--self-check` verifies every
path a multi-route step calls: 109 declared routes, all present in the app.

**Added in the reach pass** — the rest of the reachable surface (`--only surface`):

* `surface.read_sweep` — every GET the app serves that no step declared and no sweep covers
  (32 routes then, 31 now that the squad GET is declared by a step; enumerated from the live
  URL map so it shrinks as steps are added). For each
  one: an authenticated customer must get **no 5xx and no 401**. A 404 for a random UUID is
  recorded as the correct answer; a 403 is kept but warned about, because it usually means a
  feature flag is off. This is a liveness contract, not a behaviour test.
* `surface.cart_and_saved` — remove one cart item, then clear the cart (**only when it was
  empty beforehand**), and the saved-items loop: save, list, update, remove.
* `surface.order_locks_lifecycle` — create, list, read, reschedule and cancel an order lock,
  plus the guard that a lock for a past date is refused.
* `surface.notifications_and_challenges` — notification preferences, marking an unknown
  notification read (a clean 4xx, never a 500), and the three engagement posts, which answer
  cleanly whether they award or refuse.
* `surface.storefront_writes` — newsletter subscribe/duplicate/unsubscribe on a throwaway
  address, both promo validators against a nonsense code (a clean 4xx, never a false
  "valid"), and the delivery fee calculator returning a number.
* `surface.auth_self_service` — on a throwaway account: the `/api/auth/users/search` alias,
  an untrusted photo URL refused, password change (then signing in with the new password),
  logout-all-devices, a password-reset request, and account deletion refusing a wrong
  password. The deletion itself is left to the account teardown.
* `webhooks.flutterwave_wallet_topup` — the Flutterwave money-in path, mirroring the Paystack
  step: signed top-up credits the wallet, the replay is a no-op, wallet restored afterwards.
  Skips unless `FLUTTERWAVE_WEBHOOK_SECRET` is available; a forged signature is never sent.
* `surface.rewards_redeem` — redeem a catalogue reward for HP on a throwaway account and
  choose its delivery mode; skips cleanly when the catalogue cannot satisfy a fresh account.
* `surface.free_sides_deselect` — select a free side and remove it again.
* `surface.hp_transfer` — HP moving between two throwaway accounts, both balances checked,
  and an over-transfer refused.
* `surface.challenges_complete` — complete an offered milestone; a clean 400/409 is accepted
  when the account does not meet the condition.

**Added in the order follow-up pass** — what a customer does with a *delivered* order
(`make flow`, or `--only flow.order_followups`, which closes over the whole flow chain):

* `flow.order_followups` — the flow's own delivered order is reordered (the helper returns
  the items at today's price), shared once and shared again the same day (the second call
  must award **0 HP** and add no row — the prompt is per user per day), reviewed (delivered
  only, a second review refused), and given images: the untrusted host is refused, a trusted
  Cloudinary URL — built from the upload signature the app itself returns — is accepted and
  stored on the review, and an image posted before any review exists is refused. The guest
  `/claim` route answers 400 for an order that already belongs to a signed-in customer.
  Ledger rows, the review, the share row, the monthly-cap counter and the profile's HP
  fields are all restored in a `finally`, so it is safe against a real account.
* `flow.squad_members` — the account is added to its own order as a squad member (registered
  branch: no invite email, `split_hp=false` so the delivered HP is not redistributed), read
  back from the list route, and then the two post-delivery guards are pinned: removing a
  member from a delivered order is refused (400) and resending to a registered member is
  refused (400). The member rows are deleted afterwards.

### The 13 routes still not exercised, and why

**Need an inbox (2).** `POST /api/auth/reset-password/confirm` and `POST /api/auth/verify-email`
require the token/OTP that is only ever delivered by email. They can be covered honestly by
using Supabase's admin `generate_link` with the service key to obtain the token instead of
sending mail — not done here because it needs a decision about generating recovery links in
a live project.

**Start a real provider transaction (3).** `POST /api/wallet/fund/card`,
`POST /api/wallet/fund/bank` and `POST /api/hp/bundles/purchase` call Paystack to create a
transaction. The suite deliberately does not start provider-side objects; the webhook steps
already cover what happens when the provider answers. Run them once by hand with test keys
if you want them exercised.

**Need catalogue fixtures that may not exist (7).** `POST /api/events/<id>/register`,
`POST /api/events/<id>/checkin`, `POST /api/events/catering-requests`,
`POST /api/marketplace/<id>/purchase`, `POST /api/marketplace/purchases/<id>/report`,
`POST /api/marketplace/requests` and `POST /api/hp/flash-redeem/<id>` all need an active
event, listing or flash sale in the database. Each step would skip on a catalogue that has
none — worth adding if any of those features are live at launch.

**A framework route (1).** `GET /static/<filename>` is Flask's own asset handler, not an
API route: any name we probe answers 404 (there is nothing to serve), so asserting it would
add a number without adding a fact. The read sweep skips the `static` endpoint for the same
reason.

**What the order pass reaches only through a guard.** Two of the four squad-member routes
are pinned as refusals rather than happy paths — removing a member and resending an invite
both need a **non-delivered, squad-flagged order**, and the flow's order is delivered by
design. `POST /api/orders/<id>/claim` is likewise exercised only on the "already belongs to
a customer" branch; the happy path needs a guest order carrying a claim token.

Still not covered after all passes: invoking the full job set by default, the
virtual-account / bank-transfer deposit branch, the split-payment amount check named below,
the guest-order and squad-order happy paths above, and functional depth on the 241
permission-swept routes (a refusal proves the gate, not the handler) and the read-swept GETs
(a clean answer proves no crash, not correctness).

### Residual risks, stated plainly

1. **The role lookup on the order-status path fails open.** If the profile read errors,
   `caller_role` stays `None` and the rider/kitchen/admin scoping checks are skipped. It
   now logs at `error`, but it still permits the transition. Deliberately unchanged so a
   transient read failure cannot block a role from its own path — **this is a decision to
   confirm, not an oversight**.
2. **Cancel restore is Python-only.** The database has no path that returns HP or releases
   a reward, so a cancel performed outside the API (a manual SQL edit, a future job) would
   not restore them. Today the API is the only canceller, so this is consistent — it stops
   being true the moment something else cancels orders.
3. **`make contract` "passes" without proving anything when the network is down.** It
   prints unreachable per item; read its output rather than its exit code.
4. **The authorization sweeps prove refusal, not correctness.** A route that is correctly
   gated can still be functionally broken, and a route that 404s on an unmatched id cannot
   reveal a missing gate from the status code alone (hence the loader's separate failure on
   any `/api/admin/...` path with no gate at all). The sweep answers "can this role reach
   it", nothing more.
5. **The concurrency steps only run against a real server** (`BASE_URL`), and they assert
   atomicity of the paths they cover — not every race. Order locks and kitchen capacity
   have no race step yet.
6. **The scheduled-job sweep is opt-in by design.** `--with-cron` invokes jobs that message
   real users; without it, 16 of the 17 jobs are only checked for wiring, not for runtime
   health.
7. **The surface steps check one path each, on throwaway accounts.** Squads skip when the
   feature flag is off, spins are random (a HP prize is asserted only as "a prize"), and
   the graduation happy path needs an eligible academic level to exist. They cover the
   route's main branch, not every branch in it.
8. **Production switches:** `ALLOW_UNSIGNED_WEBHOOKS` and `PAYSTACK_SANDBOX_MOCK_NUBAN`
   are refused at boot outside DEBUG/TESTING (verified by attempting the boot). Do not
   weaken that guard to get a deploy out.
9. **The audit is code-level.** A database-side review (O1) can still find something none
   of this could see — policies that are missing, or broader than intended.
