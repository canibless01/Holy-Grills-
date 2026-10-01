# Forensic audit — business logic, code quality, security

Scope: the whole backend (`app/`, 41 blueprints, ~405 routes), re-verified against the
live test-2 database where a claim could not be settled from code alone.

Method: `pyflakes` over `app/` (68 warnings, triaged), a scripted pass that lists every
route with no auth decorator, targeted greps for secrets/leaks/swallowed exceptions,
and manual reading of the money paths. Everything below is quoted from the file at the
line shown. Items already fixed in this session are **not** repeated — see the last
section for that list, so nothing gets fixed twice.

**Status of this document: current.** Every item carries its state — 🔴 CRITICAL, all
four 🟠 HIGH, 🟡 M1/M2/M3/M4/M5 and the whole 🔵 LOW table are closed as of `e874c98`;
`pyflakes` now reports **zero** warnings for `app/` and `scripts/live_test.py`. The ledger
at the bottom is the single place that answers "what is left".

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
| O5 | Three cosmetic `operating_hour_overrides` rows | Storefront-only; safe to delete in the admin UI |
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

### Session note — silent-except pass

Triage rule applied: log when the failure changes what the caller believes happened.
First draft of the `reorder` log line referenced `item_id_ref`, which does not exist —
a `NameError` inside an `except` block, i.e. exactly the class of bug this pass is meant
to remove. Caught because a `pyflakes` run had silently failed (`No module named
pyflakes` piped into a `grep`, so the empty match read as "clean"). Reinstalled, then
re-ran with a planted-error control to prove the check actually fires. Both notes are
here because the earlier rounds' two `NameError`s were recorded the same way.
