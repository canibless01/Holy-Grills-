# Email delivery and the Resend → OneSignal fallback

Everything here is about one promise: **an email the app decided to send is not lost
because a free plan ran out.** Resend's free tier is 100 messages/day; OneSignal has no
practical email cap for us.

## The single funnel

```
order / guest order / marketplace / event QR / newsletter / campaign / admin
                              │
                              ▼
                   send_email_raw()  ·  send_email()  ·  send_email_routed()
                              │
                              ▼
                   send_email_routed()   ← the only counted place
                     ├── email_usage.reserve_slot()   ← claims a slot *before* sending
                     ├── _attempt_and_settle()        ← keeps or gives the slot back
                     │      └── _email_attempt()      ← the only HTTP transport
                     │             ├── Resend  POST /emails
                     │             └── OneSignal POST /notifications (channel: email)
                     └── (on a definite miss) one attempt on the other provider
```

`tests/test_email_counting_coverage.py` enforces this with an AST scan: no module
outside `app/utils/email.py` may reference the Resend endpoint, and `_email_attempt`
may only be reached through `_attempt_and_settle` → `send_email_routed`. If someone ever
adds a second transport, that test fails instead of the counter silently under-reporting.

Supabase's own auth mail (invite / confirm / recover) is sent by Supabase, not by us —
it never touches Resend and is not part of these counters.

## The counter

Table `public.email_send_counters(provider, usage_date, sent_count)`, keyed by the
**Africa/Lagos** day, written only by two `service_role` RPCs:

| RPC | Purpose |
| --- | --- |
| `hg_record_email_send(provider, day)` | atomic `+1`, returns the new count |
| `hg_release_email_send(provider, day)` | atomic `-1` (floor 0), for a claim that was not used |

Limits are configuration, not policy:

* `EMAIL_DAILY_LIMIT_RESEND` — default **100**
* `EMAIL_DAILY_LIMIT_ONESIGNAL` — default **0 = unlimited** (so once traffic moves to
  OneSignal it stays there for the rest of the day, which is the intent)

`0` for a provider disables pre-emption for it. An unreadable counter (migration not
applied, RPC error, timeout) returns `None` and routing continues unchanged — a
bookkeeping outage must never stop mail.

## Which provider is tried first

**Resend, then OneSignal.** `get_email_provider()` resolves
`explicit setting → system_settings.email_provider_{scope}_default → Resend`, and
`send_email_routed(provider=None)` uses the same resolution.

The two allowances are not interchangeable:

| Provider | Allowance | Resets |
| --- | --- | --- |
| Resend | 100 / day | Yes, at the Lagos midnight |
| OneSignal | 10,000 / month | No rollover until the month rolls over |

So the daily allowance is spent first: a busy day costs nothing that tomorrow cannot
earn back, and OneSignal's monthly pool stays available as the overflow absorber. A
month's practical capacity is therefore Resend's ~100/day **plus** OneSignal's 10,000 —
roughly 13,000 — instead of 10,000 with a hard wall once the monthly pool is gone.

The router switches to OneSignal when Resend refuses for quota, when our daily counter
says Resend is at `EMAIL_DAILY_LIMIT_RESEND` (default 100), or when Resend accepts but
delivers to nobody.

### Watching the monthly pool

`GET /api/admin/email-health` reports, per provider: `sent_today`, `daily_limit`,
`sent_this_month`, `monthly_limit`, `monthly_remaining`, `monthly_exhausted`. The
monthly figure is summed from the daily counter rows, so it needs no extra table or RPC.
OneSignal's monthly ceiling is `EMAIL_MONTHLY_LIMIT_ONESIGNAL` (default 10,000) and is
informational: once it is reached the only capacity left is Resend's 100/day, which the
panel shows via `monthly_exhausted`.

## Addresses are normalised before they reach a provider

OneSignal keys an Email subscription by its token, so `a@b.com` and `a@b.com ` are
*different* addresses: the subscription attaches to one and the send targets the other,
which OneSignal reports as an invalid/unsubscribed identifier. `normalize_email()`
(strip, lowercase, trim surrounding quotes/punctuation, reject lists and inner spaces)
is applied to subscription creation, `include_email_tokens`, and every raw/guest path.
A malformed address is skipped with `invalid_email_address` instead of being sent.

## Stale "unsubscribed" subscriptions repair themselves

Creating a subscription for an address that already has one returns the existing record
unchanged — including one that is switched off. If the account's own preference says it
wants email, `ensure_email_subscription` PATCHes
`/apps/{app_id}/subscriptions/{id}` with `enabled: true`, and if create reports "already
exists" it looks the subscription up and does the same. A deliberate opt-out
(`enabled=False` requested) is never repaired.

## Per-send decision

0. **Marketing mail is never re-routed after an unsubscribe.** If OneSignal refuses a
   *marketing* send as unsubscribed, it is recorded `skipped` (`skipped_reason:
   unsubscribed`) and stops there — delivering it through Resend would override the
   customer's own opt-out. Transactional mail still falls back, so receipts and QR
   codes arrive.
1. **Claim before sending.** `reserve_slot(preferred)` increments the preferred
   provider's counter. If the claimed count is past its limit, that claim is released
   and a claim is taken on the other provider instead.
   Claiming first is what makes this correct under a burst: with read-then-send, 200
   simultaneous guest registrations all read "98 of 100" and all pick Resend. Here the
   database is the arbiter.
2. **Attempt.** If accepted → the claim stays. If the answer proves nothing was sent
   (provider not configured, quota refusal, "no recipients / not subscribed") → the
   claim is released and the other provider is tried once.
