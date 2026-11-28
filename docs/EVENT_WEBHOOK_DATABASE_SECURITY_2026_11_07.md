# Event/webhook database security — 7 November 2026

Applied `20261107145459_restrict_webhook_and_table_maintenance.sql` exactly once.

- Removed browser/public TRUNCATE, REFERENCES and TRIGGER privileges across current public tables (109 anon / 111 authenticated tables previously carried each privilege). TRUNCATE is not protected by row policies. No maintenance command was executed against application data.
- Removed browser INSERT/UPDATE/DELETE privileges on webhook_events. Its payload is trusted on administrative replay, so a scoped admin must not manufacture a provider delivery through the Data API. Replaced the ALL policy and redundant SELECT policy with one scoped authenticated SELECT policy. Backend service processing retains read/write permission.
- Removed the same maintenance privileges from postgres-owned future-table defaults. Supabase's separately owned supabase_admin defaults remain platform-controlled; future platform-created tables must have their grants checked. This migration does not claim to alter that role's defaults.

`tests/sql/webhook_and_event_security.sql` passed with entirely fresh BEGIN/ROLLBACK fixtures: actual role permissions, own/foreign/global webhook visibility, denied admin payload updates/deletes, denied student reads, permitted service update and published/draft/inactive ticket-tier boundaries. There are zero remaining browser maintenance grants on current public tables, one authoritative webhook SELECT policy, and one migration entry. No existing user, event, payment or provider request was changed.

The overlapping event-tier policies were inspected: the parent visibility policy is RESTRICTIVE, so it correctly combines with active-tier reads. No unnecessary policy replacement was made. Existing ticket/check-in financial writes remain backend-only.

Broader historical RPC review, webhook replay races/UI controls and event-management lifecycle coverage continue separately. Existing advisor findings are not blanket evidence of exploits; public RLS helpers and trigger-only functions need individual treatment.
