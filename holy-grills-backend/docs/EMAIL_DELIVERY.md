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

## Per-send decision

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

## Observability

* `GET /api/admin/email-health` — today's claimed counts, limits, remaining headroom and
  whether each provider is configured. Shown in the admin campaign page.
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
