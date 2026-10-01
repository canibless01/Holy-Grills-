# Forensic audit — business logic, code quality, security

Scope: the whole backend (`app/`, 41 blueprints, ~405 routes), re-verified against the
live test-2 database where a claim could not be settled from code alone.

Method: `pyflakes` over `app/` (68 warnings, triaged), a scripted pass that lists every
route with no auth decorator, targeted greps for secrets/leaks/swallowed exceptions,
and manual reading of the money paths. Everything below is quoted from the file at the
line shown. Items already fixed in this session are **not** repeated — see the last
section for that list, so nothing gets fixed twice.

**Status of this document: current.** Every item carries its state — 🔴 CRITICAL and
🟠 HIGH are all closed as of `fd00000`; the MEDIUM/LOW items that remain open are
marked *open* with what they need. The ledger at the bottom is the single place that
answers "what is left".

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

---

## 🟡 MEDIUM

### M1. 90 `except Exception:` handlers — the user-visible ones are FIXED, the rest are *open*
Verified sample, each genuinely hiding a failure: `events.py:885`, `events.py:267`,
`events.py:723`, `events.py:1693`, `db.py:545`, `admin_gifts.py:212`, `admin_gifts.py:214`,
`exclusive_spin.py:244`, `graduation.py:112`.

`db.py:545` and the two `events.py` ones were the ones that mattered — all five
user-visible sites are fixed (H2/H3 above). The rule for the remainder: **a swallowed
exception is only acceptable if the code that follows it records why.**

**Still open — 88 sites, counted not estimated** (`except ...:` immediately followed by
`pass`): `app/routes` 27 · `app/services` 35 · `app/tasks` 23 · `app/utils` 3.

The routes sites are the ones a user can feel, so they are listed exactly:

    admin_gifts.py:214  events.py:634  events.py:724  events.py:1711  graduation.py:124
    hp.py:493  hp.py:503  kitchen.py:597  leaderboard.py:220  leaderboard.py:266
    menu.py:41  orders.py:756  orders.py:913  orders.py:1221  orders.py:1237
    orders.py:1341  orders.py:1510  orders.py:1592  orders.py:1603  orders.py:1617
    referrals.py:244  rewards.py:304  rewards.py:528  rewards.py:638
    webhooks.py:112  webhooks.py:206  webhooks.py:611

Triage rule, so this does not turn into an 88-site refactor: **log it when the swallowed
failure changes what the caller believes happened** — a wallet credit, a ticket, a
refund, a delivery. Purely cosmetic ones (an avatar URL, a leaderboard badge) may stay
silent.

I checked the three `webhooks.py` sites rather than assuming, and the interesting one is
**not** what I first wrote:

* `webhooks.py:112` and `:206` swallow only the *bookkeeping* write that records a
  failure. The outer handler still calls `_notify_admin_webhook_failure(...)` and returns
  **500**, so the provider is not told "OK" — these are the least urgent of the 88.
* `webhooks.py:611` is inside `_notify_admin_webhook_failure` itself: it is the alert
  path. If that notification fails, a failed webhook produces **no alert at all** — the
  one place where a silent swallow hides the failure of the failure-reporting. Worth a
  `logger.error` even though nothing else can be done at that point.

### M2. N+1 queries: 121 database round-trips inside loops — *open*
Worst verified case — `app/routes/admin.py:1100-1103`:

```python
        for b in batches:
            counted = db.table("orders").select("id", count="exact").eq("batch_id", b["id"]).limit(1).execute()
            b["order_count"] = (counted or {}).get("count") or 0
```

One extra HTTP round-trip **per batch** on every page of the batch list (limit up to
hundreds). At 100 batches that is 101 REST calls to render one screen.

**Fix** — one query for the page, group in Python:

```python
        ids = [b["id"] for b in batches]
        rows = db.table("orders").select("batch_id").in_("batch_id", ids).execute() or []
        counts = {}
        for r in rows:
            counts[r["batch_id"]] = counts.get(r["batch_id"], 0) + 1
        for b in batches:
            b["order_count"] = counts.get(b["id"], 0)
```

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

### M6. Two public endpoints worth a deliberate decision (not confirmed leaks) — *open, needs you*
`app/routes/menu.py:1525` (`GET /api/menu/kitchen-capacity`) and
`app/routes/hp.py:255` (`GET /api/hp/bundles`) have **no auth decorator**. Both may be
intentional (customer-facing "how busy are we", public bundle pricing). I did not read
their response bodies, so I am not calling them leaks — but they are the first two to
check with:

```bash
curl -s 'https://<host>/api/menu/kitchen-capacity?campus_id=<id>' | head -c 400
curl -s 'https://<host>/api/hp/bundles' | head -c 400
```

If either returns internal counters (order volumes, costs, margins) rather than a
customer-facing summary, add `@optional_auth` and trim the payload.

---

## 🔵 LOW

| # | Location | Finding | Fix |
|---|----------|---------|-----|
| L1 | `app/db.py:432` | `f-string is missing placeholders` | drop the `f` prefix |
| L2 | `app/routes/events.py:511,730` | `import uuid` re-imported inside functions, shadowing the module import | delete the local imports |
| L3 | `app/routes/events.py:1142` | `_exc` bound and never read (see H1) | use it in the log |
| L4 | `app/routes/graduation.py:103` | `except Exception as e:` — `e` unused | log it or use `except Exception:` |
| L5 | `app/routes/hp.py:515` | `from app.db import get_db, get_user_client` — `get_db` unused | import only what is used |
| L6 | `app/services/hp_service.py:350,376` | `update_monthly_tracker` imported twice; the first is unused | keep line 376 |
| L7 | `app/services/order_service.py:782` | `squad_delivery_discount` assigned, never read | delete the assignment (the discount **is** applied on the next line — this is dead code, not a lost discount) |
| L8 | `app/services/streak_service.py:231` | `action` assigned, never used | remove |
| L9 | `app/tasks/scheduled.py:261` | `is_feature_enabled` re-imported, shadowing line 184 | delete the inner import |
| L10 | 56 files | unused imports (`pyflakes`: 56) | `python -m pyflakes app/ \| grep "imported but unused"` |

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
| O2 | Does `hg_create_order_atomic` **debit the wallet half of a split order at creation**? | Decides `refund_wallet_when_unpaid` in `orders.py` — if yes, that half must be refunded on a pending cancel; if no, the current `False` is correct |
| O3 | Does it **restore `hp_redeemed` on cancel**? | Today neither the HP nor a claimed reward comes back when a customer cancels. Needs a product decision, then a fix |
| O4 | `docs/audit-report.md` + the truncated tail of the ecosystem map ("Admin grant routes missing …") | Not in this checkout; can't be actioned blind |
| O5 | Three cosmetic `operating_hour_overrides` rows | Storefront-only; safe to delete in the admin UI |
| O6 | `migrations/schema.sql`, `scripts/seed.py`, `scripts/seed.sql` | Referenced by docs, absent from the repo — send them or drop the references |

### Open — mine, no decision needed

| # | Item | Where |
|---|------|-------|
| O7 | Remaining `except Exception: pass` — 88 sites, 27 of them in `routes/` | M1 list, with the triage rule |
| O8 | N+1 in the delivery-batch list | M2 |
| O9 | The two unauth public endpoints, once you confirm the intent | M6 |
| O10 | 56 unused imports + the LOW table | L1–L10 |

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
