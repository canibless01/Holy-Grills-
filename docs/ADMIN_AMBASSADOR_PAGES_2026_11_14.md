# Ambassador administration — 14 November 2026

Completed this batch: roster/search/tag retry controls, milestone create/edit/activation, promotional-message creation recovery and review/recommendation/financial-grant controls. This supplements the existing programme attribution, immutable grant, claim and financial-conservation evidence; it is not proof of a WhatsApp recipient reading a message.

## Changes

- Super-admin lists and mutations use the selected campus, with All Campuses ignoring the account's original student campus. Campus staff require their assigned campus. Assignment filtering happens before retrieval; foreign recipients do not leak through global messages.
- Search discards obsolete responses, exposes read failure/Retry and hides inactive accounts. Busy operations cannot be submitted twice or dismissed midway; failed clipboard access does not report success. Untag retries return the inactive row without a second audit entry; racing tag creation recovers the existing active tag.
- Milestones now expose edit and active/inactive controls, retain their IDs and existing earned claims, validate compatible financial limits and reject stale edits. Campus admins cannot create global policies. Community managers can inspect policy but cannot configure or issue rewards.
- `hg_write_ambassador_milestone` commits policy and request receipt together. Repeated request UUIDs replay the saved snapshot; changed requests conflict. Same-actor identical recent creates are serialized/deduplicated for older clients. The existing audit ledger is reused; no new tables or columns. Direct anon/authenticated execution is denied and persisted inactive actors are denied even on replay.
- Monthly reviews carry scoped readable profile names. Failed month/history reads clear old results and expose Retry; review/grant actions are locked during submission.

## Verification

- Backend full suite: **1,787 passed**; ambassador suite **89 passed**.
- Native Chromium: `scripts/test-ambassador-admin-browser.py`, 393px campus admin, 1280px super admin and 393px community manager. Stale query, inactive results, search failure/Retry, tag, reward limits, create response loss/replay, global checkbox, edit/disable and read-only manager controls pass.
- Existing `scripts/test-ambassador-rewards-browser.py`: meal-benefit read/retry, checkout attachment, promo creation response-loss/replay, manager recommendation and admin decision/grant replay all pass.
- Independent PostgreSQL sessions: six same-intent creates produce one policy, different-intent identical creates reuse it; competing edits admit one winner, stale editor denied; rolled-back write retry and committed-response replay pass. See `tests/ambassador_milestone_sessions.py`; disposable localhost database only.
- Live Supabase: combined DDL/fixture rollback before apply, then service-role fixture/permission/receipt rollback after apply pass. Migration **20261114140235_ambassador_milestone_write_intents** appears once in history. Fixtures leave no rows; existing customer programme policies/grants untouched.
- Security advisors unchanged: 2 backend-only RLS/no-policy findings, 1 pg_net extension placement, 6 anon and 15 authenticated intentional definer exposures, 1 leaked-password protection setting. No newly exposed helper.

- Native distribution exceptions also pass at 393px/1280px: failed recipient read/Retry, personalized link, Cloudinary graphic link, clipboard failure, intercepted synchronous WhatsApp share without fabricated Shared activity, failed status write/retry, Pending/Seen/Shared transitions, failed roster read/Retry and selected-recipient creation. No external message sent.
- TypeScript, edited-component ESLint and full production build (contracts/client/SSR/prerender) pass.

Remaining follow-up: CMS/presentation variants and historical database dependency review; genuine provider delivery and staff operational acceptance remain separate observations. Existing completed pages are not reopened from obsolete inventory rows.
