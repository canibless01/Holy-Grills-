# Forensic audit — business logic, code quality, security

Scope: the whole backend (`app/`, 41 blueprints, ~405 routes), re-verified against the
live test-2 database where a claim could not be settled from code alone.

Method: `pyflakes` over `app/` (68 warnings, triaged), a scripted pass that lists every
route with no auth decorator, targeted greps for secrets/leaks/swallowed exceptions,
and manual reading of the money paths. Everything below is quoted from the file at the
line shown. Items already fixed in this session are **not** repeated — see the last
section for that list, so nothing gets fixed twice.

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

Verified: `python -m pyflakes app/ | grep "undefined name"` → only this one existed.

---

## 🟠 HIGH

### H1. A failed event insert is retried with columns silently dropped, for *any* error
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

**Fix** — only retry the error it was written for, and keep the evidence:

```python
try:
    result = db.table("events").insert(safe).execute()
except SupabaseError as exc:
    details = exc.details if isinstance(exc.details, dict) else {}
    code = str(details.get("code") or "")
    if code not in ("PGRST204", "42703"):        # not a missing-column error
        raise
    PHASE2_COLS = {"hp_per_attendee", "funding_source", "max_attendees",
                   "hp_required", "total_value", "is_paid"}
    logger.warning("create_event: retrying without phase-2 columns after %s", exc)
    safe2 = {k: v for k, v in safe.items() if k not in PHASE2_COLS}
    result = db.table("events").insert(safe2).execute()
```

### H2. A paid customer can receive no ticket email, with no log line
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

**Fix:**

```python
    except Exception as exc:
        logger.error("event ticket email failed for ticket %s (%s): %s",
                     ticket_id, email, exc)
        ctx_warnings = locals().get("warnings")
        # and surface it in the response so the client can tell the user to fetch the PDF
```

The same pattern exists at `events.py:267` (milestone triggers),
`admin_gifts.py:212` (`multiplier_live` push), `graduation.py:112` (graduation badge) and
`exclusive_spin.py:244` (`exclusive_spin_won` push) — each should log at minimum.

### H3. `get_user_client()` can silently hand a route the service-role client
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

**Fix** — fail closed, never fail privileged:

```python
    except Exception as exc:
        logger.error("get_user_client: could not scope to the caller (%s) — "
                     "falling back to anon", exc)
        return UserSupabaseClient(get_db(), None, paginate=paginate)   # anon, RLS applies
```

---

## 🟡 MEDIUM

### M1. 90 `except Exception:` handlers, 10+ of which swallow silently
Verified sample, each genuinely hiding a failure: `events.py:885`, `events.py:267`,
`events.py:723`, `events.py:1693`, `db.py:545`, `admin_gifts.py:212`, `admin_gifts.py:214`,
`exclusive_spin.py:244`, `graduation.py:112`.

`db.py:545` and the two `events.py` ones are the ones that matter (H2 above). The rest
need `logger.warning(...)` at most — the fix is one line each, and the rule is: **a
swallowed exception may only be acceptable if the code that follows it records why.**

### M2. N+1 queries: 121 database round-trips inside loops
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

### M6. Two public endpoints worth a deliberate decision (not confirmed leaks)
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

## Still needs the project owner

1. **`SUPABASE_DB_URL`** — RLS/grants/per-role visibility is the one layer that has never
   been read. Everything in this report is code-level.
2. **Does `hg_create_order_atomic` debit the wallet half of a split order at creation?**
   decides the cancel-refund flag (`refund_wallet_when_unpaid`, `orders.py`);
3. **Does it restore `hp_redeemed` when an order is cancelled?** Today the HP is not
   returned (same for a claimed reward) — needs a decision, then a fix.
4. The truncated tail of the ecosystem map ("Admin grant routes missing …") and
   `docs/audit-report.md`.
