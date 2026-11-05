# Feature Flags — global controls and override visibility, 29 October 2026

This batch verifies the native global flag controls and repairs their handling of existing campus overrides. It does not certify every feature consumer or a running background worker.

## Fixed

The database has a unique index on feature name plus campus, not feature name alone. There are three legacy campus overrides (all on audit-labelled campuses) alongside their global rows. The admin API formerly looked up and updated flags by name alone while its documentation and UI assumed a single global row. Depending on the query, this could make a lookup ambiguous or an update target more than the intended row.

Global create/retry lookup, detail and update now explicitly require `campus_id IS NULL`. The list returns one global switch and its visible campus overrides as read-only metadata. The UI shows campus name and effective override value, rather than duplicate apparently global switches. Changing a global row preserves existing overrides; those overrides still take precedence in the existing public endpoint and backend helper. No override was removed or disabled, and no release flag was changed by this audit.

The UI also guards repeated submissions synchronously, prevents concurrent create/toggle actions, and explains that a newly stored flag name has no behavior until a consumer is connected. Campus admins remain read-only; super-admins edit global rows. Input rules, duplicate-create conflict/matching replay, failed-write retention, read Retry and public client-gate refresh remain covered.

## Executed proof

- `scripts/test-admin-feature-flags-browser.py`: real native page and controlled HTTP. Toggle off/on, failed update retains saved state, client `isFeatureEnabled` cache refresh in global context, create name/description, default-off draft, visible read-only campus override, campus-admin denial and failed list retry. The controlled public endpoint represents global scope; campus-specific effective behavior is not inferred from it.
- `tests/test_feature_flag_mutations.py`: **7 tests**, including explicit null-scope lookup/update and grouping of global/override list entries; prior validation and safe create replay cases retained.
- Real Supabase `tests/sql/admin_feature_flag_global_scope.sql`: isolated rollback fixtures with the same name at global and campus scope; actual super-admin global update affects one row and preserves the override; campus admin and student cannot mutate switches. Existing unique index and RLS inspected; no schema or grant changes.
- Selected existing backend consumer tests passed: flash pricing/action gates, timed multiplier recipients/broadcast, effective campus pause, and event release gates. These establish their recorded assertions, not every path through every flag.
- Complete backend suite: **771 passed**. Frontend typecheck, lint, message-registry and full production build pass.

## Still open

The complete enabled-consumer matrix (including tasks, jobs and UI surfaces) remains open. Unknown custom names do not implement new features. Real push/device proof and deployment of worker schedules remain separate. Durable email counters/retries and the remaining admin pages are not closed by this batch.