3. **Ambiguous outcomes keep their claim and get no second attempt** — timeouts, 5xx and
   unrecognised 4xx. The first provider may already be delivering; a second transport
   would send the message twice. A duplicate is worse than a lost email here, and the
   claim stays counted because it probably did send.
4. **Both at their limit** → the preferred provider is still attempted (a provider that
   counts differently from us may accept it); mail is never dropped just because our own
   bookkeeping says both are full.

### Worked example

200 guests register for an event after 5 orders have already gone out that day:

* claims 1–95 → Resend accepts → Resend is at 100/100
* claim 96 → Resend over limit → released → claimed on OneSignal → delivered
* claims 97–200 → OneSignal → delivered

Nothing is dropped, and no quota notification from Resend has to arrive for the switch to
happen. The reactive path is untouched underneath: a 429/`daily_quota_exceeded` still
switches provider mid-send even when the counter thinks there is headroom.

## Marketing vs transactional

* A send that carries `List-Unsubscribe` headers is **marketing**: the headers go to
  Resend; if the message ends up on OneSignal it is sent with `include_unsubscribed`
  omitted, so OneSignal's own unsubscribe list is honoured too.
* Everything else is **transactional** and is sent with `include_unsubscribed: true`,
  because an order confirmation or a password reset must arrive.
* Either way, our own `promotions` / `email_enabled` preferences are applied
  *before* dispatch (`notification_preferences.permitted_channels`), so the provider is
  never asked to filter on our behalf.

## OneSignal email subscriptions

OneSignal cannot deliver to an address it does not know, so every account is registered
as an **Email Subscription** against `external_id`:

| Trigger | Where |
| --- | --- |
| Sign-up (regardless of the promotions tick box) | `auth_service.register` |
| Login (backfills accounts created earlier) | `routes/auth.py` |
| Master email switch turned on/off | `PATCH /api/notifications/preferences` |
| Existing accounts, on demand | `POST /api/admin/email-subscriptions/backfill` |

Declining promotions does **not** unregister the address — that would also stop the
order and QR emails. It only stops marketing mail, which is filtered server-side.

## Where subscriptions come from (and nowhere else)

OneSignal Email subscriptions are created or repaired only by
`app/services/onesignal_email.py`, from four triggers:

| Trigger | Where |
| --- | --- |
| Sign-up (every account, regardless of the promotions box) | `auth_service.register` |
| Login — also the repair path for accounts that predate this | `routes/auth.py` |
| Master email switch on/off | `PATCH /api/notifications/preferences` |
| Existing accounts, on demand | `POST /api/admin/email-subscriptions/backfill` |

**Sending never creates a subscription.** An earlier revision registered the address
mid-send and retried; that was unnecessary machinery. A send that OneSignal refuses
stays refused and is recorded as such.

Guest addresses (event registrations, guest orders, catering) do not need a local
subscription: OneSignal auto-creates one from `include_email_tokens` on first send.

## Observability

* `GET /api/admin/email-health` — today's claimed counts, limits, remaining headroom,
  whether each provider is configured, and `onesignal_app_id` /
  `onesignal_api_key_present` / `onesignal_api_key_type` /
  `onesignal_app_id_looks_valid`. A wrong `ONESIGNAL_APP_ID` writes subscriptions into a
  different app and looks identical to "nothing reaches OneSignal", so it is reported
  explicitly. Shown in the admin campaign page.
* `onesignal:` log lines now carry the provider's answer — `create user … rejected
  (401): <body>`, `email subscription for … rejected (400): {"errors":[…]}`,
  `no email subscription for a***@example.com — provider said: …`, and one line per
  failed link in a backfill sweep. Addresses are masked.
* `notification_deliveries` — one row per notification × channel with the real outcome.
* `notification_blasts.metadata.dispatch` — per-channel sent/failed/skipped counts,
  written after dispatch settles, plus `email_delivery_failed` when no email got through.

## Subscribing accounts that already exist

Registration, login and the preference switch keep new sessions covered. For accounts
created before this existed (or that never log in again), there are two options:

| Option | How |
| --- | --- |
| One account, verified | `POST /api/admin/email-subscriptions/backfill {"user_id": "<profiles.id>"}` — synchronous, returns OneSignal's own answer (`subscription_id`, `http_status`, `errors`, or a `reason` such as `onesignal_not_configured`) |
| Everyone | `POST /api/admin/email-subscriptions/backfill {}` (or the button on the campaign page) — background sweep, 500 profiles per call, pass `offset` for the next page |

The sweep pages with `limit()`/`offset()` and reads preferences in a second query: this
repo's PostgREST builder (`TableQuery` in `app/db.py`) has no `range()` and no nested
select, and the first version used both — so every sweep died with
`'TableQuery' object has no attribute 'range'` before reading a single profile. There is
now a test for the query shape.

Either way the address is looked up from `profiles`, never from the request body, so an
admin can only link an account that exists.

## Proving a single send works

`POST /api/notifications/blasts/test` now returns `email: {status, message_id,
delivered_at, error}` read from `notification_deliveries` (it waits up to ~6 s for the
dispatch thread). `status: "sent"` means the provider accepted with a message id;
`"failed"` carries the provider's error; `"pending"` means no answer arrived in time.
The campaign page's **Test to Me** button surfaces that verdict.

## Deploy checklist

1. Apply `20261030140000_email_send_counters.sql` and `20261030170000_email_send_release.sql`.
2. Set `EMAIL_DAILY_LIMIT_RESEND` to the real plan limit (raise it on a paid plan).
3. Ensure `EMAIL_FROM` / `EMAIL_FROM_NAME` point at a **verified** OneSignal sender
   domain; unverified senders are why an "accepted" OneSignal email never arrived.
4. Run the subscriber backfill once from the admin campaign page.
